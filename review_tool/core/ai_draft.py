"""AI 草稿 / 定稿标记（纯规则，零 I/O）。

约定：
- **草稿**：含待人审标记（「七、AI」blockquote 或 HTML 注释）→
  ``ingest`` **默认跳过**该 md（防误吞未定稿）。
- **定稿**：人审后去掉草稿标记；可选写在「七-B · 定稿」区。
- **草稿箱目录**（``local/每日复盘/草稿箱/``）：与收件箱同级，永不参与扫描。

见 ``docs/LLM能力拆分草案.md`` 草稿/定稿专节与 intake skill。
"""
from __future__ import annotations

# 文件头 / 正文均可出现；任一命中即视为未定稿
AI_DRAFT_MARKERS: tuple[str, ...] = (
    "草稿 / 待人审",
    "<!-- dailylumen:ai-draft -->",
    "<!-- dailylumen:llm-pending-review -->",
)

# llm-vision / llm-day --write 落盘时戳此注释（人审后删）
LLM_PENDING_HTML = "<!-- dailylumen:llm-pending-review -->"

# 与 wrap_ai_draft 对齐的可见提示（blockquote 首行关键词）
AI_DRAFT_VISIBLE = "草稿 / 待人审"

DRAFTS_DIRNAME = "草稿箱"


def is_ai_draft_pending(md_text: str | None) -> bool:
    """正文是否仍含未定稿标记。"""
    if not md_text:
        return False
    return any(m in md_text for m in AI_DRAFT_MARKERS)


def stamp_llm_pending(md_text: str) -> str:
    """幂等：在文首加入 ``LLM_PENDING_HTML``（已有则不动）。"""
    text = (md_text or "").replace("\r\n", "\n")
    if LLM_PENDING_HTML in text:
        return text
    if text.startswith("---\n") or text.lstrip().startswith("#"):
        return LLM_PENDING_HTML + "\n" + text
    return LLM_PENDING_HTML + "\n\n" + text


def clear_llm_pending(md_text: str) -> str:
    """去掉 pending HTML 注释行（人审定稿辅助；纯字符串）。"""
    text = (md_text or "").replace("\r\n", "\n")
    lines = [
        ln
        for ln in text.splitlines(keepends=True)
        if LLM_PENDING_HTML not in ln and "<!-- dailylumen:ai-draft -->" not in ln
    ]
    return "".join(lines)


__all__ = [
    "AI_DRAFT_MARKERS",
    "AI_DRAFT_VISIBLE",
    "DRAFTS_DIRNAME",
    "LLM_PENDING_HTML",
    "clear_llm_pending",
    "is_ai_draft_pending",
    "stamp_llm_pending",
]
