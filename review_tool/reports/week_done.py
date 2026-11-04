"""week-done：本周做成了什么（M43 / v1.50.0 / FR-A4）。

只读聚合：本周 ``clickup_done`` 快照 + 复盘「二、今日三件事」原文。
不写叙事结论、不加评分、不替代 ``week`` / ``fuse``。

用法::

    python -m review_tool week-done              # 当前 ISO 周
    python -m review_tool week-done 45           # 指定 ISO 周
    python -m review_tool week-done --json
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys

from ..core.bodyweight import section_body
from ..storage.db import init_db
from .clickup_done import collect as collect_clickup

USAGE = "week-done [ISO周] [--json] [--db PATH]"

_BULLET_RE = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s*)?(.+?)\s*$")


def _iso_week_bounds(iso_week: int, *, year: int | None = None) -> tuple[str, str]:
    y = year or datetime.date.today().isocalendar()[0]
    start = datetime.date.fromisocalendar(y, iso_week, 1)
    end = datetime.date.fromisocalendar(y, iso_week, 7)
    return start.isoformat(), end.isoformat()


def extract_three_things(md_text: str) -> list[str]:
    """从复盘 md「二、今日三件事」抽出条目原文（去勾选框）。"""
    body = section_body(md_text or "")
    items: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        text = m.group(1).strip()
        if not text or text.startswith((">", "（", "(")):
            continue
        # 跳过明显占位
        if text in ("（未提）", "未提", "无", "空", "—", "-"):
            continue
        items.append(text)
    return items


def _read_md(path: str | None) -> str:
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def collect(conn, *, iso_week: int, year: int | None = None) -> dict:
    """本周完成清单（结构化）。"""
    start, end = _iso_week_bounds(iso_week, year=year)
    # 以库内该周实际日期为准（跨年周时 year 兜底）
    rows = conn.execute(
        "SELECT date, raw_path, summary FROM daily_reviews "
        "WHERE iso_week=? AND date>=? AND date<=? ORDER BY date",
        (iso_week, start, end),
    ).fetchall()
    if rows:
        start = rows[0]["date"]
        end = rows[-1]["date"]

    cu = collect_clickup(conn, start=start, end=end)
    three_by_day: list[dict] = []
    three_total = 0
    for r in rows:
        day = r["date"]
        items = extract_three_things(_read_md(r["raw_path"]))
        three_total += len(items)
        three_by_day.append({"date": day, "items": items, "path": r["raw_path"]})

    return {
        "iso_week": iso_week,
        "start": start,
        "end": end,
        "clickup": cu,
        "three_things": three_by_day,
        "three_total": three_total,
        "clickup_total": cu.get("total") or 0,
    }


def render(data: dict) -> str:
    L: list[str] = []
    wk = data["iso_week"]
    L.append(f"本周做成了什么 · ISO W{wk}（{data['start']} ~ {data['end']}）")
    L.append("-" * 62)
    L.append("只读清单（ClickUp 完成快照 + 复盘三件事原文）；不写叙事、不加分。")
    L.append("")

    L.append(f"## ClickUp 完成（{data['clickup_total']} 条）")
    L.append("")
    if not data["clickup_total"]:
        L.append("（本周无 clickup_done 快照。先跑 `clickup-pull`，或本周确实无完成项。）")
        L.append("")
    else:
        for day in data["clickup"]["days"]:
            L.append(f"### {day['date']}（{len(day['items'])}）")
            for it in day["items"]:
                L.append(f"- {it['name']}")
            L.append("")

    L.append(f"## 复盘三件事（{data['three_total']} 条）")
    L.append("")
    if not data["three_total"]:
        L.append("（本周复盘「二、今日三件事」无条目，或 md 未找到。）")
        L.append("")
    else:
        for day in data["three_things"]:
            if not day["items"]:
                continue
            L.append(f"### {day['date']}（{len(day['items'])}）")
            for it in day["items"]:
                L.append(f"- {it}")
            L.append("")

    if not data["clickup_total"] and not data["three_total"]:
        L.append("> 本周两侧皆空：不是空白假装有产出 —— 需补 clickup-pull / 写三件事，或本周确实无记录。")
    return "\n".join(L).rstrip() + "\n"


def _parse(argv: list[str]) -> tuple[int | None, bool, str | None]:
    week: int | None = None
    as_json = False
    db_path: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--db":
            i += 1
            if i >= len(argv):
                raise ValueError("--db 需要跟路径")
            db_path = argv[i]
        elif a.startswith("--db="):
            db_path = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            try:
                week = int(a)
            except ValueError:
                raise ValueError(f"ISO 周应为整数，收到: {a}") from None
            if not 1 <= week <= 53:
                raise ValueError(f"ISO 周应在 1–53，收到: {week}")
        i += 1
    return week, as_json, db_path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("本周做成了什么：ClickUp 完成 + 复盘三件事只读清单。")
        return 0
    try:
        week, as_json, db_path = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    conn = init_db(db_path)
    try:
        if week is None:
            # 优先库最新日所在周，否则今天
            row = conn.execute("SELECT MAX(date) FROM daily_reviews").fetchone()
            if row and row[0]:
                d = datetime.date.fromisoformat(row[0])
            else:
                d = datetime.date.today()
            week = d.isocalendar()[1]
        data = collect(conn, iso_week=week)
    finally:
        conn.close()

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
