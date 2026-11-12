"""Web 看板：健康 / 学习 / 督导只读查询（W6 / FR-D* · FR-E* · FR-H*）。

与 ``queries.py`` 同约束：不依赖 fastapi / pydantic；只接收调用方传入的只读连接；
数字全部来自 reports 层既有 ``collect`` / ``render``（R1 单源），本模块不做任何计算。

每个查询返回 ``{"text": render(data), "data": data}``：
- ``text`` = 对应 CLI 文本输出（逐字同源，对拍测试守住）；
- ``data`` = 对应 CLI ``--json`` 输出（经 ``json`` 往返，``default=str`` 与 CLI 一致）。

⚠️ ``tutor``：CLI 默认 ``rebuild=True`` 会重建复习队列并 ``commit``（写库）。
Web 只读连接**固定 ``rebuild=False``**——队列以最近一次 CLI ``tutor`` 重建为准，
响应带 ``queue_rebuilt=False`` 明示，前端据此提示。
"""
from __future__ import annotations

import json
from typing import Any

from .queries import QueryError, _check_date, resolve_week

DOMAINS = ("body", "coach", "habits", "nutrition", "tutor", "promises", "correlate")
STEWARD_SLOTS = ("morning", "evening", "week")


def _jsonable(data: Any) -> Any:
    """与 CLI ``--json`` 同口径的序列化（日期等非 JSON 类型 → str）。"""
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _pack(data: dict, text: str, **extra: Any) -> dict[str, Any]:
    return {"text": text, "data": _jsonable(data), **extra}


def body(conn) -> dict[str, Any]:
    """= ``body`` / ``body --json``。"""
    from ..reports import body as m

    data = m.collect(conn)
    return _pack(data, m.render(data))


def coach(conn, as_of: str | None = None) -> dict[str, Any]:
    """= ``coach [DATE]``。"""
    from ..reports import coach as m

    data = m.collect(conn, as_of=_check_date(as_of) if as_of else None)
    return _pack(data, m.render(data))


def habits(conn, as_of: str | None = None) -> dict[str, Any]:
    """= ``habits [DATE]``（habit_logs，与 personal_tracks 物理隔离）。"""
    from ..reports import habits as m

    data = m.collect(conn, as_of=_check_date(as_of) if as_of else None)
    return _pack(data, m.render(data))


def nutrition(conn, as_of: str | None = None) -> dict[str, Any]:
    """= ``nutrition [DATE]``。"""
    from ..reports import nutrition as m

    data = m.collect(conn, as_of=_check_date(as_of) if as_of else None)
    return _pack(data, m.render(data))


def tutor(conn, as_of: str | None = None) -> dict[str, Any]:
    """= ``tutor [DATE]``，但**不重建**复习队列（只读）。"""
    from ..reports import tutor as m

    data = m.collect(conn, as_of=_check_date(as_of) if as_of else None, rebuild=False)
    return _pack(data, m.render(data), queue_rebuilt=False)


def promises(conn, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """= ``promises [START [END]]``（只给 start 时 end=start，与 CLI 一致）。"""
    from ..reports import promises as m

    if end and not start:
        raise QueryError(422, "invalid_request", "指定 end 时必须同时给 start")
    if start:
        _check_date(start)
        end = _check_date(end) if end else start
    data = m.collect(conn, start=start, end=end)
    return _pack(data, m.render(data))


def correlate(conn, min_samples: int | None = None) -> dict[str, Any]:
    """= ``correlate [--min-samples N]``。"""
    from ..reports import correlate as m

    n = m.MIN_SAMPLES if min_samples is None else min_samples
    if n < 2:
        raise QueryError(422, "invalid_request", "min_samples 至少为 2")
    data = m.collect(conn, min_samples=n)
    return _pack(data, m.render(data))


def week_done(conn, year: int | None = None, week: int | None = None) -> dict[str, Any]:
    """= ``week-done [ISO周]``（W7 / FR-F5）：ClickUp 完成 + 复盘三件事。

    周解析走 ``resolve_week``（PRE-06），并把解析出的 ISO 年显式传给 collect，
    避免 CLI「默认今年」在跨年时取错窗口。
    """
    from ..reports import week_done as m

    y, wk = resolve_week(conn, year, week)
    data = m.collect(conn, iso_week=wk, year=y)
    return _pack(data, m.render(data), year=y, week=wk)


def streaks(conn, as_of: str | None = None) -> dict[str, Any]:
    """正向连续（复盘入库 / 训练达标 / 打卡），= 周月报 streak 段同源。"""
    from ..reports.streak import render_streaks, summarize_streaks

    data = summarize_streaks(conn, as_of=_check_date(as_of) if as_of else None)
    return _pack(data, render_streaks(data))


def day_help(day: str | None = None, mode: str | None = None) -> dict[str, Any]:
    """= ``day-help [DATE] [--mode M]``：一日三步 + 可复制命令。

    不读库；训练日分支仅看本地复盘 md 数据块（D7），无文件则不追加。
    """
    from datetime import date as _d

    from ..config import get_llm_mode
    from ..core.day_help import infer_training_day_hint, render_day_help

    day = _check_date(day) if day else _d.today().isoformat()
    mode = mode or get_llm_mode()
    if mode not in ("workbuddy", "deepseek"):
        raise QueryError(422, "invalid_mode", "mode 须为 workbuddy|deepseek")
    td = infer_training_day_hint(day)
    return {
        "date": day,
        "mode": mode,
        "training_day": td,
        "text": render_day_help(day, mode, training_day=td),
    }


def steward(conn, slot: str, *, as_of: str | None = None,
            year: int | None = None, week: int | None = None) -> dict[str, Any]:
    """= ``steward --slot morning|evening|week``。

    week 槽位的周解析走 ``resolve_week``（PRE-06 跨年歧义 409），其余同 CLI。
    """
    from ..reports import steward as m

    if slot not in STEWARD_SLOTS:
        raise QueryError(422, "invalid_slot", f"slot 须为 {'|'.join(STEWARD_SLOTS)}")
    if slot == "week":
        _y, wk = resolve_week(conn, year, week)
        data = m.collect(conn, slot="week", iso_week=wk)
    else:
        data = m.collect(conn, slot=slot, as_of=_check_date(as_of) if as_of else None)
    return _pack(data, m.render(data))
