"""收工摘要 / 今日红绿灯的 I/O 装配（读 md / 库 / 收件箱）。"""
from __future__ import annotations

import datetime
import os
from typing import Any

from ..config import INPUT_DIR
from ..core.ai_draft import is_ai_draft_pending
from ..core.day_close import (
    CLOSE_FOCUS_FIELDS,
    classify_day_ready,
    format_close_summary,
    missing_focus_fields,
    render_day_ready_line,
)
from ..core.llm_contract import OPTIONAL_CONTRACT_FIELDS
from ..pipeline.keepstrong_sync import review_md_path
from ..pipeline.vision_intake import extract_data_block_body
from ..storage.db import init_db


def _parse_data_filled(md_text: str) -> list[str]:
    """从 md 数据块推断已填契约键（值非空）。"""
    body = extract_data_block_body(md_text or "")
    if not body.strip():
        return []
    # 复用契约归一：把 data 块伪造成 JSON 风格较难；按行扫
    filled: list[str] = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        for sep in (":", "："):
            if sep in s:
                key, _, rest = s.partition(sep)
                key, rest = key.strip(), rest.strip()
                if key and rest:
                    filled.append(key)
                break
    return filled


def _inbox_pending_for_day(day: str, *, input_dir: str | None = None) -> bool:
    """收件箱根下是否仍有文件名含该日的待处理素材（已处理/ 下不算）。"""
    root = input_dir or INPUT_DIR
    inbox = os.path.join(root, "收件箱")
    if not os.path.isdir(inbox):
        return False
    for name in os.listdir(inbox):
        if name.startswith((".", "_")) or name == "README.md":
            continue
        path = os.path.join(inbox, name)
        if os.path.isdir(path):
            continue  # 已处理/ 等子目录跳过
        if day in name:
            return True
    return False


def assess_day_ready(
    day: str | None = None,
    *,
    md_path: str | None = None,
    db_path: str | None = None,
    input_dir: str | None = None,
) -> dict[str, Any]:
    """评估指定日能否收工（含红绿灯）。"""
    day = day or datetime.date.today().isoformat()
    path = md_path or review_md_path(day)
    md_exists = os.path.isfile(path)
    pending = False
    filled: list[str] = []
    if md_exists:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        pending = is_ai_draft_pending(text)
        filled = _parse_data_filled(text)

    ingested = False
    conn = init_db(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM daily_reviews WHERE date=? LIMIT 1", (day,)
        ).fetchone()
        ingested = bool(row)
    finally:
        conn.close()

    miss = missing_focus_fields(filled)
    opt_miss = [
        k for k in sorted(OPTIONAL_CONTRACT_FIELDS)
        if k not in filled
    ]
    inbox_pending = _inbox_pending_for_day(day, input_dir=input_dir)
    status = classify_day_ready(
        md_exists=md_exists,
        pending_draft=pending,
        ingested=ingested,
        missing_focus=miss,
        inbox_pending=inbox_pending,
        optional_missing=opt_miss,
    )
    status.update({
        "day": day,
        "md_path": path,
        "md_exists": md_exists,
        "pending_draft": pending,
        "ingested": ingested,
        "filled": filled,
        "inbox_pending": inbox_pending,
        "focus_fields": list(CLOSE_FOCUS_FIELDS),
    })
    return status


