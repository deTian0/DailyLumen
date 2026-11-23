"""微信读书（WeRead Agent Gateway）集成门面 —— F2 书单旁证只读。"""

from .client import (
    DEFAULT_BASE_URL,
    DEFAULT_SKILL_VERSION,
    DEFAULT_TIMEOUT_S,
    Client,
    WeReadError,
    build_headers,
    client_from_settings,
)
from .creds import CredError, load_api_key

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_SKILL_VERSION",
    "DEFAULT_TIMEOUT_S",
    "Client",
    "CredError",
    "WeReadError",
    "build_headers",
    "client_from_settings",
    "load_api_key",
]
