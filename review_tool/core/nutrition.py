"""营养缺口纯规则：宏量判定 / 缺口 / 组合建议 / 三餐结构 / 极端值（零 I/O）。

🔴 R1：``macros_below_target`` / ``format_macro_below_flags`` 是
``reports/ai_review.attention_flags`` 饮食宏量判定的**唯一来源** ——
改口径只改这里，ai_review 与 nutrition 报告共用。

不参与四维评分（G5）；不做食物明细表（FOOD_LIB 仅建议侧静态配置）。
"""
from __future__ import annotations

import math
from typing import Any

from ..config import FOOD_LIB, NUTRITION_RULES, PROFILE

# 与 ai_review 历史文案对齐的无单位简称（避免「碳水(g) 160g」）
MACRO_FLAG_LABELS = {"carbs_g": "碳水", "protein_g": "蛋白质", "fat_g": "脂肪"}

# day 字段 → FOOD_LIB 宏量键
_COL_TO_ATTR = {"carbs_g": "carbs", "protein_g": "protein", "fat_g": "fat"}
_ATTR_TO_COL = {v: k for k, v in _COL_TO_ATTR.items()}


def resolve_targets(macro_targets: dict | None = None) -> dict[str, float]:
    """解析宏量目标；``None`` 时用 ``PROFILE["macro_targets"]``。"""
    if macro_targets is not None:
        return dict(macro_targets)
    return dict(PROFILE.get("macro_targets") or {})


def macros_below_target(
    day: dict,
    macro_targets: dict | None = None,
) -> list[dict[str, Any]]:
    """低于目标的宏量列表（与 ai_review 判定同源）。

    每项：``{col, label, actual, target, deficit}``。
    仅当 ``actual is not None and actual < target`` 时入列（与历史行为一致）。
    """
    if not day:
        return []
    mt = resolve_targets(macro_targets)
    out: list[dict[str, Any]] = []
    for col, tgt in mt.items():
        v = day.get(col)
        if v is not None and v < tgt:
            out.append({
                "col": col,
                "label": MACRO_FLAG_LABELS.get(col, col),
                "actual": v,
                "target": tgt,
                "deficit": tgt - v,
            })
    return out


def format_macro_below_flags(
    day: dict,
    macro_targets: dict | None = None,
) -> list[str]:
    """ai_review 关注点文案：``蛋白质 59g 低于目标 82g``（字节级兼容既有测试）。"""
    return [
        f"{g['label']} {g['actual']}g 低于目标 {g['target']}g"
        for g in macros_below_target(day, macro_targets)
    ]


def gap_analysis(
    day: dict,
    macro_targets: dict | None = None,
) -> dict[str, Any]:
    """当日缺口全景（含已达标项，deficit≤0 表示不缺）。

    返回 ``{targets, actuals, deficits, below, diet_kcal}``。
    """
    mt = resolve_targets(macro_targets)
    actuals: dict[str, float | None] = {}
    deficits: dict[str, float | None] = {}
    for col, tgt in mt.items():
        v = day.get(col) if day else None
        actuals[col] = v
        if v is None:
            deficits[col] = None
        else:
            deficits[col] = round(tgt - v, 2)
    return {
        "targets": mt,
        "actuals": actuals,
        "deficits": deficits,
        "below": macros_below_target(day or {}, macro_targets),
        "diet_kcal": (day or {}).get("diet_kcal"),
    }


