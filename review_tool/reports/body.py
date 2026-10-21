"""体征趋势报告：最新值 + BMI + 7 日均 + 周变化 + 距目标。

用法:
    python -m review_tool body
    python -m review_tool body --json

BMI / 均线等派生值在此渲染时计算，不入源、不进库（G3）。
身高 / 目标未配置时输出「未配置」文案，不报错（M9 决策点）。
"""
from __future__ import annotations

import json
import sys

from ..config import BODY_TARGETS, PROFILE
from ..core.body import (
    bmi,
    bmi_band,
    distance_to_target,
    eta_weeks,
    moving_average,
    trend_direction,
    weekly_delta,
)
from ..storage.db import init_db, load_body_metrics

# 出趋势所需的最小非空体重观测数。
# 口径跟随 ``core.body.weekly_delta``：「近 7 个观测 vs 前 7 个观测」，
# 故至少 7 + 1 = 8 个点才有两侧均值。注意它**不等于「两周」** ——
# 一周称 2 次时两周只有 4 个点，按天算会高估达标速度。
_BODY_TREND_MIN_OBS = 8


def collect(conn) -> dict:
    """从库汇总体征报告数据（结构化，供文本 / JSON 共用）。"""
    rows = load_body_metrics(conn)
    height = PROFILE.get("height_cm")
    low = BODY_TARGETS.get("weight_kg_low")
    high = BODY_TARGETS.get("weight_kg_high")

    weights: list[float | None] = []
    series: list[dict] = []
    for r in rows:
        w = r["weight_kg"]
        weights.append(w)
        series.append({
            "date": r["date"],
            "weight_kg": w,
            "body_fat_pct": r["body_fat_pct"],
            "waist_cm": r["waist_cm"],
            "src": r["src"],
            "note": r["note"],
        })

    ma = moving_average(weights, window=7)
    delta = weekly_delta(weights)
    latest = series[-1] if series else None
    latest_bmi = bmi(latest["weight_kg"], height) if latest else None
    latest_band = bmi_band(latest_bmi)
    dist = (
        distance_to_target(latest["weight_kg"], low, high) if latest else None
    )
    # 外推：有目标带时取较近端（或当前在带外时的那一端）
    target_for_eta = None
    if latest and latest["weight_kg"] is not None and low is not None and high is not None:
        w = latest["weight_kg"]
        if w < low:
            target_for_eta = low
        elif w > high:
            target_for_eta = high
        else:
            target_for_eta = (low + high) / 2.0
    eta = eta_weeks(
        latest["weight_kg"] if latest else None,
        target_for_eta,
        delta,
    )

    return {
        "count": len(series),
        "height_cm": height,
        "targets": {"weight_kg_low": low, "weight_kg_high": high},
        "latest": latest,
        "bmi": latest_bmi,
        "bmi_band": latest_band,
        "ma7": ma[-1] if ma else None,
        "weekly_delta": delta,
        "trend_direction": trend_direction(delta),
        "distance_to_target": dist,
        "eta_weeks": eta,
        "series": series,
    }


