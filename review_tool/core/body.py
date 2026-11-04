"""体征纯规则：BMI / 分档 / 均线 / 周变化 / 距目标 / 外推周数。

零 I/O：禁止 sqlite3 / os / pathlib。全部由 ``weight_kg``（库）+
``height_cm``（config）在渲染时计算 —— BMI **不入源、不进库**（G3）。

BMI 分档按中国成人标准：偏瘦 <18.5 / 正常 <24 / 超重 <28 / 肥胖 ≥28。
"""
from __future__ import annotations

from datetime import datetime


def bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    """BMI 保留 1 位小数；身高或体重为空 / 身高 ≤0 返回 ``None``。"""
    if weight_kg is None or height_cm is None:
        return None
    if height_cm <= 0 or weight_kg <= 0:
        return None
    h_m = height_cm / 100.0
    return round(weight_kg / (h_m * h_m), 1)


def bmi_band(bmi_value: float | None) -> str | None:
    """中国成人 BMI 分档：偏瘦 / 正常 / 超重 / 肥胖。"""
    if bmi_value is None:
        return None
    if bmi_value < 18.5:
        return "偏瘦"
    if bmi_value < 24:
        return "正常"
    if bmi_value < 28:
        return "超重"
    return "肥胖"


def moving_average(
    series: list[float | None], window: int = 7
) -> list[float | None]:
    """滑动均线；窗口内缺失（``None``）日不参与分母。

    返回与 ``series`` 等长的列表：位置 ``i`` 取 ``series[max(0,i-window+1):i+1]``
    中非空值的均值；窗口内全空则该位置为 ``None``。
    """
    if window <= 0:
        raise ValueError(f"window 必须为正整数，收到 {window!r}")
    out: list[float | None] = []
    for i in range(len(series)):
        chunk = series[max(0, i - window + 1): i + 1]
        vals = [v for v in chunk if v is not None]
        out.append(round(sum(vals) / len(vals), 2) if vals else None)
    return out


def weekly_delta(series: list[float | None]) -> float | None:
    """最近 7 个点均值 − 前 7 个点均值；任一侧无有效值则 ``None``。

    ``series`` 按时间升序。两侧各取最多 7 个非空观测（从尾部往前数），
    不足一侧有效观测时返回 ``None``。
    """
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return None
    recent = vals[-7:]
    prior = vals[-14:-7]
    if not recent or not prior:
        return None
    return round(sum(recent) / len(recent) - sum(prior) / len(prior), 2)


def distance_to_target(
    weight: float | None,
    low: float | None,
    high: float | None,
) -> float | None:
    """距目标带：带内返回 0；低于 ``low`` 为负；高于 ``high`` 为正。

    ``low`` / ``high`` 任一未配置（``None``）时返回 ``None``。
    """
    if weight is None or low is None or high is None:
        return None
    if low > high:
        low, high = high, low
    if weight < low:
        return round(weight - low, 2)
    if weight > high:
        return round(weight - high, 2)
    return 0.0


def eta_weeks(
    current: float | None,
    target: float | None,
    weekly_delta_kg: float | None,
) -> float | None:
    """按当前周变化速率外推到达 ``target`` 的周数。

    速率为 0、符号与所需方向不符、或缺参时返回 ``None``。
    """
    if current is None or target is None or weekly_delta_kg is None:
        return None
    if weekly_delta_kg == 0:
        return None
    need = target - current
    if need == 0:
        return 0.0
    # 速率符号须与所需方向一致（同号才是在靠近）
    if need * weekly_delta_kg <= 0:
        return None
    return round(need / weekly_delta_kg, 1)


# 平稳阈值：|周变化| ≤ 此值（kg/周）视为平稳 / 平台期。
# 依据：家用体秤日波动噪声约 ±0.5 kg，两侧各 7 点均值后抖动收敛到 ~0.1–0.2 kg，
# 取 0.15 居中（M23）；如需个性化改此处常量即可（未入 config，避免可配置层膨胀）。
WEIGHT_TREND_THRESHOLD_KG = 0.15


