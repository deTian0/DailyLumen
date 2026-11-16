"""一日三步：可复制命令模板（纯规则，零 I/O）。

心智：投放收件箱 → 草稿（llm-day / WorkBuddy 宿主）→ 定稿入库归档；
有事看 ``doctor`` 红绿灯。本模块只渲染文案，不读盘、不调 API ——
训练日推断只认调用方传入的 md 文本；读盘由 reports / api 层完成。
"""
from __future__ import annotations

import re

from .llm_mode import (
    LLM_MODE_DEEPSEEK,
    LLM_MODE_WORKBUDDY,
    normalize_llm_mode,
)

# 与 README / intake / 独立部署顶部口径对齐的三步标题
DAY_STEPS: tuple[str, ...] = (
    "① 投放收件箱",
    "② 草稿（llm-day 或 WorkBuddy 宿主）",
    "③ 定稿入库归档（llm-finalize → ingest → 归档）",
)

_INBOX = "local/每日复盘/收件箱"
_REVIEW_MD = "local/每日复盘/复盘/{ym}/{day}.md"
_TRAINING_DAY_RE = re.compile(
    r"^[ \t]*(?:训练日|training_day)[ \t]*[:：][ \t]*(.*)$",
    re.M | re.I,
)
_YES = frozenset({"是", "yes", "y", "true", "1"})
_NO = frozenset({"否", "no", "n", "false", "0"})


def review_md_template(day: str) -> str:
    """复盘 md 路径模板（按日推年月）。"""
    ym = day[:7] if len(day) >= 7 else "YYYY-MM"
    return _REVIEW_MD.format(ym=ym, day=day)


def infer_training_day_hint(day: str, *, md_text: str | None = None) -> bool | None:
    """从复盘 md 数据块文本推断训练日（零 I/O；无字段 → None）。

    ``md_text`` 由调用方读盘后传入（core 层零 I/O；reports / api 负责读文件）；
    打网、读盘都不在本层。
    """
    m = _TRAINING_DAY_RE.search(md_text or "")
    if not m:
        return None
    val = (m.group(1) or "").strip().split()[0].lower() if (m.group(1) or "").strip() else ""
    if val in _YES:
        return True
    if val in _NO:
        return False
    return None


def training_day_branch(day: str) -> list[str]:
    """训练日附加指引（纯文案；调用方决定是否插入）。"""
    return [
        "训练日附加（有练练 completed 时）",
        f"  python -m review_tool keepstrong --date {day} --write"
        "   # 先落复盘 md（G1）；Web：Life→训练→练练→复盘 md",
        f"  python -m review_tool keepstrong --date {day} --write --ingest"
        "  # 或一条写 md+入库",
        "  # 可选代勾 ClickUp「练练健身」（须预览→确认，禁止静默自动勾）：",
        "  python -m review_tool clickup-habit --habit lianlian"
        "   # 默认 dry-run",
        "",
    ]


def render_day_help(
    day: str,
    mode: str | None = None,
    *,
    highlight_current: bool = True,
    training_day: bool | None = None,
) -> str:
    """打印「一日三步」+ workbuddy / deepseek 两套可复制命令。

    ``mode`` 非法时仍归一失败会抛 ``LlmModeError``（与全局约定一致）。
    ``training_day=True`` 时追加 keepstrong --write / 可选代勾说明（D7）；
    ``False``/``None`` 不插入，避免非训练日误导。
    """
    m = normalize_llm_mode(mode)
    md = review_md_template(day)
    inbox_ex = f"{_INBOX}/截图-{day}-….jpg"

    lines: list[str] = [
        f"# 一日三步 · {day} · 当前 mode={m}",
        "",
        "闭环：投放收件箱 → 草稿 → llm-finalize → ingest → 归档；"
        "有事看 doctor 红绿灯。",
        "健康叙事：饮食 + 睡眠 + 运动逐日（体重按周记、体脂可选，缺测勿伪造）。",
        "",
        DAY_STEPS[0],
        f"  截图 / 简报 → {_INBOX}/（或口述给宿主）",
        f"  复盘 md：复制模板 → {md}",
        "",
        DAY_STEPS[1],
        "",
        f"  【{LLM_MODE_WORKBUDDY}】宿主按 intake / llm-host-contract 落 md"
        "（勿跑 llm-day / llm-vision / llm-review）",
        f"    python -m review_tool ai-context {day}",
        "    python -m review_tool doctor",
        "",
        f"  【{LLM_MODE_DEEPSEEK}】仓库 CLI"
        f"（须 DAILYLUMEN_LLM_MODE=deepseek 且 INTEGRATION_DEEPSEEK_ENABLED=true）",

        f"    python -m review_tool llm-day --image {inbox_ex} "
        f"--date {day} --diff",
        f"    python -m review_tool llm-day --image {inbox_ex} "
        f"--date {day} --write [--review] [--archive-inbox]",
        "    # 或分类型：--kind diet|sleep|screen",
        "",
        DAY_STEPS[2],
        f"  python -m review_tool llm-finalize {day}          # dry-run + 并排 diff",
        f"  python -m review_tool llm-finalize {day} --write",
        f"  python -m review_tool ingest {md}",
        f"  python -m review_tool inbox-archive --date {day} "
        f"--file {inbox_ex} --write",
        "  # 若草稿已 --archive-inbox，可跳过 inbox-archive",
        "",
    ]
    if training_day is True:
        lines.extend(training_day_branch(day))
    lines.extend([
        "收工检查",
        "  python -m review_tool doctor   # 收工摘要 + 红绿灯 + 集成开关/最近失败",
        "  # 关 INTEGRATION_* 时勿把缺 ClickUp/练练素材当库病",
        "  # 可选分数收口：python -m review_tool finalize "
        f"--date {day} --apply",
        "",
    ])
    if highlight_current:
        if m == LLM_MODE_WORKBUDDY:
            lines.append(
                f"→ 当前 mode={m}：走【{LLM_MODE_WORKBUDDY}】路径；"
                f"独立跑再改 DAILYLUMEN_LLM_MODE={LLM_MODE_DEEPSEEK}。"
            )
        else:
            lines.append(
                f"→ 当前 mode={m}：走【{LLM_MODE_DEEPSEEK}】路径；"
                f"测完建议改回 {LLM_MODE_WORKBUDDY}。"
            )
    return "\n".join(lines)


def draft_next_hint(
    day: str,
    mode: str | None = None,
    *,
    training_day: bool | None = None,
) -> str:
    """无 md / 需补草稿时的下一条命令（按 mode）。

    训练日优先提示 ``keepstrong --write``（落 md），不诱导静默代勾。
    """
    if training_day is True:
        return (
            f"python -m review_tool keepstrong --date {day} --write"
            f"  # 训练日落复盘 md；可选再 clickup-habit --habit lianlian（须确认）"
        )
    m = normalize_llm_mode(mode)
    if m == LLM_MODE_DEEPSEEK:
        return (
            f"python -m review_tool llm-day --image 图 --date {day} --diff"
        )
    return (
        f"宿主按 intake 落 md 后："
        f"python -m review_tool llm-finalize {day} --write"
        f"（复习流程：python -m review_tool day-help）"
    )


__all__ = [
    "DAY_STEPS",
    "draft_next_hint",
    "infer_training_day_hint",
    "render_day_help",
    "review_md_template",
    "training_day_branch",
]
