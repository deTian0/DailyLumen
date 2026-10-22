"""熔断检测：把「单维度持续异常就熔断」这条规则从文档搬进代码。

背景（v1.4.0）
-------------
这条规则此前**只存在于 README 叙事和 7 月几篇复盘正文里**，代码零实现 ——
2026-07-28 的复盘甚至写着「aggregate 会主动标红」，而那个 aggregate 是语雀
时代的旧流程，从未迁进本工具。结果是：学习维度连续 24 天 <6，系统一声不吭。

低分判定：双条件（v1.38.0 / M32 定版）
-------------------------------------
某天某维度计为「低」，须**同时**满足：

1. **绝对**：当日分 < ``rules['threshold']``（<6，用户原始定义）；
2. **相对**：当日分 < 此前 ``rules['baseline_days']`` 日自身均值 −
   ``rules['relative_drift']``（即显著低于自己近期的正常水平）。

为什么必须加第 2 个条件：79 天实测，标尺 v2 下 **78% 的天数至少一维处于
熔断态**（系统分 61/79 天 <6、历史最高仅 6.5）—— 稳定低位天天亮灯，
等于没有报警。双条件下实测降到 **33%**：「一直低但稳定」不报，
「突然掉下去」才报。基线样本不足 ``min_baseline_days`` 天时不计低
（建库初期不乱报）。

仍保留的两层防护
----------------
1. **长期低位失效降级**：连续超过 ``long_run_days`` 天满足双条件 → 显式提示
   「阈值对该维度已失去分辨力」，且不计入熔断态与退出码（v1.33.2 起）。
2. **相对基线漂移**：近 ``recent_days`` 日均值 vs 更早 ``baseline_days`` 日
   均值，偏离 ≥ ``rules['drift']`` 分才算「真的在变」—— 这是趋势信号，
   与逐日熔断互补。
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


def _series(conn, month: int | None = None) -> list[tuple[str, dict]]:
    """按日期升序返回 [(date, {dim: value}), ...]，系统分缺失时按四维均值补。

    month（形如 202610）给定时只取该月窗口（M27 深评用）；
    此时连续段 / 漂移都在**月内**计算，不跨周回溯。
    """
    sql = (
        "SELECT date, health_score, work_score, learn_score, life_score, system_score "
        "FROM daily_reviews"
    )
    params: tuple = ()
    if month is not None:
        sql += " WHERE date LIKE ?"
        params = (f"{month // 100:04d}-{month % 100:02d}-%",)
    rows = conn.execute(sql + " ORDER BY date", params).fetchall()
    out = []
    for r in rows:
        vals = dict(zip(CHECK_DIMS, r[1:], strict=True))
        if vals["system_score"] is None and all(vals[d] is not None for d in DIMENSIONS):
            vals["system_score"] = round(sum(vals[d] for d in DIMENSIONS) / 4, 2)
        out.append((r[0], vals))
    return out


def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _low_flags(series: list[tuple[str, dict]], dim: str, R: dict
               ) -> list[tuple[str, bool, float | None]]:
    """逐日判定「低」：[(date, is_low, baseline), ...]。

    baseline = 该天**之前** ``baseline_days`` 天内该维度非 None 值的均值；
    样本不足 ``min_baseline_days`` 时为 None（该天不计低）。
    """
    th = R["threshold"]
    out: list[tuple[str, bool, float | None]] = []
    for i, (date, vals) in enumerate(series):
        v = vals.get(dim)
        pool = [x[1].get(dim) for x in series[max(0, i - R["baseline_days"]):i]]
        base = _mean(pool)
        if base is not None and len([p for p in pool if p is not None]) < R["min_baseline_days"]:
            base = None  # 样本不足：基线不可用
        low = v is not None and v < th and base is not None and v < base - R["relative_drift"]
        out.append((date, low, base))
    return out


def _streak_ending_latest(flags: list[tuple[str, bool, float | None]]
                          ) -> tuple[int, str | None]:
    """末尾连续计低的记录数，以及该段起点日期。"""
    run, start = 0, None
    for date, low, _base in reversed(flags):
        if not low:
            break
        run += 1
        start = date
    return run, start


def _longest_streak(flags: list[tuple[str, bool, float | None]]) -> int:
    best = cur = 0
    for _date, low, _base in flags:
        cur = cur + 1 if low else 0
        best = max(best, cur)
    return best


def find_fuses(conn, *, rules: dict | None = None,
               month: int | None = None) -> dict:
    """执行熔断检测，返回结构化结果（不打印，便于测试与复用）。

    month（形如 202610）给定时只在月窗口内计算（M27 深评用）。
    """
    R = {**FUSE_RULES, **(rules or {})}
    th, days = R["threshold"], R["days"]
    series = _series(conn, month=month)
    result: dict = {
        "as_of": series[-1][0] if series else None,
        "records": len(series),
        "threshold": th,
        "days": days,
        "relative_drift": R["relative_drift"],
        "min_baseline_days": R["min_baseline_days"],
        "baseline_days": R["baseline_days"],
        "absolute": [],
        "quiet": [],
        "drift": [],
    }
    if not series:
        return result

    for dim in CHECK_DIMS:
        flags = _low_flags(series, dim, R)
        run, since = _streak_ending_latest(flags)
        longest = _longest_streak(flags)
        last_base = flags[-1][2] if flags else None
        item = {
            "dim": dim,
            "label": DIM_CN[dim],
            "run": run,
            "since": since,
            "longest": longest,
            "fused": run >= days,
            "long_run": run >= R["long_run_days"],
            "low_today": flags[-1][1] if flags else False,
            "baseline": last_base,
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
    L.append(f"  规则：任一维度连续 ≥{results['days']} 天 < {results['threshold']} 分"
             f"且低于自身 {results['baseline_days']} 日基线 ≥{results['relative_drift']} 分 → 熔断")

    L.append("")
    L.append("[绝对信号]")
    if results["absolute"]:
        for it in results["absolute"]:
            if it["long_run"]:
                # 长期低位：本身已声明「阈值失效」，不再用熔断符号与倍数渲染
                L.append(f"  ⚠️ {it['label']}：连续 {it['run']} 天显著低于基线"
                         f"（自 {it['since']} 起）· 长期低位，阈值已失效")
            else:
                base = f"，基线 {it['baseline']}" if it["baseline"] is not None else ""
                L.append(f"  🔴 {it['label']}：连续 {it['run']} 天 < {results['threshold']}"
                         f"且低于基线（自 {it['since']} 起{base}）"
                         f"｜超阈值 {it['run'] / results['days']:.1f} 倍")
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
        L.append(f"  以下维度连续超过 {R['long_run_days']} 天显著低于基线，"
                 "绝对阈值对它已失去分辨力：")
        for it in long_runs:
            L.append(f"  ·  {it['label']}（连续 {it['run']} 天）—— 请改用下面的相对基线判断")
        L.append("     （连续低位在这条分布上近乎恒真，刷同一条告警没有信息量）")

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
    active = [it for it in results["absolute"] if not it["long_run"]]
    stale = [it for it in results["absolute"] if it["long_run"]]
    if active:
        names = "、".join(it["label"] for it in active)
        L.append(f"结论: ⚠️ {len(active)} 个维度处于熔断态（{names}）")
        if stale:
            names = "、".join(it["label"] for it in stale)
            L.append(f"      另 {len(stale)} 个维度长期低位（{names}）：绝对阈值已失效，看相对基线")
    elif stale:
        names = "、".join(it["label"] for it in stale)
        L.append(f"结论: △ 无新增熔断；{names}长期低位（绝对阈值已失效）→ 以相对基线为准")
    else:
        L.append("结论: ✓ 无维度触发熔断")
    return "\n".join(L)


def has_active_fuse(results: dict) -> bool:
    """是否有**未失效**的熔断（长期低位不算：阈值对它已失去分辨力）。"""
    return any(not it["long_run"] for it in results["absolute"])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    db = argv[0] if argv and not argv[0].startswith("-") else None
    conn = init_db(db)
    try:
        results = find_fuses(conn)
    finally:
        conn.close()
    print(render(results))
    return 1 if has_active_fuse(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
