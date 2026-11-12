"""D6：夜间 ``daily-pull`` 薄封装（plan→confirm）。

语义 = CLI ``daily-pull --apply``：练练落 md+ingest → 习惯快照 → 全量 ingest。
plan 只列步骤（零副作用）；confirm 调 ``pipeline.daily_pull.run_steps``。
**不**静默代勾；不扩大 pull 范围。
"""
from __future__ import annotations

from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, plan_out, register, today


def plan_daily_pull(
    tokens: TokenStore,
    day: str | None = None,
) -> dict[str, Any]:
    """预览三步清单；不打网、不写盘。"""
    from ...pipeline.daily_pull import step_specs

    day = _check_date(day or today())
    steps = step_specs(day)
    preview = {
        "date": day,
        "steps": steps,
        "step_count": len(steps),
        "night_only": True,
        "will_network": True,
        "does_not": ["clickup_habit_auto", "ks_app_writeback", "finalize"],
        "disclaimer": (
            "确认后会打网（练练 + ClickUp）并写 md / habit_logs / 库；"
            "仅建议夜间使用。失败的一步不阻断其余步骤。不含代勾练练健身、不含 finalize。"
        ),
    }
    cli = f"python -m review_tool daily-pull --date {day} --apply"
    return plan_out(
        tokens,
        "daily_pull",
        {"date": day},
        preview=preview,
        cli=cli,
    )


@register("daily_pull")
def _apply_daily_pull(p: dict[str, Any]) -> dict[str, Any]:
    """确认：跑与 CLI --apply 同源的三步；结构化回报。"""
    from ...pipeline.daily_pull import run_steps

    day = p["date"]
    try:
        outcome = run_steps(day)
    except Exception as e:  # noqa: BLE001 — 编排层意外错误
        raise QueryError(500, "daily_pull_failed", f"daily-pull 执行失败：{e}") from e

    return {
        "date": day,
        "ok": outcome["ok"],
        "failed": outcome["failed"],
        "failures": outcome["failures"],
        "steps": outcome["steps"],
        "db_changed": True,  # 习惯快照 / ingest 可能写库（即使某步失败也可能已部分写入）
        "next": (
            "全部完成。若当晚还改了手填字段，另跑 finalize --apply 收口分数。"
            if outcome["ok"]
            else "部分步骤失败：请对照 steps[].rc / failures；练练 401 通常是 Key 过期。"
        ),
    }
