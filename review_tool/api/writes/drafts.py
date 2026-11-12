"""E1 / FR-K3：候选草稿 Web 上板（promise / three-things / improve）。

与 CLI 同源：promise（M34 明日 Top 3）/ three-things（M36 今日三件事）/ improve
（M37 改进点取数骨架）。plan **内存渲染**预览（零写盘）；confirm 把预览时冻结的
md 文本写进 ``收件箱/``。红线：

- **草稿不入库**（收件箱本就被 ingest 跳过；沿袭 M34/M36/M37）；
- **机器只搬运，不编造**：候选 = ClickUp 任务名原样 / ai-context 同源数字；
- **不做 Web 端勾选回填**——回填复盘 md 仍在 md / 会话完成；
- 已存在同名草稿 → 422 ``draft_exists``（不静默覆盖；CLI ``--out`` 或先归档）。
"""
from __future__ import annotations

import os
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, plan_out, register, today

# 三类草稿的收件箱文件前缀（与 CLI INBOX_PREFIX 一致）
_PREFIXES = {"promise_draft": "明日候选", "three_things_draft": "三件事候选",
             "improve_draft": "改进点候选"}


def _draft_path(kind: str, day: str) -> str:
    from ...config import INBOX_DIR

    return os.path.join(INBOX_DIR, f"{_PREFIXES[kind]}-{day}.md")


def _load_creds(env):
    """ClickUp 凭据（与 clickup 域同款错误映射）。"""
    from ...integrations.clickup import CredError
    from ...integrations.flags import IntegrationDisabled, require_enabled
    from ...pipeline import clickup as cu

    try:
        require_enabled("clickup")
    except IntegrationDisabled as e:
        raise QueryError(503, "integration_disabled", str(e)) from e
    try:
        return cu.load_creds(env=env)
    except CredError as e:
        raise QueryError(503, "credentials_missing", str(e)) from e


def _map_fetch_error(e: Exception) -> QueryError:
    """ClickUp 取数失败 → 结构化错误（对齐 writes/clickup.py 口径）。"""
    import urllib.error

    code = getattr(e, "code", None)
    if str(code) == "429":
        return QueryError(429, "rate_limited", "ClickUp 限流，请稍后再试")
    if str(code) in ("401", "403"):
        return QueryError(502, "upstream_auth", "ClickUp 凭据失效或权限不足")
    if isinstance(e, (urllib.error.URLError, TimeoutError)):
        return QueryError(504, "upstream_unreachable", "ClickUp 网络不可达或超时")
    return QueryError(502, "upstream_error", f"ClickUp 取数失败：{e}")


def _plan_clickup_draft(
    tokens: TokenStore, action: str, day: str | None, *,
    env=None, fetch=None,
) -> dict[str, Any]:
    """promise / three-things 共用 plan：拉 ClickUp → 内存渲染草稿（零写盘）。"""
    from ...pipeline import clickup as cu
    from ...pipeline.promise_draft import build_draft as build_promise
    from ...pipeline.promise_draft import candidate_pool as promise_pool
    from ...pipeline.three_things_draft import build_draft as build_three
    from ...pipeline.three_things_draft import candidate_pool as three_pool

    day = _check_date(day or today())
    key, _team = _load_creds(env)
    try:
        groups = cu.collect(day, None, key=key, fetch=fetch)
    except Exception as e:  # noqa: BLE001 — 统一映射结构化错误
        raise _map_fetch_error(e) from e

    if action == "promise_draft":
        pool = promise_pool(day, groups)
        text = build_promise(day, pool, generated_at=_stamp())
        # promise 的 day 是执行日（= 生成日的明天）；文件名与 CLI 口径一致按 day
    else:
        pool = three_pool(day, groups)
        text = build_three(day, pool, generated_at=_stamp())
    items = [{"list": it["list"], "name": cu._name(it["task"])} for it in pool]
    return _finish_plan(tokens, action, day, text, {"candidates": items, "count": len(items)})


