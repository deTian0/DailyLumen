"""DeepSeek HTTP 客户端 —— 兼容旧导入路径。

实现已迁至 ``review_tool.integrations.deepseek``；本模块再导出，避免大面积破测试。
仍受 ``DAILYLUMEN_LLM_MODE`` + ``INTEGRATION_DEEPSEEK_ENABLED`` 双重门禁。
"""
from __future__ import annotations

from ..integrations.deepseek import (  # noqa: F401
    CHAT_COMPLETIONS_PATH,
    DEFAULT_DEEPSEEK_VISION_MODEL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_S,
    RETRYABLE_HTTP_CODES,
    Client,
    DeepSeekCredError,
    DeepSeekError,
    DeepSeekModeError,
    assistant_text,
    build_chat_url,
    build_headers,
    friendly_http_hint,
    get_llm_mode,
    guess_image_mime,
    image_bytes_to_data_url,
    image_file_to_data_url,
    require_deepseek_mode,
    vision_user_content,
)

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "Client",
    "DEFAULT_DEEPSEEK_VISION_MODEL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_BACKOFF_S",
    "DeepSeekCredError",
    "DeepSeekError",
    "DeepSeekModeError",
    "RETRYABLE_HTTP_CODES",
    "assistant_text",
    "build_chat_url",
    "build_headers",
    "friendly_http_hint",
    "get_llm_mode",
    "guess_image_mime",
    "image_bytes_to_data_url",
    "image_file_to_data_url",
    "require_deepseek_mode",
    "vision_user_content",
]
