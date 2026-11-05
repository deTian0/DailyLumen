"""FastAPI 应用工厂：Host/Origin 守卫、统一错误体、health、dist 托管（SPA fallback）。"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import BASE_DIR
from .health import build_health

DEFAULT_DIST_DIR = os.path.join(BASE_DIR, "web", "dist")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_NO_DIST_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>DailyLumen</title></head>
<body style="font-family:system-ui;padding:2rem;max-width:40rem">
<h1>前端尚未构建</h1>
<p>未找到 <code>web/dist/index.html</code>。请先在 <code>web/</code> 下执行
<code>npm ci &amp;&amp; npm run build</code>，或使用仓库入库的 <code>web/dist</code>。</p>
<p>API 仍可用：<a href="/api/health">/api/health</a></p>
</body></html>"""


class IntegrationsOut(BaseModel):
    clickup: bool
    keepstrong: bool
    deepseek: bool


class HealthOut(BaseModel):
    """health 响应模型（字段白名单；新增字段必须显式声明，杜绝整对象直出）。"""

    status: str
    version: str
    llm_mode: str
    integrations: IntegrationsOut
    ai_enabled: bool
    db_present: bool
    readonly: bool


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _host_of(value: str) -> str:
    """从 Host 头（host[:port] / [::1]:port）取主机名，小写。"""
    v = value.strip().lower()
    if v.startswith("["):
        return v[1 : v.find("]")] if "]" in v else v
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


def create_app(
    *,
    dist_dir: str | None = None,
    write_enabled: bool = False,
    allowed_hosts: frozenset[str] | None = None,
    extra_routers: list[Any] | None = None,
) -> FastAPI:
    """构造应用。

    :param dist_dir: 前端构建目录；默认 ``web/dist``。
    :param write_enabled: 是否允许写接口（``serve --enable-write``）；默认只读。
    :param allowed_hosts: 允许的 Host 主机名集合；默认仅回环（防 DNS rebinding）。
    :param extra_routers: 业务路由（``APIRouter`` 列表），W3 起各里程碑的 ``/api/*``
        接口**必须**经此参数接入，而不是在 ``create_app`` 返回后 ``app.add_api_route``——
        后者会排在 SPA 通配路由之后，被 ``spa()`` 先截获（Starlette 按注册顺序匹配）。
    """
    dist = os.path.abspath(dist_dir or DEFAULT_DIST_DIR)
    hosts = frozenset(h.lower() for h in (allowed_hosts or LOOPBACK_HOSTS))

    app = FastAPI(title="DailyLumen 看板 API", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.write_enabled = write_enabled
    app.state.dist_dir = dist

    @app.middleware("http")
    async def host_origin_guard(request: Request, call_next):
        host = _host_of(request.headers.get("host", ""))
        if host not in hosts:
            return _error(403, "bad_host", "不允许的 Host（仅限本机访问）")
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and _host_of(urlsplit(origin).netloc) not in hosts:
                return _error(403, "bad_origin", "不允许的跨站来源")
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_req: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, f"http_{exc.status_code}", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_req: Request, _exc: RequestValidationError):
        # 不回显输入值，避免把任何敏感参数反射回响应
        return _error(422, "invalid_request", "请求参数不合法")

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, _exc: Exception):
        return _error(500, "internal_error", "服务内部错误")

    @app.get("/api/health", response_model=HealthOut)
    def health() -> dict[str, Any]:
        return build_health(write_enabled=app.state.write_enabled)

    # 业务路由必须在 SPA 通配之前注册
    for router in extra_routers or []:
        app.include_router(router)

    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    # SPA fallback 用 api_route 接住全部方法：未注册的 /api/* 一律统一 404 错误体，
    # 不落到 index.html。⚠️ 不用「/api/{rest:path}」兜底路由——它会挡住之后
    # include_router / add_api_route 追加的接口（Starlette 按注册顺序匹配）。
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                   include_in_schema=False)
    def spa(request: Request, path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        if request.method != "GET":
            raise HTTPException(status_code=405, detail="方法不允许")
        index = os.path.join(dist, "index.html")
        if not os.path.isfile(index):
            return HTMLResponse(_NO_DIST_HTML, status_code=503)
        if path:
            candidate = os.path.abspath(os.path.join(dist, path))
            # 防路径穿越：必须仍在 dist 内
            if os.path.commonpath([dist, candidate]) == dist and os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(index)

    return app
