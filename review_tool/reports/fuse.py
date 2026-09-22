"""熔断检测：把「单维度 <6 连续 3 天就熔断」这条规则从文档搬进代码。

背景（v1.4.0）
-------------
这条规则此前**只存在于 README 叙事和 7 月几篇复盘正文里**，代码零实现 ——
2026-07-28 的复盘甚至写着「aggregate 会主动标红」，而那个 aggregate 是语雀
时代的旧流程，从未迁进本工具。结果是：学习维度连续 24 天 <6，系统一声不吭。

两个信号
--------
1. **绝对熔断**：任一维度连续 ``rules['days']`` 天低于 ``rules['threshold']``。
   这是用户原始定义的规则（<6 连续 3 天）。
2. **相对基线**：近 ``recent_days`` 日均值 vs 更早 ``baseline_days`` 日均值，
   偏离达到 ``rules['drift']`` 分才算「真的在变」。

为什么必须有第 2 个信号：49 天样本里学习分 **82% 的天数 <6、60% 正好落在
最低档**，绝对阈值在这条分布上近乎恒真 —— 连续 24 天触发等于没有信息量。
**长期低位提示**（连续超过 ``long_run_days``）会显式告诉你「这条阈值对该
维度已经失去分辨力」，而不是继续刷同一条告警。
"""
from __future__ import annotations

import sys

from ..config import DIMENSIONS, FUSE_RULES
from ..storage.db import init_db

# 维度 -> 中文名（报告用）
DIM_CN = {
    "health_score": "健康",
    "work_score": "工作",
    "learn_score": "学习",
    "life_score": "生活",
    "system_score": "系统",
}
# 检测顺序：四维 + 系统分
CHECK_DIMS = DIMENSIONS + ["system_score"]


def _series(conn) -> list[tuple[str, dict]]:
    """按日期升序返回 [(date, {dim: value}), ...]，系统分缺失时按四维均值补。"""
    rows = conn.execute(
        "SELECT date, health_score, work_score, learn_score, life_score, system_score "
        "FROM daily_reviews ORDER BY date"
    ).fetchall()
    out = []
    for r in rows:
        vals = dict(zip(CHECK_DIMS, r[1:], strict=True))
        if vals["system_score"] is None and all(vals[d] is not None for d in DIMENSIONS):
            vals["system_score"] = round(sum(vals[d] for d in DIMENSIONS) / 4, 2)
        out.append((r[0], vals))
    return out


def _streak_ending_latest(series: list[tuple[str, dict]], dim: str, th: float) -> tuple[int, str | None]:
    """末尾连续低于阈值的记录数，以及该段起点日期。"""
    run, start = 0, None
    for date, vals in reversed(series):
        v = vals.get(dim)
        if v is None or v >= th:
            break
        run += 1
        start = date
    return run, start


def _longest_streak(series: list[tuple[str, dict]], dim: str, th: float) -> int:
    best = cur = 0
    for _date, vals in series:
        v = vals.get(dim)
        if v is not None and v < th:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def find_fuses(conn, *, rules: dict | None = None) -> dict:
    """执行熔断检测，返回结构化结果（不打印，便于测试与复用）。"""
    R = {**FUSE_RULES, **(rules or {})}
    th, days = R["threshold"], R["days"]
    series = _series(conn)
    result: dict = {
        "as_of": series[-1][0] if series else None,
        "records": len(series),
        "threshold": th,
        "days": days,
        "absolute": [],
        "quiet": [],
        "drift": [],
    }
    if not series:
        return result

    for dim in CHECK_DIMS:
        run, since = _streak_ending_latest(series, dim, th)
        longest = _longest_streak(series, dim, th)
        item = {
            "dim": dim,
            "label": DIM_CN[dim],
            "run": run,
            "since": since,
            "longest": longest,
            "fused": run >= days,
            "long_run": run >= R["long_run_days"],
        }
        (result["absolute"] if item["fused"] else result["quiet"]).append(item)

        recent = [v[dim] for _d, v in series[-R["recent_days"]:]]
        base_pool = series[-(R["recent_days"] + R["baseline_days"]):-R["recent_days"]]
        baseline = [v[dim] for _d, v in base_pool]
        rv, bv = _mean(recent), _mean(baseline)
        if rv is not None and bv is not None:
            delta = round(rv - bv, 2)
            result["drift"].append({
                "dim": dim, "label": DIM_CN[dim],
                "recent": rv, "baseline": bv, "delta": delta,
                "moved": abs(delta) >= R["drift"],
                "n_baseline": len([v for v in baseline if v is not None]),
            })
    return result


def render(results: dict) -> str:
    """把检测结果渲染成可读文本。"""
    R = FUSE_RULES
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 熔断检测")
    L.append("=" * 52)
    L.append(f"  样本 {results['records']} 天｜截至 {results['as_of']}")
    L.append(f"  规则：任一维度连续 ≥{results['days']} 天 < {results['threshold']} 分 → 熔断")

    L.append("")
    L.append("[绝对信号 · 已触发]")
    if results["absolute"]:
        for it in results["absolute"]:
            flag = "🔴" if not it["long_run"] else "⚠️"
            L.append(f"  {flag} {it['label']}：连续 {it['run']} 天 < {results['threshold']}"
                     f"（自 {it['since']} 起）｜超阈值 {it['run'] / results['days']:.1f} 倍")
    else:
        L.append("  ✓ 无维度触发")

    L.append("")
    L.append("[绝对信号 · 未触发]")
    if results["quiet"]:
        for it in results["quiet"]:
            L.append(f"  ·  {it['label']}：当前连续 {it['run']} 天｜历史最长 {it['longest']} 天")
    else:
        L.append("  （无）")

    long_runs = [it for it in results["absolute"] if it["long_run"]]
    if long_runs:
        L.append("")
        L.append("[阈值失效提示]")
        L.append(f"  以下维度连续超过 {R['long_run_days']} 天 < {results['threshold']}，"
                 "绝对阈值对它已失去分辨力：")
        for it in long_runs:
            L.append(f"  ·  {it['label']}（连续 {it['run']} 天）—— 请改用下面的相对基线判断")
        L.append("     （连续 N 天 <6 在这条分布上近乎恒真，刷同一条告警没有信息量）")

    L.append("")
    L.append(f"[相对基线] 近 {R['recent_days']} 日均值 vs 之前 {R['baseline_days']} 日均值")
    if results["drift"]:
        for d in sorted(results["drift"], key=lambda x: x["delta"]):
            arrow = "▲" if d["delta"] > 0 else ("▼" if d["delta"] < 0 else "－")
            mark = "  ← 变化明显" if d["moved"] else ""
            L.append(f"  {d['label']}  {d['baseline']} → {d['recent']}  "
                     f"{arrow} {d['delta']:+.2f}{mark}")
    else:
        L.append("  （样本不足，需先积累更多天数）")

    L.append("")
    L.append("-" * 52)
    if results["absolute"]:
        names = "、".join(it["label"] for it in results["absolute"])
        L.append(f"结论: ⚠️ {len(results['absolute'])} 个维度处于熔断态（{names}）")
    else:
        L.append("结论: ✓ 无维度触发熔断")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    db = argv[0] if argv and not argv[0].startswith("-") else None
    conn = init_db(db)
    try:
        results = find_fuses(conn)
    finally:
        conn.close()
    print(render(results))
    return 1 if results["absolute"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
