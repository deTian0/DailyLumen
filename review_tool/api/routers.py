"""生产路由清单：``serve`` 用 ``default_routers()`` 交给 ``create_app(extra_routers=...)``。

新里程碑的路由在此追加（唯一接入点），测试可另行 ``build_router(...)`` 注入假依赖。
"""
from __future__ import annotations

from typing import Any


def default_routers(*, db_path: str | None = None) -> list[Any]:
    from .routes_clickup import build_router as clickup_router
    from .routes_reports import build_router as reports_router

    return [clickup_router(db_path=db_path), reports_router(db_path=db_path)]
