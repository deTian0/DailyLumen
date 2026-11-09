"""Web 看板路由：ClickUp 今日 / 完成清单 / 素材预览（W3 / FR-B2 · FR-C1~C5）。

本文件只做 HTTP 适配（路径 / 查询参数 / 响应模型），编排全部转交
``api.clickup_queries``；不在此处重复任何归日 / 选取 / 渲染逻辑。

错误：直接抛 :class:`~review_tool.api.queries.QueryError`，由 ``create_app`` 的统一
处理器转成 ``{error:{code,message}}``（保留 code，前端据此给不同文案）。

``build_router(fetch=, env=, db_path=)`` 允许测试注入离线假 fetch / 凭据 / 临时库；
生产走默认（真实 ClickUp 客户端 + ``os.environ`` + ``config.DB_PATH``）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import clickup_queries as cq
from .queries import QueryError, readonly


class TaskOut(BaseModel):
    id: str
    name: str
    status: str
    list: str
    due: str | None = None
    closed_day: str | None = None
    closed_clock: str | None = None
    completion_day: str | None = None
    rebated_to: str | None = None


class ClickUpGroupOut(BaseModel):
    id: str
    name: str
    role: str
    done: list[TaskOut]
    open: list[TaskOut]
    in_progress: list[TaskOut]
    overdue: list[TaskOut]
    cross_day: list[TaskOut]


class TodayTotalsOut(BaseModel):
    done: int
    open: int
    in_progress: int
    overdue: int
    cross_day: int
    rebated: int


class TodayOut(BaseModel):
    date: str
    fetched_at: str
    groups: list[ClickUpGroupOut]
    totals: TodayTotalsOut
    bulk_hint: str | None = None
    # 刷新失败、回退到上次成功结果时为 True（FR-B2：失败保留旧数据并提示）
    stale: bool = False
    stale_code: str | None = None
    stale_reason: str | None = None


class MaterialOut(BaseModel):
    date: str
    markdown: str
    filename: str


class ClickUpDoneItemOut(BaseModel):
    name: str
    owner: str | None = None
    minutes: float | None = None
    subject: str | None = None
    is_self: bool


class ClickUpDoneDayOut(BaseModel):
    date: str
    count: int
    self_count: int
    self_sum: float | None = None
    self_max: float | None = None
    self_no_hours: int
    items: list[ClickUpDoneItemOut]


class ClickUpDoneOut(BaseModel):
    start: str
    end: str
    days: list[ClickUpDoneDayOut]
    total: int
    self_total: int
    text: str


class LastErrorOut(BaseModel):
    last: dict[str, Any] | None = None


def build_router(*, fetch=None, env=None, db_path: str | None = None,
                 cache: cq.TodayCache | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["clickup"])
    today_cache = cache or cq.TodayCache()

    def _today_with_fallback(date: str | None) -> dict[str, Any]:
        try:
            data = cq.today(date, fetch=fetch, env=env)
        except QueryError as e:
            # 参数错误不回退（那是调用方的错，不是上游故障）
            # 限流（429）也回退上次成功结果：它是上游故障，不是调用方参数错
            if e.status < 500 and e.code != "rate_limited":
                raise
            cached = today_cache.get(date or cq._today())
            if cached is None:
                raise
            return {**cached, "stale": True, "stale_code": e.code, "stale_reason": e.message}
        today_cache.put(data["date"], data)
        return data

    @router.get("/today", response_model=TodayOut)
    def get_today(date: str | None = Query(default=None, description="YYYY-MM-DD，省略为今天")):
        """今日待办 / 已办（FR-C1 / FR-C2）。上游失败时回退上次成功结果并标 stale。"""
        return _today_with_fallback(date)

    @router.post("/today/refresh", response_model=TodayOut)
    def post_today_refresh(date: str | None = Query(default=None)):
        """显式刷新（远端只读 GET，不写任何状态；走 POST 以便受 Origin 守卫）。"""
        return _today_with_fallback(date)

    @router.get("/clickup/material", response_model=MaterialOut)
    def get_clickup_material(date: str | None = Query(default=None)):
        """素材预览（FR-C5）= ``clickup DATE --stdout`` 同源 markdown（不落文件）。"""
        return cq.material(date, fetch=fetch, env=env)

    @router.get("/clickup/material.md", response_class=PlainTextResponse)
    def get_clickup_material_md(date: str | None = Query(default=None)):
        """素材预览纯文本（复制 / 下载用）。"""
        data = cq.material(date, fetch=fetch, env=env)
        return PlainTextResponse(
            data["markdown"],
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''"
                     + _quote(data["filename"])},
        )

    @router.get("/clickup/done", response_model=ClickUpDoneOut)
    def get_clickup_done(
        date: str | None = Query(default=None, description="开始日期，省略为今天"),
        end: str | None = Query(default=None, description="结束日期，省略同开始"),
    ):
        """指定日期（或区间）完成清单（FR-C3），读本地快照，不联网。"""
        with readonly(db_path) as conn:
            return cq.done(conn, date, end)

    @router.get("/integrations/errors", response_model=LastErrorOut)
    def get_integration_errors():
        """最近一次集成失败摘要（已脱敏，只读）。"""
        return cq.integration_errors()

    return router


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")
