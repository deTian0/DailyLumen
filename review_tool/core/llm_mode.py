"""LLM 运行模式（互斥）：纯规则，零 I/O。

``workbuddy``（默认）= 宿主 Agent 代劳落 md，仓库不调外部模型 API；
``deepseek`` = 仓库进程内调 DeepSeek。同时仅一种。

依赖方向：只允许标准库；禁止 storage / pipeline / reports / config。
"""
from __future__ import annotations

from typing import Any

LLM_MODE_WORKBUDDY = "workbuddy"
LLM_MODE_DEEPSEEK = "deepseek"
DEFAULT_LLM_MODE = LLM_MODE_WORKBUDDY
ALLOWED_LLM_MODES = frozenset({LLM_MODE_WORKBUDDY, LLM_MODE_DEEPSEEK})


class LlmModeError(ValueError):
    """非法 mode 或违反互斥约定。"""


def normalize_llm_mode(value: Any) -> str:
    """空 / None → ``workbuddy``；合法值小写归一；其余抛 ``LlmModeError``。"""
    if value is None:
        return DEFAULT_LLM_MODE
    if isinstance(value, str) and not value.strip():
        return DEFAULT_LLM_MODE
    s = str(value).strip().lower()
    if s not in ALLOWED_LLM_MODES:
        allowed = " | ".join(sorted(ALLOWED_LLM_MODES))
        raise LlmModeError(
            f"DAILYLUMEN_LLM_MODE 非法：{value!r}（仅允许 {allowed}；"
            "互斥，同时仅一种）"
        )
    return s


def is_deepseek_mode(mode: str) -> bool:
    return normalize_llm_mode(mode) == LLM_MODE_DEEPSEEK


def is_workbuddy_mode(mode: str) -> bool:
    return normalize_llm_mode(mode) == LLM_MODE_WORKBUDDY


__all__ = [
    "ALLOWED_LLM_MODES",
    "DEFAULT_LLM_MODE",
    "LLM_MODE_DEEPSEEK",
    "LLM_MODE_WORKBUDDY",
    "LlmModeError",
    "is_deepseek_mode",
    "is_workbuddy_mode",
    "normalize_llm_mode",
]
