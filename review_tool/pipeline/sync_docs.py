"""把库里的四维分/系统分回写到 md —— 让文档与数据库保持同一套口径。

为什么需要它（v1.4.0）
--------------------
历史复盘 md 有两处分数呈现：

1. **附录数据块**里的 ``健康分 / 工作分 / 学习分 / 生活分 / 系统分`` —— 会被
   ``parse`` 读回，是「手写覆盖入口」；
2. **「六、四维评分」表格** —— 给人看的展示层。

两处都是**派生值**。旧流程把它们写进文档后就不管了，于是规则一改、数据库
按新口径重算，下一次 ``ingest`` 又被文档里的旧值覆盖回去 —— 口径变更无法
追溯生效。本模块的做法是：**数据库是唯一权威，文档由它渲染**。

    python -m review_tool sync-docs --check   # 只报告差异，不写
    python -m review_tool sync-docs           # 回写

统一后的格式
------------
数据块（追加在 ``一句话总结`` 之后，无该行则置于块末）::

    健康分: 6
    工作分: 7
    学习分:
    生活分: 3
    系统分: 4.75

「六、四维评分」统一为四列表格，数值来自数据库；标「无法评分」即该维度
缺输入字段。语雀九段式原文（标题带 ``（1 – 10）``）不在回写范围内 ——
它们保留原貌，见 v1.3.3 的文档格式规约。
"""
from __future__ import annotations

import os
import re
import sys

from ..config import GENERATED_DIR
from ..storage.db import init_db

# 数据块里的分数行：标签 -> 数据库列
SCORE_LABELS: list[tuple[str, str]] = [
    ("健康分", "health_score"),
    ("工作分", "work_score"),
    ("学习分", "learn_score"),
    ("生活分", "life_score"),
    ("系统分", "system_score"),
]
_SCORE_KEYS = {label for label, _ in SCORE_LABELS}

# 「六、四维评分」表格里的行标签 -> 数据库列
BAND_LABELS: list[tuple[str, str]] = [
    ("健康", "health_score"),
    ("工作", "work_score"),
    ("学习", "learn_score"),
    ("生活", "life_score"),
    ("系统", "system_score"),
]

# 各维度缺数据时要回填的字段（用于「待补字段」列）
REQUIRED_FIELDS = {
    "work_score": ["深度工作_h"],
    "learn_score": ["学习投入_h"],
    "life_score": ["生活投入_h"],
}

_DATA_BLOCK_RE = re.compile(r"```data\s*\n(.*?)```", re.S)
_KV_RE = re.compile(r"^([\w一-鿿_]+)\s*[:：]\s*(.*)$")
_SIX_RE = re.compile(r"^(##\s*六、四维评分[^\n]*)\n(.*?)(?=^##\s|\Z)", re.S | re.M)

SIX_INTRO = (
    "> 由系统按「附录·系统数据」自动计算。标「无法评分」表示该维度缺少必要字段；"
    "下表「待补字段」即需要回填的项，填好后下一次收集会自动重算。"
)
_SIX_TABLE_HEAD = "| 维度 | 分数 | 状态 | 待补字段 |\n| -- | -- | -- | -- |\n"


def fmt_score(v) -> str:
    """int -> '6'；float -> '4.75'；None -> ''。"""
    if v is None:
        return ""
    if isinstance(v, float) and v != int(v):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(int(v))


def render_data_lines(scores: dict) -> list[str]:
    """渲染数据块里的 5 行分数。"""
    return [f"{label}: {fmt_score(scores.get(col))}" for label, col in SCORE_LABELS]


def is_score_line(line: str) -> bool:
    """该行是否是一条分数行（``健康分: 6``）。"""
    m = _KV_RE.match(line.strip())
    return bool(m) and m.group(1).strip() in _SCORE_KEYS


def rewrite_data_block(text: str, scores: dict) -> str:
    """替换数据块里的分数行（统一追加在「一句话总结」之后）。"""
    m = _DATA_BLOCK_RE.search(text)
    if not m:
        return text
    kept = [ln for ln in m.group(1).splitlines() if not is_score_line(ln)]

    insert_at = len(kept)
    for i, ln in enumerate(kept):
        mm = _KV_RE.match(ln.strip())
        if mm and mm.group(1).strip() == "一句话总结":
            insert_at = i + 1
            break
    kept[insert_at:insert_at] = render_data_lines(scores)

    body = "\n".join(kept).strip("\n")
    return text[:m.start(1)] + body + "\n" + text[m.end(1):]


