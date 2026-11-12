"""D2：今日训练日只读状态（R1 单源聚合）。

复用 ``keepstrong_completed_hint`` + 本地复盘 md 是否含 keepstrong 块；
**不**静默代勾、**不**改 ``is_healthy`` / 复盘四步。代勾是否已完成不强制查
ClickUp（避免今日页强依赖远端）；有 completed 时给出「可去代勾」建议即可。
"""
from __future__ import annotations

import datetime
import os
from typing import Any

from .queries import _check_date


def _today() -> str:
    return datetime.date.today().isoformat()


def training_day_status(
    day: str | None = None,
    *,
    env=None,
    ks_client=None,
) -> dict[str, Any]:
    """聚合：练练 completed 旁证 + 复盘 md 是否已同步训练块。"""
    from ..pipeline.clickup_habit import keepstrong_completed_hint
    from ..pipeline.keepstrong_sync import BEGIN, review_md_path

    day = _check_date(day or _today())
    hint = keepstrong_completed_hint(day, ks_client=ks_client, env=env)
    path = review_md_path(day)
    md_exists = os.path.isfile(path)
    md_synced = False
    if md_exists:
        with open(path, encoding="utf-8") as f:
            md_synced = BEGIN in f.read()

    completed = bool(hint.get("completed"))
    if not md_exists:
        next_step = "create_md"
    elif completed and not md_synced:
        next_step = "sync_md"
    elif completed and md_synced:
        next_step = "habit_optional"
    elif hint.get("checked") and not completed:
        next_step = "none"
    else:
        next_step = "unknown"

    return {
        "date": day,
        "keepstrong": hint,
        "md_exists": md_exists,
        "md_synced": md_synced,
        "md_file": os.path.basename(path) if md_exists else None,
        "next": next_step,
        "links": {
            "sync": "#/life?tab=coach&focus=keepstrong-sync",
            "habit": "#/life?tab=coach&focus=clickup-habit",
            "coach": "#/life?tab=coach",
        },
        "note": "只读状态；同步 md / 代勾须在生活管家训练页预览→确认，禁止静默自动勾。",
    }
