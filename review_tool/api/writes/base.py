"""写操作框架底座（W13 从 ``write_ops`` 拆出）：一次性 token、预览出参、DB 备份、动作注册表。

两段式：``plan_*`` 只算预览（不写任何东西），把「将要写的确切内容」存进服务端一次性
确认 token；``confirm(token)`` 才执行，且执行的正是预览过的内容。新增写类型只需：

1. 在域模块里写 ``plan_x``（调 ``plan_out``）与 ``_apply_x``；
2. 用 ``@register("x", needs=(...))`` 登记 apply，``needs`` 声明它要的上下文
   （``db_path`` / ``backup_dir`` / ``env`` / ``cu_client`` / ``ks_client``）；
3. 在 ``routes_write`` 加一条 ``/x/plan`` 路由。

不依赖 fastapi / pydantic。写操作全局串行（NFR-9 SQLite 单写者）。
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from typing import Any

from ..queries import QueryError

TOKEN_TTL_S = 300
WRITE_LOCK = threading.Lock()

# confirm 可注入的上下文键（与 confirm(...) 的关键字参数一一对应）
CONTEXT_KEYS = ("db_path", "backup_dir", "env", "cu_client", "ks_client")


class TokenStore:
    """一次性确认 token（内存；进程重启即全部失效）。"""

    def __init__(self, ttl_s: float = TOKEN_TTL_S, clock=time.monotonic):
        self._ttl = ttl_s
        self._clock = clock
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def issue(self, action: str, payload: dict[str, Any]) -> str:
        tok = secrets.token_urlsafe(24)
        with self._lock:
            now = self._clock()
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            self._items[tok] = (now + self._ttl, {"action": action, **payload})
        return tok

    def take(self, token: str) -> dict[str, Any]:
        with self._lock:
            item = self._items.pop(token or "", None)
        if item is None:
            raise QueryError(409, "token_invalid", "确认已失效或已使用，请重新预览后再确认")
        exp, payload = item
        if exp <= self._clock():
            raise QueryError(409, "token_expired", "确认已过期（5 分钟），请重新预览")
        return payload


# ---------------------------------------------------------------------------
# 动作注册表：action -> (apply 函数, 需要的上下文键)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, tuple[Callable[..., dict[str, Any]], tuple[str, ...]]] = {}


def register(*actions: str, needs: tuple[str, ...] = ()):
    """登记 apply 函数；同一函数可对应多个 action（如 task_create / task_status）。"""
    bad = set(needs) - set(CONTEXT_KEYS)
    if bad:
        raise ValueError(f"未知上下文键：{sorted(bad)}")

    def deco(fn):
        for a in actions:
            if a in _REGISTRY:
                raise ValueError(f"写动作重复登记：{a}")
            _REGISTRY[a] = (fn, tuple(needs))
        return fn

    return deco


def registered_actions() -> list[str]:
    return sorted(_REGISTRY)


def confirm(tokens: TokenStore, token: str, **ctx: Any) -> dict[str, Any]:
    """执行预览过的写操作（单次、串行）；返回结果 + 等价 CLI。"""
    unknown = set(ctx) - set(CONTEXT_KEYS)
    if unknown:
        raise TypeError(f"confirm 不接受参数：{sorted(unknown)}")
    p = tokens.take(token)
    entry = _REGISTRY.get(p["action"])
    if entry is None:  # pragma: no cover - issue() 只发已登记动作
        raise QueryError(400, "bad_action", "未知写操作")
    fn, needs = entry
    with WRITE_LOCK:
        out = fn(p, **{k: ctx.get(k) for k in needs})
    return {"action": p["action"], "date": p["date"], "cli": p["cli"], "result": out}


# ---------------------------------------------------------------------------
# 共用小工具
# ---------------------------------------------------------------------------

def sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def plan_out(tokens: TokenStore, action: str, payload: dict[str, Any], *,
             preview: dict[str, Any], cli: str) -> dict[str, Any]:
    if action not in _REGISTRY:  # 防止发出无法确认的 token
        raise QueryError(500, "bad_action", f"写动作未登记：{action}")
    tok = tokens.issue(action, {**payload, "cli": cli})
    return {"action": action, "token": tok, "expires_in": TOKEN_TTL_S,
            "cli": cli, "preview": preview}


def today() -> str:
    return datetime.date.today().isoformat()


def backup_db(db_path: str, backup_dir: str | None) -> str:
    from ...config import LOCAL_DIR

    d = backup_dir or os.path.join(LOCAL_DIR, "backups", "web")
    os.makedirs(d, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dst = os.path.join(d, f"{stamp}-{os.path.basename(db_path)}")
    shutil.copy2(db_path, dst)
    if sha_file(dst) != sha_file(db_path):
        raise QueryError(500, "backup_failed", "数据库备份校验失败，已中止写入")
    return dst


def require_db(db_path: str | None) -> str:
    from ...config import DB_PATH

    path = os.path.abspath(db_path or DB_PATH)
    if not os.path.isfile(path):
        raise QueryError(503, "db_missing", "数据库尚未建立，请先在 CLI 执行 ingest")
    return path


def clean_text(value: str, *, field: str, limit: int) -> str:
    v = (value or "").strip()
    if not v or len(v) > limit or any(ord(c) < 32 for c in v):
        raise QueryError(422, "invalid_param", f"{field} 为空、过长（>{limit}）或含控制字符")
    return v


def quote_arg(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
