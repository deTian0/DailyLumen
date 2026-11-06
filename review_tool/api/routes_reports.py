"""Web 看板路由：报告与分析（W4 / FR-F1~F4 · FR-G1~G2 · FR-L1 · FR-L3）。

只做 HTTP 适配；编排全部在 ``api.queries``（W2 已对拍）。所有读库都走
``queries.readonly``（URI ``mode=ro`` + ``query_only``），不调用 ``init_db``。

响应模型：顶层字段（markdown / filename / 周月号 / 健康结论）严格声明；
``summary`` / ``result`` / ``context`` 是下层 collect 的结构化产物，原样透传
（``dict[str, Any]``）——字段由 reports 层单源定义，API 不再复制一份 schema。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from . import queries as q


class WeekRef(BaseModel):
    year: int
    week: int


class WeekReportOut(BaseModel):
    year: int
    week: int
    markdown: str
    filename: str
    summary: dict[str, Any]


class MonthReportOut(BaseModel):
    month: int
    markdown: str
    filename: str
    summary: dict[str, Any]


class AiContextOut(BaseModel):
    date: str
    markdown: str
    context: dict[str, Any]


class DoctorOut(BaseModel):
    healthy: bool
    text: str
    result: dict[str, Any]


class FuseOut(BaseModel):
    active: bool
    text: str
    result: dict[str, Any]


def _md_download(text: str, filename: str) -> PlainTextResponse:
    """FR-F4：下载内容 = 页面内容（同一份 markdown）。"""
    return PlainTextResponse(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")},
    )


def build_router(*, db_path: str | None = None, input_dir: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["reports"])

    # ---------------- 周 / 月报 ----------------
    @router.get("/reports/weeks", response_model=list[WeekRef])
    def list_weeks():
        with q.readonly(db_path) as conn:
            return q.available_weeks(conn)

    @router.get("/reports/week", response_model=WeekReportOut)
    def get_week(year: int | None = Query(default=None), week: int | None = Query(default=None)):
        with q.readonly(db_path) as conn:
            return q.week_report(conn, year, week)

    @router.get("/reports/week.md", response_class=PlainTextResponse)
    def get_week_md(year: int | None = Query(default=None), week: int | None = Query(default=None)):
        with q.readonly(db_path) as conn:
            data = q.week_report(conn, year, week)
        return _md_download(data["markdown"], data["filename"])

    @router.get("/reports/months", response_model=list[int])
    def list_months():
        with q.readonly(db_path) as conn:
            return q.available_months(conn)

    @router.get("/reports/month", response_model=MonthReportOut)
    def get_month(month: int | None = Query(default=None, description="YYYYMM")):
        with q.readonly(db_path) as conn:
            return q.month_report(conn, month)

    @router.get("/reports/month.md", response_class=PlainTextResponse)
    def get_month_md(month: int | None = Query(default=None)):
        with q.readonly(db_path) as conn:
            data = q.month_report(conn, month)
        return _md_download(data["markdown"], data["filename"])

    # ---------------- 日上下文 ----------------
    @router.get("/reports/ai-context", response_model=AiContextOut)
    def get_ai_context(date: str | None = Query(default=None)):
        with q.readonly(db_path) as conn:
            return q.ai_context(conn, date)

    # ---------------- 统计 / 体检 / 熔断 ----------------
    @router.get("/stats", response_model=dict[str, Any])
    def get_stats():
        with q.readonly(db_path) as conn:
            return q.stats(conn, input_dir=input_dir, db_path=db_path)

    @router.get("/doctor", response_model=DoctorOut)
    def get_doctor():
        with q.readonly(db_path) as conn:
            return q.doctor(conn, input_dir=input_dir)

    @router.get("/fuse", response_model=FuseOut)
    def get_fuse(month: int | None = Query(default=None)):
        with q.readonly(db_path) as conn:
            return q.fuse(conn, month)

    # ---------------- 图表（首期嵌现有 SVG）----------------
    # W16：JSON 路由必须排在 SVG 路由之前——`{kind}` 默认匹配 `[^/]+`（含点），
    # 否则 `/charts/trends.json` 会被 `{kind}` 抢先匹配成 kind="trends.json"。
    @router.get("/charts/{kind}.json")
    def get_chart_json(kind: str):
        with q.readonly(db_path) as conn:
            data = q.chart_series(conn, kind)
        return JSONResponse(data, headers={"Cache-Control": "no-store"})

    @router.get("/charts/{kind}")
    def get_chart(kind: str):
        with q.readonly(db_path) as conn:
            svg = q.chart_svg(conn, kind)
        return Response(svg, media_type="image/svg+xml; charset=utf-8",
                        headers={"Cache-Control": "no-store"})

    return router
