"""ClickUp 集成门面：凭据 + HTTP 客户端 + 常用 API。

稳定导出（供 CLI / pipeline 调用）::

    CredError, load_creds
    Client, fetch_tasks, http_get, http_put, http_post, http_delete
    auth_headers, PAGE_SIZE, MAX_PAGES

编排（归日 / 渲染 / 写 md）仍在 ``review_tool.pipeline.clickup*``。
"""

from .client import (
    MAX_PAGES,
    PAGE_SIZE,
    Client,
    auth_headers,
    fetch_tasks,
    http_delete,
    http_get,
    http_post,
    http_put,
)
from .creds import CredError, load_creds

__all__ = [
    "Client",
    "CredError",
    "MAX_PAGES",
    "PAGE_SIZE",
    "auth_headers",
    "fetch_tasks",
    "http_delete",
    "http_get",
    "http_post",
    "http_put",
    "load_creds",
]
