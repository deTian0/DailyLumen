"""ClickUp 域写操作：建任务 / 改状态（FR-J1）、批量改状态（W12）、完成快照 clickup-pull（W11）、
习惯代勾 clickup-habit（B15）。

建任务 / 改状态复用 ``pipeline.clickup_task``（dry-run + 写后回读）；快照复用
``pipeline.clickup_pull.collect``（与 CLI 同一归日口径，R1），写库前备份、写后回读。
B15 代勾只写 ClickUp（不写 ``habit_logs`` / ``training_*``）；入库仍走 ``habits --sync``。
"""
from __future__ import annotations

import datetime
import os
import urllib.error
from typing import Any

from ..queries import QueryError
from .base import (
    ID_RE,
    TokenStore,
    backup_db,
    clean_text,
    plan_out,
    quote_arg,
    register,
    require_db,
    today,
)

MAX_BATCH = 20


def plan_task_create(tokens: TokenStore, name: str, list_id: str | None = None, *,
                     env=None) -> dict[str, Any]:
    from ...config import CLICKUP_LIST_META, LIST_DAILY
    from ...pipeline.clickup_task import run_create
    from ..clickup_queries import _creds

    name = clean_text(name, field="任务名", limit=200)
    lid = (list_id or LIST_DAILY or "").strip()
    if lid not in CLICKUP_LIST_META:  # 白名单：只允许 config 里登记过的 list
        raise QueryError(422, "invalid_list", "清单不在本机登记的 ClickUp list 中")
    _creds(env)  # 集成关闭 / 凭据缺失在预览阶段就拦下
    _rc, msg = run_create(name, list_id=lid, status=None, apply=False, key="")
    list_name = CLICKUP_LIST_META[lid]["name"]
    preview = {"name": name, "list": list_name, "message": msg}
    return plan_out(tokens, "task_create", {"date": today(), "name": name, "list_id": lid},
                    preview=preview,
                    cli=f"python -m review_tool clickup-task --create {quote_arg(name)} --list {lid} --apply")


def plan_task_status(tokens: TokenStore, task_id: str, status: str, *, name: str | None = None,
                     env=None) -> dict[str, Any]:
    from ...pipeline.clickup_task import run_status
    from ..clickup_queries import _creds

    tid = (task_id or "").strip()
    if not ID_RE.match(tid):
        raise QueryError(422, "invalid_task", "task id 不合法")
    status = clean_text(status, field="状态", limit=40)
    _creds(env)
    _rc, msg = run_status(tid, status, apply=False, key="")
    preview = {"task_id": tid, "name": (name or "")[:200], "status": status, "message": msg}
    return plan_out(tokens, "task_status", {"date": today(), "task_id": tid, "status": status},
                    preview=preview,
                    cli=f"python -m review_tool clickup-task --status {tid} {quote_arg(status)} --apply")


@register("task_create", "task_status", needs=("env", "cu_client"))
def _apply_task(p: dict[str, Any], *, env=None, cu_client=None) -> dict[str, Any]:
    from ...pipeline.clickup_task import run_create, run_status
    from ..clickup_queries import _creds

    key, _team = _creds(env)
    try:
        if p["action"] == "task_create":
            rc, msg = run_create(p["name"], list_id=p["list_id"], status=None, apply=True,
                                 key=key, client=cu_client)
        else:
            rc, msg = run_status(p["task_id"], p["status"], apply=True, key=key, client=cu_client)
    except (urllib.error.URLError, TimeoutError) as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时，可重新预览后重试") from e
    if rc != 0:
        # msg 来自 clickup_task 的固定中文模板（HTTP 码 / 回读不符），不含凭据
        raise QueryError(502, "writeback_failed", msg)
    return {"written": True, "message": msg, "readback": True}


def plan_task_batch(tokens: TokenStore, items: list[dict[str, Any]], status: str = "complete", *,
                    env=None) -> dict[str, Any]:
    """一次预览 + 一次性 token 对应一批（≤20 条、去重）；回显逐条等价 CLI。"""
    from ..clickup_queries import _creds

    status = clean_text(status, field="状态", limit=40)
    if not items or len(items) > MAX_BATCH:
        raise QueryError(422, "invalid_param", f"一次批量 1..{MAX_BATCH} 条")
    seen: set[str] = set()
    picked: list[dict[str, str]] = []
    for it in items:
        tid = str((it or {}).get("task_id") or "").strip()
        if not ID_RE.match(tid):
            raise QueryError(422, "invalid_task", "task id 不合法")
        if tid in seen:
            continue
        seen.add(tid)
        picked.append({"task_id": tid, "name": str(it.get("name") or "")[:200]})
    _creds(env)
    clis = [f"python -m review_tool clickup-task --status {x['task_id']} {quote_arg(status)} --apply"
            for x in picked]
    preview = {"status": status, "count": len(picked), "items": picked, "clis": clis}
    return plan_out(tokens, "task_batch", {"date": today(), "items": picked, "status": status},
                    preview=preview, cli="\n".join(clis))