def suggest_next_command(
    status: dict[str, Any],
    *,
    mode: str | None = None,
) -> str:
    """按红绿灯状态给一条可复制的下一条命令（对齐一日三步）。"""
    from ..config import get_llm_mode
    from ..core.day_help import draft_next_hint
    from ..core.llm_mode import LLM_MODE_DEEPSEEK, normalize_llm_mode

    day = status.get("day") or datetime.date.today().isoformat()
    m = normalize_llm_mode(mode if mode is not None else get_llm_mode())
    if not status.get("md_exists"):
        return draft_next_hint(day, m)
    if status.get("pending_draft"):
        return f"python -m review_tool llm-finalize {day} --write"
    if status.get("missing_focus"):
        if m == LLM_MODE_DEEPSEEK:
            return (
                f"python -m review_tool llm-vision --image 图 --date {day} "
                f"--kind diet|sleep|screen --diff"
            )
        return (
            f"宿主补关注字段后："
            f"python -m review_tool llm-finalize {day} --write"
            f"（流程：python -m review_tool day-help）"
        )
    if not status.get("ingested"):
        return f"python -m review_tool ingest {status.get('md_path') or ''}".rstrip()
    if status.get("inbox_pending"):
        return f"python -m review_tool inbox-archive --date {day} --file 图 --write"
    return "一日三步已齐；复习流程：python -m review_tool day-help"


def close_summary_for_llm_day(result: dict[str, Any]) -> str:
    """llm-day 结束后的三行摘要。"""
    vision = result.get("vision") or {}
    classification = vision.get("classification") or {}
    filled = classification.get("filled") or list((result.get("fields") or {}).keys())
    opt_miss = classification.get("optional_missing") or []
    miss = classification.get("missing") or []
    focus_miss = missing_focus_fields(filled)
    n_img = len(vision.get("images") or result.get("images") or [])
    read_bits = list(filled[:12])
    read = (
        ("、".join(read_bits) if read_bits else "（未识别契约字段）")
        + (f"（{n_img} 张图）" if n_img else "")
    )
    empty_bits = list(focus_miss)
    if "体脂率" in opt_miss:
        empty_bits.append("体脂率（可选）")
    elif miss:
        empty_bits.extend([m for m in miss[:6] if m not in empty_bits])
    empty = "、".join(empty_bits) if empty_bits else "（核心关注已齐）"

    day = result.get("day") or ""
    if result.get("written") and (
        (result.get("review") or {}).get("written")
        or vision.get("written")
    ):
        next_cmd = f"python -m review_tool llm-finalize {day} --write"
    elif not result.get("written"):
        next_cmd = (
            f"确认后：python -m review_tool llm-day --image … --date {day} --write"
        )
    else:
        next_cmd = f"python -m review_tool llm-finalize {day} --write"
    return format_close_summary(read=read, empty=empty, next_cmd=next_cmd)


def close_summary_for_doctor(
    result: dict[str, Any],
    *,
    day: str | None = None,
) -> tuple[str, str]:
    """doctor 结束：三行摘要 + 红绿灯行。返回 (summary, ready_line)。"""
    day = day or result.get("latest_date") or datetime.date.today().isoformat()
    ready = assess_day_ready(day, input_dir=None)
    # 若 diagnose 已带 day_ready 则复用
    if isinstance(result.get("day_ready"), dict):
        ready = result["day_ready"]

    llm = result.get("llm") or {}
    rows = result.get("rows")
    latest = result.get("latest_date") or "—"
    read = (
        f"库 {rows} 条；最新 {latest}；"
        f"mode={llm.get('mode') or '—'}"
    )
    empty_bits: list[str] = []
    if result.get("not_ingested"):
        empty_bits.append(f"未入库 {len(result['not_ingested'])} 天")
    if result.get("inbox_pending"):
        empty_bits.append(f"收件箱待处理 {len(result['inbox_pending'])}")
    if ready.get("missing_focus"):
        empty_bits.append("今日缺: " + "、".join(ready["missing_focus"]))
    if ready.get("pending_draft"):
        empty_bits.append("今日未定稿")
    empty = "；".join(empty_bits) if empty_bits else "（无阻塞空缺）"
    next_cmd = suggest_next_command(ready)
    summary = format_close_summary(read=read, empty=empty, next_cmd=next_cmd)
    return summary, render_day_ready_line(ready)


__all__ = [
    "assess_day_ready",
    "close_summary_for_doctor",
    "close_summary_for_llm_day",
    "render_day_ready_line",
    "suggest_next_command",
]
