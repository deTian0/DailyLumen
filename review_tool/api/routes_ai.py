"""Web 看板路由：AI 评价预览 + mode 门禁（W8）。

- ``GET  /api/ai/status``：门禁状态（mode / 是否允许 / 原因），不含凭据。
- ``POST /api/ai/review-preview``：= ``llm-review DATE --dry-run``。走 POST 是因为会触网计费，
  需受 Origin 守卫保护（浏览器跨站请求无法触发）；**不写 md、不写库**。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from . import ai_queries as aq
from .queries import readonly


class AiStatusOut(BaseModel):
    mode: str
    allowed: bool
    reason: str | None = None


class ReviewPreviewOut(BaseModel):
    date: str
    section: str
    old_section: str
    diff_text: str
    context_empty: bool
    flags: list[Any]
    written: bool
    cli: str


def build_router(*, db_path: str | None = None, client=None, mode: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/ai", tags=["ai"])

    @router.get("/status", response_model=AiStatusOut)
    def get_status():
        return aq.ai_status()

    @router.post("/review-preview", response_model=ReviewPreviewOut)
    def post_review_preview(date: str | None = Query(default=None)):
        with readonly(db_path) as conn:
            return aq.review_preview(conn, date, client=client, mode=mode)

    return router
