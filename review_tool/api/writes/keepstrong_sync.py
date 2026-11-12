"""D1：练练 completed → 复盘 md（``keepstrong --write`` 同源）。

与 ``writes/keepstrong.py`` 的 ``ks_*`` **App 写回**不同：本动作只改本地复盘 md
（训练块 / 训练日 / 体重行），**不**写练练远端、**不**写库。入库请另走 ``ingest``。

plan：读练练（可注入 ``ks_client``）+ 内存 ``sync_markdown`` 出预览；confirm：
``write_sync(..., dry_run=False)``，用预览时冻结的 payload（不二次拉网）。
"""
from __future__ import annotations

import os
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, plan_out, register, sha_file, today
from .keepstrong import _client, _ks_creds, _map_ks_error
from .review_md import check_unchanged, ingest_cli, md_path


def _day_key(day_iso: str) -> str:
    """YYYY-MM-DD → YYYYMMDD（对齐练练 dayStr）。"""
    return day_iso.replace("-", "")


def _filter_day_records(records: list | None, day_iso: str) -> list[dict]:
    key = _day_key(day_iso)
    out: list[dict] = []
    for r in records or []:
        if not isinstance(r, dict):
            continue
        raw = str(r.get("dayStr") or r.get("date") or "").replace("-", "")
        if raw == key:
            out.append(r)
    return out


def plan_keepstrong_sync(
    tokens: TokenStore,
    day: str | None = None,
    *,
    env=None,
    ks_client=None,
) -> dict[str, Any]:
    """预览：拉练练当日 completed + 内存同步摘要；零写盘。"""
    from ...integrations.keepstrong import to_day_str
    from ...pipeline.keepstrong import collect
    from ...pipeline.keepstrong_sync import sync_markdown

    day = _check_date(day or today())
    path = md_path(day)
    api_key = _ks_creds(env)
    client = _client(api_key, ks_client)
    day_s = to_day_str(day)
    try:
        bundle = collect(day_s, day_s, types={"records", "body"}, client=client)
    except Exception as e:  # noqa: BLE001 — 映射为结构化错误
        raise _map_ks_error(e) from e

    day_records = _filter_day_records(bundle.get("records") or [], day)
    training_day = bool(day_records)
    body_logs = list(bundle.get("body_logs") or [])
    body_profile = bundle.get("body_profile")

    with open(path, encoding="utf-8") as f:
        raw = f.read()
    _new_text, summary = sync_markdown(
        raw,
        records=day_records,
        body_logs=body_logs,
        body_profile=body_profile,
        day_str=day_s,
        training_day=training_day,
    )

    n_raw = len(bundle.get("records") or [])
    empty_note = None
    if not summary.get("training_written"):
        if n_raw == 0 and not day_records:
            empty_note = (
                "当日无 status=completed 训练记录：不会写入「附录 · 训练明细」"
                "（合法空结果；训练日将按「否」处理）。"
            )
        elif n_raw and not day_records:
            empty_note = (
                f"拉到 {n_raw} 条记录但无一匹配当日 {day}："
                "不会写入训练明细（检查 dayStr/date 归日）。"
            )

    preview = {
        "date": day,
        "file": os.path.basename(path),
        "records_raw": n_raw,
        "records_day": len(day_records),
        "training_written": bool(summary.get("training_written")),
        "training_replaced": bool(summary.get("training_replaced")),
        "training_day": summary.get("training_day"),
        "weight_kg": summary.get("weight_kg"),
        "weight_written": bool(summary.get("weight_written")),
        "changed": bool(summary.get("changed")),
        "empty_note": empty_note,
        "writes": "local_review_md",
        "does_not": ["keepstrong_app", "reviews.db", "habit_logs"],
        "disclaimer": "写入本地复盘 md（训练块/训练日/体重），不是练练 App 写回；入库请另确认 ingest。",
        "next_ingest_cli": ingest_cli(day),
    }
    cli = f"python -m review_tool keepstrong --date {day} --write"
    payload = {
        "date": day,
        "md": path,
        "md_sha": sha_file(path),
        "day_str": day_s,
        "records": day_records,
        "body_logs": body_logs,
        "body_profile": body_profile,
        "training_day": training_day,
    }
    return plan_out(tokens, "keepstrong_sync", payload, preview=preview, cli=cli)


@register("keepstrong_sync")
def _apply_keepstrong_sync(p: dict[str, Any]) -> dict[str, Any]:
    """确认：用预览冻结的数据写 md（不二次拉网、不写库）。"""
    from ...pipeline.keepstrong_sync import write_sync

    check_unchanged(p)
    try:
        summary = write_sync(
            p["md"],
            records=p.get("records") or [],
            body_logs=p.get("body_logs") or [],
            body_profile=p.get("body_profile"),
            day_str=p["day_str"],
            training_day=p.get("training_day"),
            dry_run=False,
        )
    except OSError as e:
        raise QueryError(500, "write_failed", f"写复盘 md 失败：{e}") from e

    return {
        "written": bool(summary.get("changed")),
        "db_changed": False,
        "training_written": bool(summary.get("training_written")),
        "training_day": summary.get("training_day"),
        "weight_kg": summary.get("weight_kg"),
        "next": f"已写入复盘 md（未入库）。下一步：{ingest_cli(p['date'])}",
    }
