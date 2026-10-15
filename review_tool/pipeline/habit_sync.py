"""ClickUp 习惯 → habit_logs 快照（唯一 ClickUp→库写方向，v1.15.0 / M11）。

用法:
    python -m review_tool habits --sync                 # 同步今天
    python -m review_tool habits --sync 2026-10-15      # 指定日
    python -m review_tool habits --sync --dry-run       # 只打印不写
    python -m review_tool clickup --with-habits         # 拉素材时顺带同步

口径
----
1. **权威**：ClickUp 执行层 → habit_logs 快照。与 ``clickup-push``（库→ClickUp）
   方向相反、互不干扰。
2. **幂等**：同一日期重复同步不产生重复行；默认**不改写已有 done**。
3. **隔离**：只写 ``habit_logs``，绝不碰 ``personal_tracks``（R3）。
4. **不参与四维**（G5）。

退出码：0 = 成功 / dry-run；1 = 取数失败；2 = 用法 / 凭据问题。
"""
from __future__ import annotations

import datetime
import sys
import urllib.error

from ..config import DB_PATH, HABITS, HABITS_LIST_ID
from ..core.habits import HABIT_CATEGORY
from ..storage.db import init_db, upsert_habit_log
from .clickup import (
    CredError,
    completion_day,
    fetch_tasks,
    load_creds,
    select_habits,
)

USAGE = "habits --sync [YYYY-MM-DD] [--dry-run] [--db PATH] [--overwrite-done]"


def day_done_for_task(task: dict, day: str, *, tz_hours: int | None = None,
                      rule: dict | None = None) -> int:
    """该任务在 ``day`` 是否算完成（归日含次日补勾回拨）。"""
    if not task.get("date_closed"):
        return 0
    return 1 if completion_day(task, tz_hours=tz_hours, rule=rule) == day else 0


def rows_for_day(tasks: list[dict], day: str, *,
                 items: list[dict] | None = None) -> list[dict]:
    """把 ClickUp 习惯任务落成当日 habit_logs 行（含未完成 → done=0）。

    每个 ``HABITS`` key 至多一行；任务名归一化失败的跳过。
    """
    catalog = items if items is not None else HABITS
    selected = select_habits(tasks, items=catalog)
    by_key: dict[str, dict] = {}
    for h in selected:
        key = h["habit_key"]
        # 同 key 多任务：任一条当日完成即 done=1
        done = day_done_for_task(h["task"], day)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = {
                "date": day,
                "habit_key": key,
                "category": HABIT_CATEGORY,
                "item": h["label"],
                "done": done,
                "src": "clickup",
                "note": None,
            }
        elif done == 1:
            prev["done"] = 1
    # 目录里有、但 ClickUp 未匹配到的项：不造假行（避免凭空 done=0 污染依从率）
    return [by_key[k] for k in sorted(by_key)]


def sync_habits(conn, day: str, tasks: list[dict] | None = None, *,
                key: str = "", fetch=None, dry_run: bool = False,
                overwrite_done: bool = False,
                list_id: str | None = None) -> dict:
    """拉取（或使用注入的）习惯任务并写入 ``habit_logs``。

    返回 ``{"day", "fetched", "written", "rows", "dry_run"}``。
    """
    lid = list_id or HABITS_LIST_ID
    if tasks is None:
        tasks = fetch_tasks(lid, key, fetch=fetch)
    rows = rows_for_day(tasks, day)
    written = 0
    if not dry_run:
        for row in rows:
            upsert_habit_log(conn, row, overwrite=overwrite_done)
            written += 1
        conn.commit()
    return {
        "day": day,
        "fetched": len(tasks),
        "matched": len(rows),
        "written": written,
        "rows": rows,
        "dry_run": dry_run,
    }


def _parse_sync_argv(argv: list[str]) -> tuple[str, bool, str | None, bool]:
    """返回 ``(day, dry_run, db_path, overwrite_done)``。"""
    day, dry_run, db_path, overwrite = "", False, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--dry-run",):
            dry_run = True
        elif a in ("--overwrite-done",):
            overwrite = True
        elif a == "--db" or a.startswith("--db="):
            if a.startswith("--db="):
                db_path = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--db 需要跟一个路径")
                db_path = argv[i]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day:
                raise ValueError(f"多余的参数: {a}")
            day = a
        i += 1
    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    else:
        day = datetime.date.today().isoformat()
    return day, dry_run, db_path, overwrite


def sync_main(argv: list[str] | None = None, *, fetch=None, env=None) -> int:
    """``habits --sync`` 的实现（也可被 ``clickup --with-habits`` 调用）。"""
    argv = list(argv or [])
    try:
        day, dry_run, db_path, overwrite = _parse_sync_argv(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        api_key, _team = load_creds(env=env)
    except CredError as e:
        print(f"凭据错误: {e}", file=sys.stderr)
        return 2

    conn = init_db(db_path or DB_PATH)
    try:
        summary = sync_habits(
            conn, day, key=api_key, fetch=fetch,
            dry_run=dry_run, overwrite_done=overwrite,
        )
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        print(f"取数失败: HTTP {code}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"取数失败: 网络不可达 —— {e.reason}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    tag = "（dry-run）" if dry_run else ""
    print(f"habit_sync {day}{tag}: 拉取 {summary['fetched']} 条，"
          f"匹配 {summary['matched']} 项，"
          f"{'将写入' if dry_run else '已写入'} {summary['matched']} 行")
    for r in summary["rows"]:
        mark = "✓" if r["done"] else "·"
        print(f"  {mark} {r['habit_key']}: {r['item']} done={r['done']}")
    return 0


__all__ = [
    "day_done_for_task",
    "rows_for_day",
    "sync_habits",
    "sync_main",
]
