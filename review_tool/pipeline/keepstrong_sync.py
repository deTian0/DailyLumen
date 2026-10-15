"""练练健身素材 → 当日复盘 md（M18 · 打通 G1）。

流程：API/素材 dict → 写入「附录 · 训练明细」+ 可选数据块体重 →（可选）``ingest``。
⛔ 禁止只进库不落 md。幂等：重复同步只**替换** ``<!-- keepstrong:begin/end -->`` 块。

``keepstrong --write`` 才落盘；默认 dry-run 只打印将要写入的内容。
"""
from __future__ import annotations

import os
import re
from typing import Any

from ..config import GENERATED_DIR, KS_ACTION_MAP, TRAINING_MOVES
from ..core.training import resolve_move
from ..core.util import slugify

BEGIN = "<!-- keepstrong:begin -->"
END = "<!-- keepstrong:end -->"

_SECTION_HEADER = "## 附录 · 训练明细"
_SECTION_RE = re.compile(
    r"(^##[^\n]*训练明细[^\n]*$\n?)(.*?)(?=^##\s|\Z)", re.S | re.M
)
_DATA_BLOCK_RE = re.compile(r"(```data\s*\n)(.*?)(```)", re.S)
_WEIGHT_LINE_RE = re.compile(
    r"^([ \t]*(?:体重_kg|体重|weight_kg)\s*[:：]\s*)(.*)$", re.M
)


def resolve_ks_item(
    name: str | None,
    action_id: str | None = None,
    *,
    action_map: dict | None = None,
    moves: dict | None = None,
) -> tuple[str, str]:
    """练练动作名 / actionId → ``(item_key, 展示名)``。

    顺序：``KS_ACTION_MAP``（id 优先）→ ``TRAINING_MOVES`` → ``slugify(name)``。
    """
    amap = KS_ACTION_MAP if action_map is None else action_map
    raw_name = (name or "").strip()
    aid = (action_id or "").strip()
    if aid and aid in amap:
        key = amap[aid]
        return key, raw_name or key
    if raw_name and raw_name in amap:
        key = amap[raw_name]
        return key, raw_name
    if raw_name:
        item_key, label, _ = resolve_move(raw_name, moves or TRAINING_MOVES)
        if item_key != raw_name or raw_name in (moves or TRAINING_MOVES):
            return item_key, label
        return slugify(raw_name), raw_name
    if aid:
        return slugify(aid), aid
    return "unknown", "unknown"


def seconds_to_min(seconds: Any) -> int | None:
    """``durationSeconds`` → 分钟（至少 1，若 >0）；无效返回 None。"""
    try:
        sec = int(seconds)
    except (TypeError, ValueError):
        return None
    if sec <= 0:
        return None
    return max(1, int(round(sec / 60.0)))


def format_action_line(action: dict, *, action_map: dict | None = None) -> str | None:
    name = action.get("name") or action.get("actionName")
    aid = action.get("actionId") or action.get("id")
    key, label = resolve_ks_item(name, aid, action_map=action_map)
    display = label or key
    sets = action.get("sets") or action.get("setCount")
    reps = action.get("reps") or action.get("repCount")
    weight = action.get("weight")
    unit = action.get("weightUnit") or "kg"
    if sets is not None and reps is not None:
        line = f"- {display} {int(sets)}×{int(reps)}"
        if weight not in (None, "", 0, "0"):
            line += f" @{weight}{unit}"
        return line
    mins = None
    if action.get("durationSeconds") is not None:
        mins = seconds_to_min(action.get("durationSeconds"))
    elif action.get("minutes") is not None:
        try:
            mins = max(1, int(round(float(action["minutes"]))))
        except (TypeError, ValueError):
            mins = None
    if mins is not None:
        return f"- {display} {mins}min"
    # 无组次也无时长：仍落一行名字，保证可重建
    return f"- {display}"


def records_to_block(
    records: list[dict] | None,
    *,
    action_map: dict | None = None,
    plan_fallback: str = "练练训练",
) -> str | None:
    """多条记录 → keepstrong 标记块正文；无记录返回 ``None``（不造空章节）。"""
    if not records:
        return None
    chunks: list[str] = []
    for i, rec in enumerate(records):
        ttype = rec.get("trainingType") or rec.get("type") or ""
        plan = (
            rec.get("name")
            or rec.get("planName")
            or ("临时训练" if ttype in ("temp", "temporary") else "")
            or ttype
            or plan_fallback
        )
        if len(records) > 1:
            plan = f"{plan}#{i + 1}"
        lines = [f"- 计划：{plan}｜来源：练练"]
        actions = rec.get("actions") or []
        if isinstance(actions, list) and actions:
            for a in actions:
                if isinstance(a, dict):
                    line = format_action_line(a, action_map=action_map)
                    if line:
                        lines.append(line)
        else:
            mins = seconds_to_min(rec.get("durationSeconds"))
            if mins is not None:
                lines.append(f"- 训练 {mins}min")
            else:
                # 有记录但无时长无动作 —— 仍写一行占位，避免丢 session
                lines.append("- 训练（无明细）")
        chunks.append("\n".join(lines))
    inner = "\n\n".join(chunks)
    return f"{BEGIN}\n{inner}\n{END}"


def _wrap_section(block: str) -> str:
    return f"{_SECTION_HEADER}\n\n{block}\n"


