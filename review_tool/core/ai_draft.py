"""AI 草稿 / 定稿标记（纯规则，零 I/O）。

约定：
- **草稿**：含待人审标记（「七、AI」blockquote 或 HTML 注释）→
  ``ingest`` **默认跳过**该 md（防误吞未定稿）。
- **定稿**：人审后去掉草稿标记；可选写在「七-B · 定稿」区。
- **草稿箱目录**（``local/每日复盘/草稿箱/``）：与收件箱同级，永不参与扫描。

见 ``docs/LLM能力拆分草案.md`` 草稿/定稿专节与 intake skill。
"""
from __future__ import annotations

import re

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

_SECTION_RE = re.compile(
    r"(^##\s*七、AI 评价与建议[^\n]*\n)(.*?)(?=^##\s|\Z)",
    re.S | re.M,
)
_A_HEADER = "### 七-A · AI 草稿（待人审）"
_B_HEADER = "### 七-B · 定稿（人审通过）"
_A_RE = re.compile(
    rf"(^{re.escape(_A_HEADER)}\s*\n)(.*?)(?=^{re.escape(_B_HEADER)}\s*$|\Z)",
    re.S | re.M,
)
_B_RE = re.compile(
    rf"(^{re.escape(_B_HEADER)}\s*\n)(.*?)(?=^###\s|\Z)",
    re.S | re.M,
)

# 七-B 仍是占位 / 指引时，可被七-A 正文覆盖
_B_PLACEHOLDER_HINTS: tuple[str, ...] = (
    "人审通过后的评价与建议写在这里",
    "（人审通过后填写）",
    "定稿后请删除七-A",
)


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


def _strip_draft_blockquote(body: str) -> str:
    """去掉七-A 顶部含「草稿 / 待人审」的连续 blockquote 行。"""
    lines = (body or "").replace("\r\n", "\n").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(">") and AI_DRAFT_VISIBLE in lines[i]:
        while i < len(lines) and (
            lines[i].lstrip().startswith(">") or not lines[i].strip()
        ):
            # 空行仍算在草稿说明块内，直到下一段非 > 正文
            if not lines[i].strip():
                # 预看：若后面还是 > 则继续吞；否则结束
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines) or not lines[j].lstrip().startswith(">"):
                    break
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        return "\n".join(lines[i:]).strip()
    # 无标准草稿块时，仍剔除含可见标记的行
    kept = [ln for ln in lines if AI_DRAFT_VISIBLE not in ln]
    return "\n".join(kept).strip()


def _is_b_placeholder(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return True
    return any(h in text for h in _B_PLACEHOLDER_HINTS)


def promote_ai_draft(md_text: str) -> str:
    """本地定稿变换：清 pending/草稿标记；七-A 正文提升到七-B（占位时）。

    纯字符串、零 I/O、不依赖 DeepSeek。幂等：已定稿再跑基本不变
    （仍保证无 pending 标记）。
    """
    text = clear_llm_pending((md_text or "").replace("\r\n", "\n"))
    sm = _SECTION_RE.search(text)
    if not sm:
        # 无「七、AI」节：只清残留标记行
        lines = [ln for ln in text.splitlines(keepends=True) if AI_DRAFT_VISIBLE not in ln]
        return "".join(lines)

    head, body = sm.group(1), sm.group(2)
    am = _A_RE.search(body)
    bm = _B_RE.search(body)
    if am and bm:
        a_body = _strip_draft_blockquote(am.group(2))
        b_body = (bm.group(2) or "").strip()
        if a_body and _is_b_placeholder(b_body):
            b_body = a_body
        elif not b_body and a_body:
            b_body = a_body
        new_a = (
            f"{_A_HEADER}\n\n"
            f"> （已定稿；原稿已提升至七-B）\n\n"
        )
        new_b = f"{_B_HEADER}\n\n{b_body.strip()}\n\n" if b_body else f"{_B_HEADER}\n\n"
        # 保留 A/B 之外的前缀（如节首说明 blockquote）
        prefix = body[: am.start()].rstrip()
        # 去掉前缀里仍含「草稿 / 待人审」的行（模板说明可保留其它句）
        if prefix:
            pref_lines = [
                ln for ln in prefix.splitlines()
                if AI_DRAFT_VISIBLE not in ln
            ]
            prefix = "\n".join(pref_lines).rstrip()
        mid = (prefix + "\n\n" if prefix else "") + new_a + new_b
        # A/B 之后若还有尾巴（少见）
        tail = body[bm.end() :]
        new_section = head + mid.rstrip() + "\n" + (tail.lstrip("\n") if tail.strip() else "")
        if not new_section.endswith("\n"):
            new_section += "\n"
        text = text[: sm.start()] + new_section + text[sm.end() :]
    else:
        # 无分区：剔除可见草稿行即可
        lines = [ln for ln in text.splitlines(keepends=True) if AI_DRAFT_VISIBLE not in ln]
        text = "".join(lines)

    # 兜底：任何残留 HTML / 可见标记
    text = clear_llm_pending(text)
    if AI_DRAFT_VISIBLE in text:
        text = "".join(
            ln for ln in text.splitlines(keepends=True) if AI_DRAFT_VISIBLE not in ln
        )
    return text


__all__ = [
    "AI_DRAFT_MARKERS",
    "AI_DRAFT_VISIBLE",
    "DRAFTS_DIRNAME",
    "LLM_PENDING_HTML",
    "clear_llm_pending",
    "is_ai_draft_pending",
    "promote_ai_draft",
    "stamp_llm_pending",
]
