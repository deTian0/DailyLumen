"""第三方集成能力开关（与 ``config.INTEGRATIONS`` / Settings 对齐）。

关闭时命令入口应 ``require_enabled`` 后立即退出，⛔ 不发网络请求。
DeepSeek 另受 ``DAILYLUMEN_LLM_MODE`` 门禁（mode=deepseek 且开关开才允许）。
"""
from __future__ import annotations

from typing import Any

# 延迟读 config，避免 import 环；测试可 patch INTEGRATIONS。


class IntegrationDisabled(RuntimeError):
    """集成开关关闭。"""


def _integrations() -> dict[str, Any]:
    from ..config import INTEGRATIONS

    return INTEGRATIONS


def is_enabled(name: str) -> bool:
    """``name`` ∈ ``clickup`` / ``keepstrong`` / ``deepseek``；缺省视为开。"""
    return bool(_integrations().get(name, True))


def disabled_hint(name: str) -> str:
    """开关关闭时的中文提示（单一来源）。"""
    env_key = {
        "clickup": "INTEGRATION_CLICKUP_ENABLED",
        "keepstrong": "INTEGRATION_KEEPSTRONG_ENABLED",
        "deepseek": "INTEGRATION_DEEPSEEK_ENABLED",
    }.get(name, f"INTEGRATION_{name.upper()}_ENABLED")
    return (
        f"集成「{name}」已关闭（config.INTEGRATIONS['{name}'] = False / "
        f"local/.env 的 {env_key}=false）。\n"
        f"  → 开启：在 local/.env 设 {env_key}=true 后重试；"
        "关闭状态下本命令不发网络请求。"
    )


def require_enabled(name: str) -> None:
    """未启用则抛 ``IntegrationDisabled``（含可读提示）。"""
    if not is_enabled(name):
        raise IntegrationDisabled(disabled_hint(name))