@register("task_batch", needs=("env", "cu_client"))
def _apply_task_batch(p: dict[str, Any], *, env=None, cu_client=None) -> dict[str, Any]:
    """逐条执行；单条失败不阻断其余条，结果里逐条回报（以回读为准）。"""
    from ...pipeline.clickup_task import run_status
    from ..clickup_queries import _creds

    key, _team = _creds(env)
    ok: list[str] = []
    failed: list[dict[str, str]] = []
    for it in p["items"]:
        try:
            rc, msg = run_status(it["task_id"], p["status"], apply=True, key=key, client=cu_client)
        except (urllib.error.URLError, TimeoutError):
            rc, msg = 1, "ClickUp 网络不可达或超时"
        if rc == 0:
            ok.append(it["task_id"])
        else:
            failed.append({"task_id": it["task_id"], "name": it["name"], "error": msg})
    return {"written": len(ok), "ok": ok, "failed": failed, "readback": True}


# ---------------------------------------------------------------------------
# 完成快照（clickup-pull）
# ---------------------------------------------------------------------------

def _week_of(day: str) -> list[str]:
    d = datetime.date.fromisoformat(day)
    mon = d - datetime.timedelta(days=d.weekday())
    return [(mon + datetime.timedelta(days=i)).isoformat() for i in range(7)]


def _clickup_counts(db_path: str | None, dates: list[str]) -> dict[str, int]:
    """库内现有 clickup_done 每日条数（只读；库缺失视为全 0）。"""
    from ...storage.db import load_clickup_done
    from ..queries import readonly

    if not dates:
        return {}
    out: dict[str, int] = {}
    try:
        with readonly(db_path) as conn:
            for r in load_clickup_done(conn, dates=dates):  # storage 层单一出入口
                out[r["date"]] = out.get(r["date"], 0) + 1
    except QueryError:
        return {}
    return out


def plan_clickup_pull(tokens: TokenStore, *, days: int = 14, env=None, fetch=None,
                      db_path: str | None = None) -> dict[str, Any]:
    from ...pipeline.clickup_pull import DEFAULT_LISTS, _list_ids, collect
    from ..clickup_queries import _creds

    if not 1 <= int(days) <= 366:
        raise QueryError(422, "invalid_param", "days 须在 1..366")
    key, _team = _creds(env)
    try:
        stats, by_date = collect(list_ids=_list_ids(None) or DEFAULT_LISTS, days=int(days),
                                 fetch=fetch, key=key)
    except urllib.error.HTTPError as e:
        raise QueryError(502, "upstream_error", f"ClickUp 返回 HTTP {getattr(e, 'code', '?')}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时") from e
    before = _clickup_counts(db_path, sorted(set(by_date) | set(_week_of(today()))))
    per_day = [{"date": d, "count": len(by_date[d]), "before": before.get(d, 0)}
               for d in sorted(by_date, reverse=True)]
    # W12：本周节奏「替换后」投影 —— 预览中出现的日期取新条数，其余日期保持库内现值
    week = [{"date": d, "before": before.get(d, 0),
             "after": len(by_date[d]) if d in by_date else before.get(d, 0),
             "replaced": d in by_date} for d in _week_of(today())]
    preview = {"days": int(days), "fetched": stats["fetched"], "closed": stats["closed"],
               "dates": stats["dates"], "range": stats["range"], "per_day": per_day,
               "replace_dates": sorted(by_date), "week": week,
               "target_table": "clickup_done", "strategy": "按整天替换（仅预览中出现的日期）"}
    return plan_out(tokens, "clickup_pull", {"date": today(), "by_date": by_date},
                    preview=preview, cli=f"python -m review_tool clickup-pull --days {int(days)}")


# ---------------------------------------------------------------------------
# B15：代勾 ClickUp 习惯（窄通道；默认仅 lianlian）
# ---------------------------------------------------------------------------

