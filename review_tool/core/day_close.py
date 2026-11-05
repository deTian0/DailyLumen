"""收工摘要与「今日能否收工」红绿灯（纯规则，零 I/O）。

对外健康叙事口径（v1.58.0）：体重 + 饮食 + 睡眠 + 训练；
``体脂率`` 可选，缺测不拉红灯、禁止伪造。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# 收工关注的核心字段（体脂不在此列）
CLOSE_FOCUS_FIELDS: tuple[str, ...] = (
    "体重_kg",
    "饮食热量_kcal",
    "睡眠时长_h",
    "运动时长_min",
)

LIGHT_GREEN = "green"
LIGHT_YELLOW = "yellow"
LIGHT_RED = "red"

_LIGHT_LABEL = {
    LIGHT_GREEN: "绿",
    LIGHT_YELLOW: "黄",
    LIGHT_RED: "红",
}


def light_label(light: str) -> str:
    return _LIGHT_LABEL.get(light, light)


def format_close_summary(
    *,
    read: str,
    empty: str,
    next_cmd: str,
) -> str:
    """固定约三行收工摘要。"""
    return "\n".join(
        [
            f"读到: {read or '（无）'}",
            f"空缺: {empty or '（无）'}",
            f"下一条: {next_cmd or '（无）'}",
        ]
    )


def missing_focus_fields(
    filled: Iterable[str] | None,
    *,
    focus: Sequence[str] = CLOSE_FOCUS_FIELDS,
) -> list[str]:
    """关注字段里尚未填上的项（顺序稳定）。"""
    have = {str(x) for x in (filled or [])}
    return [k for k in focus if k not in have]


def classify_day_ready(
    *,
    md_exists: bool,
    pending_draft: bool,
    ingested: bool,
    missing_focus: Sequence[str] | None = None,
    inbox_pending: bool = False,
    optional_missing: Sequence[str] | None = None,
) -> dict[str, Any]:
    """合成今日收工红绿灯。

    - 红：无 md / 仍未定稿（含 pending）/ 核心关注字段大面积缺失（≥3）
    - 黄：未入库、收件箱未归档、少量缺字段、或仅可选缺测
    - 绿：md 存在且已定稿、已入库、核心字段齐、收件箱无待归档
    """
    miss = list(missing_focus or [])
    reasons: list[str] = []

    if not md_exists:
        return {
            "light": LIGHT_RED,
            "label": light_label(LIGHT_RED),
            "reasons": ["无复盘 md"],
            "missing_focus": miss,
            "optional_missing": list(optional_missing or []),
        }

    if pending_draft:
        reasons.append("未定稿（pending / 草稿待人审）")
    if miss:
        reasons.append("缺关注字段: " + "、".join(miss))
    if not ingested:
        reasons.append("未入库")
    if inbox_pending:
        reasons.append("收件箱未归档")

    opt = [x for x in (optional_missing or []) if x]
    # 体脂等可选：只作说明，不单独拉黄（若已有其它黄因则附注）
    opt_note = ""
    if "体脂率" in opt or any("体脂" in str(x) for x in opt):
        opt_note = "体脂率可选缺测（勿伪造）"

    if pending_draft or len(miss) >= 3:
        light = LIGHT_RED
    elif miss or (not ingested) or inbox_pending:
        light = LIGHT_YELLOW
    else:
        light = LIGHT_GREEN
        if not reasons:
            reasons = ["可收工"]
        if opt_note:
            reasons.append(opt_note)

    if light != LIGHT_GREEN and opt_note and opt_note not in reasons:
        reasons.append(opt_note)

    return {
        "light": light,
        "label": light_label(light),
        "reasons": reasons,
        "missing_focus": miss,
        "optional_missing": opt,
    }


def render_day_ready_line(status: Mapping[str, Any]) -> str:
    """单行：今日能否收工: 绿/黄/红 — 原因。"""
    label = status.get("label") or light_label(str(status.get("light") or ""))
    reasons = status.get("reasons") or []
    why = "；".join(str(r) for r in reasons) if reasons else "—"
    return f"今日能否收工: {label} — {why}"


__all__ = [
    "CLOSE_FOCUS_FIELDS",
    "LIGHT_GREEN",
    "LIGHT_RED",
    "LIGHT_YELLOW",
    "classify_day_ready",
    "format_close_summary",
    "light_label",
    "missing_focus_fields",
    "render_day_ready_line",
]