def avg_field(rows: list[dict], col: str) -> float | None:
    """对非 None 值求均值；无值返回 None。"""
    vals = [r[col] for r in rows if r.get(col) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def meal_structure(day: dict) -> dict[str, Any]:
    """三餐结构（粗颗粒：``meals_count`` + ``breakfast_on_time``）。

    无逐餐热量时，只能给启发式「建议补哪一餐」。
    """
    rules = NUTRITION_RULES
    expected = int(rules.get("expected_meals", 3))
    meals = day.get("meals_count") if day else None
    breakfast = day.get("breakfast_on_time") if day else None
    notes: list[str] = []
    if breakfast == 0:
        notes.append("早餐未按时")
    if meals is not None and meals < expected:
        notes.append(f"餐次 {meals} < 预期 {expected}")
    elif meals is not None and meals > expected + 1:
        notes.append(f"餐次偏多（{meals}）")

    # 启发式建议餐次：缺早餐优先补早餐；餐次不足优先晚餐；否则晚餐加一份
    if breakfast == 0:
        slot = "早餐"
    elif meals is not None and meals < expected:
        slot = "加餐"
    else:
        slot = "晚餐"

    return {
        "meals_count": meals,
        "breakfast_on_time": breakfast,
        "expected_meals": expected,
        "notes": notes,
        "suggest_slot": slot,
    }


def extreme_kcal_streak(
    recent: list[dict],
    *,
    threshold: int | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """从最近一天往前数，连续 ``diet_kcal < threshold`` 的天数。

    ``triggered`` = streak ≥ days（默认 3 天 < 1000 kcal）。
    未记录热量的天**打断**连续（与熔断 streak 口径一致：谓词不满足即停）。
    """
    rules = NUTRITION_RULES
    thr = int(threshold if threshold is not None else rules["extreme_kcal"])
    need = int(days if days is not None else rules["extreme_streak_days"])
    streak = 0
    for r in reversed(recent or []):
        dk = r.get("diet_kcal")
        if dk is not None and dk < thr:
            streak += 1
        else:
            break
    return {
        "threshold": thr,
        "need_days": need,
        "streak": streak,
        "triggered": streak >= need,
    }


def format_extreme_flag(ext: dict[str, Any]) -> str | None:
    """极端偏低文案；未触发返回 None。明确「勿当做得好」。"""
    if not ext.get("triggered"):
        return None
    return (
        f"连续 {ext['streak']} 天饮食 < {ext['threshold']}kcal"
        f"（极端偏低，勿当「做得好」）"
    )


def scale_food(food: dict, amount: float) -> dict[str, float]:
    """按 ``amount``（相对 ``food['per']``）缩放宏量与热量。"""
    per = float(food.get("per") or 100)
    ratio = amount / per
    return {
        "kcal": round(food["kcal"] * ratio, 1),
        "carbs": round(food["carbs"] * ratio, 1),
        "protein": round(food["protein"] * ratio, 1),
        "fat": round(food["fat"] * ratio, 1),
    }


def _density(food: dict, attr: str) -> float:
    """单位量（1g / 1 个 / 1ml）上的营养密度。"""
    per = float(food.get("per") or 100)
    return float(food.get(attr) or 0) / per


def _round_amount(food: dict, raw: float) -> float:
    """按单位取整：克类凑 10g；可数类凑整；毫升凑 50。"""
    unit = food.get("unit") or "g"
    if unit in ("个", "份", "勺"):
        return max(1.0, float(math.ceil(raw)))
    if unit in ("ml", "毫升"):
        return max(50.0, float(math.ceil(raw / 50.0) * 50))
    # g
    return max(30.0, float(math.ceil(raw / 10.0) * 10))


def suggest_foods(
    deficits: dict[str, float | None],
    food_lib: list[dict] | None = None,
    *,
    max_foods: int | None = None,
) -> list[dict[str, Any]]:
    """贪心补最大缺口，限制 ≤ ``max_foods`` 种食物。

    ``deficits`` 键为 ``carbs_g`` / ``protein_g`` / ``fat_g``（可含 None）。
    每条建议含：food key/name、amount、unit、贡献宏量 —— 全部可手工复算。
    """
    lib = list(food_lib if food_lib is not None else FOOD_LIB)
    limit = int(
        max_foods if max_foods is not None
        else NUTRITION_RULES.get("max_suggest_foods", 3)
    )
    remaining = {
        col: float(v)
        for col, v in deficits.items()
        if v is not None and v > 0
    }
    if not remaining or not lib:
        return []

    picks: list[dict[str, Any]] = []
    used: set[str] = set()

    while len(picks) < limit and remaining:
        # 最大缺口营养素
        col = max(remaining, key=remaining.get)
        attr = _COL_TO_ATTR.get(col)
        if not attr:
            remaining.pop(col, None)
            continue
        need = remaining[col]

        # 选密度最高且未用过的食物（同分按 key 稳定排序）
        candidates = [
            f for f in lib
            if f.get("key") not in used and _density(f, attr) > 0
        ]
        if not candidates:
            remaining.pop(col, None)
            continue
        candidates.sort(key=lambda f: (-_density(f, attr), f.get("key") or ""))
        food = candidates[0]
        dens = _density(food, attr)
        raw_amount = need / dens
        amount = _round_amount(food, raw_amount)
        macros = scale_food(food, amount)

        picks.append({
            "key": food["key"],
            "name": food["name"],
            "amount": amount,
            "unit": food.get("unit") or "g",
            "kcal": macros["kcal"],
            "carbs": macros["carbs"],
            "protein": macros["protein"],
            "fat": macros["fat"],
            "for_gap": col,
            "for_label": MACRO_FLAG_LABELS.get(col, col),
        })
        used.add(food["key"])

        # 扣减剩余缺口
        for a, c in _ATTR_TO_COL.items():
            if c in remaining:
                remaining[c] = round(remaining[c] - macros[a], 2)
                if remaining[c] <= 0.5:
                    remaining.pop(c, None)

    return picks


def format_suggestion_line(pick: dict, *, slot: str | None = None) -> str:
    """人类可读建议行，数字均可对照 FOOD_LIB 复算。"""
    prefix = f"{slot}加 " if slot else ""
    amt = pick["amount"]
    # 整数克/个不写小数
    amt_s = str(int(amt)) if float(amt).is_integer() else f"{amt:g}"
    return (
        f"{prefix}{pick['name']}（{amt_s}{pick['unit']} ≈ "
        f"{pick['protein']:g}g 蛋白 / {pick['carbs']:g}g 碳水 / "
        f"{pick['fat']:g}g 脂肪 / {pick['kcal']:g}kcal）"
    )
