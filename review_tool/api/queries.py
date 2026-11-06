"""Web 看板只读查询编排（W2 / PRE-02·05·06）。

本模块**不依赖** fastapi / pydantic：只做「参数解析 + 调下层共享函数」，
让路由层（W3/W4）与对拍测试都调同一入口。约束：

- 一律接收调用方传入的连接（Web 侧为 ``storage.db.get_readonly_conn``），
  **不**调用 ``init_db``（不建库、不迁移、不写）。
- 不另写任何评分 / 归日 / 汇总口径；数字全部来自 reports 的 collect / render。
- 失败统一抛 :class:`QueryError`（带 HTTP 语义的 code/status），由路由层转成错误体。
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date as _date
from typing import Any

from ..storage.db import get_readonly_conn

CHART_KINDS = ("trends", "body", "training", "nutrition")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class QueryError(Exception):
    """可预期的查询失败（参数不合法 / 无数据 / 歧义）。"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@contextmanager
def readonly(db_path: str | None = None):
    """只读连接上下文；库不存在 → ``QueryError(503, db_missing)``。"""
    try:
        conn = get_readonly_conn(db_path)
    except FileNotFoundError as e:
        raise QueryError(503, "db_missing", "数据库尚未建立，请先在 CLI 执行 ingest") from e
    try:
        yield conn
    finally:
        conn.close()


def _check_date(value: str) -> str:
    if not _DATE_RE.match(value or ""):
        raise QueryError(422, "invalid_date", "日期格式应为 YYYY-MM-DD")
    try:
        _date.fromisoformat(value)
    except ValueError as e:
        raise QueryError(422, "invalid_date", "日期不存在") from e
    return value


# ---------------------------------------------------------------------------
# 周 / 月报（FR-F1 / FR-F2）
# ---------------------------------------------------------------------------

def resolve_week(conn, year: int | None = None, week: int | None = None) -> tuple[int, int]:
    """解析 ``(ISO 年, ISO 周)``。PRE-06：库只存周号，跨年同号必须显式报歧义。

    - 都不给 → 库内最新入库日所在周（``analyze.default_week``）。
    - 只给 week → 该周号在库中只落在一个 ISO 年时采用；多年混叠 → 409。
    - 给了 year → 必须与数据实际所在年一致，否则 404；混叠同样 409
      （CLI ``week N`` 按周号聚合，Web 不能假装能区分年）。
    """
    from ..reports.analyze import default_week, week_iso_years

    if week is None:
        if year is not None:
            raise QueryError(422, "invalid_request", "指定 year 时必须同时给 week")
        dw = default_week(conn)
        if dw is None:
            raise QueryError(404, "no_data", "库中暂无任何复盘数据")
        year, week = dw
    if not 1 <= week <= 53:
        raise QueryError(422, "invalid_week", "ISO 周号应在 1–53")
    years = week_iso_years(conn, week)
    if not years:
        raise QueryError(404, "no_data", f"ISO 第 {week} 周暂无数据")
    if year is not None and year not in years:
        raise QueryError(404, "no_data", f"{year} 年 ISO 第 {week} 周暂无数据")
    if len(years) > 1:
        raise QueryError(
            409, "ambiguous_week",
            f"ISO 第 {week} 周的数据跨越多个年份（{', '.join(map(str, years))}），"
            "现有周报按周号聚合，无法按年区分",
        )
    return years[0], week


def week_report(conn, year: int | None = None, week: int | None = None) -> dict[str, Any]:
    """周报：markdown 全文（= ``week N --write`` 落盘内容）+ 结构化汇总（= ``week N --json``）。"""
    from ..reports.analyze import collect, render_week_md, week_highlights

    y, wk = resolve_week(conn, year, week)
    md = render_week_md(conn, wk)
    summary = collect(conn, "iso_week=?", (wk,), f"ISO 周 {wk}")
    if md is None or summary is None:
        raise QueryError(404, "no_data", f"ISO 第 {wk} 周暂无数据")
    summary["highlights"] = week_highlights(conn, wk)
    return {"year": y, "week": wk, "markdown": md, "summary": summary,
            "filename": f"周总结-W{wk}.md"}


def available_weeks(conn) -> list[dict[str, int]]:
    """库内有数据的 ``(year, week)`` 列表（新→旧），供前端切周。"""
    from ..reports.analyze import week_iso_years

    out = []
    for (wk,) in conn.execute(
        "SELECT DISTINCT iso_week FROM daily_reviews WHERE iso_week IS NOT NULL"
    ):
        for y in week_iso_years(conn, wk):
            out.append({"year": y, "week": wk})
    return sorted(out, key=lambda d: (d["year"], d["week"]), reverse=True)


def resolve_month(conn, month: int | None = None) -> int:
    from ..reports.analyze import default_month

    if month is None:
        month = default_month(conn)
        if month is None:
            raise QueryError(404, "no_data", "库中暂无任何复盘数据")
    y, m = divmod(month, 100)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise QueryError(422, "invalid_month", "月份格式应为 YYYYMM")
    return month


