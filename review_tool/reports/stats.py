"""stats —— 一键统计：文档常引用的「随时间增长的数值」（M22 / v1.30.0）。

背景：2026-10-20 全套文档对账发现，过时值清一色是手抄的统计值（复盘篇数 /
入库天数 / 打卡行数 / 库大小），迁移指南一度停在 v1.4.x 时代的数字上。
本命令是文档取数的**单一出口**：只读库 + 数 md 文件，不写任何东西。

口径与 ``doctor`` 一致（不另写一套）：

- md 计数：``每日复盘/复盘/`` 递归 ``.md``，跳过 ``收件箱`` / ``历史源复盘``
  （同 doctor 对账的目录口径）；「日复盘篇数」只认文件名主干恰为 ``YYYY-MM-DD``
  的文件（周 / 月汇总自然排除，复用 ``doctor._date_from_filename``）。
- 历史断更：复用 ``doctor.history_gaps``。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date

from ..config import DB_PATH, DIMENSIONS, INPUT_DIR
from ..core.score import balance_spread, weakest_dimension
from ..storage.db import SCHEMA_VERSION, init_db
from .doctor import _date_from_filename, history_gaps

# 跳过的目录名（相对 input_dir 的任一层级命中即跳过），与 doctor 对账口径一致
_SKIP_DIRS = ("收件箱", "历史源复盘")

# 四维 + 系统分的展示标签（顺序即展示顺序）
_DIM_LABELS = {
    "health_score": "健康", "work_score": "工作", "learn_score": "学习",
    "life_score": "生活", "system_score": "系统",
}


def _dimension_stats(rows: list[dict]) -> dict:
    """四维 / 系统分分布概览 + 短板维度分布 + 均衡度（v1.34.0）。

    为什么需要这一段：标尺 v2 起系统分**不再承担绝对及格判断**（上限只有 6.5
    左右），「今天哪里拖后腿」改由「短板维度」和「均衡度」回答。核心实现见
    ``core.score.weakest_dimension`` / ``balance_spread``。
    """

    def _one(field: str) -> dict | None:
        vals = sorted(r[field] for r in rows if r.get(field) is not None)
        if not vals:
            return None
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        return {"n": n, "avg": round(sum(vals) / n, 2), "median": median,
                "min": vals[0], "max": vals[-1], "levels": len(set(vals))}

    full = [r for r in rows if all(r.get(d) is not None for d in DIMENSIONS)]
    weak: dict[str, int] = {}
    spreads: list[int] = []
    for r in full:
        got = weakest_dimension(r)
        if got:
            weak[got[0]] = weak.get(got[0], 0) + 1
        sp = balance_spread(r)
        if sp is not None:
            spreads.append(sp)
    return {
        "dims": {f: _one(f) for f in _DIM_LABELS},
        "full_days": len(full),
        "weak": weak,
        "spread_avg": round(sum(spreads) / len(spreads), 2) if spreads else None,
    }


def _count_md(input_dir: str) -> dict:
    """递归统计 md：总数 / 日复盘数 / 按月分组（月 = 所在子目录名）。"""
    total = 0
    daily = 0
    by_month: dict[str, int] = {}
    for root, _dirs, files in os.walk(input_dir):
        rel = os.path.relpath(root, input_dir)
        if any(p in _SKIP_DIRS for p in rel.split(os.sep)):
            continue
        for f in files:
            if not f.endswith(".md"):
                continue
            total += 1
            month = os.path.basename(root) if rel != "." else ""
            if month:
                by_month[month] = by_month.get(month, 0) + 1
            if _date_from_filename(f):
                daily += 1
    return {"total": total, "daily": daily, "by_month": dict(sorted(by_month.items()))}


def _count_table(conn, table: str) -> int:
    """表行数；表不存在（异常环境）按 0 计，不让统计命令炸在半路。"""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def collect(conn, input_dir: str, *, db_path: str | None = None) -> dict:
    """收集统计结果（不打印），便于测试与复用。

    :param conn: 已初始化的 SQLite 连接（``init_db`` 产物）
    :param input_dir: 复盘文档根目录（``每日复盘/``）
    :param db_path: 库文件路径（仅用于取文件大小；省略用 ``config.DB_PATH``）
    """
    path = db_path or DB_PATH
    db_dates = [r[0] for r in conn.execute("SELECT date FROM daily_reviews")]
    gaps = history_gaps(db_dates)
    score_rows = [dict(r) for r in conn.execute(
        "SELECT health_score, work_score, learn_score, life_score, system_score "
        "FROM daily_reviews ORDER BY date")]

    result: dict = {
        "generated_at": date.today().isoformat(),
        "md": _count_md(input_dir),
        "schema_version": conn.execute("PRAGMA user_version").fetchone()[0],
        "schema_expected": SCHEMA_VERSION,
        "days": _count_table(conn, "daily_reviews"),
        "tracks": _count_table(conn, "personal_tracks"),
        "habit_logs": _count_table(conn, "habit_logs"),
        "body_metrics": _count_table(conn, "body_metrics"),
        "training_sessions": _count_table(conn, "training_sessions"),
        "training_items": _count_table(conn, "training_items"),
        "latest_date": max(db_dates) if db_dates else None,
        "db_size_kb": round(os.path.getsize(path) / 1024) if os.path.exists(path) else 0,
        "history_gaps": gaps,
        "history_gap_days": sum(g["missing"] for g in gaps),
        "scores": _dimension_stats(score_rows),
    }
    return result


def render(result: dict) -> str:
    """渲染成人读文本（对齐 doctor 的分区风格）。"""
    md = result["md"]
    L: list[str] = []
    L.append("[复盘文档]")
    L.append(f"  md 总数      : {md['total']}（其中日复盘 {md['daily']} 篇）")
    if md["by_month"]:
        parts = [f"{m} {n} 篇" for m, n in md["by_month"].items()]
        L.append(f"  按月         : {' | '.join(parts)}")
    L.append("")
    L.append("[数据库]")
    flag = "" if result["schema_version"] == result["schema_expected"] else \
        f"（⚠️ 期望 v{result['schema_expected']}）"
    L.append(f"  schema       : v{result['schema_version']}{flag}")
    L.append(f"  入库天数     : {result['days']}（最新 {result['latest_date'] or '—'}）")
    L.append(f"  打卡行       : {result['tracks']}")
    L.append(f"  habit_logs   : {result['habit_logs']}")
    L.append(f"  体征记录     : {result['body_metrics']}")
    L.append(f"  训练         : {result['training_sessions']} 课 / "
             f"{result['training_items']} 动作项")
    L.append(f"  库大小       : {result['db_size_kb']} KB")
    L.append("")
    L.append("[历史断更]（复用 doctor 口径）")
    gaps = result["history_gaps"]
    if gaps:
        L.append(f"  共 {len(gaps)} 处断更 / 共缺 {result['history_gap_days']} 天:")
        for g in gaps:
            L.append(f"    - {g['prev']} → {g['next']}（缺 {g['missing']} 天）")
    else:
        L.append("  相邻入库日连续，无历史空洞")

    sc = result.get("scores") or {}
    L.append("")
    L.append("[四维概览]（标尺 v2；系统分只做趋势，及格看单维）")
    for field, label in _DIM_LABELS.items():
        s = (sc.get("dims") or {}).get(field)
        if not s:
            continue
        L.append(f"  {label}   均 {s['avg']:.2f}｜中位 {s['median']:g}｜"
                 f"值域 {s['min']:g}–{s['max']:g}｜{s['levels']} 个不同值（n={s['n']}）")
    if sc.get("full_days"):
        order = sorted(sc["weak"].items(), key=lambda kv: -kv[1])
        parts = [f"{_DIM_LABELS[k]} {v / sc['full_days'] * 100:.0f}%" for k, v in order]
        L.append(f"  短板   {' | '.join(parts)}（{sc['full_days']} 个四维齐全日）")
    if sc.get("spread_avg") is not None:
        L.append(f"  均衡度 四维极差均值 {sc['spread_avg']:.2f}"
                 "（0=完全均衡，9=一维满格另一维耗尽）")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stats", description="一键统计（文档取数用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供脚本解析）")
    args = parser.parse_args(argv)
    conn = init_db()
    try:
        result = collect(conn, INPUT_DIR)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
