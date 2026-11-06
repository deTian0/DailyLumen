"""W14 serve 最小鉴权：``/api/*`` 必须带 ``DAILYLUMEN_WEB_KEY``（请求头，不收查询串）。

- 支持 ``Authorization: Bearer <key>`` 或 ``X-DailyLumen-Key: <key>``；
- 比较用 ``hmac.compare_digest``（常量时间）；
- ``/api/ping`` 是唯一免 key 的存活探针，响应不含任何信息；
- 静态 dist（``/``、``/assets/*``）不需 key：key 只在用户登录页输入，绝不进 bundle。
"""
from __future__ import annotations

import hmac
from collections.abc import Mapping

PING_PATH = "/api/ping"
KEY_HEADER = "x-dailylumen-key"

MISSING_KEY_HINT = (
    "serve 需要访问密钥 DAILYLUMEN_WEB_KEY，当前未配置，拒绝启动。\n"
    "  → 在 local/.env 末尾追加一行 DAILYLUMEN_WEB_KEY=<随机串>，例如用\n"
    "    python -c \"import secrets; print(secrets.token_urlsafe(32))\" 生成；\n"
    "  → 打开看板后在登录页输入同一个值。⛔ 不要把它写进 .env.example 或任何入 git 的文件。"
)


def extract_key(headers: Mapping[str, str]) -> str | None:
    """从请求头取 key；两种头都没有时返回 None。"""
    auth = headers.get("authorization")
    if auth:
        scheme, _, value = auth.strip().partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    alt = headers.get(KEY_HEADER)
    if alt and alt.strip():
        return alt.strip()
    return None


def key_matches(provided: str | None, expected: str) -> bool:
    """常量时间比较；``expected`` 为空时一律拒绝（fail-closed）。"""
    if not expected or provided is None:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def requires_key(path: str) -> bool:
    """哪些路径要 key：``/api`` 与 ``/api/*``，探针除外。"""
    if path == PING_PATH:
        return False
    return path == "/api" or path.startswith("/api/")
