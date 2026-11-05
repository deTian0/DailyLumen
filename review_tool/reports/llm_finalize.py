"""llm-finalize：本地定稿（草稿 → 定稿区；清 pending）。

纯 md 变换，**不依赖** DeepSeek / ``DAILYLUMEN_LLM_MODE``。
默认 dry-run；``--write`` 落盘前展示数据块 +「七、AI」并排 diff。
⛔ 不写库（定稿后另跑 ``ingest``）。
"""
from __future__ import annotations

import datetime
import os
import sys
from typing import Any

from ..core.ai_draft import is_ai_draft_pending, promote_ai_draft
from ..pipeline.keepstrong_sync import review_md_path
from ..pipeline.vision_intake import extract_data_block_body
from .llm_review import extract_ai_section, format_section_diff

USAGE = (
    "llm-finalize [YYYY-MM-DD] [--write] [--dry-run] [--diff] [--stdout] [--md PATH]"
)


def _parse(argv: list[str]) -> dict[str, Any]:
    day: str | None = None
    write = False
    dry_run = False
    show_diff = False
    to_stdout = False
    md_path: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--write":
            write = True
        elif a == "--dry-run":
            dry_run = True
        elif a == "--diff":
            show_diff = True
        elif a == "--stdout":
            to_stdout = True
        elif a == "--md":
            i += 1
            if i >= len(argv):
                raise ValueError("--md 需要跟路径")
            md_path = argv[i]
        elif a.startswith("--md="):
            md_path = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day is None:
                day = a
            else:
                raise ValueError(f"多余参数: {a}")
        i += 1
    if md_path is None and not day:
        raise ValueError("必须提供日期 YYYY-MM-DD 或 --md PATH")
    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    if dry_run:
        write = False
    elif not write:
        dry_run = True
    return {
        "day": day,
        "write": write,
        "dry_run": dry_run,
        # --write 前默认也展示并排 diff
        "diff": show_diff or dry_run or write,
        "stdout": to_stdout,
        "md_path": md_path,
    }


def _side_by_side_preview(original: str, updated: str) -> str:
    """数据块 +「七、AI」一眼看完。"""
    lines: list[str] = ["=== 定稿前并排预览：数据块 +「七、AI」 ==="]
    before_data = extract_data_block_body(original).strip()
    after_data = extract_data_block_body(updated).strip()
    lines.append("--- 数据块 ---")
    if before_data == after_data:
        lines.append("（无变更）")
        # 仍展示摘要前几行，便于一眼确认
        for ln in (after_data.splitlines()[:8] or ["（无 data 块）"]):
            lines.append(f"  {ln}")
        if after_data and len(after_data.splitlines()) > 8:
            lines.append("  …")
    else:
        o_set = {ln.strip() for ln in before_data.splitlines() if ln.strip()}
        for ln in after_data.splitlines():
            s = ln.strip()
            if not s:
                continue
            if s not in o_set:
                lines.append(f"+ {s}")
        for ln in before_data.splitlines():
            s = ln.strip()
            if s and s not in {x.strip() for x in after_data.splitlines()}:
                lines.append(f"- {s}")
    lines.append("--- 七、AI ---")
    old_ai = extract_ai_section(original)
    new_ai = extract_ai_section(updated)
    if old_ai == new_ai:
        lines.append("（无变更）")
    else:
        diff = format_section_diff(old_ai, new_ai)
        # 控制刷屏：最多约 40 行
        dlines = diff.splitlines()
        lines.extend(dlines[:40])
        if len(dlines) > 40:
            lines.append("…")
    return "\n".join(lines)


def run_llm_finalize(
    day: str | None = None,
    *,
    md_path: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """读 md → ``promote_ai_draft`` → 可选写回。"""
    path = md_path or review_md_path(day or "")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"复盘 md 不存在: {path}")
    with open(path, encoding="utf-8") as f:
        original = f.read()
    pending_before = is_ai_draft_pending(original)
    updated = promote_ai_draft(original)
    pending_after = is_ai_draft_pending(updated)
    changed = updated != original
    written = False
    if write and changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        # 写盘回读校验（本机写盘不可信）
        with open(path, encoding="utf-8") as f:
            back = f.read()
        if back != updated:
            raise OSError(f"写盘回读不一致: {path}")
        written = True
    return {
        "day": day,
        "md_path": path,
        "pending_before": pending_before,
        "pending_after": pending_after,
        "changed": changed,
        "written": written,
        "original": original,
        "updated": updated,
        "preview": _side_by_side_preview(original, updated),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("本地定稿：清 pending /「草稿 / 待人审」；七-A 提升至七-B（占位时）。")
        print("默认 dry-run；--write 落盘前展示数据块 +「七、AI」并排 diff。")
        print("不依赖 DeepSeek；⛔ 不写库。")
        return 0
    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        result = run_llm_finalize(
            opts["day"],
            md_path=opts["md_path"],
            write=opts["write"],
        )
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"写盘失败: {e}", file=sys.stderr)
        return 1

    if opts["stdout"]:
        print(result["updated"])
    elif opts.get("diff"):
        print(result.get("preview") or _side_by_side_preview(
            result["original"], result["updated"]
        ))
        print(
            f"pending: {result['pending_before']} → {result['pending_after']}；"
            f"changed={result['changed']}"
        )

    if opts["dry_run"]:
        state = "仍有 pending" if result["pending_before"] else "无 pending"
        print(
            f"[dry-run] 未写盘；目标: {result['md_path']}；"
            f"当前 {state}；变换后 pending={result['pending_after']}；"
            f"changed={result['changed']}"
        )
        print("确认后加 --write；再 ingest（本命令不写库）。")
    elif result["written"]:
        print(f"已定稿写入: {result['md_path']}")
        print("可 ingest（pending 已清）。")
    elif not result["pending_before"] and not result["changed"]:
        print(f"已是定稿状态（无需变更）: {result['md_path']}")
    else:
        print(f"无变更可写: {result['md_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
