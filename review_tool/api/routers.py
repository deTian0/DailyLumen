"""生产路由清单：``serve`` 用 ``default_routers()`` 交给 ``create_app(extra_routers=...)``。

新里程碑的路由在此追加（唯一接入点），测试可另行 ``build_router(...)`` 注入假依赖。
"""
from __future__ import annotations

from typing import Any


def default_routers(*, db_path: str | None = None, write_enabled: bool = False) -> list[Any]:
    from .routes_ai import build_router as ai_router
    from .routes_clickup import build_router as clickup_router
    from .routes_life import build_router as life_router
    from .routes_reports import build_router as reports_router

    routers = [clickup_router(db_path=db_path), reports_router(db_path=db_path),
               life_router(db_path=db_path), ai_router(db_path=db_path)]
    if write_enabled:
        # W9：写接口只在 serve --enable-write 时挂载；默认只读启动根本不存在这些路由
        from .routes_write import build_router as write_router

        routers.append(write_router(db_path=db_path))
    return routers
