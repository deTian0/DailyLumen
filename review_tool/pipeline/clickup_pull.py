"""ClickUp 已完成任务 → ``clickup_done`` 快照（D2 / v1.37.0）。

用法::

    python -m review_tool clickup-pull                 # 全量拉取（工作 + 日常事务）
    python -m review_tool clickup-pull --days 30       # 只要最近 30 天有归属日的
    python -m review_tool clickup-pull --list 901410092299
    python -m review_tool clickup-done 2026-10-20      # 看某天完成了什么

设计红线
--------
1. **只读**：ClickUp → 本地快照，绝不反推复盘（与 ``clickup-push`` 方向相反）。
2. **按整天替换**：某天的记录以本次拉取为准整批替换，不 upsert ——
   否则任务被取消完成 / 改名 / 换 list 后会留下幽灵行。
3. **失败不猜**：网络或凭据失败时非 0 退出，**不动库**；不做「部分成功」静默。
4. **不做语义匹配**：快照只提供事实（谁、哪天、多少分钟），判定留给上层。
"""
from __future__ import annotations

import sys
from collections import defaultdict

from ..config import CLICKUP_LISTS, LIST_DAILY, LIST_WORK
from ..core.clickup_done import to_row
from ..storage.db import init_db, replace_clickup_days
from .clickup import CredError, completion_day, fetch_tasks, load_creds

USAGE = "clickup-pull [--days N] [--list ID] [--db PATH] [--dry-run]"

# 默认只拉这两张表：工作（工时流水）+ 日常事务（行为流水）。
# 习惯 list 已由 habit_sync 单独处理，项目孵化/年度目标不是「完成记录」来源。
DEFAULT_LISTS = (LIST_WORK, LIST_DAILY)


def _list_ids(explicit: str | None) -> tuple[str, ...]:
    if explicit:
        return (explicit,)
    known = {item["id"] for item in CLICKUP_LISTS}
    return tuple(lid for lid in DEFAULT_LISTS if lid in known) or DEFAULT_LISTS


def pull(
    conn,
    *,
    list_ids: tuple[str, ...] = DEFAULT_LISTS,
    days: int | None = None,
    today: str | None = None,
    fetch=None,
    key: str | None = None,
    dry_run: bool = False,
) -> dict:
    """拉取已完成任务并写快照。返回统计字典。

    ``days`` 只过滤**入库范围**（不减少 API 调用 —— ClickUp 按 list 拉全量，
    分页反而更慢；830 条的体量下全拉一次不到 2 秒）。
    """
    from datetime import date as _date
    from datetime import datetime, timedelta

    fetch = fetch or fetch_tasks
    if key is None:
        key, _ = load_creds()
    today = today or _date.today().isoformat()
    floor = None
    if days:
        floor = (
            datetime.strptime(today, "%Y-%m-%d") - timedelta(days=max(days, 1) - 1)
        ).strftime("%Y-%m-%d")

    by_date: dict[str, list[dict]] = defaultdict(list)
    fetched = closed = skipped_open = skipped_floor = 0
    per_list: dict[str, int] = {}

    for lid in list_ids:
        tasks = fetch(lid, key)
        fetched += len(tasks)
        per_list[lid] = len(tasks)
        for t in tasks:
            day = completion_day(t)
            if day is None:
                skipped_open += 1        # 未完成 / 没有 date_closed
                continue
            if floor and day < floor:
                skipped_floor += 1
                continue
            closed += 1
            by_date[day].append(to_row(t, lid, day))

    stats = {
        "lists": list(list_ids),
        "fetched": fetched,
        "per_list": per_list,
        "closed": closed,
        "skipped_open": skipped_open,
        "skipped_floor": skipped_floor,
        "dates": len(by_date),
        "range": (min(by_date), max(by_date)) if by_date else None,
        "applied": {},
    }
    if dry_run or not by_date:
        return stats

    stats["applied"] = replace_clickup_days(conn, by_date)
    conn.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    days = None
    list_arg = None
    dry_run = "--dry-run" in argv
    args = list(argv)
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
        if a == "--list" and i + 1 < len(args):
            list_arg = args[i + 1]

    list_ids = _list_ids(list_arg)
    conn = init_db()
    try:
        stats = pull(conn, list_ids=list_ids, days=days, dry_run=dry_run)
    except CredError as e:
        print(f"缺少 ClickUp 凭据: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # 网络失败：不动库，非 0 退出
        print(f"拉取失败（未写入）: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"ClickUp 完成任务快照 · {len(stats['lists'])} 个 list")
    for lid, n in stats["per_list"].items():
        print(f"  {lid}: 拉取 {n} 条")
    print(
        f"  已完成 {stats['closed']} 条 / 跳过未完成 {stats['skipped_open']} 条"
        + (f" / 早于窗口 {stats['skipped_floor']} 条" if stats["skipped_floor"] else "")
    )
    if stats["range"]:
        print(f"  覆盖 {stats['dates']} 天（{stats['range'][0]} ~ {stats['range'][1]}）")
    if dry_run:
        print("  [dry-run] 未写库")
    else:
        ins = sum(v["inserted"] for v in stats["applied"].values())
        print(f"  写入 {ins} 条（按整天替换，{len(stats['applied'])} 天）")
    return 0
