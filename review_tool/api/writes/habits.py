"""habits sync（FR-D3）：ClickUp「习惯与打卡」→ ``habit_logs``。

只写 ``habit_logs``，**不碰** ``personal_tracks``（R3）。写库前整库备份，写后回读。
"""
from __future__ import annotations

import datetime
import os
import urllib.error
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, backup_db, plan_out, register, require_db


def plan_habits_sync(tokens: TokenStore, day: str | None = None, *, fetch=None, env=None
                     ) -> dict[str, Any]:
    from ...pipeline import habit_sync as hs
    from ..clickup_queries import _creds

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
    return plan_out(tokens, "habits_sync", {"date": day, "rows": rows}, preview=preview,
                    cli=f"python -m review_tool habits --sync {day}")


@register("habits_sync", needs=("db_path", "backup_dir"))
def _apply_habits(p: dict[str, Any], *, db_path: str | None, backup_dir: str | None
                  ) -> dict[str, Any]:
    from ...storage.db import get_conn, load_habit_logs, upsert_habit_log

    path = require_db(db_path)
    backup = backup_db(path, backup_dir)
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
