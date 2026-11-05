"""Web 看板 ClickUp 今日编排（W3 / FR-B2 · FR-C1~C5）。

与 ``queries.py`` 同约束：不依赖 fastapi / pydantic；口径全部复用
``pipeline.clickup``（归日 / 回拨 / 选取 / 渲染）与 ``reports.clickup_done``。

- 今日待办 / 已办、素材预览：**实时只读 GET** ClickUp（与 CLI ``clickup --stdout`` 同源）。
- 指定日完成清单：读本地 ``clickup_done`` 快照（与 CLI ``clickup-done`` 同源），不联网。
- 失败一律映射为 :class:`QueryError`，文案取自下层既有的中文提示，**不含密钥**；
  任务对象按白名单字段输出（不整对象直出 ClickUp 原始 JSON）。
- 本模块**不写** ``integration_last_error.json``（Web 读路径零写盘）；最近错误由
  :func:`integration_errors` 只读展示 CLI 侧写下的摘要。
"""
from __future__ import annotations

import datetime
import threading
import urllib.error
from typing import Any

from .queries import QueryError, _check_date


def _today() -> str:
    return datetime.date.today().isoformat()


def _task_dto(t: dict, *, list_name: str) -> dict[str, Any]:
    from ..pipeline import clickup as cu

    due = t.get("due_date")
    closed = t.get("date_closed")
    rebated = cu.rebate_target(t) if closed else None
    return {
        "id": str(t.get("id") or ""),
        "name": cu._name(t),
        "status": cu._status(t) or "",
        "list": list_name,
        "due": cu.day_of(due) if due else None,
        "closed_day": cu.day_of(closed) if closed else None,
        "closed_clock": cu.clock_of(closed) if closed else None,
        "completion_day": cu.completion_day(t) if closed else None,
        "rebated_to": rebated,
    }


def _creds(env=None) -> tuple[str, str | None]:
    from ..integrations.clickup import CredError
    from ..integrations.flags import IntegrationDisabled, require_enabled
    from ..pipeline import clickup as cu

    try:
        require_enabled("clickup")
    except IntegrationDisabled as e:
        raise QueryError(503, "integration_disabled", str(e)) from e
    try:
        return cu.load_creds(env=env)
    except CredError as e:
        raise QueryError(503, "credentials_missing", str(e)) from e


def _collect(day: str, *, fetch=None, env=None) -> tuple[list[dict], str | None]:
    """调 ``pipeline.clickup.collect``；网络 / 认证错误映射为结构化错误。"""
    from ..pipeline import clickup as cu

    key, team = _creds(env)
    try:
        return cu.collect(day, key=key, fetch=fetch), team
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", None)
        if code in (401, 403):
            msg = f"ClickUp 拒绝访问（HTTP {code}）：token 失效或权限不足，检查 local/.env 的 CLICKUP_API_KEY"
            raise QueryError(502, "upstream_auth", msg) from e
        raise QueryError(502, "upstream_error", f"ClickUp 返回 HTTP {code}") from e
    except urllib.error.URLError as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时") from e
    except TimeoutError as e:
        raise QueryError(504, "upstream_unreachable", "ClickUp 请求超时") from e


def today(day: str | None = None, *, fetch=None, env=None, now=None) -> dict[str, Any]:
    """今日待办 / 已办（= ``clickup DAY --stdout`` 的同一份 ``collect`` 分组）。"""
    from ..pipeline import clickup as cu

    day = _check_date(day) if day else _today()
    groups, _team = _collect(day, fetch=fetch, env=env)
    out_groups = []
    for g in groups:
        name = g["name"]
        out_groups.append({
            "id": g["id"],
            "name": name,
            "role": g["role"],
            **{k: [_task_dto(t, list_name=name) for t in g.get(k) or []]
               for k in ("done", "open", "in_progress", "overdue", "cross_day")},
        })
    totals = {k: sum(len(g[k]) for g in out_groups)
              for k in ("done", "open", "in_progress", "overdue", "cross_day")}
    totals["rebated"] = sum(1 for g in out_groups for t in g["done"] if t["rebated_to"])
    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "date": day,
        "fetched_at": stamp,
        "groups": out_groups,
        "totals": totals,
        "bulk_hint": cu.bulk_hint(groups),
    }


def material(day: str | None = None, *, fetch=None, env=None, now=None) -> dict[str, Any]:
    """素材预览 = ``clickup DAY --stdout`` 的 markdown（不落文件、不同步习惯）。"""
    from ..pipeline import clickup as cu

    day = _check_date(day) if day else _today()
    groups, team = _collect(day, fetch=fetch, env=env)
    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return {"date": day, "markdown": cu.render(day, groups, generated_at=stamp, workspace=team),
            "filename": f"clickup-素材-{day}.md"}


def done(conn, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """= ``clickup-done [START [END]] --json``（读本地快照，不联网）。"""
    from ..reports.clickup_done import collect, render

    start = _check_date(start) if start else _today()
    end = _check_date(end) if end else start
    if end < start:
        raise QueryError(422, "invalid_range", "结束日期不能早于开始日期")
    res = collect(conn, start=start, end=end)
    return {**res, "text": render(res)}


def integration_errors() -> dict[str, Any]:
    """CLI 侧写下的最近集成失败摘要（已脱敏；只读）。"""
    from ..integrations.last_error import read_last_error

    return {"last": read_last_error()}


class TodayCache:
    """进程内「上次成功的今日数据」：刷新失败时保留旧数据（FR-B2）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}

    def get(self, day: str) -> dict[str, Any] | None:
        with self._lock:
            return self._data.get(day)

    def put(self, day: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._data[day] = value
