"""improve-draft：改进点候选取数上下文（M37 / v1.44.0）。

主落地是 skill ``daily-review-intake`` §0.8 + ``life-decision-guide``：
会话查书排序后写 ``收件箱/改进点候选-<日期>.md``，人勾 1 条才回填复盘。

本 CLI **只做取数上下文**（复用 ``ai-context`` 同源 ``build_context``）：
- 默认 ``--stdout`` 打印，零写盘；
- 显式 ``--out DIR`` 才落骨架草稿（数据段 + 空候选槽），**不**自动查书、
  **不**写入复盘正文、**不**入库。
"""
from __future__ import annotations

import datetime
import os
import sys

from ..config import INBOX_DIR
from .ai_review import build_context, render_markdown

USAGE = "improve-draft [--date YYYY-MM-DD] [--stdout] [--out DIR] [--db PATH]"

INBOX_PREFIX = "改进点候选"

# 候选条目必填字段（skill / 会话填；CLI 骨架只留空槽）
CANDIDATE_FIELDS = ("事项", "钱", "时间", "毅力", "收益", "证据等级", "书条目")


def build_skeleton(day: str, *, generated_at: str, context_md: str,
                   candidates: list[dict] | None = None) -> str:
    """渲染改进点候选草稿。

    ``candidates`` 有值时写入已填条目（测试 / 会话回写用）；
    默认空槽 —— CLI 不替代查书。
    """
    L: list[str] = []
    L.append(f"# 改进点候选（{day}）")
    L.append("")
    L.append(f"> 生成时间 {generated_at}｜取数：近 7 日 ``ai-context`` 同源；"
             "排序须走 ``life-decision-guide`` + 书正文。")
    L.append("> **本文件是草稿，不入库**；人勾 **1** 条回填复盘 md「三、一个改进点」。")
    L.append("> ⛔ 未勾选前不得机器写入复盘改进点段。")
    L.append("")
    L.append("## 取数上下文（只读）")
    L.append("")
    # 嵌套引用，避免与外层标题抢层级
    for line in context_md.strip().splitlines():
        L.append(f"> {line}" if line else ">")
    L.append("")
    L.append("## 候选（查书后填写；勾 1 条回填）")
    L.append("")
    if candidates:
        for i, c in enumerate(candidates, 1):
            L.append(f"### 候选 {i}")
            L.append("")
            L.append(f"- [ ] **{c.get('事项', '')}**")
            for key in CANDIDATE_FIELDS[1:]:
                L.append(f"  - {key}：{c.get(key, '')}")
            L.append("")
    else:
        L.append("（以下空槽由会话按 `life-decision-guide` 填；钱/时间/毅力 + 收益 + 证据等级 A/B/C + 第几节第几条）")
        L.append("")
        for i in range(1, 4):
            L.append(f"### 候选 {i}")
            L.append("")
            L.append("- [ ] **（事项）**")
            for key in CANDIDATE_FIELDS[1:]:
                L.append(f"  - {key}：")
            L.append("")
    L.append("## 回填提醒")
    L.append("")
    L.append("1. 勾 **恰好 1** 条写入「三、一个改进点」（可改写成更短动作句）；")
    L.append("2. 书里没写的明说没写；常识补的单独标注；")
    L.append("3. 纯只读建议，不参与四维评分。")
    return "\n".join(L) + "\n"


def _parse(argv: list[str]) -> tuple[str, bool, str | None, str | None]:
    day: str | None = None
    to_stdout = False
    out_dir: str | None = None
    db_path: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stdout":
            to_stdout = True
        elif a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期（YYYY-MM-DD）")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a == "--out":
            i += 1
            if i >= len(argv):
                raise ValueError("--out 需要跟目录")
            out_dir = argv[i]
        elif a.startswith("--out="):
            out_dir = a.split("=", 1)[1]
        elif a == "--db":
            i += 1
            if i >= len(argv):
                raise ValueError("--db 需要跟路径")
            db_path = argv[i]
        elif a.startswith("--db="):
            db_path = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            # 兼容位置日期
            if day is None:
                day = a
            else:
                raise ValueError(f"多余的位置参数: {a}")
        i += 1
    if day is None:
        day = datetime.date.today().isoformat()
    else:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    # 无 --out 时默认 stdout（取数上下文零写盘）
    if out_dir is None:
        to_stdout = True
    return day, to_stdout, out_dir, db_path


def main(argv: list[str] | None = None, *, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("改进点候选取数上下文：近 7 日关注点 → stdout / 可选骨架草稿。")
        print("排序与书条目须走 life-decision-guide；草稿不入库。")
        return 0
    try:
        day, to_stdout, out_dir, db_path = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    ctx = build_context(day, db_path=db_path)
    context_md = render_markdown(ctx)
    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    draft = build_skeleton(day, generated_at=stamp, context_md=context_md)

    if to_stdout and out_dir is None:
        print(draft)
        return 0

    if out_dir is not None:
        target = out_dir or INBOX_DIR
        os.makedirs(target, exist_ok=True)
        out = os.path.join(target, f"{INBOX_PREFIX}-{day}.md")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(draft)
        with open(out, encoding="utf-8") as f:
            got = f.read()
        if got != draft:
            print(f"写盘校验失败: {out}", file=sys.stderr)
            return 1
        print(f"已生成骨架: {out}")
        print("请按 life-decision-guide 填候选（钱/时间/毅力 + 证据等级 + 书条目）；勾 1 条回填。")
        if to_stdout:
            print(draft)
        return 0

    print(draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