def month_report(conn, month: int | None = None) -> dict[str, Any]:
    """月报：markdown 全文（= ``month M --write``）+ 结构化汇总（= ``month M --json``）。"""
    from ..reports.analyze import collect, render_month_md

    mon = resolve_month(conn, month)
    md = render_month_md(conn, mon)
    summary = collect(conn, "month=?", (mon,), f"月份 {mon}")
    if md is None or summary is None:
        raise QueryError(404, "no_data", f"月份 {mon} 暂无数据")
    return {"month": mon, "markdown": md, "summary": summary,
            "filename": f"月总结-{mon}.md"}


def available_months(conn) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT month FROM daily_reviews WHERE month IS NOT NULL ORDER BY month DESC"
    )]


# ---------------------------------------------------------------------------
# 日上下文 / 体检 / 统计 / 熔断 / 图表
# ---------------------------------------------------------------------------

def ai_context(conn, day: str | None = None) -> dict[str, Any]:
    """= ``ai-context [DATE]``：结构化上下文 + 同一份 markdown。"""
    from ..reports.ai_review import build_context, render_markdown

    if day is not None:
        _check_date(day)
    ctx = build_context(day, conn=conn)
    return {"date": ctx["date"], "markdown": render_markdown(ctx), "context": ctx}


def doctor(conn, *, input_dir: str | None = None, today: str | None = None) -> dict[str, Any]:
    """= ``doctor``：体检结果 + 文本 + 健康结论（与 CLI rc 同源）。"""
    from ..reports.doctor import diagnose, is_healthy, render

    result = diagnose(input_dir=input_dir, today=today, conn=conn)
    return {"healthy": is_healthy(result), "text": render(result, encoding="utf-8"),
            "result": result}


def stats(conn, *, input_dir: str | None = None, db_path: str | None = None) -> dict[str, Any]:
    """= ``stats --json``。"""
    from ..config import INPUT_DIR
    from ..reports.stats import collect

    return collect(conn, input_dir or INPUT_DIR, db_path=db_path)


def fuse(conn, month: int | None = None) -> dict[str, Any]:
    """= ``fuse``：熔断结果 + 是否有未失效绝对熔断（CLI rc=1 语义）。"""
    from ..reports.fuse import find_fuses, has_active_fuse, render

    res = find_fuses(conn, month=month)
    return {"active": has_active_fuse(res), "text": render(res), "result": res}


def chart_svg(conn, kind: str) -> str:
    """= ``chart --type KIND --stdout`` 的单图 SVG（默认图 ``trends``）。"""
    from ..reports import chart

    builders = {
        "trends": chart.build_chart,
        "body": chart.build_body_chart,
        "training": chart.build_training_chart,
        "nutrition": chart.build_nutrition_chart,
    }
    fn = builders.get(kind)
    if fn is None:
        raise QueryError(404, "unknown_chart", f"未知图表类型（可选 {'/'.join(CHART_KINDS)}）")
    return fn(conn)


def chart_series(conn, kind: str) -> dict:
    """W16：图表的 JSON 序列（与 ``chart_svg`` 同源，复用 ``reports.chart.fetch_*_series``）。

    返回 ``{"kind","dates","series","target"}``，前端 ECharts 直接消费；不另算均线 /
    目标带（R1：均线复用 ``core.body.moving_average``、目标带复用 ``config.BODY_TARGETS``）。
    """
    from ..config import BODY_TARGETS
    from ..core.body import moving_average
    from ..reports import chart

    if kind not in CHART_KINDS:
        raise QueryError(404, "unknown_chart", f"未知图表类型（可选 {'/'.join(CHART_KINDS)}）")

    if kind == "trends":
        cols = [m[0] for m in chart.DEFAULT_SERIES]
        dates, series = chart.fetch_series(conn, cols)
        return {
            "kind": kind,
            "dates": dates,
            "series": [
                {"key": c, "name": label, "color": color, "unit": unit,
                 "values": series[c], "type": "line"}
                for (c, label, color, unit) in chart.DEFAULT_SERIES
            ],
            "target": None,
        }

    if kind == "body":
        dates, weights = chart.fetch_body_series(conn)
        ma7 = moving_average(weights, window=7)
        low = BODY_TARGETS.get("weight_kg_low")
        high = BODY_TARGETS.get("weight_kg_high")
        return {
            "kind": kind,
            "dates": dates,
            "series": [
                {"key": "weight_kg", "name": "体重", "color": "#2563eb",
                 "unit": "kg", "values": weights, "type": "line"},
                {"key": "ma7", "name": "7日均", "color": "#ea580c",
                 "unit": "kg", "values": ma7, "type": "line", "dash": True},
            ],
            "target": (None if low is None or high is None
                       else {"low": float(low), "high": float(high)}),
        }

    if kind == "training":
        dates, volumes = chart.fetch_training_series(conn)
        return {
            "kind": kind,
            "dates": dates,
            "series": [
                {"key": "exercise_min", "name": "训练量", "color": "#16a34a",
                 "unit": "分钟", "values": volumes, "type": "bar"},
            ],
            "target": None,
        }

    # nutrition：双轴
    dates, kcals, weights = chart.fetch_nutrition_series(conn)
    return {
        "kind": kind,
        "dates": dates,
        "series": [
            {"key": "diet_kcal", "name": "热量", "color": "#ea580c",
             "unit": "kcal", "values": kcals, "type": "line", "yAxisIndex": 0},
            {"key": "weight_kg", "name": "体重", "color": "#2563eb",
             "unit": "kg", "values": weights, "type": "line", "yAxisIndex": 1},
        ],
        "target": None,
    }
