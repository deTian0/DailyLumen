"""ClickUp REST 客户端（标准库 urllib）：认证 / 任务 / 评论 / 自定义字段。

HTTP 细节集中在此；归日规则、素材渲染、写 md 等编排留在 ``pipeline.clickup*``。
``get`` / ``put`` / ``post`` 均可注入，测试全离线。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ...config import CLICKUP_BASE_URL, CLICKUP_TIMEOUT_S

# ClickUp list 任务接口单页上限 100 —— 超过就必须翻页，否则静默少拿
PAGE_SIZE = 100
MAX_PAGES = 20

# 429 限流：最多重试次数与单次最长等待（秒），防止紧循环与长时间阻塞
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT_S = 60.0

Fetcher = Callable[..., dict]
Mutator = Callable[..., dict]


def _rate_limit_wait(err: urllib.error.HTTPError) -> float:
    """按 ``X-RateLimit-Reset``（Unix 时间戳，秒）算等待时长，夹在 [1, 60] 秒。"""
    headers = getattr(err, "headers", None) or {}
    try:
        reset = float(headers.get("X-RateLimit-Reset"))
    except (TypeError, ValueError):
        return 10.0
    if reset > 1e12:  # 若按毫秒给出，统一换算成秒
        reset /= 1000.0
    return min(max(reset - time.time(), 1.0), RATE_LIMIT_MAX_WAIT_S)


def auth_headers(api_key: str, *, json_body: bool = False) -> dict[str, str]:
    """组装 Authorization（及可选 Content-Type）。"""
    h = {"Authorization": api_key}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def http_get(
    path: str,
    key: str,
    *,
    timeout: float = CLICKUP_TIMEOUT_S,
    base_url: str = CLICKUP_BASE_URL,
    urlopen=None,
) -> dict:
    """GET 一个 ClickUp API 路径，返回解析后的 JSON。

    遇 429（每分钟每 token 限额）按 ``X-RateLimit-Reset`` 有上限地等待后重试，
    重试次数耗尽仍 429 则原样抛出，由上层映射为 ``rate_limited``。
    """
    opener = urlopen or urllib.request.urlopen
    req = urllib.request.Request(base_url.rstrip("/") + path)
    for k, v in auth_headers(key).items():
        req.add_header(k, v)
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            with opener(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt >= RATE_LIMIT_RETRIES:
                raise
            time.sleep(_rate_limit_wait(e))
    raise AssertionError("unreachable")  # pragma: no cover


def http_put(
    path: str,
    key: str,
    body: dict,
    *,
    timeout: float = CLICKUP_TIMEOUT_S,
    base_url: str = CLICKUP_BASE_URL,
    urlopen=None,
) -> dict:
    """PUT 一个 ClickUp API 路径，返回解析后的 JSON。"""
    opener = urlopen or urllib.request.urlopen
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path, data=data, method="PUT"
    )
    for k, v in auth_headers(key, json_body=True).items():
        req.add_header(k, v)
    with opener(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post(
    path: str,
    key: str,
    body: dict,
    *,
    timeout: float = CLICKUP_TIMEOUT_S,
    base_url: str = CLICKUP_BASE_URL,
    urlopen=None,
) -> dict:
    """POST 一个 ClickUp API 路径，返回解析后的 JSON。"""
    opener = urlopen or urllib.request.urlopen
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path, data=data, method="POST"
    )
    for k, v in auth_headers(key, json_body=True).items():
        req.add_header(k, v)
    with opener(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_delete(
    path: str,
    key: str,
    *,
    timeout: float = CLICKUP_TIMEOUT_S,
    base_url: str = CLICKUP_BASE_URL,
    urlopen=None,
) -> dict | None:
    """DELETE；响应体可为空。"""
    opener = urlopen or urllib.request.urlopen
    req = urllib.request.Request(
        base_url.rstrip("/") + path, method="DELETE"
    )
    for k, v in auth_headers(key).items():
        req.add_header(k, v)
    with opener(req, timeout=timeout) as resp:
        raw = resp.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


class Client:
    """可注入 transport 的 ClickUp 门面（常用能力）。

    构造**不**发网络请求。方法覆盖现有用法并略扩「常用」：
    list 任务（分页）、get/create/update task、comments、自定义字段。
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        get: Fetcher | None = None,
        put: Mutator | None = None,
        post: Mutator | None = None,
        delete: Callable[..., Any] | None = None,
    ):
        self.api_key = api_key
        self.base_url = (base_url or CLICKUP_BASE_URL).rstrip("/")
        self.timeout = float(
            timeout if timeout is not None else CLICKUP_TIMEOUT_S
        )
        self._get = get
        self._put = put
        self._post = post
        self._delete = delete

    def get(self, path: str) -> dict:
        if self._get is not None:
            return self._get(path, self.api_key, timeout=self.timeout) or {}
        return http_get(
            path, self.api_key, timeout=self.timeout, base_url=self.base_url
        )

    def put(self, path: str, body: dict) -> dict:
        if self._put is not None:
            return self._put(path, self.api_key, body, timeout=self.timeout) or {}
        return http_put(
            path,
            self.api_key,
            body,
            timeout=self.timeout,
            base_url=self.base_url,
        )

    def post(self, path: str, body: dict) -> dict:
        if self._post is not None:
            return self._post(path, self.api_key, body, timeout=self.timeout) or {}
        return http_post(
            path,
            self.api_key,
            body,
            timeout=self.timeout,
            base_url=self.base_url,
        )

    def delete(self, path: str) -> dict | None:
        if self._delete is not None:
            return self._delete(path, self.api_key, timeout=self.timeout)
        return http_delete(
            path, self.api_key, timeout=self.timeout, base_url=self.base_url
        )

    # ---- 任务 ------------------------------------------------------------
    def list_tasks(
        self,
        list_id: str,
        *,
        include_closed: bool = True,
        subtasks: bool = True,
        page_size: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES,
    ) -> list[dict]:
        """拉一个 list 的全部任务（含子任务与已完成），按 id 去重。

        ⚠️ 必须 ``include_closed=true``，否则已完成整批漏掉；
        ``subtasks=true`` 翻页会重复返回，按 id 去重。
        """
        seen: set[str] = set()
        out: list[dict] = []
        for page in range(max_pages):
            qs = (
                f"/list/{list_id}/task?subtasks={'true' if subtasks else 'false'}"
                f"&include_closed={'true' if include_closed else 'false'}"
                f"&page={page}"
            )
            batch = (self.get(qs) or {}).get("tasks") or []
            for t in batch:
                tid = t.get("id")
                if tid in seen:
                    continue
                seen.add(tid)
                out.append(t)
            if len(batch) < page_size:
                break
        return out

    def get_task(self, task_id: str) -> dict:
        """GET ``/task/{id}``。"""
        return self.get(f"/task/{task_id}") or {}

    def create_task(self, list_id: str, name: str, **fields: Any) -> dict:
        """POST ``/list/{id}/task``；``fields`` 透传 ClickUp 请求体字段。"""
        body = {"name": name, **fields}
        return self.post(f"/list/{list_id}/task", body) or {}

    def update_task(self, task_id: str, **fields: Any) -> dict:
        """PUT ``/task/{id}``；常用 ``status`` / ``name`` / ``due_date`` 等。"""
        return self.put(f"/task/{task_id}", dict(fields)) or {}

    def set_task_status(self, task_id: str, status: str) -> dict:
        """便捷：只改状态。"""
        return self.update_task(task_id, status=status)

    def delete_task(self, task_id: str) -> dict | None:
        """DELETE ``/task/{id}``（薄封装；复盘 CLI 默认不暴露）。"""
        return self.delete(f"/task/{task_id}")

    def get_list(self, list_id: str) -> dict:
        """GET ``/list/{id}`` 只读元数据（名称 / 状态等）。"""
        return self.get(f"/list/{list_id}") or {}

    # ---- 评论 ------------------------------------------------------------
    def list_comments(self, task_id: str) -> list[dict]:
        """GET ``/task/{id}/comment``。"""
        data = self.get(f"/task/{task_id}/comment") or {}
        return list(data.get("comments") or [])

    def add_comment(self, task_id: str, comment_text: str, **fields: Any) -> dict:
        """POST ``/task/{id}/comment``。"""
        body = {"comment_text": comment_text, **fields}
        return self.post(f"/task/{task_id}/comment", body) or {}

    # ---- 自定义字段 ------------------------------------------------------
    def set_custom_field(
        self, task_id: str, field_id: str, value: Any, **extra: Any
    ) -> dict:
        """POST ``/task/{id}/field/{field_id}``。"""
        body = {"value": value, **extra}
        return self.post(f"/task/{task_id}/field/{field_id}", body) or {}

    def get_custom_fields(self, task: dict | None = None, *, task_id: str | None = None) -> list[dict]:
        """从任务对象或再 GET 一次，取出 ``custom_fields`` 列表。"""
        if task is None:
            if not task_id:
                raise ValueError("需要 task 或 task_id")
            task = self.get_task(task_id)
        return list((task or {}).get("custom_fields") or [])


def fetch_tasks(
    list_id: str,
    key: str,
    *,
    fetch: Fetcher | None = None,
    timeout: float = CLICKUP_TIMEOUT_S,
) -> list[dict]:
    """兼容旧签名：拉 list 全量任务（分页 + 去重）。

    ``fetch`` 可注入（测试用假实现）；未注入时走 :class:`Client`。
    """
    if fetch is not None:
        seen: set[str] = set()
        out: list[dict] = []
        for page in range(MAX_PAGES):
            path = (
                f"/list/{list_id}/task?subtasks=true&include_closed=true&page={page}"
            )
            batch = (fetch(path, key, timeout=timeout) or {}).get("tasks") or []
            for t in batch:
                tid = t.get("id")
                if tid in seen:
                    continue
                seen.add(tid)
                out.append(t)
            if len(batch) < PAGE_SIZE:
                break
        return out
    return Client(key, timeout=timeout).list_tasks(list_id)


__all__ = [
    "Client",
    "MAX_PAGES",
    "PAGE_SIZE",
    "auth_headers",
    "fetch_tasks",
    "http_delete",
    "http_get",
    "http_post",
    "http_put",
]