def trend_direction(
    weekly_delta_kg: float | None,
    *,
    threshold_kg: float = WEIGHT_TREND_THRESHOLD_KG,
) -> str | None:
    """周变化 → 趋势方向：``"down"`` / ``"up"`` / ``"flat"``；缺参 ``None``。

    与 ``weekly_delta`` 配套使用：``weekly_delta`` 负责算数，本函数负责定性 ——
    报告层据此出建议（M23 体征建议官）。
    """
    if weekly_delta_kg is None:
        return None
    if weekly_delta_kg < -threshold_kg:
        return "down"
    if weekly_delta_kg > threshold_kg:
        return "up"
    return "flat"


# 单周体重波动阈值（FR-B6 / M41）：7 日历日内 |Δ| ≥ 此值 → 预警。
# doctor / body 报告必须复用本常量与 ``week_weight_spikes``（R1）。
WEEK_SPIKE_KG = 1.5


def week_weight_spikes(
    dated_weights: list[tuple[str, float]],
    *,
    threshold: float = WEEK_SPIKE_KG,
) -> list[dict]:
    """7 日历日窗口内体重 |Δ| ≥ ``threshold`` 的突变列表（升序输入）。

    每个终点只保留最近一次超阈突变。样本 < 2 点 → 空列表（调用方区分「未超阈」
    与「样本不足」：不足时勿硬编）。

    返回项：``{prev, next, delta, span_days, from_kg, to_kg}``。
    """
    spikes: list[dict] = []
    for i, (d2, w2) in enumerate(dated_weights):
        t2 = datetime.strptime(d2, "%Y-%m-%d").date()
        for j in range(i - 1, -1, -1):
            d1, w1 = dated_weights[j]
            t1 = datetime.strptime(d1, "%Y-%m-%d").date()
            span = (t2 - t1).days
            if span > 7:
                break
            if span < 1:
                continue
            delta = round(w2 - w1, 2)
            if abs(delta) >= threshold:
                spikes.append({
                    "prev": d1, "next": d2,
                    "delta": delta, "span_days": span,
                    "from_kg": w1, "to_kg": w2,
                })
                break
    return spikes


def spike_window_context(
    spike: dict,
    day_rows: list[dict],
) -> dict:
    """并联同窗 ``exercise_min`` / ``diet_kcal``（只陈述、不下因果）。

    ``day_rows`` 为含 ``date`` / ``exercise_min`` / ``diet_kcal`` 的日行。
    返回 ``{exercise_n, exercise_sum, diet_n, diet_mean, note}``。
    """
    prev, nxt = spike["prev"], spike["next"]
    ex_vals: list[float] = []
    diet_vals: list[float] = []
    for r in day_rows:
        d = r.get("date")
        if d is None or d < prev or d > nxt:
            continue
        if r.get("exercise_min") is not None:
            ex_vals.append(float(r["exercise_min"]))
        if r.get("diet_kcal") is not None:
            diet_vals.append(float(r["diet_kcal"]))
    note_parts: list[str] = []
    if ex_vals:
        note_parts.append(
            f"同窗运动 {len(ex_vals)} 天合计 {sum(ex_vals):.0f} min"
        )
    else:
        note_parts.append("同窗运动样本不足")
    if diet_vals:
        mean = sum(diet_vals) / len(diet_vals)
        note_parts.append(
            f"同窗饮食 {len(diet_vals)} 天日均 {mean:.0f} kcal"
        )
    else:
        note_parts.append("同窗饮食样本不足")
    return {
        "exercise_n": len(ex_vals),
        "exercise_sum": round(sum(ex_vals), 1) if ex_vals else None,
        "diet_n": len(diet_vals),
        "diet_mean": round(sum(diet_vals) / len(diet_vals), 1) if diet_vals else None,
        "note": "；".join(note_parts),
    }
