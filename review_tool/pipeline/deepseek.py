"""DeepSeek HTTP 客户端（标准库 urllib，OpenAI 兼容 chat completions）。

仅当 ``DAILYLUMEN_LLM_MODE=deepseek`` 时允许发请求；``workbuddy`` 模式明确拒绝。
⛔ 不引入 openai / DeepSeek SDK；⛔ import 时不发网络请求。
产出契约仍是「先落 md 再 ingest」（见 ``docs/LLM能力拆分草案.md`` §4）；本模块只做 HTTP。
Vision：``content`` 数组 + ``image_url`` data URL；默认模型 ``deepseek-flash``。
v1.55.0：有限次退避重试 + 配额/HTTP 友好提示；多图 content 组装。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..config import SETTINGS
from ..core.llm_mode import (
    LLM_MODE_DEEPSEEK,
    LLM_MODE_WORKBUDDY,
    normalize_llm_mode,
)
from ..settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_DEEPSEEK_TIMEOUT_S,
)

Opener = Callable[..., Any]

CHAT_COMPLETIONS_PATH = "/chat/completions"
# Vision 用 Flash（文档：deepseek-flash；旧名 deepseek-v4-flash-vision-exp 仍可接受）
DEFAULT_DEEPSEEK_VISION_MODEL = "deepseek-flash"

# 有限次退避（含首次共 max_retries+1 次尝试）
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_S = 0.8
RETRYABLE_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504})


class DeepSeekError(RuntimeError):
    """DeepSeek 调用失败。"""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class DeepSeekModeError(DeepSeekError):
    """当前 mode 不允许调用 DeepSeek。"""


class DeepSeekCredError(DeepSeekError):
    """缺少 API Key。"""


def get_llm_mode(*, settings: Any | None = None) -> str:
    """读取当前互斥 mode（默认从 ``SETTINGS``）。"""
    s = SETTINGS if settings is None else settings
    return normalize_llm_mode(getattr(s, "llm_mode", LLM_MODE_WORKBUDDY))


def require_deepseek_mode(mode: str | None = None, *, settings: Any | None = None) -> str:
    """断言当前为 deepseek；否则抛清晰错误（workbuddy 下禁止外部调用）。"""
    m = normalize_llm_mode(mode) if mode is not None else get_llm_mode(settings=settings)
    if m != LLM_MODE_DEEPSEEK:
        raise DeepSeekModeError(
            f"当前 DAILYLUMEN_LLM_MODE={m!r}，禁止调用 DeepSeek API"
            f"（仅 {LLM_MODE_DEEPSEEK!r} 模式可调；"
            f"{LLM_MODE_WORKBUDDY!r} 由宿主 Agent 代劳落 md）"
        )
    return m


def build_chat_url(base_url: str) -> str:
    """拼接 chat completions URL；兼容根地址带 / 或不带。"""
    root = (base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    return root + CHAT_COMPLETIONS_PATH


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def guess_image_mime(path: str) -> str:
    """按扩展名猜 MIME；未知则 ``image/png``。"""
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("image/"):
        return mime
    return "image/png"


def image_bytes_to_data_url(raw: bytes, *, mime: str = "image/png") -> str:
    """原始图片字节 → ``data:<mime>;base64,...``。"""
    if not raw:
        raise DeepSeekError("图片字节为空")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def image_file_to_data_url(path: str) -> str:
    """本地图片文件 → data URL（只读文件，不发网）。"""
    with open(path, "rb") as f:
        raw = f.read()
    return image_bytes_to_data_url(raw, mime=guess_image_mime(path))


def vision_user_content(
    text: str,
    image_data_url: str | Sequence[str],
    *,
    detail: str | None = "low",
) -> list[dict[str, Any]]:
    """组装多模态 user ``content`` 数组（text + 一张或多张 image_url）。"""
    urls = (
        [image_data_url]
        if isinstance(image_data_url, str)
        else list(image_data_url)
    )
    if not urls:
        raise DeepSeekError("至少需要一张图片 data URL")
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for url in urls:
        image_url: dict[str, Any] = {"url": url}
        if detail:
            image_url["detail"] = detail
        parts.append({"type": "image_url", "image_url": image_url})
    return parts


def assistant_text(resp: Mapping[str, Any]) -> str:
    """从 chat completions 响应取出 assistant 文本；缺失则空串。"""
    try:
        choices = resp.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        # 少数兼容实现可能返回 parts 列表
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text") or ""))
                elif isinstance(p, str):
                    parts.append(p)
            return "".join(parts)
        return str(content)
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""


def friendly_http_hint(status: int | None, detail: str = "") -> str:
    """把 HTTP 状态码翻译成可操作的中文提示（不含密钥）。"""
    d = (detail or "").strip()
    tail = f"（详情截断：{d[:160]}）" if d else ""
    if status == 401:
        return (
            "密钥无效或未授权（HTTP 401）。请检查 local/.env 的 DEEPSEEK_API_KEY，"
            "勿把密钥写进报告或 git。" + tail
        )
    if status == 402:
        return "账户余额不足或需付费（HTTP 402）。请到 DeepSeek 控制台充值后再试。" + tail
    if status == 403:
        return "访问被拒绝（HTTP 403）。确认模型名与账号权限。" + tail
    if status == 404:
        return "端点或模型不存在（HTTP 404）。检查 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL。" + tail
    if status == 429:
        return (
            "触发限流或配额（HTTP 429）。请稍后重试，或降低并发 / 换时段。"
            "本客户端会自动有限次退避。" + tail
        )
    if status is not None and status >= 500:
        return f"DeepSeek 服务端异常（HTTP {status}）。可稍后重试。" + tail
    if status is not None:
        return f"DeepSeek HTTP {status}{tail}"
    return f"DeepSeek 请求失败{tail}"


def _read_json_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DeepSeekError(f"DeepSeek 响应非 JSON：{e}") from e


def _detail_from_body(parsed: Any) -> str:
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)[:300]
    return ""


class Client:
    """可注入 ``urlopen`` 的 DeepSeek 客户端（测试全离线）。

    构造**不**发网络请求。``chat_completions`` 在 mode≠deepseek 时立即拒绝。
    对 429 / 5xx 等做有限次指数退避重试。
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        mode: str | None = None,
        settings: Any | None = None,
        urlopen: Opener | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
        sleeper: Callable[[float], None] | None = None,
    ):
        s = SETTINGS if settings is None else settings
        self.api_key = (
            api_key if api_key is not None else getattr(s, "deepseek_api_key", "") or ""
        )
        raw_base = (
            base_url
            if base_url is not None
            else getattr(s, "deepseek_base_url", "") or ""
        )
        self.base_url = (raw_base or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        raw_model = (
            model if model is not None else getattr(s, "deepseek_model", "") or ""
        )
        self.model = raw_model or DEFAULT_DEEPSEEK_MODEL
        if timeout is not None:
            self.timeout = float(timeout)
        else:
            self.timeout = float(
                getattr(s, "deepseek_timeout_s", None) or DEFAULT_DEEPSEEK_TIMEOUT_S
            )
        self.mode = (
            normalize_llm_mode(mode)
            if mode is not None
            else get_llm_mode(settings=s)
        )
        self._urlopen = urlopen or urllib.request.urlopen
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_s = float(retry_backoff_s)
        self._sleep = sleeper or time.sleep

    def chat_completions(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """POST ``/chat/completions``；仅 deepseek 模式；缺 key 报错；可重试。"""
        require_deepseek_mode(self.mode)
        if not (self.api_key or "").strip():
            raise DeepSeekCredError(
                "DEEPSEEK_API_KEY 未配置（仅 deepseek 模式需要；写入 local/.env，"
                "勿写入报告 / git / llm_last_run）"
            )
        if not messages:
            raise DeepSeekError("messages 不能为空")

        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": list(messages),
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if extra:
            body.update(dict(extra))

        url = build_chat_url(self.base_url)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=build_headers(self.api_key),
            method="POST",
        )

        attempts = self.max_retries + 1
        last_err: DeepSeekError | None = None
        for attempt in range(attempts):
            try:
                with self._urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return _read_json_body(raw)
            except urllib.error.HTTPError as e:
                raw = e.read() if hasattr(e, "read") else b""
                parsed = _read_json_body(raw) if raw else None
                detail = _detail_from_body(parsed)
                hint = friendly_http_hint(e.code, detail)
                retryable = e.code in RETRYABLE_HTTP_CODES
                last_err = DeepSeekError(
                    hint, status=e.code, retryable=retryable
                )
                if retryable and attempt < attempts - 1:
                    self._sleep(self.retry_backoff_s * (2 ** attempt))
                    continue
                raise last_err from e
            except urllib.error.URLError as e:
                last_err = DeepSeekError(
                    f"DeepSeek 网络不可达：{getattr(e, 'reason', e)}。"
                    "请检查网络 / 代理 / DEEPSEEK_BASE_URL。",
                    retryable=True,
                )
                if attempt < attempts - 1:
                    self._sleep(self.retry_backoff_s * (2 ** attempt))
                    continue
                raise last_err from e
        assert last_err is not None
        raise last_err

    def vision_completions(
        self,
        text: str,
        image_data_url: str | Sequence[str],
        *,
        model: str | None = None,
        detail: str | None = "low",
        temperature: float | None = 0,
        max_tokens: int | None = 1024,
        system: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """多模态 chat：默认 ``deepseek-flash``；支持多图；仍受 mode / key 门禁。"""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "user",
                "content": vision_user_content(
                    text, image_data_url, detail=detail
                ),
            }
        )
        return self.chat_completions(
            messages,
            model=model or DEFAULT_DEEPSEEK_VISION_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            extra=extra,
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