def advice_lines(data: dict) -> list[str]:
    """确定性建议段（M23）：每条带依据数字，可复算；不下医学结论。

    返回行文本列表；空列表表示「无体重数据可建议」（渲染层给占位说明）。
    决策仅用 ``weekly_delta`` / ``trend_direction`` / ``distance_to_target`` /
    ``eta_weeks`` 四个既有派生值 —— 不引入新口径。
    """
    out: list[str] = []
    if data["count"] == 0 or data["latest"]["weight_kg"] is None:
        return out
    delta = data["weekly_delta"]
    trend = data["trend_direction"]
    dist = data["distance_to_target"]
    low = data["targets"]["weight_kg_low"]
    high = data["targets"]["weight_kg_high"]
    eta = data["eta_weeks"]

    if trend is None or delta is None:
        # 样本不足以定性趋势；带外位置仍值得提醒一句。
        # 门槛口径：weekly_delta 取「近 7 个观测 vs 前 7 个观测」，故需 ≥8 个
        # 非空体重观测 —— 不是「两周」：一周称 2 次时两周只有 4 个点。
        if dist:
            side = "低于下限" if dist < 0 else "高于上限"
            obs = len(
                [r for r in data["series"] if r.get("weight_kg") is not None]
            )
            need = max(0, _BODY_TREND_MIN_OBS - obs)
            gap = f"，还差 {need} 次" if need else ""
            out.append(
                f"当前{side} {abs(dist):.2f} kg —— 趋势要「近 7 点 vs 前 7 点」"
                f"共 {_BODY_TREND_MIN_OBS} 个观测（现有 {obs} 次{gap}），"
                "凑够后才出趋势与外推"
            )
        return out

    label = {"down": "下行", "up": "上行", "flat": "平稳（平台期）"}[trend]
    base = f"趋势{label}：周变化 {delta:+.2f} kg（近 7 点均 vs 前 7 点均）"

    if dist is None:
        out.append(f"{base}；未配置目标带（config.BODY_TARGETS），仅提示趋势")
        return out
    band = f"{low}–{high} kg"
    if dist == 0:
        if trend == "down":
            out.append(f"{base}；已在目标带内（{band}），持续下行会跌破下限 "
                       f"{low} kg，留意")
        elif trend == "up":
            out.append(f"{base}；已在目标带内（{band}），持续上行会突破上限 "
                       f"{high} kg，留意")
        else:
            out.append(f"{base}；已在目标带内（{band}），保持当前节奏即可")
    elif dist > 0:
        if trend == "down" and eta is not None:
            out.append(f"{base}；高于上限 {abs(dist):.2f} kg，按当前速率约 "
                       f"{eta} 周回到目标带（{high} kg）")
        elif trend == "down":
            out.append(f"{base}；高于上限 {abs(dist):.2f} kg，速率尚不足以按周外推，"
                       "继续观察")
        else:
            out.append(f"{base}；高于上限 {abs(dist):.2f} kg —— 先让趋势转向下行，"
                       "再谈外推")
    else:  # dist < 0
        if trend == "up" and eta is not None:
            out.append(f"{base}；低于下限 {abs(dist):.2f} kg，按当前速率约 "
                       f"{eta} 周回到目标带（{low} kg）")
        elif trend == "up":
            out.append(f"{base}；低于下限 {abs(dist):.2f} kg，速率尚不足以按周外推，"
                       "继续观察")
        else:
            out.append(f"{base}；低于下限 {abs(dist):.2f} kg —— 先让趋势转向上行，"
                       "再谈外推")
    return out


def render(data: dict) -> str:
    """人类可读文本。"""
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 体征报告")
    L.append("=" * 52)

    if data["count"] == 0:
        L.append("")
        L.append("  （尚无体征记录；在数据块填 体重_kg / 体脂率 / 腰围_cm 后 ingest）")
        return "\n".join(L)

    latest = data["latest"]
    L.append("")
    L.append(f"[最新] {latest['date']}")
    L.append(f"  体重     : {_fmt(latest['weight_kg'], 'kg')}")
    L.append(f"  体脂率   : {_fmt(latest['body_fat_pct'], '%')}")
    L.append(f"  腰围     : {_fmt(latest['waist_cm'], 'cm')}")
    if latest.get("src"):
        L.append(f"  来源     : {latest['src']}")

    L.append("")
    L.append("[BMI]")
    if data["height_cm"] is None:
        L.append("  未配置身高（config.PROFILE[\"height_cm\"]）")
    elif data["bmi"] is None:
        L.append("  （最新体重为空，无法计算）")
    else:
        band = data["bmi_band"] or "?"
        L.append(f"  {data['bmi']}（{band}）· 身高 {data['height_cm']} cm")

    L.append("")
    L.append("[趋势]")
    L.append(f"  7 日均线 : {_fmt(data['ma7'], 'kg')}")
    L.append(f"  周变化   : {_fmt_delta(data['weekly_delta'], 'kg')}")

    L.append("")
    L.append("[目标]")
    low = data["targets"]["weight_kg_low"]
    high = data["targets"]["weight_kg_high"]
    if low is None or high is None:
        L.append("  未配置目标带（config.BODY_TARGETS）")
    else:
        L.append(f"  目标带   : {low}–{high} kg")
        dist = data["distance_to_target"]
        if dist is None:
            L.append("  距目标   : （无体重）")
        elif dist == 0:
            L.append("  距目标   : 已在目标带内")
        else:
            side = "低于下限" if dist < 0 else "高于上限"
            L.append(f"  距目标   : {dist:+.2f} kg（{side}）")
        eta = data["eta_weeks"]
        if eta is None:
            L.append("  外推     : 速率不足或方向不符")
        else:
            L.append(f"  外推     : 约 {eta} 周")

    L.append("")
    L.append("[建议]")
    lines = advice_lines(data)
    if lines:
        L.extend(f"  - {x}" for x in lines)
    else:
        L.append("  （暂无：缺体重数据，无可建议项）")

    L.append("")
    L.append(f"共 {data['count']} 条体征记录")
    return "\n".join(L)


def _fmt(val, unit: str) -> str:
    if val is None:
        return "—"
    return f"{val} {unit}"


def _fmt_delta(val, unit: str) -> str:
    if val is None:
        return "—（样本不足）"
    return f"{val:+.2f} {unit}"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
