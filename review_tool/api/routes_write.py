"""Web 看板路由：P2 写操作第一批（W9）。**仅 ``serve --enable-write`` 时挂载**。

两段式确认流：
1. ``POST /api/write/{habits-sync|ai-draft|finalize}/plan`` → 预览 + 一次性 token + 等价 CLI（不写任何东西）
2. ``POST /api/write/confirm``（JSON ``{"token": ...}``）→ 执行预览过的内容，写后回读校验

全部是 POST：受 ``app.host_origin_guard`` 的 Host / Origin 校验；confirm 要求 JSON 体，
跨站表单无法构造（非简单请求触发 CORS 预检，而本服务不发 CORS 头）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from . import write_ops as wo
from .queries import readonly


class PlanOut(BaseModel):
    action: str
    token: str
    expires_in: int
    cli: str
    preview: dict[str, Any]


class ConfirmIn(BaseModel):
    token: str


class ConfirmOut(BaseModel):
    action: str
    date: str
    cli: str
    result: dict[str, Any]


def build_router(*, db_path: str | None = None, fetch=None, env=None, client=None,
                 mode: str | None = None, backup_dir: str | None = None,
                 tokens: wo.TokenStore | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/write", tags=["write"])
    store = tokens or wo.TokenStore()

    @router.post("/habits-sync/plan", response_model=PlanOut)
    def plan_habits(date: str | None = Query(default=None)):
        return wo.plan_habits_sync(store, date, fetch=fetch, env=env)

    @router.post("/ai-draft/plan", response_model=PlanOut)
    def plan_ai(date: str | None = Query(default=None)):
        with readonly(db_path) as conn:
            return wo.plan_ai_draft(store, conn, date, client=client, mode=mode)

    @router.post("/finalize/plan", response_model=PlanOut)
    def plan_final(date: str = Query(...)):
        return wo.plan_finalize(store, date)

    @router.post("/confirm", response_model=ConfirmOut)
    def post_confirm(body: ConfirmIn):
        return wo.confirm(store, body.token, db_path=db_path, backup_dir=backup_dir)

    return router
