"""Web 看板 P2 写操作第一批（W9 / FR-D3 · FR-H3 · FR-H4 · PRE-07 · PRE-08）。

两段式：``plan_*`` 只算预览（不写任何东西），把「将要写的确切内容」存进
服务端一次性确认 token；``confirm(token)`` 才执行，且执行的正是预览过的内容
（不二次拉 ClickUp / 不二次调 DeepSeek）。约束：

- token 单次有效、5 分钟过期、与动作绑定；用过即作废（防重放 / 双击重复写）。
- 写 md 一律复用下层既有写函数（``llm_review.write_ai_section`` /
  ``llm_finalize.run_llm_finalize``），二者自带写后回读校验（规则 3）；本模块不 ``open(..., "w")``。
- md 在预览与确认之间被改动 → 409 ``stale_plan``，要求重新预览（不覆盖他处的手改）。
- 动 ``reviews.db`` 前先整库备份到 ``local/backups/web/``；写后回读核对。
- habits sync 只写 ``habit_logs``，**不碰** ``personal_tracks``（R3）。
- 只写 md 不写库的动作（AI 草稿 / 定稿）响应里给出下一步 ``ingest`` CLI（规则 9：先 md 再 ingest）。
- 不依赖 fastapi / pydantic。写操作全局串行（NFR-9 SQLite 单写者）。
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import secrets
import shutil
import threading
import time
import urllib.error
from typing import Any

from .queries import QueryError, _check_date

TOKEN_TTL_S = 300
_WRITE_LOCK = threading.Lock()


class TokenStore:
    """一次性确认 token（内存；进程重启即全部失效）。"""

    def __init__(self, ttl_s: float = TOKEN_TTL_S, clock=time.monotonic):
        self._ttl = ttl_s
        self._clock = clock
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def issue(self, action: str, payload: dict[str, Any]) -> str:
        tok = secrets.token_urlsafe(24)
        with self._lock:
            now = self._clock()
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            self._items[tok] = (now + self._ttl, {"action": action, **payload})
        return tok

    def take(self, token: str) -> dict[str, Any]:
        with self._lock:
            item = self._items.pop(token or "", None)
        if item is None:
            raise QueryError(409, "token_invalid", "确认已失效或已使用，请重新预览后再确认")
        exp, payload = item
        if exp <= self._clock():
            raise QueryError(409, "token_expired", "确认已过期（5 分钟），请重新预览")
        return payload


def _sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _plan_out(tokens: TokenStore, action: str, payload: dict[str, Any], *,
              preview: dict[str, Any], cli: str) -> dict[str, Any]:
    tok = tokens.issue(action, {**payload, "cli": cli})
    return {"action": action, "token": tok, "expires_in": TOKEN_TTL_S,
            "cli": cli, "preview": preview}


# ---------------------------------------------------------------------------
# habits sync（FR-D3）：ClickUp「习惯与打卡」→ habit_logs
# ---------------------------------------------------------------------------

def plan_habits_sync(tokens: TokenStore, day: str | None = None, *, fetch=None, env=None
                     ) -> dict[str, Any]:
    from ..pipeline import habit_sync as hs
    from .clickup_queries import _creds

    day = _check_date(day) if day else datetime.date.today().isoformat()
    key, _team = _creds(env)
    try:
        res = hs.sync_habits(None, day, None, key=key, fetch=fetch, dry_run=True)
    except urllib.error.HTTPError as e:
        raise QueryError(502, "upstream_error", f"ClickUp 返回 HTTP {getattr(e, 'code', '?')}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时") from e
    rows = [dict(r) for r in res["rows"]]
    preview = {"date": day, "fetched": res["fetched"], "rows": rows,
               "target_table": "habit_logs", "untouched": ["personal_tracks"]}
    return _plan_out(tokens, "habits_sync", {"date": day, "rows": rows}, preview=preview,
                     cli=f"python -m review_tool habits --sync {day}")


def _backup_db(db_path: str, backup_dir: str | None) -> str:
    from ..config import LOCAL_DIR

    d = backup_dir or os.path.join(LOCAL_DIR, "backups", "web")
    os.makedirs(d, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dst = os.path.join(d, f"{stamp}-{os.path.basename(db_path)}")
    shutil.copy2(db_path, dst)
    if _sha_file(dst) != _sha_file(db_path):
        raise QueryError(500, "backup_failed", "数据库备份校验失败，已中止写入")
    return dst


def _apply_habits(p: dict[str, Any], *, db_path: str | None, backup_dir: str | None
                  ) -> dict[str, Any]:
    from ..config import DB_PATH
    from ..storage.db import get_conn, load_habit_logs, upsert_habit_log

    path = os.path.abspath(db_path or DB_PATH)
    if not os.path.isfile(path):
        raise QueryError(503, "db_missing", "数据库尚未建立，请先在 CLI 执行 ingest")
    backup = _backup_db(path, backup_dir)
    conn = get_conn(path)
    try:
        for row in p["rows"]:
            upsert_habit_log(conn, row, overwrite=False)
        conn.commit()
        got = {r["habit_key"]: r for r in load_habit_logs(conn, date=p["date"])}
    finally:
        conn.close()
    missing = [r["habit_key"] for r in p["rows"] if r["habit_key"] not in got]
    if missing:
        raise QueryError(500, "readback_failed", f"回读缺少 {len(missing)} 条习惯记录，请用备份核对")
    return {"written": len(p["rows"]), "backup": os.path.basename(backup),
            "rows": [{"habit_key": k, "item": got[k]["item"], "done": got[k]["done"]}
                     for k in sorted(got)]}


# ---------------------------------------------------------------------------
# AI 草稿写入（FR-H3）与定稿（FR-H4）：只写 md，不写库
# ---------------------------------------------------------------------------

def _md_path(day: str) -> str:
    from ..reports import llm_review as lr

    path = lr.review_md_path(day)
    if not os.path.isfile(path):
        raise QueryError(404, "md_missing", f"找不到 {day} 的复盘 md，请先建当日复盘文件")
    return path


def plan_ai_draft(tokens: TokenStore, conn, day: str | None = None, *, client=None,
                  mode: str | None = None) -> dict[str, Any]:
    from .ai_queries import review_preview

    res = review_preview(conn, day, client=client, mode=mode)  # 含 mode 门禁
    path = _md_path(res["date"])
    preview = {"date": res["date"], "section": res["section"], "diff_text": res["diff_text"],
               "pending_mark": True}
    return _plan_out(tokens, "ai_draft", {"date": res["date"], "md": path,
                                          "md_sha": _sha_file(path), "section": res["section"]},
                     preview=preview, cli=f"python -m review_tool llm-review {res['date']} --write")


def plan_finalize(tokens: TokenStore, day: str) -> dict[str, Any]:
    from ..reports.llm_finalize import run_llm_finalize

    day = _check_date(day)
    path = _md_path(day)
    res = run_llm_finalize(day, md_path=path, write=False)
    preview = {"date": day, "changed": res["changed"], "pending_before": res["pending_before"],
               "pending_after": res["pending_after"], "side_by_side": res["preview"]}
    return _plan_out(tokens, "finalize", {"date": day, "md": path, "md_sha": _sha_file(path)},
                     preview=preview, cli=f"python -m review_tool llm-finalize {day} --write")


def _check_unchanged(p: dict[str, Any]) -> None:
    if not os.path.isfile(p["md"]) or _sha_file(p["md"]) != p["md_sha"]:
        raise QueryError(409, "stale_plan", "复盘 md 在预览后被改动，请重新预览再确认")


def _ingest_cli(day: str) -> str:
    return f"python -m review_tool ingest 复盘/{day[:7]}/{day}.md"


def _apply_ai_draft(p: dict[str, Any]) -> dict[str, Any]:
    from ..reports.llm_review import write_ai_section

    _check_unchanged(p)
    changed = write_ai_section(p["md"], p["section"])
    return {"written": changed, "pending_review": True,
            "next": "人审后点「定稿」，再 ingest（草稿态 ingest 默认跳过）"}


def _apply_finalize(p: dict[str, Any]) -> dict[str, Any]:
    from ..reports.llm_finalize import run_llm_finalize

    _check_unchanged(p)
    res = run_llm_finalize(p["date"], md_path=p["md"], write=True)
    return {"written": res["written"], "pending_after": res["pending_after"],
            "next": f"定稿已写入 md；入库请执行：{_ingest_cli(p['date'])}"}


# ---------------------------------------------------------------------------
# ClickUp 建任务 / 改状态（FR-J1）：复用 pipeline.clickup_task（dry-run + 写后回读）
# ---------------------------------------------------------------------------

_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _clean_text(value: str, *, field: str, limit: int) -> str:
    v = (value or "").strip()
    if not v or len(v) > limit or any(ord(c) < 32 for c in v):
        raise QueryError(422, "invalid_param", f"{field} 为空、过长（>{limit}）或含控制字符")
    return v


def _quote_arg(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def plan_task_create(tokens: TokenStore, name: str, list_id: str | None = None, *,
                     env=None) -> dict[str, Any]:
    from ..config import CLICKUP_LIST_META, LIST_DAILY
    from ..pipeline.clickup_task import run_create
    from .clickup_queries import _creds

    name = _clean_text(name, field="任务名", limit=200)
    lid = (list_id or LIST_DAILY or "").strip()
    if lid not in CLICKUP_LIST_META:  # 白名单：只允许 config 里登记过的 list
        raise QueryError(422, "invalid_list", "清单不在本机登记的 ClickUp list 中")
    _creds(env)  # 集成关闭 / 凭据缺失在预览阶段就拦下
    _rc, msg = run_create(name, list_id=lid, status=None, apply=False, key="")
    list_name = CLICKUP_LIST_META[lid]["name"]
    preview = {"name": name, "list": list_name, "message": msg}
    return _plan_out(tokens, "task_create", {"date": _today(), "name": name, "list_id": lid},
                     preview=preview,
                     cli=f"python -m review_tool clickup-task --create {_quote_arg(name)} --list {lid} --apply")


def plan_task_status(tokens: TokenStore, task_id: str, status: str, *, name: str | None = None,
                     env=None) -> dict[str, Any]:
    from ..pipeline.clickup_task import run_status
    from .clickup_queries import _creds

    tid = (task_id or "").strip()
    if not _TASK_ID_RE.match(tid):
        raise QueryError(422, "invalid_task", "task id 不合法")
    status = _clean_text(status, field="状态", limit=40)
    _creds(env)
    _rc, msg = run_status(tid, status, apply=False, key="")
    preview = {"task_id": tid, "name": (name or "")[:200], "status": status, "message": msg}
    return _plan_out(tokens, "task_status", {"date": _today(), "task_id": tid, "status": status},
                     preview=preview,
                     cli=f"python -m review_tool clickup-task --status {tid} {_quote_arg(status)} --apply")


def _apply_task(p: dict[str, Any], *, env=None, cu_client=None) -> dict[str, Any]:
    from ..pipeline.clickup_task import run_create, run_status
    from .clickup_queries import _creds

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


# ---------------------------------------------------------------------------
# ingest 单文件（FR-K1）：路径限定在 INPUT_DIR 内；写库前备份；写后回读
# ---------------------------------------------------------------------------

def _resolve_ingest_path(path: str | None, day: str | None) -> str:
    from ..config import INPUT_DIR
    from ..reports import llm_review as lr

    if path:
        if not os.path.isabs(path):
            raise QueryError(422, "invalid_path", "请传绝对路径")
        cand = os.path.realpath(path)
    elif day:
        cand = os.path.realpath(lr.review_md_path(_check_date(day)))
    else:
        raise QueryError(422, "invalid_param", "须给 path 或 date")
    root = os.path.realpath(INPUT_DIR)
    try:
        inside = os.path.commonpath([root, cand]) == root
    except ValueError:  # 不同盘符
        inside = False
    if not inside or not cand.lower().endswith(".md"):
        raise QueryError(422, "path_forbidden", "只允许 local/每日复盘/ 内的 .md 文件")
    if not os.path.isfile(cand):
        raise QueryError(404, "md_missing", "找不到该复盘 md")
    return cand


def plan_ingest(tokens: TokenStore, *, path: str | None = None, day: str | None = None,
                allow_ai_draft: bool = False) -> dict[str, Any]:
    from ..core.ai_draft import is_ai_draft_pending
    from ..pipeline.parse import parse_file

    md = _resolve_ingest_path(path, day)
    with open(md, encoding="utf-8") as f:
        pending = is_ai_draft_pending(f.read())
    row = parse_file(md)
    if not row.get("date"):
        raise QueryError(422, "no_date", "该 md 未解析到日期，无法入库")
    keys = ("health_score", "work_score", "learn_score", "life_score", "diet_kcal",
            "sleep_h", "exercise_min")
    fields = {k: row.get(k) for k in keys}
    will_skip = pending and not allow_ai_draft
    rel = os.path.relpath(md, os.path.dirname(os.path.dirname(md)))
    preview = {"date": row["date"], "file": os.path.basename(md), "rel": rel,
               "pending": pending, "allow_ai_draft": allow_ai_draft, "will_skip": will_skip,
               "fields": fields}
    flag = " --allow-ai-draft" if allow_ai_draft else ""
    return _plan_out(tokens, "ingest", {"date": row["date"], "md": md, "md_sha": _sha_file(md),
                                        "allow_ai_draft": allow_ai_draft},
                     preview=preview, cli=f"python -m review_tool ingest {_quote_arg(md)}{flag}")


def _apply_ingest(p: dict[str, Any], *, db_path: str | None, backup_dir: str | None
                  ) -> dict[str, Any]:
    import contextlib
    import io

    from ..config import DB_PATH
    from ..pipeline.ingest import ingest_path
    from ..storage.db import fetch_all, get_conn

    _check_unchanged(p)
    path = os.path.abspath(db_path or DB_PATH)
    if not os.path.isfile(path):
        raise QueryError(503, "db_missing", "数据库尚未建立，请先在 CLI 执行 ingest")
    backup = _backup_db(path, backup_dir)
    buf = io.StringIO()
    conn = get_conn(path)
    try:
        with contextlib.redirect_stdout(buf):
            row = ingest_path(conn, p["md"], allow_ai_draft=p["allow_ai_draft"])
        got = [dict(r) for r in fetch_all(conn) if r["date"] == p["date"]]
    finally:
        conn.close()
    log = [ln for ln in buf.getvalue().splitlines() if ln.strip()][:20]
    if not row:
        raise QueryError(409, "ingest_skipped", (log[0].strip() if log else "ingest 跳过了该文件"))
    if not got:
        raise QueryError(500, "readback_failed", "入库后回读不到该日记录，请用备份核对")
    g = got[0]
    return {"written": True, "backup": os.path.basename(backup), "log": log,
            "readback": {k: g.get(k) for k in ("date", "health_score", "work_score",
                                                "learn_score", "life_score", "system_score")}}


def _today() -> str:
    return datetime.date.today().isoformat()


def confirm(tokens: TokenStore, token: str, *, db_path: str | None = None,
            backup_dir: str | None = None, env=None, cu_client=None) -> dict[str, Any]:
    """执行预览过的写操作（单次、串行）；返回结果 + 等价 CLI。"""
    p = tokens.take(token)
    with _WRITE_LOCK:
        if p["action"] == "habits_sync":
            out = _apply_habits(p, db_path=db_path, backup_dir=backup_dir)
        elif p["action"] == "ai_draft":
            out = _apply_ai_draft(p)
        elif p["action"] == "finalize":
            out = _apply_finalize(p)
        elif p["action"] in ("task_create", "task_status"):
            out = _apply_task(p, env=env, cu_client=cu_client)
        elif p["action"] == "ingest":
            out = _apply_ingest(p, db_path=db_path, backup_dir=backup_dir)
        else:  # pragma: no cover - issue() 只发已知动作
            raise QueryError(400, "bad_action", "未知写操作")
    return {"action": p["action"], "date": p["date"], "cli": p["cli"], "result": out}
