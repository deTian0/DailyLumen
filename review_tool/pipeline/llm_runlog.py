"""LLM 最近一次运行摘要（落 ``local/``，gitignore；无密钥 / 无正文隐私大段）。

供 ``llm-review`` / ``llm-vision`` 写入、``doctor`` 只读展示。
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from ..config import LOCAL_DIR

DEFAULT_LLM_LAST_RUN_NAME = "llm_last_run.json"
# 正文类字段一律不落；匹配到即丢弃
_FORBIDDEN_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|sk-|password|secret|token|"
    r"raw_text|section|prompt|content|body|message|data_url|base64)",
    re.I,
)
_ALLOWED_TOP = frozenset({
    "command",
    "mode",
    "ok",
    "day",
    "ts",
    "error_kind",
    "error_summary",
    "missing_fields",
    "filled_fields",
    "image_count",
    "written",
    "changed",
})


def default_llm_last_run_path() -> str:
    """固定落点：``local/llm_last_run.json``（可被 Settings 覆盖）。"""
    return os.path.join(LOCAL_DIR, DEFAULT_LLM_LAST_RUN_NAME)


def sanitize_run_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    """只保留允许的顶层键；字符串截断；剔除疑似密钥/正文。"""
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k)
        if key not in _ALLOWED_TOP:
            continue
        if _FORBIDDEN_KEY_RE.search(key):
            continue
        if isinstance(v, str):
            s = v.strip()
            if _FORBIDDEN_KEY_RE.search(s) and ("sk-" in s.lower() or "bearer" in s.lower()):
                continue
            out[key] = s[:240]
        elif isinstance(v, bool):
            out[key] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = v
        elif isinstance(v, list):
            # 仅允许短字符串列表（字段名）
            cleaned = []
            for item in v[:40]:
                if isinstance(item, str) and not _FORBIDDEN_KEY_RE.search(item):
                    cleaned.append(item[:64])
            out[key] = cleaned
        elif v is None:
            continue
    return out


def write_llm_last_run(
    record: Mapping[str, Any],
    *,
    path: str | None = None,
) -> str:
    """写入摘要 JSON；回读校验。返回实际路径。"""
    dest = path or default_llm_last_run_path()
    payload = sanitize_run_record(record)
    if "ts" not in payload:
        payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(dest, encoding="utf-8") as f:
        got = f.read()
    if got.replace("\r\n", "\n") != text.replace("\r\n", "\n"):
        raise OSError(f"llm 运行日志写盘回读不一致: {dest}")
    # 红线：落盘内容不得含 api key 字面
    low = got.lower()
    if "sk-" in low and "api" in low:
        # 宽松：若 sanitize 后仍出现 sk- 前缀长串则报警
        if re.search(r"sk-[a-z0-9]{8,}", low):
            raise OSError("llm 运行日志疑似含 API key，已拒绝保留")
    return dest


def read_llm_last_run(path: str | None = None) -> dict[str, Any] | None:
    """读最近一次摘要；文件不存在或损坏返回 None。"""
    dest = path or default_llm_last_run_path()
    if not os.path.isfile(dest):
        return None
    try:
        with open(dest, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return sanitize_run_record(data)


__all__ = [
    "DEFAULT_LLM_LAST_RUN_NAME",
    "default_llm_last_run_path",
    "read_llm_last_run",
    "sanitize_run_record",
    "write_llm_last_run",
]
