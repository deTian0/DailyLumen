"""体征纯规则：BMI / 分档 / 均线 / 周变化 / 距目标 / 外推周数。

零 I/O：禁止 sqlite3 / os / pathlib。全部由 ``weight_kg``（库）+
``height_cm``（config）在渲染时计算 —— BMI **不入源、不进库**（G3）。

BMI 分档按中国成人标准：偏瘦 <18.5 / 正常 <24 / 超重 <28 / 肥胖 ≥28。
"""
from __future__ import annotations


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
