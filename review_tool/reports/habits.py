"""行为习惯报告：依从率 / streak / 断更（独立指标区，不计入四维）。

用法:
    python -m review_tool habits                      # 报告
    python -m review_tool habits --json
    python -m review_tool habits --sync [YYYY-MM-DD]  # ClickUp → habit_logs
    python -m review_tool habits --sync --dry-run
"""
from __future__ import annotations

import json
import sys
from datetime import date

from ..config import HABITS
from ..core.habits import (
    adherence_from_rows,
    detect_gaps,
    habit_streak,
)
from ..pipeline.habit_sync import sync_main
from ..storage.db import init_db, load_habit_logs


def collect(conn, *, as_of: str | None = None) -> dict:
    """汇总体习惯报告数据。"""
    rows_raw = load_habit_logs(conn)
    rows = [dict(r) for r in rows_raw]
    end = as_of or (max((r["date"] for r in rows), default=None)
                    or date.today().isoformat())
    adh = adherence_from_rows(rows)
    streaks = [
        habit_streak(rows, spec["key"], as_of=end) for spec in HABITS
    ]
    gaps = detect_gaps(rows, as_of=end)
    return {
        "as_of": end,
        "count": len(rows),
        "adherence": adh,
        "streaks": streaks,
        "gaps": gaps,
        "catalog": [
            {
                "key": s["key"],
                "label": s["label"],
                "target_per_week": s["target_per_week"],
                "alert_days": s["alert_days"],
            }
            for s in HABITS
        ],
    }


def render(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 行为习惯报告（不计入四维评分）")
    L.append("=" * 52)
    L.append(f"锚点日: {data['as_of']}  ·  日志行: {data['count']}")
    L.append("")
    L.append("---- 依从率 ----")
    items = (data.get("adherence") or {}).get("items") or []
    if not items:
        L.append("  （尚无 habit_logs；跑 clickup --with-habits 或 habits --sync）")
    else:
        for it in items:
            rate = it["adherence"]
            pct = f"{rate * 100:.1f}%" if rate is not None else "—"
            L.append(
                f"  {it['habit_key']}: {pct}（{it['done']}/{it['recorded']}）"
                f" · {it['item']}"
            )
        tot = data["adherence"]["total"]
        if tot["recorded"]:
            tp = tot["adherence"]
            L.append(
                f"  合计: {tp * 100:.1f}%（{tot['done']}/{tot['recorded']}）"
                if tp is not None else "  合计: —"
            )
    L.append("")
    L.append("---- 连续完成 ----")
    for s in data.get("streaks") or []:
        L.append(f"  {s['habit_key']}: {s['current']} 天"
                 f"（累计完成 {s['total_days']} 天）")
    L.append("")
    L.append("---- 断更（建议性）----")
    gaps = data.get("gaps") or []
    if not gaps:
        L.append("  （无触发 alert_days 的断更）")
    else:
        for g in gaps:
            L.append(
                f"  ! {g['habit_key']}（{g.get('label', '')}）："
                f"连续 {g['gap_days']} 天未完成"
                f"（阈值 {g['alert_days']}）"
            )
    L.append("")
    L.append("与 personal_tracks（补剂/护肤）分栏隔离（R3）。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法: python -m review_tool habits [--json] [--sync ...]")
        print("      python -m review_tool habits --sync [YYYY-MM-DD] "
              "[--dry-run] [--db PATH]")
        return 0

    if "--sync" in argv:
        # 去掉 --sync，其余交给 habit_sync
        rest = [a for a in argv if a != "--sync"]
        return sync_main(rest)

    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    db_path = args[0] if args else None

    conn = init_db(db_path)
    try:
        data = collect(conn)
    finally:
        conn.close()

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
