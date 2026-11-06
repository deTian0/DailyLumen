"""ingest 单文件（FR-K1）：路径限定在 ``INPUT_DIR`` 内；写库前备份；写后回读。"""
from __future__ import annotations

import os
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, backup_db, plan_out, quote_arg, register, require_db, sha_file
from .review_md import check_unchanged


def _resolve_ingest_path(path: str | None, day: str | None) -> str:
    from ...config import INPUT_DIR
    from ...reports import llm_review as lr

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
    from ...core.ai_draft import is_ai_draft_pending
    from ...pipeline.parse import parse_file

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
    return plan_out(tokens, "ingest", {"date": row["date"], "md": md, "md_sha": sha_file(md),
                                       "allow_ai_draft": allow_ai_draft},
                    preview=preview, cli=f"python -m review_tool ingest {quote_arg(md)}{flag}")


@register("ingest", needs=("db_path", "backup_dir"))
def _apply_ingest(p: dict[str, Any], *, db_path: str | None, backup_dir: str | None
                  ) -> dict[str, Any]:
    import contextlib
    import io

    from ...pipeline.ingest import ingest_path
    from ...storage.db import fetch_all, get_conn

    check_unchanged(p)
    path = require_db(db_path)
    backup = backup_db(path, backup_dir)
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