def render_six_section(scores: dict) -> str:
    """渲染「六、四维评分」章节正文（不含标题行）。"""
    rows = []
    for label, col in BAND_LABELS:
        v = scores.get(col)
        if v is not None:
            rows.append(f"| {label} | {fmt_score(v)} / 10 | ✅ 已评 | — |")
        elif col == "system_score":
            missing = " / ".join(lb for lb, c in BAND_LABELS[:4] if scores.get(c) is None)
            rows.append(f"| 系统 | 无法评分 | ⚠️ 四维不全 | {missing or '—'} |")
        else:
            missing = " / ".join(REQUIRED_FIELDS.get(col, ["—"]))
            rows.append(f"| {label} | 无法评分 | ⚠️ 缺数据 | {missing} |")
    return f"{SIX_INTRO}\n\n{_SIX_TABLE_HEAD}" + "\n".join(rows) + "\n"


def rewrite_six_section(text: str, scores: dict) -> str:
    """重写「六、四维评分」章节正文。

    语雀九段式原文（标题带「（1 – 10）」）属保留范围，原样返回。
    章节末尾统一补回 ``---`` 分隔（与下一章标题之间的现行排版）。
    """
    m = _SIX_RE.search(text)
    if not m:
        return text
    if "（1" in m.group(1) or "(1" in m.group(1):
        return text
    body = "\n" + render_six_section(scores) + "\n---\n\n"
    return text[:m.start(2)] + body + text[m.end(2):]


def render(path: str, scores: dict) -> str:
    """返回同步后的文本（不落盘）。"""
    return rewrite_six_section(rewrite_data_block(
        open(path, encoding="utf-8").read(), scores), scores)


def sync_file(path: str, scores: dict) -> bool:
    """同步单个 md。返回是否发生了变更（只在有变更时才写盘）。"""
    with open(path, encoding="utf-8") as f:
        original = f.read()
    updated = rewrite_six_section(rewrite_data_block(original, scores), scores)
    if updated == original:
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    return True


def daily_files(input_dir: str | None = None) -> list[str]:
    """按日期命名的日复盘 md（周总结/月总结不在内）。"""
    root = input_dir or GENERATED_DIR
    out: list[str] = []
    for cur, _dirs, files in os.walk(root):
        for f in sorted(files):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", f):
                out.append(os.path.join(cur, f))
    return sorted(out)


def scores_by_date(db_path: str | None = None) -> dict[str, dict]:
    """从库中取每日分数。"""
    cols = ("health_score", "work_score", "learn_score", "life_score", "system_score")
    conn = init_db(db_path)
    try:
        cur = conn.execute(f"SELECT date, {', '.join(cols)} FROM daily_reviews")
        return {r[0]: dict(zip(cols, r[1:], strict=True)) for r in cur}
    finally:
        conn.close()


def sync_all(*, db_path: str | None = None, input_dir: str | None = None,
             apply: bool = True) -> dict:
    """把库里的分数回写到所有日复盘 md。返回 {changed, skipped, total}。"""
    by_date = scores_by_date(db_path)
    changed: list[str] = []
    skipped: list[str] = []
    for path in daily_files(input_dir):
        date = os.path.basename(path)[:-3]
        scores = by_date.get(date)
        if scores is None:
            skipped.append(date)
            continue
        if apply:
            if sync_file(path, scores):
                changed.append(date)
        elif render(path, scores) != open(path, encoding="utf-8").read():
            changed.append(date)
    return {"changed": changed, "skipped": skipped, "total": len(by_date)}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    result = sync_all(apply=not check)
    verb = "待同步" if check else "已同步"
    print(f"库中 {result['total']} 天记录｜需要{verb} {len(result['changed'])} 篇 md")
    for d in result["changed"]:
        print(f"    {d}")
    if result["skipped"]:
        print(f"  没有对应 md 的日期 ({len(result['skipped'])}): "
              + ", ".join(result["skipped"][:8]))
    if check and result["changed"]:
        print("    → 运行 python -m review_tool sync-docs 回写")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
