"""根据结构化数据动态生成四维评分 (健康/工作/学习/生活)。

原则:
- 健康分: 完全基于客观健康子指标，规则可解释 (compute_health_score)
- 工作分: 基于 深度工作_h (deepwork_h)
- 学习分: 基于 学习投入_h (learn_h)
- 生活分: 基于 生活投入_h (life_h)
- 任一维度数据缺失 -> 该维留 None (不瞎编)，系统分四维齐全才计算
- 所有阈值/权重来自 config.SCORE_THRESHOLDS（可配置，默认=用户偏好）
- 服药/护肤等个人定制项不计入通用评分（统计于 personal_tracks 表）

标尺 v2（v1.34.0）
------------------
时长三维从「阈值分档」改为「锚点插值」：分档必然产生空档（旧标尺的分值集合
只有 {1,2,3,4,5,7,9}，6 分不可达），插值则保证 1~10 每个整数可达且随原始值
单调。健康六子项仍用分档（单指标，分档更易解释），但把「一个分值覆盖 >50%
样本」的死档全部拆开。设计判据与实测依据见 ``config.SCORE_THRESHOLDS`` 上方
注释与 ``docs/设计说明.md``「评分标尺 v2」。
"""
from __future__ import annotations

import math

from ..config import DIET_TARGET_KCAL, DIMENSIONS, SCORE_THRESHOLDS


def _round_half_up(v: float) -> int:
    """四舍五入（.5 一律进位）。

    ⛔ 不用内置 ``round()`` —— 它是银行家舍入，``round(2.5) == 2``，
    会让「刚好半程」反而拿不到对应档位（v1.4.0 就踩过，v1.34.0 统一修掉）。
    """
    return int(math.floor(float(v) + 0.5))


def _clamp(v, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, _round_half_up(v)))


def system_score_from(row: dict) -> float | None:
    """根据四维评分算系统分；任一缺失返回 None。

    口径 = 四维**算术平均**（保留 2 位）。为什么不用几何平均：几何平均会
    重罚单维极低的日子（[6,9,1,1] 算术 4.25 → 几何 2.71），对「点状崩一天」
    过于严厉、且不可心算。均衡与否改由 ``balance_spread`` /
    ``weakest_dimension`` 单独呈现 —— 让系统分只承担「纵向趋势」，
    **不承担绝对及格判断**（实测全库最高 6.50，用 6 分当及格线没有意义）。
    """
    vals = [row.get(d) for d in DIMENSIONS]
    if all(v is not None for v in vals):
        return round(sum(vals) / len(vals), 2)
    return None


def weakest_dimension(row: dict) -> tuple[str, int] | None:
    """四维里分值最低的一维（短板）。任一维缺失返回 None。

    用途：报告里直接点名「今天哪一维在拖后腿」。这是系统分不再承担及格判断
    之后的替代物 —— 总分只做趋势，短板看这里。
    """
    vals = [(d, row.get(d)) for d in DIMENSIONS]
    if any(v is None for _, v in vals):
        return None
    field, value = min(vals, key=lambda kv: kv[1])
    return field, value


def balance_spread(row: dict) -> int | None:
    """四维极差（最高维 - 最低维）。0 = 完全均衡，9 = 一维满格另一维耗尽。

    时间预算是零和的：某一维拉到 9，往往意味着另一维被挤到 1。
    极差大 = 当天的时间分配偏斜，值得在复盘里问一句「这是有意的吗」。
    """
    vals = [row.get(d) for d in DIMENSIONS]
    if any(v is None for v in vals):
        return None
    return max(vals) - min(vals)


# ---------------------------------------------------------------------------
# 通用打分原语
# ---------------------------------------------------------------------------

