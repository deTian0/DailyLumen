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

from .config import DIMENSIONS, SCORE_THRESHOLDS


def _clamp(v, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, int(round(v))))


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

    # 入睡时间
    bt = row.get("bedtime")
    if bt is not None:
        if bt <= T["bedtime"]["late_night_max"]:
            s = 3           # 00:00-05:00 熬夜
        elif bt <= T["bedtime"]["early_max"]:
            s = 10          # <=22:30
        elif bt <= T["bedtime"]["ok_max"]:
            s = 8           # 22:30-23:30
        else:
            s = 5           # 23:30 之后
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
    dw = row.get("deepwork_h")
    if dw is None:
        return None
    T = SCORE_THRESHOLDS["work"]
    if dw >= T["full"]:
        return 9
    if dw >= T["good"]:
        return 7
    if dw >= T["ok"]:
        return 5
    return 3


def compute_learn_score(row: dict) -> int | None:
    """基于学习投入小时生成学习分；未填 learn_h 返回 None。"""
    lh = row.get("learn_h")
    if lh is None:
        return None
    T = SCORE_THRESHOLDS["learn"]
    if lh >= T["full"]:
        return 9
    if lh >= T["good"]:
        return 7
    if lh >= T["ok"]:
        return 5
    return 3


def compute_life_score(row: dict) -> int | None:
    """基于生活投入小时生成生活分；未填 life_h 返回 None。"""
    lh = row.get("life_h")
    if lh is None:
        return None
    T = SCORE_THRESHOLDS["life"]
    if lh >= T["full"]:
        return 9
    if lh >= T["good"]:
        return 7
    if lh >= T["ok"]:
        return 5
    return 3


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
