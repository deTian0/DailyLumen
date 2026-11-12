"""Web 看板路由：健康 / 学习 / 督导（W6）。

只做 HTTP 适配；编排全部在 ``api.life_queries``（与 CLI 同源，对拍测试守住）。
读库一律 ``queries.readonly``（``mode=ro`` + ``query_only``）。
``data`` 是下层 collect 的结构化产物，原样透传（schema 由 reports 层单源定义）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from . import life_queries as lq
from .queries import readonly


class DomainOut(BaseModel):
    text: str
    data: dict[str, Any]


class TutorOut(DomainOut):
    # Web 只读：不重建复习队列，以最近一次 CLI tutor 为准
    queue_rebuilt: bool


class WeekDoneOut(DomainOut):
    year: int
    week: int


class DayHelpOut(BaseModel):
    date: str
    mode: str
    text: str


def build_router(*, db_path: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["life"])
    D = Query(default=None, description="YYYY-MM-DD，省略为库内最新")

    @router.get("/body", response_model=DomainOut)
    def get_body():
        with readonly(db_path) as conn:
            return lq.body(conn)

    @router.get("/coach", response_model=DomainOut)
    def get_coach(date: str | None = D):
        with readonly(db_path) as conn:
            return lq.coach(conn, date)

    @router.get("/habits", response_model=DomainOut)
    def get_habits(date: str | None = D):
        with readonly(db_path) as conn:
            return lq.habits(conn, date)

    @router.get("/nutrition", response_model=DomainOut)
    def get_nutrition(date: str | None = D):
        with readonly(db_path) as conn:
            return lq.nutrition(conn, date)

    @router.get("/tutor", response_model=TutorOut)
    def get_tutor(date: str | None = D):
        with readonly(db_path) as conn:
            return lq.tutor(conn, date)

    @router.get("/promises", response_model=DomainOut)
    def get_promises(start: str | None = Query(default=None), end: str | None = Query(default=None)):
        with readonly(db_path) as conn:
            return lq.promises(conn, start, end)

    @router.get("/correlate", response_model=DomainOut)
    def get_correlate(min_samples: int | None = Query(default=None)):
        with readonly(db_path) as conn:
            return lq.correlate(conn, min_samples)

    # D2：今日训练日只读状态（练练旁证 + md 是否已同步）；不影响 is_healthy
    @router.get("/training-day")
    def get_training_day(date: str | None = D):
        from . import training_day as td

        return td.training_day_status(date)

    @router.get("/week-done", response_model=WeekDoneOut)
    def get_week_done(year: int | None = Query(default=None), week: int | None = Query(default=None)):
        with readonly(db_path) as conn:
            return lq.week_done(conn, year, week)

    @router.get("/streaks", response_model=DomainOut)
    def get_streaks(date: str | None = D):
        with readonly(db_path) as conn:
            return lq.streaks(conn, date)

    @router.get("/day-help", response_model=DayHelpOut)
    def get_day_help(date: str | None = D, mode: str | None = Query(default=None)):
        return lq.day_help(date, mode)

    @router.get("/steward/{slot}", response_model=DomainOut)
    def get_steward(slot: str, date: str | None = D,
                    year: int | None = Query(default=None), week: int | None = Query(default=None)):
        with readonly(db_path) as conn:
            return lq.steward(conn, slot, as_of=date, year=year, week=week)

    return router