def apply_training_block(md_text: str, block: str | None) -> str:
    """把 keepstrong 块幂等写入 md。

    - ``block is None``：若已有 keepstrong 块则删除；否则不动。
    - 已有 ``BEGIN/END``：整段替换。
    - 已有训练明细章节、无标记：在章节末尾追加块（手写内容保留）。
    - 无章节：在 `` ```data `` 前（或文末）新建章节。
    """
    text = md_text.replace("\r\n", "\n")
    if block is None:
        if BEGIN in text and END in text:
            text = re.sub(
                re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
                "",
                text,
                count=1,
                flags=re.S,
            )
            # 若章节因此变空，去掉空章节头
            text = re.sub(
                r"^##[^\n]*训练明细[^\n]*\n+(?=(?:##\s|```data|\Z))",
                "",
                text,
                count=1,
                flags=re.M,
            )
        return text.rstrip() + "\n"

    if BEGIN in text and END in text:
        return re.sub(
            re.escape(BEGIN) + r".*?" + re.escape(END),
            block.strip(),
            text,
            count=1,
            flags=re.S,
        )

    m = _SECTION_RE.search(text)
    if m:
        # 章节已存在：在正文末尾追加标记块
        body = m.group(2).rstrip()
        new_body = (body + "\n\n" if body else "") + block.strip() + "\n"
        return text[: m.start(2)] + new_body + text[m.end(2) :]

    section = _wrap_section(block.strip())
    dm = _DATA_BLOCK_RE.search(text)
    if dm:
        insert_at = dm.start()
        return text[:insert_at].rstrip() + "\n\n" + section + "\n" + text[insert_at:]
    return text.rstrip() + "\n\n" + section + "\n"


def pick_weight_kg(
    body_logs: list[dict] | None,
    body_profile: dict | None = None,
    *,
    day_str: str | None = None,
) -> float | None:
    """优先取当日 body_logs；否则 profile.weight。"""
    day = (day_str or "").replace("-", "")
    for row in body_logs or []:
        d = str(row.get("dayStr") or row.get("date") or "").replace("-", "")
        if day and d and d != day:
            continue
        val = row.get("value") if row.get("value") is not None else row.get("weight")
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    if isinstance(body_profile, dict) and body_profile.get("weight") is not None:
        # profile 无 day 限制时，仅在未指定 day 或 profile.dayStr 匹配时用
        pdata = str(body_profile.get("dayStr") or "").replace("-", "")
        if not day or not pdata or pdata == day:
            try:
                return float(body_profile["weight"])
            except (TypeError, ValueError):
                return None
    return None


def apply_weight_kg(md_text: str, weight: float | None) -> str:
    """写入 / 更新数据块 ``体重_kg``；``weight is None`` 则不动。"""
    if weight is None:
        return md_text
    text = md_text.replace("\r\n", "\n")
    val = f"{weight:g}"

    def _sub_block(m: re.Match) -> str:
        body = m.group(2)
        if _WEIGHT_LINE_RE.search(body):
            body2 = _WEIGHT_LINE_RE.sub(rf"\g<1>{val}", body, count=1)
        else:
            # 插在日期行后
            if re.search(r"^日期\s*[:：].*$", body, re.M):
                body2 = re.sub(
                    r"^(日期\s*[:：].*)$",
                    rf"\1\n体重_kg: {val}",
                    body,
                    count=1,
                    flags=re.M,
                )
            else:
                body2 = f"体重_kg: {val}\n" + body
        return m.group(1) + body2 + m.group(3)

    if not _DATA_BLOCK_RE.search(text):
        return text
    return _DATA_BLOCK_RE.sub(_sub_block, text, count=1)


def review_md_path(day_iso: str, *, root: str | None = None) -> str:
    """``YYYY-MM-DD`` → ``复盘/YYYY-MM/YYYY-MM-DD.md``。"""
    day = day_iso.strip()
    if len(day) == 8 and day.isdigit():
        day = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    y, m, _ = day.split("-")
    base = root if root is not None else GENERATED_DIR
    return os.path.join(base, f"{y}-{m}", f"{day}.md")


def sync_markdown(
    md_text: str,
    *,
    records: list[dict] | None = None,
    body_logs: list[dict] | None = None,
    body_profile: dict | None = None,
    day_str: str | None = None,
    action_map: dict | None = None,
) -> tuple[str, dict[str, Any]]:
    """纯函数：md + 练练数据 → 新 md + 摘要。"""
    block = records_to_block(records, action_map=action_map)
    out = apply_training_block(md_text, block)
    weight = pick_weight_kg(body_logs, body_profile, day_str=day_str)
    out2 = apply_weight_kg(out, weight)
    summary = {
        "training_written": block is not None,
        "training_replaced": BEGIN in md_text and block is not None,
        "weight_kg": weight,
        "weight_written": weight is not None and out2 != out,
        "changed": out2 != md_text.replace("\r\n", "\n"),
    }
    return out2, summary


def write_sync(
    path: str,
    *,
    records: list[dict] | None = None,
    body_logs: list[dict] | None = None,
    body_profile: dict | None = None,
    day_str: str | None = None,
    action_map: dict | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """读 md → sync →（可选）写回。返回摘要。"""
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    new_text, summary = sync_markdown(
        raw,
        records=records,
        body_logs=body_logs,
        body_profile=body_profile,
        day_str=day_str,
        action_map=action_map,
    )
    summary["path"] = path
    summary["dry_run"] = dry_run
    if dry_run or not summary["changed"]:
        return summary
    with open(path, "wb") as f:
        f.write(new_text.replace("\r\n", "\n").encode("utf-8"))
    # 回读校验
    with open(path, "rb") as f:
        got = f.read().decode("utf-8")
    if got.replace("\r\n", "\n") != new_text.replace("\r\n", "\n"):
        raise OSError(f"写盘回读不一致: {path}")
    return summary
