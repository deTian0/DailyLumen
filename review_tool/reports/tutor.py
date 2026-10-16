"""学习 / 复习报告：今日待复习 + 本周主题 / 投入 / 产出物（独立指标区）。

用法:
    python -m review_tool tutor
    python -m review_tool tutor --json
    python -m review_tool tutor 2026-10-15

不参与四维（G5）。「讲解 / 出题」不写代码——那是 AI 现场能力。
证据链：``clickup --list 901422213142 --list 901422213140``（阅读与学习 + 成长课）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta

from ..config import LEARNING_LIST_IDS, SPACED_REPEAT
from ..core.learning import due_status, week_rollup
from ..storage.db import (
    init_db,
    load_learning_logs,
    load_review_queue,
    rebuild_review_queue,
)


def _iso_week_bounds(as_of: str) -> tuple[str, str]:
    """锚点日所在 ISO 周的周一 / 周日（含）。"""
    d = datetime.strptime(as_of, "%Y-%m-%d").date()
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def collect(conn, *, as_of: str | None = None,
            rebuild: bool = True) -> dict:
    """汇学习报告数据（结构化，文本 / JSON 共用）。"""
    if as_of is None:
        row = conn.execute(
            "SELECT MAX(date) FROM learning_logs"
        ).fetchone()
        as_of = row[0] if row and row[0] else date.today().isoformat()

    if rebuild:
        rebuild_review_queue(conn)
        conn.commit()

    queue_rows = [dict(r) for r in load_review_queue(conn)]
    due_today: list[dict] = []
    overdue: list[dict] = []
    pending: list[dict] = []
    for q in queue_rows:
        status = due_status(as_of, q["due_date"])
        item = {**q, "status": status}
        if status == "due":
            due_today.append(item)
        elif status == "overdue":
            overdue.append(item)
        else:
            pending.append(item)

    week_start, week_end = _iso_week_bounds(as_of)
    week_logs = [
        dict(r) for r in load_learning_logs(
            conn, start=week_start, end=week_end
        )
    ]
    week = week_rollup(week_logs)

    return {
        "as_of": as_of,
        "intervals": list(SPACED_REPEAT.get("intervals") or [1, 3, 7, 16]),
        "due_today": due_today,
        "overdue": overdue,
        "pending": pending,
        "queue_total": len(queue_rows),
        "week": {
            "start": week_start,
            "end": week_end,
            **week,
        },
        "evidence_lists": list(LEARNING_LIST_IDS),
    }


def week_section_lines(week: dict) -> list[str]:
    """给 analyze 周报挂段用的纯文本行（不含大标题）。"""
    L: list[str] = []
    topics = week.get("topics") or []
    if not topics:
        L.append("  （本周无 learning_logs）")
        return L
    total = week.get("total_minutes")
    total_s = f"{total:.0f}min" if total is not None else "—"
    L.append(
        f"  投入 {total_s} · {week.get('entries', 0)} 条 · "
        f"{len(week.get('days') or [])} 天"
    )
    for t in topics:
        m = t.get("minutes")
        ms = f"{m:.0f}min" if m is not None else "—"
        L.append(f"  · {t['topic_key']}: {ms}（{t['entries']}）· {t['topic']}")
    arts = week.get("artifacts") or []
    if arts:
        L.append("  产出物: " + "；".join(arts[:8]))
        if len(arts) > 8:
            L.append(f"  …另有 {len(arts) - 8} 项")
    return L


def render(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 学习 / 复习报告（不计入四维评分）")
    L.append("=" * 52)
    L.append(
        f"锚点日: {data['as_of']}  ·  间隔: "
        f"{'/'.join(str(i) + 'd' for i in data['intervals'])}"
        f"  ·  队列: {data['queue_total']}"
    )
    L.append("")
    L.append("---- 今日待复习 ----")
    due = data.get("due_today") or []
    overdue = data.get("overdue") or []
    if not due and not overdue:
        L.append("  （无到期 / 逾期项）")
    else:
        for it in overdue:
            L.append(
                f"  ! 逾期 {it['topic']}（{it['topic_key']}）"
                f"  due={it['due_date']} stage={it['stage']}"
                f"  last={it.get('last_seen') or '—'}"
            )
        for it in due:
            L.append(
                f"  * 到期 {it['topic']}（{it['topic_key']}）"
                f"  stage={it['stage']}"
                f"  last={it.get('last_seen') or '—'}"
            )
    L.append("")
    week = data.get("week") or {}
    L.append(
        f"---- 本周主题 / 投入 / 产出物"
        f"（{week.get('start')} ~ {week.get('end')}）----"
    )
    L.extend(week_section_lines(week))
    L.append("")
    ids = data.get("evidence_lists") or []
    if ids:
        L.append(
            "证据链（ClickUp，只读素材）: "
            + " ".join(f"--list {i}" for i in ids)
        )
        L.append("讲解 / 出题交给对话现场能力，本命令不生成题库。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法: python -m review_tool tutor [YYYY-MM-DD] [--json]")
        print("      今日待复习 + 本周主题/投入/产出物（独立指标区）")
        print("      证据链: clickup --list 901422213138   # v1.24.0 起并入日常事务")
        return 0

    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    as_of = args[0] if args else None

    conn = init_db()
    try:
        data = collect(conn, as_of=as_of, rebuild=True)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(render(data))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
