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


def confirm(tokens: TokenStore, token: str, *, db_path: str | None = None,
            backup_dir: str | None = None) -> dict[str, Any]:
    """执行预览过的写操作（单次、串行）；返回结果 + 等价 CLI。"""
    p = tokens.take(token)
    with _WRITE_LOCK:
        if p["action"] == "habits_sync":
            out = _apply_habits(p, db_path=db_path, backup_dir=backup_dir)
        elif p["action"] == "ai_draft":
            out = _apply_ai_draft(p)
        elif p["action"] == "finalize":
            out = _apply_finalize(p)
        else:  # pragma: no cover - issue() 只发三种
            raise QueryError(400, "bad_action", "未知写操作")
    return {"action": p["action"], "date": p["date"], "cli": p["cli"], "result": out}
