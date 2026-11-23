"""微信读书 Agent Gateway 凭据解析。"""
from __future__ import annotations

import os

from ...config import SETTINGS


class CredError(RuntimeError):
    """缺少 WEREAD_API_KEY。"""


def load_api_key(*, env=None, settings=None) -> str:
    """读 ``WEREAD_API_KEY``：进程环境优先，其次 Settings。

    显式传入 ``settings=`` 时不再回落到模块级 ``SETTINGS``（方便测试注入空 key）。
    """
    env = os.environ if env is None else env
    key = (env.get("WEREAD_API_KEY") or "").strip()
    if key:
        return key
    s = settings if settings is not None else SETTINGS
    key = (getattr(s, "weread_api_key", "") or "").strip()
    if key:
        return key
    raise CredError(
        "找不到微信读书凭据：未设环境变量 / local/.env 的 WEREAD_API_KEY。\n"
        "  → 格式 wrk-…；来源见 skills.sh Tencent/WeChatReading。"
    )
