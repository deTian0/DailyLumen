"""一日三步：可复制命令模板（纯规则，零 I/O）。

心智：投放收件箱 → 草稿（llm-day / WorkBuddy 宿主）→ 定稿入库归档；
有事看 ``doctor`` 红绿灯。本模块只渲染文案，不读盘、不调 API。
"""
from __future__ import annotations

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


def review_md_template(day: str) -> str:
    """复盘 md 路径模板（按日推年月）。"""
    ym = day[:7] if len(day) >= 7 else "YYYY-MM"
    return _REVIEW_MD.format(ym=ym, day=day)


def render_day_help(
    day: str,
    mode: str | None = None,
    *,
    highlight_current: bool = True,
) -> str:
    """打印「一日三步」+ workbuddy / deepseek 两套可复制命令。

    ``mode`` 非法时仍归一失败会抛 ``LlmModeError``（与全局约定一致）。
    """
    m = normalize_llm_mode(mode)
    md = review_md_template(day)
    inbox_ex = f"{_INBOX}/截图-{day}-….jpg"

    lines: list[str] = [
        f"# 一日三步 · {day} · 当前 mode={m}",
        "",
        "闭环：投放收件箱 → 草稿 → llm-finalize → ingest → 归档；"
        "有事看 doctor 红绿灯。",
        "健康叙事：体重 + 饮食 + 睡眠 + 训练（体脂可选，勿伪造）。",
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
        f"    python -m review_tool doctor",
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
        "收工检查",
        "  python -m review_tool doctor   # 收工摘要 + 红绿灯 + 集成开关/最近失败",
        "  # 关 INTEGRATION_* 时勿把缺 ClickUp/练练素材当库病",
        "  # 可选分数收口：python -m review_tool finalize "
        f"--date {day} --apply",
        "",
    ]
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


def draft_next_hint(day: str, mode: str | None = None) -> str:
    """无 md / 需补草稿时的下一条命令（按 mode）。"""
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
    "render_day_help",
    "review_md_template",
]
