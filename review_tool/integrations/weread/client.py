"""微信读书 Agent Gateway 薄客户端（只读；F2 书单旁证）。

契约以 ``weread-skills`` 为准：
``POST https://i.weread.qq.com/api/agent/gateway``，
body 平铺 ``api_name`` + 业务参数 + 强制 ``skill_version``。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ...config import SETTINGS
from .creds import CredError, load_api_key

Opener = Callable[..., Any]

DEFAULT_BASE_URL = "https://i.weread.qq.com/api/agent/gateway"
DEFAULT_SKILL_VERSION = "1.0.6"
DEFAULT_TIMEOUT_S = 30.0


class WeReadError(RuntimeError):
    """微信读书 API / 凭据相关错误。"""

    def __init__(self, message: str, *, errcode: int | None = None):
        super().__init__(message)
        self.errcode = errcode


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


class Client:
    """微信读书 Gateway 客户端；``opener`` 可注入（测试假实现）。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        skill_version: str | None = None,
        timeout: float | None = None,
        opener: Opener | None = None,
    ):
        self.api_key = api_key
        self.base_url = (base_url or getattr(
            SETTINGS, "weread_base_url", DEFAULT_BASE_URL
        ) or DEFAULT_BASE_URL).rstrip("/")
        self.skill_version = (
            skill_version
            or getattr(SETTINGS, "weread_skill_version", None)
            or DEFAULT_SKILL_VERSION
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else getattr(SETTINGS, "weread_timeout_s", DEFAULT_TIMEOUT_S)
            or DEFAULT_TIMEOUT_S
        )
        self.opener = opener or urllib.request.urlopen

    def call(self, api_name: str, **params: Any) -> dict:
        """调用 Gateway；业务参数与 ``api_name`` / ``skill_version`` 同层平铺。"""
        body = {
            "api_name": api_name,
            "skill_version": self.skill_version,
            **params,
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers=build_headers(self.api_key),
            method="POST",
        )
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise WeReadError(
                f"微信读书 HTTP {e.code}: {detail or e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise WeReadError(f"微信读书网络不可达: {e.reason}") from e

        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (TypeError, ValueError) as e:
            raise WeReadError("微信读书回包不是合法 JSON") from e
        if not isinstance(payload, dict):
            raise WeReadError("微信读书回包格式异常")
        errcode = payload.get("errcode")
        if errcode not in (None, 0, "0"):
            raise WeReadError(
                f"微信读书 errcode={errcode}: {payload.get('errmsg') or payload}",
                errcode=int(errcode) if str(errcode).lstrip("-").isdigit() else None,
            )
        return payload

    def shelf_sync(self) -> dict:
        return self.call("/shelf/sync")

    def readdata_detail(
        self, *,
        mode: str = "weekly",
        base_time: int | None = None,
    ) -> dict:
        params: dict[str, Any] = {"mode": mode}
        if base_time is not None:
            params["baseTime"] = int(base_time)
        return self.call("/readdata/detail", **params)


def client_from_settings(*,
                        env=None,
                        settings=None,
                        opener: Opener | None = None) -> Client:
    """凭据 + Settings 构造客户端。"""
    key = load_api_key(env=env, settings=settings)
    s = settings if settings is not None else SETTINGS
    return Client(
        key,
        base_url=getattr(s, "weread_base_url", None),
        skill_version=getattr(s, "weread_skill_version", None),
        timeout=getattr(s, "weread_timeout_s", None),
        opener=opener,
    )


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
