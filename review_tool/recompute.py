"""按当前规则把库里的四维分 / 系统分从字段重算（「库为准」的唯一权威实现）。

    python -m review_tool recompute-scores            # 试算，只打印差异
    python -m review_tool recompute-scores --apply    # 写入数据库

口径（与 v1.4.0 历史迁移一致，见 README「分数的单一权威」）：

- 每个维度一律取「按当前规则从字段重算」的结果；字段不足以评分时为 NULL
  （**不保留**旧的手填值 —— 全库只认最新一套规则，保证格式统一）。
- 系统分 = 四维齐全时的均值（保留 2 位），任一维度缺失则为 NULL。
- 依赖字段缺失而被置空的维度会单独列出，便于确认「置空」是预期行为。

这个子命令取代了早期散落在 .workbuddy/backup/ 里的一次性迁移脚本，让
「重算」成为可重复、可审查的一等操作（`doctor` 的 [分数一致性] 段会提示用它）。
"""
from __future__ import annotations

import argparse
from datetime import datetime

from .db import init_db
from .score import (
    compute_health_score,
    compute_learn_score,
    compute_life_score,
    compute_work_score,
    system_score_from,
)

# 维度列 -> 展示名 -> 重算函数（与 doctor._DIM_COMPUTERS 同源）
_COMPUTERS = [
    ("health_score", "健康", compute_health_score),
    ("work_score", "工作", compute_work_score),
    ("learn_score", "学习", compute_learn_score),
    ("life_score", "生活", compute_life_score),
]
_ALL_COLS = [c for c, _l, _f in _COMPUTERS] + ["system_score"]


def target_row(row: dict) -> dict:
    """按当前规则算出该行应有的四维 + 系统分。"""
    out: dict = {col: fn(row) for col, _label, fn in _COMPUTERS}
    out["system_score"] = system_score_from(out)
    return out


def plan(conn) -> list[tuple[str, str, object, object]]:
    """返回需变更的 (date, col, old, new) 列表（不改库）。"""
    changes: list[tuple[str, str, object, object]] = []
    for row in conn.execute("SELECT * FROM daily_reviews ORDER BY date"):
        rec = dict(row)
        target = target_row(rec)
        for col in _ALL_COLS:
            old, new = rec.get(col), target[col]
            if old != new:
                changes.append((rec["date"], col, old, new))
    return changes


def apply_changes(conn, changes: list[tuple[str, str, object, object]]) -> int:
    """把变更写入数据库（单事务）。返回写入条数。"""
    if not changes:
        return 0
    stamp = datetime.now().isoformat(timespec="seconds")
    try:
        conn.execute("BEGIN")
        for date, col, _old, new in changes:
            conn.execute(
                f"UPDATE daily_reviews SET {col}=?, ingested_at=? WHERE date=?",
                (new, stamp, date),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(changes)


_LABEL = {c: lbl for c, lbl, _f in _COMPUTERS}
_LABEL["system_score"] = "系统"


def render(changes: list[tuple[str, str, object, object]], total: int) -> str:
    """渲染差异报告。"""
    L: list[str] = []
    if not changes:
        return f"库中 {total} 天记录，四维 / 系统分与字段重算完全一致，无需变更。"
    by_date: dict[str, list[str]] = {}
    nulled = 0
    for date, col, old, new in changes:
        if new is None and old is not None:
            nulled += 1
        by_date.setdefault(date, []).append(
            f"{_LABEL[col]} {old} → {new}"
        )
    L.append(f"需变更 {len(changes)} 处，涉及 {len(by_date)} 天：")
    for date in sorted(by_date):
        L.append(f"  {date}: " + "；".join(by_date[date]))
    if nulled:
        L.append(f"  其中 {nulled} 处因字段不足被置空（无字段支撑的手填分）")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m review_tool recompute-scores",
        description="按当前规则重算库中四维分 / 系统分（默认只试算）",
    )
    parser.add_argument("--apply", action="store_true", help="写入数据库（默认只打印差异）")
    parser.add_argument("--db", help="指定数据库文件（默认 config.DB_PATH，测试用）")
    args = parser.parse_args(argv)

    conn = init_db(db_path=args.db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
        changes = plan(conn)
        print(render(changes, total))
        if args.apply and changes:
            n = apply_changes(conn, changes)
            print(f"已写入 {n} 处变更。")
        elif changes:
            print("（试算模式，未写入；加 --apply 落地）")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
