"""第三方集成层：ClickUp / 练练健身 / DeepSeek 网关。

依赖方向：允许依赖 ``core`` 与包根 ``config`` / ``settings``；
⛔ 禁止依赖 ``storage`` / ``pipeline`` / ``reports``。
pipeline / reports / CLI 可调用本层；core / storage 不得反向依赖。

能力开关见 ``config.INTEGRATIONS`` / ``Settings.integration_*_enabled``；
关闭时 CLI 明确报错、不发网（``flags.require_enabled``）。
"""

from .flags import (
    IntegrationDisabled,
    disabled_hint,
    is_enabled,
    require_enabled,
)

__all__ = [
    "IntegrationDisabled",
    "disabled_hint",
    "is_enabled",
    "require_enabled",
]
