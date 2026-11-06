"""复盘 md 域写操作：AI 草稿写入（FR-H3）与定稿（FR-H4）—— 只写 md，不写库。

写 md 一律复用下层既有写函数（``llm_review.write_ai_section`` /
``llm_finalize.run_llm_finalize``），二者自带写后回读校验（规则 3）。
md 在预览与确认之间被改动 → 409 ``stale_plan``（不覆盖他处的手改）。
"""
from __future__ import annotations

import os
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, plan_out, register, sha_file


def md_path(day: str) -> str:
    from ...reports import llm_review as lr

    path = lr.review_md_path(day)
    if not os.path.isfile(path):
        raise QueryError(404, "md_missing", f"找不到 {day} 的复盘 md，请先建当日复盘文件")
    return path


def check_unchanged(p: dict[str, Any]) -> None:
    if not os.path.isfile(p["md"]) or sha_file(p["md"]) != p["md_sha"]:
        raise QueryError(409, "stale_plan", "复盘 md 在预览后被改动，请重新预览再确认")


def ingest_cli(day: str) -> str:
    return f"python -m review_tool ingest 复盘/{day[:7]}/{day}.md"


def plan_ai_draft(tokens: TokenStore, conn, day: str | None = None, *, client=None,
                  mode: str | None = None) -> dict[str, Any]:
    from ..ai_queries import review_preview

    res = review_preview(conn, day, client=client, mode=mode)  # 含 mode 门禁
    path = md_path(res["date"])
    preview = {"date": res["date"], "section": res["section"], "diff_text": res["diff_text"],
               "pending_mark": True}
    return plan_out(tokens, "ai_draft", {"date": res["date"], "md": path,
                                         "md_sha": sha_file(path), "section": res["section"]},
                    preview=preview, cli=f"python -m review_tool llm-review {res['date']} --write")


def plan_finalize(tokens: TokenStore, day: str) -> dict[str, Any]:
    from ...reports.llm_finalize import run_llm_finalize

    day = _check_date(day)
    path = md_path(day)
    res = run_llm_finalize(day, md_path=path, write=False)
    preview = {"date": day, "changed": res["changed"], "pending_before": res["pending_before"],
               "pending_after": res["pending_after"], "side_by_side": res["preview"]}
    return plan_out(tokens, "finalize", {"date": day, "md": path, "md_sha": sha_file(path)},
                    preview=preview, cli=f"python -m review_tool llm-finalize {day} --write")


@register("ai_draft")
def _apply_ai_draft(p: dict[str, Any]) -> dict[str, Any]:
    from ...reports.llm_review import write_ai_section

    check_unchanged(p)
    changed = write_ai_section(p["md"], p["section"])
    return {"written": changed, "pending_review": True,
            "next": "人审后点「定稿」，再 ingest（草稿态 ingest 默认跳过）"}


@register("finalize")
def _apply_finalize(p: dict[str, Any]) -> dict[str, Any]:
    from ...reports.llm_finalize import run_llm_finalize

    check_unchanged(p)
    res = run_llm_finalize(p["date"], md_path=p["md"], write=True)
    return {"written": res["written"], "pending_after": res["pending_after"],
            "next": f"定稿已写入 md；入库请执行：{ingest_cli(p['date'])}"}
