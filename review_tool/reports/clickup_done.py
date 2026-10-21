"""某天在 ClickUp 里完成了什么（`clickup-done`）—— 写复盘时的「今日事实」。

用法::

    python -m review_tool clickup-done            # 今天
    python -m review_tool clickup-done 2026-10-20
    python -m review_tool clickup-done 2026-10-14 2026-10-20   # 区间
    python -m review_tool clickup-done --json

为什么要有这个：复盘模板里「二、今日三件事」写着「实在想不出？就写今天做成
的最少的事」—— 到晚上回想上午干了什么，本来就不可靠。ClickUp 里有客观记录，
读出来比回忆准。

数据来自 ``clickup_done`` 快照（``clickup-pull`` 写入），**不实时联网**。
"""
from __future__ import annotations

import json
import sys

from ..core.clickup_done import summarize
from ..storage.db import init_db, load_clickup_done


def collect(conn, *, start: str, end: str) -> dict:
    """区间内每天的完成记录 + 汇总。"""
    rows = [dict(r) for r in load_clickup_done(conn, start=start, end=end)]
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)

    days = []
    for day in sorted(by_date):
        items = by_date[day]
        s = summarize(items)
        days.append(
            {
                "date": day,
                **s,
                "items": [
                    {
                        "name": r["name"],
                        "owner": r.get("owner"),
                        "minutes": r.get("minutes"),
                        "subject": r.get("subject"),
                        "is_self": bool(r.get("is_self")),
                    }
                    for r in items
                ],
            }
        )
    return {
        "start": start,
        "end": end,
        "days": days,
        "total": len(rows),
        "self_total": sum(d["self_count"] for d in days),
    }


def _fmt_minutes(v: float | None) -> str:
    if v is None:
        return "—"
    h, m = divmod(int(round(v)), 60)
    if h and m:
        return f"{h}h{m}m"
    return f"{h}h" if h else f"{m}m"


def render(result: dict) -> str:
    L: list[str] = []
    span = result["start"] if result["start"] == result["end"] else (
        f"{result['start']} ~ {result['end']}"
    )
    L.append(f"ClickUp 完成记录 · {span}")
    L.append("-" * 62)
    if not result["total"]:
        L.append("没有快照记录。先跑 `python -m review_tool clickup-pull` 拉一次。")
        L.append("（快照是离线的 —— 报告不联网，避免周报卡在 60s 超时上）")
        return "\n".join(L)

    for d in result["days"]:
        head = f"{d['date']}  完成 {d['count']} 条"
        if d["self_max"]:
            head += f" · 最长单条 {_fmt_minutes(d['self_max'])}"
        L.append(head)
        items = d["items"]
        if not items:
            L.append("    （这天没有记录 —— 可能是没填，不等于没工作）")
            L.append("")
            continue
        for it in items:
            subj = it["subject"] or it["name"]
            if it["minutes"] is None:
                L.append(f"    -        {subj[:60]}")
            else:
                L.append(f"    - {_fmt_minutes(it['minutes']):>6s}  {subj[:60]}")
        if d["self_no_hours"]:
            L.append(
                f"    · 其中 {d['self_no_hours']} 条**没有工时**"
                "（日常事务类任务本来就不记工时，或写了 `xh` 这种写不出的）"
            )
        if d["self_sum"] and d["self_max"] and d["self_sum"] > d["self_max"]:
            L.append(
                f"    · 合计 {_fmt_minutes(d['self_sum'])} —— **仅供看，别当工作时长**"
                "（任务级估算，多条会重叠）"
            )
        L.append("")

    L.append("-" * 62)
    L.append(
        f"记录合计 {result['self_total']} 条（整张工时表都是本人执行记录，"
        "姓名前缀是下发人）。"
        "这里是**事实**：哪天完成了什么。它不判承诺兑现 —— "
        "工时是任务级估算，不是专注计时，量纲不同。"
    )
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    if args:
        start = args[0]
        end = args[1] if len(args) >= 2 else start
    else:
        from datetime import date as _date

        start = end = _date.today().isoformat()

    conn = init_db()
    try:
        result = collect(conn, start=start, end=end)
    finally:
        conn.close()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(result))
    return 0