def _interp(value, anchors) -> int | None:
    """锚点插值：``anchors`` = [(原始值, 分值), ...]，区间内线性插值，两端封顶。

    这是时长三维（工作 / 学习 / 生活）的唯一计算入口。用插值而非分档的目的：
    1~10 每个整数都可达（分档必然有空档），且随原始值严格单调。
    """
    if value is None or not anchors:
        return None
    pts = sorted(anchors, key=lambda p: p[0])
    if value <= pts[0][0]:
        return _clamp(pts[0][1])
    if value >= pts[-1][0]:
        return _clamp(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= value <= x1:
            if x1 == x0:
                return _clamp(y1)
            return _clamp(y0 + (y1 - y0) * (value - x0) / (x1 - x0))
    return _clamp(pts[-1][1])


def _bands(value, bands, floor, gte: bool = True) -> int | None:
    """阈值分档：``bands`` 按「从优到劣」排列，命中即返回。

    ``gte=True`` 表示越大越好（阈值是下界，bands 需降序）；
    ``gte=False`` 表示越小越好（阈值是上界，bands 需升序）。
    全不命中时返回 ``floor``。
    """
    if value is None:
        return None
    for threshold, score in bands:
        if (value >= threshold) if gte else (value <= threshold):
            return _clamp(score)
    return _clamp(floor)


def _bedtime_score(bt, cfg) -> int | None:
    """入睡时间打分：转成「距 22:30 的延迟分钟」后单调轴分档。

    ⛔ 不能直接用「距 00:00 的分钟数」分档 —— 23:59(1439) 与 00:00(0) 相邻却
    数值差最大，跨午夜会跳变。旧标尺正是因此把 00:00–06:00 全判 3 分，
    覆盖了 89% 的样本，等于该维度失效。
    """
    if bt is None:
        return None
    anchor = int(cfg.get("anchor_min", 1350))
    delay = bt - anchor if bt >= anchor else bt + 1440 - anchor
    return _bands(delay, cfg["bands"], cfg.get("floor", 2), gte=False)


def _exercise_score(em, training_day, cfg) -> int | None:
    """运动时长打分：训练日与平日两套档线，且区分「完全没动」与「动了不够」。"""
    if em is None:
        return None
    branch = cfg["train"] if training_day == 1 else cfg["rest"]
    for threshold, score in branch["bands"]:
        if em >= threshold:
            return _clamp(score)
    return _clamp(branch["positive"]) if em > 0 else _clamp(branch["floor"])


def _diet_score(dk, cfg) -> int | None:
    """饮食热量打分：按「偏离目标热量的比例」分档，越贴近个人目标越准。

    目标热量 = ``config.DIET_TARGET_KCAL``（由 PROFILE["macro_targets"] 推导，
    碳水/蛋白 4 kcal/g + 脂肪 9 kcal/g）。改宏量目标 → 饮食分的中心自动跟着走。
    """
    if dk is None:
        return None
    target = DIET_TARGET_KCAL or cfg.get("fallback_target", 1700)
    ratio = abs(float(dk) - float(target)) / float(target)
    return _bands(ratio, cfg["bands"], cfg.get("floor", 1), gte=False)


# ---------------------------------------------------------------------------
# 四维
# ---------------------------------------------------------------------------

def compute_health_score(row: dict) -> int | None:
    """基于健康子指标规则化生成 1-10 的健康分。数据不足返回 None。

    加权模型：六子项各自折 0-10 后按 ``weights`` 加权，**缺失子项整项剔除、
    剩余权重重新归一**（不补 0，避免「少填反而低分」）。权重和恒为 1.00，
    归一化只是缺项时的兜底。
    """
    T = SCORE_THRESHOLDS
    w = T["weights"]
    parts: list[tuple[int, float]] = []  # (score_0_10, weight)

    # 睡眠时长
    sh = row.get("sleep_h")
    if sh is not None:
        cfg = T["sleep"]
        parts.append((_bands(sh, cfg["bands"], cfg.get("floor", 1),
                             gte=cfg.get("gte", True)), w["sleep_h"]))

    # 睡眠质量 (0-100 -> 0-10 直接折算；主观自评，权重最低)
    q = row.get("sleep_quality")
    if q is not None:
        parts.append((_clamp(q / 10), w["sleep_quality"]))

    # 入睡时间
    bt = row.get("bedtime")
    if bt is not None:
        parts.append((_bedtime_score(bt, T["bedtime"]), w["bedtime"]))

    # 运动
    em = row.get("exercise_min")
    if em is not None:
        parts.append((_exercise_score(em, row.get("training_day"), T["exercise"]),
                      w["exercise"]))

    # 饮食热量
    dk = row.get("diet_kcal")
    if dk is not None:
        parts.append((_diet_score(dk, T["diet"]), w["diet"]))

    # 手机屏幕
    ph = row.get("phone_h")
    if ph is not None:
        cfg = T["phone"]
        parts.append((_bands(ph, cfg["bands"], cfg.get("floor", 1),
                             gte=cfg.get("gte", False)), w["phone"]))

    if not parts:
        return None
    total_w = sum(wt for _, wt in parts)
    score = sum(s * wt for s, wt in parts) / total_w
    return _clamp(score)


def compute_work_score(row: dict) -> int | None:
    """基于深度工作小时生成工作分；未填 deepwork_h 返回 None。"""
    return _interp(row.get("deepwork_h"), SCORE_THRESHOLDS["work"]["anchors"])


def compute_learn_score(row: dict) -> int | None:
    """基于学习投入小时生成学习分；未填 learn_h 返回 None。"""
    return _interp(row.get("learn_h"), SCORE_THRESHOLDS["learn"]["anchors"])


def compute_life_score(row: dict) -> int | None:
    """基于生活投入小时生成生活分；未填 life_h 返回 None。"""
    return _interp(row.get("life_h"), SCORE_THRESHOLDS["life"]["anchors"])


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