def _plan_improve_draft(
    tokens: TokenStore, day: str | None, *, db_path=None, conn=None,
) -> dict[str, Any]:
    """improve plan：ai-context 同源取数 → 骨架草稿（不查书、不排序）。"""
    from ...reports.ai_review import build_context, render_markdown
    from ...reports.improve_draft import build_skeleton

    day = _check_date(day or today())
    if conn is not None:
        ctx = build_context(day, conn=conn)
    else:
        from ...storage.db import get_readonly_conn

        try:
            conn = get_readonly_conn(db_path)
        except FileNotFoundError as e:
            raise QueryError(503, "db_missing", "数据库尚未建立，请先在 CLI 执行 ingest") from e
        try:
            ctx = build_context(day, conn=conn)
        finally:
            conn.close()
    text = build_skeleton(day, generated_at=_stamp(), context_md=render_markdown(ctx))
    return _finish_plan(tokens, "improve_draft", day, text, {})


def _stamp() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _finish_plan(
    tokens: TokenStore, action: str, day: str, text: str, extra: dict[str, Any],
) -> dict[str, Any]:
    path = _draft_path(action, day)
    exists = os.path.isfile(path)
    preview: dict[str, Any] = {
        "date": day,
        "file": os.path.basename(path),
        "target_dir": "local/每日复盘/收件箱",
        "will_overwrite": False,
        "exists": exists,
        "bytes": len(text.encode("utf-8")),
        "writes": "inbox_md",
        "does_not": ["reviews.db", "ingest", "review_md"],
        "disclaimer": (
            "草稿只落收件箱，不入库（ingest 跳过收件箱）；勾选回填复盘 md 仍在 md / 会话完成。"
        ),
        **extra,
    }
    if exists:
        # 不静默覆盖：与 CLI（直接覆盖写）不同，Web 端先拒绝；先归档或用 CLI --out
        preview["blocked_reason"] = "draft_exists"
    cli = f"python -m review_tool {action.replace('_', '-')} --date {day} --stdout > 收件箱文件"
    return plan_out(tokens, action, {"date": day, "text": text, "path": path},
                    preview=preview, cli=cli)


def _apply_draft(p: dict[str, Any]) -> dict[str, Any]:
    """确认：把预览冻结的文本写入收件箱（写后回读）。"""
    path, text = p["path"], p["text"]
    if os.path.isfile(path):
        raise QueryError(422, "draft_exists",
                         "收件箱已有同名草稿，不覆盖；请先归档或用 CLI --out 换目录")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(path, encoding="utf-8") as f:
        got = f.read()
    if got != text:
        raise QueryError(500, "write_verify_failed", "写盘回读校验失败，请重试")
    return {
        "date": p["date"],
        "file": os.path.basename(path),
        "db_changed": False,
        "next": "已落收件箱（不入库）。去复盘 md 勾选回填；收件箱素材可 inbox-archive 归档。",
    }


@register("promise_draft", "three_things_draft", "improve_draft")
def _apply(p: dict[str, Any]) -> dict[str, Any]:
    return _apply_draft(p)


def plan_promise_draft(tokens: TokenStore, day: str | None = None, *,
                       env=None, fetch=None) -> dict[str, Any]:
    """明日 Top 3 候选（M34）：预览零写盘，确认落收件箱。"""
    return _plan_clickup_draft(tokens, "promise_draft", day, env=env, fetch=fetch)


def plan_three_things_draft(tokens: TokenStore, day: str | None = None, *,
                            env=None, fetch=None) -> dict[str, Any]:
    """今日三件事候选（M36）：预览零写盘，确认落收件箱。"""
    return _plan_clickup_draft(tokens, "three_things_draft", day, env=env, fetch=fetch)


def plan_improve_draft(tokens: TokenStore, day: str | None = None, *,
                       db_path=None, conn=None) -> dict[str, Any]:
    """改进点取数骨架（M37）：ai-context 同源；查书排序仍须会话。"""
    return _plan_improve_draft(tokens, day, db_path=db_path, conn=conn)
