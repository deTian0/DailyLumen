"""finalize：入库收尾守卫（M38 / v1.45.0）。

``ingest`` 后若未跑 ``recompute-scores --apply`` + ``sync-docs``，库分与字段重算
会静默漂移。本命令一键收口；**不**改默认 ``ingest`` 副作用。

    python -m review_tool finalize [--date D]           # dry-run
    python -m review_tool finalize [--date D] --apply   # 写入库 + 回写 md

无 ``--date`` 时扫全库差异；有 ``--date`` 时**只**收口该日（不触及未点名历史日）。
"""
from __future__ import annotations

import datetime
import os
import sys

from ..pipeline.sync_docs import daily_files, scores_by_date, sync_file
from ..storage.db import init_db
from .recompute import apply_changes, plan, render, target_row

USAGE = "finalize [--date YYYY-MM-DD] [--apply] [--db PATH] [--input-dir DIR]"


def plan_dates(conn, dates: set[str] | None = None) -> list[tuple[str, str, object, object]]:
    """重算差异；``dates`` 非空时只保留这些日。"""
    changes = plan(conn)
    if dates is None:
        return changes
    return [c for c in changes if c[0] in dates]


def sync_dates(*, dates: set[str] | None = None, db_path: str | None = None,
               input_dir: str | None = None, apply: bool = True) -> dict:
    """回写 md 分数；``dates`` 非空时只处理这些日。"""
    by_date = scores_by_date(db_path)
    changed: list[str] = []
    skipped: list[str] = []
    for path in daily_files(input_dir):
        date = os.path.basename(path)[:-3]
        if dates is not None and date not in dates:
            continue
        scores = by_date.get(date)
        if scores is None:
            skipped.append(date)
            continue
        if apply:
            if sync_file(path, scores):
                changed.append(date)
        else:
            from ..pipeline.sync_docs import render as render_md
            if render_md(path, scores) != open(path, encoding="utf-8").read():
                changed.append(date)
    return {"changed": changed, "skipped": skipped,
            "total": len(dates) if dates is not None else len(by_date)}


def _parse(argv: list[str]) -> tuple[str | None, bool, str | None, str | None]:
    day: str | None = None
    apply = False
    db_path: str | None = None
    input_dir: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--apply":
            apply = True
        elif a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期（YYYY-MM-DD）")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a == "--db":
            i += 1
            if i >= len(argv):
                raise ValueError("--db 需要跟路径")
            db_path = argv[i]
        elif a.startswith("--db="):
            db_path = a.split("=", 1)[1]
        elif a == "--input-dir":
            i += 1
            if i >= len(argv):
                raise ValueError("--input-dir 需要跟目录")
            input_dir = argv[i]
        elif a.startswith("--input-dir="):
            input_dir = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day is None:
                day = a
            else:
                raise ValueError(f"多余的位置参数: {a}")
        i += 1
    if day is not None:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    return day, apply, db_path, input_dir


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("入库收尾：recompute-scores + sync-docs 一键收口分数漂移。")
        print("默认 dry-run；加 --apply 写入。可选 --date 只收口该日。")
        return 0
    try:
        day, apply, db_path, input_dir = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    dates = {day} if day else None
    changes: list[tuple[str, str, object, object]] = []
    conn = init_db(db_path)
    try:
        if day:
            row = conn.execute(
                "SELECT * FROM daily_reviews WHERE date=?", (day,)
            ).fetchone()
            if row is None:
                print(f"库中无 {day} 记录，请先 ingest。", file=sys.stderr)
                return 1
            # 单日：直接算 target，避免全表 plan 再过滤的噪音
            rec = dict(row)
            target = target_row(rec)
            for col in ("health_score", "work_score", "learn_score",
                        "life_score", "system_score"):
                old, new = rec.get(col), target[col]
                if old != new:
                    changes.append((day, col, old, new))
            total = 1
        else:
            total = conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
            changes = plan_dates(conn, dates)

        print("[1/2] recompute-scores")
        print(render(changes, total))
        if apply and changes:
            n = apply_changes(conn, changes)
            print(f"已写入 {n} 处变更。")
        elif changes:
            print("（试算模式，未写入；加 --apply 落地）")
    finally:
        conn.close()

    print("")
    print("[2/2] sync-docs")
    result = sync_dates(
        dates=dates, db_path=db_path, input_dir=input_dir, apply=apply)
    verb = "已同步" if apply else "待同步"
    print(f"涉及 {result['total']} 天｜需要{verb} {len(result['changed'])} 篇 md")
    for d in result["changed"]:
        print(f"    {d}")
    if not apply:
        print("（dry-run；加 --apply 同时落库分 + 回写 md）")
    elif changes or result["changed"]:
        print("finalize ✓ 收口完成")
    else:
        print("finalize ✓ 无需变更")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
