"""周 / 月报叙述润色（仅 prose；判定与数字仍走既有实现 · R1）。

仅 ``DAILYLUMEN_LLM_MODE=deepseek``；``workbuddy`` 跳过并提示。
保护：表格行、标题行、代码围栏、生成脚注不得改；润色后做结构指纹校验。
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..core.llm_mode import LLM_MODE_DEEPSEEK, LLM_MODE_WORKBUDDY, normalize_llm_mode
from ..pipeline.deepseek import (
    Client,
    DeepSeekModeError,
    assistant_text,
    get_llm_mode,
)

SYSTEM_PROMPT = """你是 DailyLumen 周/月报润色助手。
硬规则（R1）：
1. 只润色叙述性散文（通顺、简洁、可执行语气）；⛔ 不得改动任何数字、单位、日期、
   百分比、分数、表格单元格、字段名、判定结论措辞中的量化部分。
2. ⛔ 不得新增事实 / 编造趋势；上下文没有的数字不要写。
3. 输入是 JSON：{"blocks":[{"id":0,"text":"..."},...]}；
   输出必须是 JSON object：{"blocks":[{"id":0,"text":"润色后"},...]}，
   id 集合与输入完全一致；只改 text。
4. 不要输出 Markdown 围栏或其它说明。"""


_FENCE_RE = re.compile(r"^```")
_HEADING_RE = re.compile(r"^#{1,6}\s")
_TABLE_RE = re.compile(r"^\s*\|")
_HR_RE = re.compile(r"^---+\s*$")
_FOOT_RE = re.compile(r"^\*生成时间：")


def is_protected_line(line: str) -> bool:
    s = line.rstrip("\n")
    if not s.strip():
        return True
    if _HEADING_RE.match(s) or _TABLE_RE.match(s) or _HR_RE.match(s):
        return True
    if _FENCE_RE.match(s.strip()) or _FOOT_RE.match(s):
        return True
    # 系统口径提示 blockquote 保护数字段
    if s.lstrip().startswith(">") and (
        "口径" in s or "脚本" in s or "数据源" in s or "不计入四维" in s
    ):
        return True
    return False


def split_polish_blocks(md_text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """拆成行；抽出可润色的连续散文块。

    返回 ``(lines, blocks)``，blocks 每项 ``{id, start, end, text}``（end 不含）。
    """
    lines = (md_text or "").replace("\r\n", "\n").splitlines(keepends=True)
    blocks: list[dict[str, Any]] = []
    i = 0
    bid = 0
    in_fence = False
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence or is_protected_line(raw):
            i += 1
            continue
        # 连续非保护行 → 一块
        start = i
        chunk: list[str] = []
        while i < len(lines):
            if _FENCE_RE.match(lines[i].strip()):
                break
            if is_protected_line(lines[i]):
                break
            chunk.append(lines[i])
            i += 1
        text = "".join(chunk).strip("\n")
        if text.strip():
            blocks.append({
                "id": bid,
                "start": start,
                "end": i,
                "text": text,
            })
            bid += 1
    return lines, blocks


def apply_polished_blocks(
    lines: list[str],
    blocks: list[dict[str, Any]],
    polished: list[dict[str, Any]],
) -> str:
    """把润色后的块写回行列表。"""
    by_id = {int(b["id"]): b for b in polished if "id" in b and "text" in b}
    # 从后往前替换，避免偏移
    ordered = sorted(blocks, key=lambda b: b["start"], reverse=True)
    out = list(lines)
    for b in ordered:
        new = by_id.get(int(b["id"]))
        if not new:
            continue
        text = (new.get("text") or "").rstrip() + "\n"
        # 保持块尾空行习惯：原块若以空行结束则补一个
        out[b["start"] : b["end"]] = [text]
    return "".join(out)


def structural_fingerprint(md_text: str) -> str:
    """只保留受保护行，用于 R1 校验。"""
    lines = (md_text or "").replace("\r\n", "\n").splitlines()
    kept: list[str] = []
    in_fence = False
    for ln in lines:
        if _FENCE_RE.match(ln.strip()):
            in_fence = not in_fence
            kept.append(ln)
            continue
        if in_fence or is_protected_line(ln + "\n"):
            kept.append(ln)
    return "\n".join(kept)


def polish_markdown(
    md_text: str,
    *,
    client: Client | None = None,
    mode: str | None = None,
    kind: str = "week",
) -> dict[str, Any]:
    """润色叙述块；返回 ``{original, polished, changed, block_count}``。"""
    m = normalize_llm_mode(mode) if mode is not None else get_llm_mode()
    if m != LLM_MODE_DEEPSEEK:
        raise DeepSeekModeError(
            f"当前 DAILYLUMEN_LLM_MODE={m!r}，周/月报 --polish 仅在 "
            f"{LLM_MODE_DEEPSEEK!r} 下可用。"
            f"\n{LLM_MODE_WORKBUDDY!r} 请由宿主润色叙述，或临时设 "
            f"DAILYLUMEN_LLM_MODE={LLM_MODE_DEEPSEEK}。"
        )

    lines, blocks = split_polish_blocks(md_text)
    if not blocks:
        return {
            "original": md_text,
            "polished": md_text,
            "changed": False,
            "block_count": 0,
            "kind": kind,
        }

    payload = {
        "kind": kind,
        "blocks": [{"id": b["id"], "text": b["text"]} for b in blocks],
    }
    c = client or Client(mode=m)
    resp = c.chat_completions(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"请润色下列 {kind} 报叙述块，严格按 JSON 契约返回：\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    raw = assistant_text(resp)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 容错：抽第一个 object
        mobj = re.search(r"\{[\s\S]*\}", raw or "")
        if not mobj:
            raise ValueError("润色模型未返回 JSON object") from None
        data = json.loads(mobj.group(0))
    polished_blocks = data.get("blocks") if isinstance(data, dict) else None
    if not isinstance(polished_blocks, list):
        raise ValueError("润色 JSON 缺少 blocks 数组")

    updated = apply_polished_blocks(lines, blocks, polished_blocks)
    if structural_fingerprint(md_text) != structural_fingerprint(updated):
        raise ValueError(
            "润色后受保护结构（表格/标题/脚注）发生变化，已拒绝落盘（R1）"
        )
    return {
        "original": md_text,
        "polished": updated,
        "changed": updated.replace("\r\n", "\n") != md_text.replace("\r\n", "\n"),
        "block_count": len(blocks),
        "kind": kind,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "apply_polished_blocks",
    "is_protected_line",
    "polish_markdown",
    "split_polish_blocks",
    "structural_fingerprint",
]
