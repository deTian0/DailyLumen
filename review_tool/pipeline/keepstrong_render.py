"""练练健身素材渲染：记录 / 体征 / 计划 → markdown（纯函数、零 I/O）。

供 ``pipeline.keepstrong`` CLI 与单测复用。中文产品名一律「练练健身」。
⛔ 不得写入 API Key / Authorization 头。
"""
from __future__ import annotations

from typing import Any

PRODUCT_CN = "练练健身"


def _day_display(day_str: str | None) -> str:
    """``yyyyMMdd`` → ``YYYY-MM-DD``；已是 ISO 则原样。"""
    if not day_str:
        return ""
    s = str(day_str).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _fmt_duration(seconds: Any) -> str:
    try:
        sec = int(seconds)
    except (TypeError, ValueError):
        return ""
    if sec < 0:
        return ""
    if sec < 60:
        return f"{sec}s"
    mins = sec // 60
    rem = sec % 60
    if rem:
        return f"{mins}min{rem}s"
    return f"{mins}min"


def _action_line(action: dict) -> str:
    name = (
        action.get("name")
        or action.get("actionName")
        or action.get("actionId")
        or "未命名动作"
    )
    bits = [str(name)]
    sets = action.get("sets") or action.get("setCount")
    reps = action.get("reps") or action.get("repCount")
    weight = action.get("weight")
    unit = action.get("weightUnit") or "kg"
    if sets is not None and reps is not None:
        bits.append(f"{sets}×{reps}")
        if weight not in (None, "", 0, "0"):
            bits.append(f"@{weight}{unit}")
    elif action.get("durationSeconds") is not None:
        bits.append(_fmt_duration(action.get("durationSeconds")))
    return "- " + " ".join(bits)


def render_records_section(records: list[dict] | None) -> list[str]:
    """训练记录段。空列表 → 显式写「无训练记录」（合法，不是错误）。"""
    lines = ["## 训练记录", ""]
    if not records:
        lines += ["（无训练记录）", ""]
        return lines
    for rec in records:
        day = _day_display(rec.get("dayStr") or rec.get("date") or "")
        ttype = rec.get("trainingType") or rec.get("type") or ""
        title = rec.get("name") or rec.get("planName") or ttype or "训练"
        dur = _fmt_duration(rec.get("durationSeconds"))
        cal = rec.get("calorie") or rec.get("calories")
        head = f"### {day} · {title}" if day else f"### {title}"
        lines.append(head)
        meta = []
        if ttype:
            meta.append(f"类型：{ttype}")
        if dur:
            meta.append(f"时长：{dur}")
        if cal is not None and cal != "":
            meta.append(f"热量：{cal} kcal")
        if meta:
            lines.append("- " + "｜".join(meta))
        actions = rec.get("actions")
        if not actions:
            lines.append("- 动作明细：（空 —— 临时训练仅有时长/热量，属合法输入）")
        else:
            for a in actions:
                if isinstance(a, dict):
                    lines.append(_action_line(a))
        lines.append("")
    return lines


def render_body_section(
    profile: Any = None,
    logs: list[dict] | None = None,
) -> list[str]:
    lines = ["## 体征", ""]
    if isinstance(profile, dict) and profile:
        w = profile.get("weight")
        fat = profile.get("fat") or profile.get("bodyFat")
        height = profile.get("height")
        bits = []
        if w is not None:
            bits.append(f"体重 {w} kg")
        if fat is not None:
            bits.append(f"体脂 {fat}%")
        if height is not None:
            bits.append(f"身高 {height} cm")
        src = profile.get("weightSource") or profile.get("dayStr")
        if bits:
            line = "- 档案：" + "｜".join(bits)
            if src:
                line += f"（来源/日：{src}）"
            lines.append(line)
        else:
            lines.append("- 档案：（无体重/体脂/身高）")
    else:
        lines.append("- 档案：（未拉取或为空）")

    logs = logs or []
    if not logs:
        lines += ["- 体重日志：（无）", ""]
        return lines
    lines.append("- 体重日志：")
    for row in logs:
        day = _day_display(row.get("dayStr") or row.get("date") or "")
        val = row.get("value") or row.get("weight")
        unit = row.get("unit") or "kg"
        lines.append(f"  - {day}: {val} {unit}".rstrip())
    lines.append("")
    return lines


def render_plan_section(plan: Any) -> list[str]:
    lines = ["## 跑（训练）计划", ""]
    if not plan:
        lines += ["（无计划）", ""]
        return lines
    # 响应可能是 list 或 {list: [...]} / 单对象
    items: list[Any]
    if isinstance(plan, list):
        items = plan
    elif isinstance(plan, dict):
        inner = plan.get("list") or plan.get("plans") or plan.get("data")
        if isinstance(inner, list):
            items = inner
        else:
            items = [plan]
    else:
        lines += ["（无法解析的计划结构）", ""]
        return lines

    if not items:
        lines += ["（无计划）", ""]
        return lines

    for p in items:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or p.get("planName") or "未命名计划"
        pid = p.get("planId") or p.get("id") or ""
        head = f"- **{name}**"
        if pid:
            head += f"（planId={pid}）"
        lines.append(head)
        schedules = (
            p.get("schedules")
            or p.get("cycle")
            or p.get("days")
            or p.get("workouts")
            or []
        )
        if isinstance(schedules, list):
            for i, slot in enumerate(schedules, 1):
                if isinstance(slot, dict):
                    label = (
                        slot.get("name")
                        or slot.get("title")
                        or slot.get("workoutName")
                        or slot.get("type")
                        or "—"
                    )
                    lines.append(f"  - 日{i}: {label}")
                else:
                    lines.append(f"  - 日{i}: {slot}")
    lines.append("")
    return lines


def render_material(
    bundle: dict[str, Any],
    *,
    label_day: str,
    generated_at: str,
    types: set[str] | None = None,
) -> str:
    """整份素材 md。``label_day`` 为文件名用的 ISO 日或区间标签。"""
    types = types or {"records", "body", "plan"}
    lines = [
        f"# {PRODUCT_CN} 素材 · {label_day}",
        "",
        f"> ⚠️ **这是素材，不是复盘成品** —— 由 `python -m review_tool keepstrong` 从「{PRODUCT_CN}」拉取。",
        "> 练练是**输入通道**（与截图同级）：须先写入当日复盘 md 附录，再 `ingest`（G1）。",
        "> ⛔ 本文件只含数据：**不含** API Key、**不含** Authorization 头。",
        "> 空训练记录 / 空动作明细是**合法输入**（临时训练可只有时长与热量）。",
        "",
        f"- 生成时间：{generated_at}",
        f"- 数据来源：{PRODUCT_CN}",
        f"- 查询区间：{_day_display(bundle.get('start'))} → {_day_display(bundle.get('end'))}",
        "",
    ]
    if "records" in types:
        lines += render_records_section(bundle.get("records") or [])
    if "body" in types:
        lines += render_body_section(
            bundle.get("body_profile"), bundle.get("body_logs") or []
        )
    if "plan" in types:
        lines += render_plan_section(bundle.get("plan"))
    return "\n".join(lines).rstrip() + "\n"
