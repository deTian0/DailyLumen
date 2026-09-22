"""根据结构化数据动态生成四维评分 (健康/工作/学习/生活)。

原则:
- 健康分: 完全基于客观健康子指标，规则可解释 (compute_health_score)
- 工作分: 基于 深度工作_h (deepwork_h)
- 学习分: 基于 学习投入_h (learn_h)
- 生活分: 基于 生活投入_h (life_h)
- 任一维度数据缺失 -> 该维留 None (不瞎编)，系统分四维齐全才计算
- 所有阈值/权重来自 config.SCORE_THRESHOLDS（可配置，默认=用户偏好）
- 服药/护肤等个人定制项不计入通用评分（统计于 personal_tracks 表）
"""
from __future__ import annotations

from ..config import DIMENSIONS, SCORE_THRESHOLDS


def _clamp(v, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, int(round(v))))


def system_score_from(row: dict) -> float | None:
    """根据四维评分算系统分；任一缺失返回 None。"""
    vals = [row.get(d) for d in DIMENSIONS]
    if all(v is not None for v in vals):
        return round(sum(vals) / len(vals), 2)
    return None


def _band(value, thresholds: dict) -> int | None:
    """时长型指标的分档评分（工作 / 学习 / 生活三者共用）。

    **达标区**（``>= ok`` 线）保持三档步进：ok -> 5、good -> 7、full -> 9。
    **未达标区**（``< ok`` 线）按 ``value/ok`` 等分成 n 档（n = sub_ceil - sub_floor + 1，
    默认 1/2/3/4 四档）：``0 -> sub_floor``，其余落在 ``(k/n, (k+1)/n]`` 区间取
    ``sub_floor + k``。用整数分档而非线性取整，避免 ``round()`` 的银行家舍入
    让 ``2.5 -> 2``（那会让「刚好半程」反而拿不到对应档位）。

    为什么要细分未达标区（v1.4.0）：历史数据显示绝大多数记录落在未达标区
    （学习分 60% 集中在最低档），原先「一律 3 分」会让 0h 与 1.5h 投入无法
    区分 —— 49 天的趋势被压成一条直线，改善不可见，熔断信号也被地板吞掉。
    细分只作用于未达标区，``>= ok`` 的分值语义（5/7/9 = 踩线分）完全不变。
    """
    if value is None:
        return None
    if value >= thresholds["full"]:
        return 9
    if value >= thresholds["good"]:
        return 7
    if value >= thresholds["ok"]:
        return 5
    floor = int(thresholds.get("sub_floor", 1))
    ceil = int(thresholds.get("sub_ceil", 4))
    if value <= 0 or ceil <= floor:
        return floor
    n = ceil - floor + 1
    idx = int(value / thresholds["ok"] * n)
    return floor + max(0, min(n - 1, idx))


def compute_health_score(row: dict) -> int | None:
    """基于健康子指标规则化生成 1-10 的健康分。数据不足返回 None。"""
    T = SCORE_THRESHOLDS
    w = T["weights"]
    parts: list[tuple[int, float]] = []  # (score_0_10, weight)

    # 睡眠时长
    sh = row.get("sleep_h")
    if sh is not None:
        if sh >= T["sleep"]["full"]:
            s = 10
        elif sh >= T["sleep"]["good"]:
            s = 8
        elif sh >= T["sleep"]["ok"]:
            s = 6
        elif sh >= T["sleep"]["low"]:
            s = 4
        else:
            s = 2
        parts.append((s, w["sleep_h"]))

    # 睡眠质量 (0-100 -> 0-10)
    q = row.get("sleep_quality")
    if q is not None:
        parts.append((_clamp(q / 10), w["sleep_quality"]))

    # 入睡时间（距 00:00 的分钟数）
    # 语义：00:00-06:00 熬夜/通宵后；<=22:30 早；22:30-23:30 尚可；>23:30 晚睡
    bt = row.get("bedtime")
    if bt is not None:
        if bt <= T["bedtime"]["late_night_max"]:
            s = 3           # 00:00-06:00 熬夜
        elif bt <= T["bedtime"]["early_max"]:
            s = 10          # <=22:30
        elif bt <= T["bedtime"]["ok_max"]:
            s = 8           # 22:30-23:30
        else:
            s = 5           # >23:30 晚睡
        parts.append((s, w["bedtime"]))

    # 运动 (训练日更严格)
    em = row.get("exercise_min")
    if em is not None:
        if row.get("training_day") == 1:
            s = 10 if em >= T["exercise"]["train_full"] else (6 if em >= T["exercise"]["train_ok"] else 2)
        else:
            s = 8 if em >= T["exercise"]["normal_full"] else 6
        parts.append((s, w["exercise"]))

    # 饮食热量
    dk = row.get("diet_kcal")
    if dk is not None:
        if T["diet"]["good_low"] <= dk <= T["diet"]["good_high"]:
            s = 8
        elif (T["diet"]["ok_low"] <= dk < T["diet"]["good_low"]) or (T["diet"]["good_high"] < dk <= T["diet"]["ok_high"]):
            s = 5
        else:
            s = 3
        parts.append((s, w["diet"]))

    # 手机屏幕
    ph = row.get("phone_h")
    if ph is not None:
        if ph <= T["phone"]["ideal"]:
            s = 10
        elif ph <= T["phone"]["good"]:
            s = 8
        elif ph <= T["phone"]["ok"]:
            s = 6
        elif ph <= T["phone"]["bad"]:
            s = 4
        else:
            s = 2
        parts.append((s, w["phone"]))

    if not parts:
        return None
    total_w = sum(wt for _, wt in parts)
    score = sum(s * wt for s, wt in parts) / total_w
    return _clamp(score)


def compute_work_score(row: dict) -> int | None:
    """基于深度工作小时生成工作分；未填 deepwork_h 返回 None。"""
    return _band(row.get("deepwork_h"), SCORE_THRESHOLDS["work"])


def compute_learn_score(row: dict) -> int | None:
    """基于学习投入小时生成学习分；未填 learn_h 返回 None。"""
    return _band(row.get("learn_h"), SCORE_THRESHOLDS["learn"])


def compute_life_score(row: dict) -> int | None:
    """基于生活投入小时生成生活分；未填 life_h 返回 None。"""
    return _band(row.get("life_h"), SCORE_THRESHOLDS["life"])


def compute_scores(row: dict) -> dict:
    """补全缺失的四维评分 (只补 None 的，不覆盖手填值)。返回 row 自身。"""
    if row.get("health_score") is None:
        row["health_score"] = compute_health_score(row)
    if row.get("work_score") is None:
        row["work_score"] = compute_work_score(row)
    if row.get("learn_score") is None:
        row["learn_score"] = compute_learn_score(row)
    if row.get("life_score") is None:
        row["life_score"] = compute_life_score(row)
    return row
