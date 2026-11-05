"""health 载荷：版本 / mode / 集成开关 / 只读状态。白名单构造，不含任何密钥与本机路径。"""
from __future__ import annotations

import os
from typing import Any

from .. import __version__
from ..config import DB_PATH, get_llm_mode
from ..integrations.flags import is_enabled

INTEGRATION_NAMES = ("clickup", "keepstrong", "deepseek")


def build_health(*, write_enabled: bool = False) -> dict[str, Any]:
    """返回 ``/api/health`` 的数据（只含布尔 / 版本 / mode，永不含凭据或路径）。"""
    mode = get_llm_mode()
    integrations = {name: bool(is_enabled(name)) for name in INTEGRATION_NAMES}
    return {
        "status": "ok",
        "version": __version__,
        "llm_mode": mode,
        "integrations": integrations,
        # DeepSeek 类功能门禁：mode=deepseek 且集成开关开（FR-H2）
        "ai_enabled": mode == "deepseek" and integrations["deepseek"],
        "db_present": os.path.isfile(DB_PATH),
        "readonly": not write_enabled,
    }
