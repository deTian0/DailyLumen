"""集成最近一次失败摘要（落 ``local/``，gitignore；无密钥）。

供 ClickUp / 练练 CLI 写入、``doctor`` / ``day-help`` 只读展示（I6）。
对齐 ``pipeline.llm_runlog`` 的「无密钥、短摘要、回读校验」口径。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from ..config import LOCAL_DIR

DEFAULT_LAST_ERROR_NAME = "integration_last_error.json"

_FORBIDDEN_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|sk-|password|secret|token|"
    r"pk_|raw_text|prompt|content|body|message)",
    re.I,
)
_ALLOWED_TOP = frozenset({
    "integration",
    "command",
    "ok",
    "ts",
    "error_kind",
    "error_summary",
    "http_code",
    "hint",
})

# 与 KeyGuidance / ClickUp 401 口径对齐的可执行下一步
HINTS = {
    "401": "检查 local/.env 的 API Key（ClickUp: CLICKUP_API_KEY；练练: KEEPSTRONG_API_KEY）是否失效并轮换。",
    "403": "Token 权限不足或 list/任务不可写；核对 list ID 与凭据归属同一 Workspace。",
    "426": (
        "练练技能文档过期（skillUpdateRequired）：重拉 docs/练练健身-API参考.md，"
        "更新 KEEPSTRONG_SKILL_VERSION 后重试。"
    ),
    "429": "限流：等待 Retry-After 后再试，不要紧循环。",
    "disabled": "集成已关（INTEGRATION_*_ENABLED=false）：属预期，勿当「缺数据」假阳性。",
}


def default_last_error_path() -> str:
    return os.path.join(LOCAL_DIR, DEFAULT_LAST_ERROR_NAME)


def sanitize_error_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k)
        if key not in _ALLOWED_TOP:
            continue
        if _FORBIDDEN_KEY_RE.search(key):
            continue
        if isinstance(v, str):
            s = v.strip()
            if _FORBIDDEN_KEY_RE.search(s) and (
                "sk-" in s.lower() or "bearer" in s.lower() or "pk_" in s.lower()
            ):
                continue
            out[key] = s[:240]
        elif isinstance(v, bool):
            out[key] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = v
        elif v is None:
            continue
    return out


def hint_for(*, http_code: int | str | None = None, error_kind: str = "") -> str:
    """按 HTTP 码 / 异常名给可执行下一步。"""
    code = str(http_code or "").strip()
    if code in HINTS:
        return HINTS[code]
    kind = (error_kind or "").lower()
    if "apikeyexpired" in kind or "cred" in kind:
        return HINTS["401"]
    if "skillupdate" in kind:
        return HINTS["426"]
    if "ratelimit" in kind:
        return HINTS["429"]
    if "disabled" in kind or "integrationdisabled" in kind:
        return HINTS["disabled"]
    return "见 error_summary；关集成时 doctor 不应把缺素材当库病。"


def write_last_error(
    record: Mapping[str, Any],
    *,
    path: str | None = None,
) -> str:
    """写入摘要 JSON；回读校验。返回实际路径。"""
    dest = path or default_last_error_path()
    payload = sanitize_error_record(record)
    if "ts" not in payload:
        payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "ok" not in payload:
        payload["ok"] = False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(dest, "wb") as f:
        f.write(text.encode("utf-8"))
    # 回读校验（本机写盘不可信）
    with open(dest, encoding="utf-8") as f:
        back = f.read()
    if '"ok"' not in back and "ok" in payload:
        raise OSError(f"integration last-error 回读失败: {dest}")
    if payload.get("error_kind") and str(payload["error_kind"]) not in back:
        raise OSError(f"integration last-error 回读缺 error_kind: {dest}")
    return dest


def read_last_error(*, path: str | None = None) -> dict[str, Any] | None:
    src = path or default_last_error_path()
    if not os.path.isfile(src):
        return None
    try:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return sanitize_error_record(data)


def record_integration_error(
    integration: str,
    *,
    command: str = "",
    error_kind: str = "",
    error_summary: str = "",
    http_code: int | str | None = None,
    path: str | None = None,
) -> str:
    """便捷：组装 hint 并落盘。"""
    hint = hint_for(http_code=http_code, error_kind=error_kind)
    return write_last_error(
        {
            "integration": integration,
            "command": command,
            "ok": False,
            "error_kind": error_kind or "error",
            "error_summary": error_summary,
            "http_code": http_code,
            "hint": hint,
        },
        path=path,
    )


__all__ = [
    "DEFAULT_LAST_ERROR_NAME",
    "HINTS",
    "default_last_error_path",
    "hint_for",
    "read_last_error",
    "record_integration_error",
    "sanitize_error_record",
    "write_last_error",
]