def plan_clickup_habit(tokens: TokenStore, habit: str = "lianlian", day: str | None = None, *,
                       env=None, fetch=None, ks_client=None, check_keepstrong: bool = True
                       ) -> dict[str, Any]:
    """预览代勾：只读定位任务 + 练练旁证；不写 ClickUp / 不写库。"""
    from ...config import HABITS_LIST_ID
    from ...pipeline import clickup_habit as ch
    from ..clickup_queries import _creds
    from ..queries import _check_date

    habit = (habit or "").strip() or "lianlian"
    day = _check_date(day) if day else today()
    if habit not in ch.ALLOWED_HABIT_KEYS:
        raise QueryError(422, "invalid_habit",
                         f"B15 仅允许习惯 {sorted(ch.ALLOWED_HABIT_KEYS)}")
    key, _team = _creds(env)
    try:
        planned = ch.plan_habit(
            day, habit, list_id=HABITS_LIST_ID, key=key, fetch=fetch,
            ks_client=ks_client, env=env, check_keepstrong=check_keepstrong,
        )
    except ValueError as e:
        raise QueryError(404, "habit_task_missing", str(e)) from e
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        if str(code) == "429":
            raise QueryError(429, "rate_limited", "ClickUp 限流，请稍后再试") from e
        if str(code) in ("401", "403"):
            raise QueryError(502, "upstream_auth", "ClickUp 凭据失效或权限不足") from e
        raise QueryError(502, "upstream_error", f"ClickUp 返回 HTTP {code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时") from e

    preview = {
        "date": day,
        "habit_key": planned["habit_key"],
        "label": planned["label"],
        "task_id": planned["task_id"],
        "name": planned["name"],
        "action": planned["action"],
        "closed": planned["closed"],
        "keepstrong_hint": planned["keepstrong_hint"],
        "disclaimer": planned["disclaimer"],
        "writes": ["ClickUp 任务 complete"],
        "does_not_write": ["habit_logs", "training_*", "training_day", "四维分"],
        "note": "确认后只勾 ClickUp；habit_logs 请另跑 habits --sync（避免双写权威）",
    }
    cli = (
        f"python -m review_tool clickup-habit --habit {habit} --date {day} --apply"
    )
    return plan_out(
        tokens, "clickup_habit",
        {"date": day, "habit_key": habit, "task_id": planned["task_id"],
         "habit_action": planned["action"], "label": planned["label"]},
        preview=preview, cli=cli,
    )


@register("clickup_habit", needs=("env", "cu_client"))
def _apply_clickup_habit(p: dict[str, Any], *, env=None, cu_client=None) -> dict[str, Any]:
    """确认代勾：只 PUT ClickUp；不写库（db_changed=False）。"""
    from ...pipeline.clickup_sync import mark_complete
    from ..clickup_queries import _creds

    if p.get("habit_action") == "skip_closed":
        return {
            "written": False, "skipped": True, "readback": True,
            "db_changed": False,
            "message": f"「{p.get('label') or p.get('habit_key')}」当日已完成 —— 幂等跳过",
        }
    key, _team = _creds(env)
    tid = str(p.get("task_id") or "").strip()
    if not ID_RE.match(tid):
        raise QueryError(422, "invalid_task", "task id 不合法")
    try:
        mark_complete(tid, key, client=cu_client)
    except RuntimeError as e:
        raise QueryError(502, "writeback_failed", str(e)) from e
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        if str(code) == "429":
            raise QueryError(429, "rate_limited", "ClickUp 限流，请稍后再试") from e
        if str(code) in ("401", "403"):
            raise QueryError(502, "upstream_auth", "ClickUp 凭据失效或权限不足") from e
        raise QueryError(502, "writeback_failed", f"回写失败: HTTP {code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时") from e
    return {
        "written": True, "skipped": False, "readback": True, "db_changed": False,
        "task_id": tid,
        "message": (
            f"已勾 ClickUp 习惯「{p.get('label') or p.get('habit_key')}」"
            f"（≠ 训练明细入库；habit_logs 请另 sync）"
        ),
    }


@register("clickup_pull", needs=("db_path", "backup_dir"))
def _apply_clickup_pull(p: dict[str, Any], *, db_path: str | None, backup_dir: str | None
                        ) -> dict[str, Any]:
    from ...storage.db import get_conn, load_clickup_done, replace_clickup_days

    path = require_db(db_path)
    by_date = p["by_date"]
    if not by_date:
        return {"written": 0, "backup": None, "dates": 0}
    backup = backup_db(path, backup_dir)
    conn = get_conn(path)
    try:
        applied = replace_clickup_days(conn, by_date)
        conn.commit()
        got = {d: len(load_clickup_done(conn, date=d)) for d in by_date}
    finally:
        conn.close()
    want = {d: len({str(r.get("task_id") or "").strip() for r in rows} - {""})
            for d, rows in by_date.items()}
    bad = [d for d in by_date if got[d] != want[d]]
    if bad:
        raise QueryError(500, "readback_failed", f"回读条数不符（{len(bad)} 天），请用备份核对")
    return {"written": sum(v["inserted"] for v in applied.values()), "dates": len(applied),
            "backup": os.path.basename(backup)}
