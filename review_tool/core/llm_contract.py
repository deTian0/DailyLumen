"""LLM / 宿主读图与写评价的结构化契约（纯规则，零 I/O）。

字段名对齐 ``docs/LLM能力拆分草案.md`` §4 与 intake 数据块清单；
供 deepseek Vision / workbuddy 宿主自检共用，不发网络请求。
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

# 通道 A：素材 → md 数据块（读图优先关注）
DIET_FIELDS = (
    "饮食热量_kcal",
    "碳水_g",
    "脂肪_g",
    "蛋白质_g",
    "三餐情况",
    "早餐按时",
)
BODY_FIELDS = (
    "体重_kg",
    "体脂率",
    "腰围_cm",
)
SLEEP_FIELDS = (
    "睡眠时长_h",
    "睡眠质量",
    "入睡时间",
)
ACTIVITY_FIELDS = (
    "手机屏幕_h",
    "运动时长_min",
    "训练日",
)
# 全量契约字段（可部分缺失；缺失留空合法）
CONTRACT_DATA_FIELDS = DIET_FIELDS + BODY_FIELDS + SLEEP_FIELDS + ACTIVITY_FIELDS

# 英文 / 别名 → 契约中文键（模型 JSON 常混用）
_ALIAS_TO_CONTRACT: dict[str, str] = {
    "diet_kcal": "饮食热量_kcal",
    "calories": "饮食热量_kcal",
    "kcal": "饮食热量_kcal",
    "carbs_g": "碳水_g",
    "carbs": "碳水_g",
    "fat_g": "脂肪_g",
    "fat": "脂肪_g",
    "protein_g": "蛋白质_g",
    "protein": "蛋白质_g",
    "meals_count": "三餐情况",
    "meals": "三餐情况",
    "breakfast_on_time": "早餐按时",
    "weight_kg": "体重_kg",
    "weight": "体重_kg",
    "body_fat": "体脂率",
    "body_fat_pct": "体脂率",
    "waist_cm": "腰围_cm",
    "sleep_h": "睡眠时长_h",
    "sleep_quality": "睡眠质量",
    "bedtime": "入睡时间",
    "phone_h": "手机屏幕_h",
    "exercise_min": "运动时长_min",
    "training_day": "训练日",
}
for _k in CONTRACT_DATA_FIELDS:
    _ALIAS_TO_CONTRACT[_k] = _k

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型回复中抽出第一个 JSON object；失败抛 ``ValueError``。"""
    if not text or not str(text).strip():
        raise ValueError("空文本，无法解析结构化 JSON")
    raw = str(text).strip()
    m = _JSON_FENCE_RE.search(raw)
    if m:
        raw = m.group(1).strip()
    else:
        m2 = _JSON_OBJECT_RE.search(raw)
        if m2:
            raw = m2.group(0)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"期望 JSON object，得到 {type(data).__name__}")
    return data


def normalize_contract_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    """别名归一到契约中文键；空串 / None 丢弃；未知键保留在 ``_unknown``。"""
    out: dict[str, Any] = {}
    unknown: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        key = str(k).strip()
        canon = _ALIAS_TO_CONTRACT.get(key) or _ALIAS_TO_CONTRACT.get(key.lower())
        if canon is None:
            unknown[key] = v
            continue
        out[canon] = v
    if unknown:
        out["_unknown"] = unknown
    return out


def classify_contract_fields(
    fields: Mapping[str, Any],
) -> dict[str, list[str]]:
    """对照契约字段清单：filled / missing / unknown。"""
    filled = [k for k in CONTRACT_DATA_FIELDS if k in fields and fields[k] not in (None, "")]
    missing = [k for k in CONTRACT_DATA_FIELDS if k not in filled]
    unknown_map = fields.get("_unknown") if isinstance(fields.get("_unknown"), dict) else {}
    unknown = sorted(unknown_map.keys()) if unknown_map else []
    return {"filled": filled, "missing": missing, "unknown": unknown}


def parse_model_structured(text: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """模型文本 → (归一字段, 分类结果)。"""
    raw = extract_json_object(text)
    fields = normalize_contract_fields(raw)
    return fields, classify_contract_fields(fields)


def render_data_block_lines(fields: Mapping[str, Any], *, date: str, weekday: str) -> str:
    """渲染 ```data 块内常用行（仅写出有值的契约字段 + 日期/星期）。"""
    lines = [f"日期: {date}", f"星期: {weekday}"]
    for key in CONTRACT_DATA_FIELDS:
        if key in fields and fields[key] not in (None, ""):
            lines.append(f"{key}: {fields[key]}")
    return "\n".join(lines)


__all__ = [
    "ACTIVITY_FIELDS",
    "BODY_FIELDS",
    "CONTRACT_DATA_FIELDS",
    "DIET_FIELDS",
    "SLEEP_FIELDS",
    "classify_contract_fields",
    "extract_json_object",
    "normalize_contract_fields",
    "parse_model_structured",
    "render_data_block_lines",
]
