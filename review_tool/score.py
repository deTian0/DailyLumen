"""根据结构化数据动态生成四维评分 (健康/工作/学习/生活)。

原则:
- 健康分: 完全基于客观健康子指标, 规则可解释 (compute_health_score)
- 工作分: 基于可选旧字段 深度工作_h (deepwork_h); 未填则留 None 由用户手填
- 学习分/生活分: 当前模板无结构化输入, 留 None 由用户手填
  (若后续在可选字段加入 学习投入_h / 生活事件, 可在此扩展自动算)
"""
from config import DIMENSIONS


def _clamp(v, lo=1, hi=10):
    return max(lo, min(hi, int(round(v))))


def compute_health_score(row):
    """基于健康子指标规则化生成 1-10 的健康分。数据不足返回 None。"""
    parts = []  # (score_0_10, weight)

    # 睡眠时长
    sh = row.get("sleep_h")
    if sh is not None:
        if sh >= 7.5:
            s = 10
        elif sh >= 7.0:
            s = 8
        elif sh >= 6.5:
            s = 6
        elif sh >= 6.0:
            s = 4
        else:
            s = 2
        parts.append((s, 0.18))

    # 睡眠质量 (0-100 -> 0-10)
    q = row.get("sleep_quality")
    if q is not None:
        parts.append((_clamp(q / 10), 0.12))

    # 入睡时间 (bedtime 为距 00:00 分钟数; 跨午夜归到凌晨段)
    bt = row.get("bedtime")
    if bt is not None:
        if bt <= 300:
            s = 3           # 00:00-05:00 熬夜到凌晨 (须先于当晚段判断)
        elif bt <= 1350:
            s = 10          # <=22:30
        elif bt <= 1410:
            s = 8           # 22:30-23:30
        elif bt <= 1439:
            s = 5           # 23:30-23:59
        else:
            s = 5
        parts.append((s, 0.15))

    # 运动 (训练日更严格)
    em = row.get("exercise_min")
    if em is not None:
        if row.get("training_day") == 1:
            s = 10 if em >= 30 else (6 if em >= 10 else 2)
        else:
            s = 8 if em >= 20 else 6
        parts.append((s, 0.25))

    # 补剂依从
    sd = row.get("supps_done")
    if sd is not None:
        parts.append((10 if sd == 1 else 4, 0.05))

    # 饮食热量
    dk = row.get("diet_kcal")
    if dk is not None:
        if 1200 <= dk <= 2200:
            s = 8
        elif 1000 <= dk < 1200 or 2200 < dk <= 2600:
            s = 5
        else:
            s = 3
        parts.append((s, 0.10))

    # 手机屏幕
    ph = row.get("phone_h")
    if ph is not None:
        if ph <= 4:
            s = 10
        elif ph <= 6:
            s = 8
        elif ph <= 8:
            s = 6
        elif ph <= 10:
            s = 4
        else:
            s = 2
        parts.append((s, 0.15))

    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_w
    return _clamp(score)


def compute_work_score(row):
    """基于深度工作小时生成工作分; 未填 deepwork_h 返回 None。"""
    dw = row.get("deepwork_h")
    if dw is None:
        return None
    if dw >= 6:
        return 9
    if dw >= 4:
        return 7
    if dw >= 2:
        return 5
    return 3


def compute_scores(row):
    """补全缺失的四维评分 (只补 None 的, 不覆盖手填值)。返回 row 自身。"""
    if row.get("health_score") is None:
        row["health_score"] = compute_health_score(row)
    if row.get("work_score") is None:
        row["work_score"] = compute_work_score(row)
    # learn_score / life_score: 暂留 None (无结构化输入, 由用户手填)
    return row


def system_score_from(row):
    """四维齐全则算系统分; 否则 None。供 ingest 在补分后重算。"""
    from config import system_score_from as _ssf
    return _ssf(row)
