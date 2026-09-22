"""一键生成当天复盘文件：从模板复制 -> 填好日期/星期 -> 清空示例值。

用法:
    python -m review_tool new-day            # 生成今天的 YYYY-MM-DD.md
    python -m review_tool new-day 2026-08-20 # 生成指定日期
    python -m review_tool new-day --force    # 已存在时覆盖

输出位置统一为 ``每日复盘/复盘/YYYY-MM/YYYY-MM-DD.md``（config.GENERATED_DIR），
与既有归档目录保持一致，不再散落到「每日复盘/」根目录。

模板约定（改模板不会让本脚本失效）
- 数据块：自动清空 ```data``` 内所有 ``key: value`` 的 value，再写回日期 / 星期
- 打卡：所有 ``- [x]`` 复位为 ``- [ ]``
- 需要整体清空的示例段落，用 ``<!--clear--> ... <!--/clear-->`` 包起来
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime

from .config import GENERATED_DIR, TEMPLATE_PATH, WEEKDAY_CN

# ```data 代码块
_DATA_BLOCK_RE = re.compile(r"```data\s*\n(.*?)```", re.S)
# data 块内的 key: value 行（只清 value，保留 key）
_DATA_KV_RE = re.compile(r"^(\s*[^:\n]+?:)[ \t]*.*$", re.M)
# 需要整体清空的示例段落
_CLEAR_BLOCK_RE = re.compile(r"<!--\s*clear\s*-->(.*?)<!--\s*/clear\s*-->", re.S)
# 行首的「日期: 」/「星期: 」字段
_DATE_LINE_RE = re.compile(r"^(\s*日期:)[ \t]*.*$", re.M)
_WEEKDAY_LINE_RE = re.compile(r"^(\s*星期:)[ \t]*.*$", re.M)


def _clear_data_block(content: str) -> str:
    """清空 ```data``` 块里所有字段的值（保留 key）。"""

    def repl(m: re.Match) -> str:
        return "```data\n" + _DATA_KV_RE.sub(r"\1 ", m.group(1)) + "```"

    return _DATA_BLOCK_RE.sub(repl, content)


def generate(target_date: date | None = None, *, force: bool = False) -> str:
    """从模板生成指定日期的复盘文件，返回输出路径（已存在且未 force 则跳过）。"""
    if target_date is None:
        target_date = date.today()
    iso = target_date.isoformat()
    wd = WEEKDAY_CN[target_date.weekday()]

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        content = f.read()

    # 1) 清空示例段落（模板用 <!--clear--> 标记的块）
    content = _CLEAR_BLOCK_RE.sub("", content)
    # 2) 数据块复位：先清空全部 value，再写回日期/星期
    content = _clear_data_block(content)
    # 3) 标题与字段填值
    content = content.replace("YYYY-MM-DD", iso)
    # 注意替换成「星期四」而不是「四」：旧版写成 (星期{wd}) 时漏了「星期」前缀，
    # 生成出「（四）」，与既有归档文件「（星期一）」的格式不一致。
    content = re.sub(r"星期[Xx]", f"星期{wd}", content)
    content = _DATE_LINE_RE.sub(rf"\1 {iso}", content)
    content = _WEEKDAY_LINE_RE.sub(rf"\1 {wd}", content)
    # 4) 打卡全部复位为未勾选
    content = content.replace("- [x]", "- [ ]").replace("- [X]", "- [ ]")

    out_dir = os.path.join(GENERATED_DIR, iso[:7])
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{iso}.md")
    if os.path.exists(out) and not force:
        print(f"已存在, 跳过: {out}")
        return out
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]
    d = datetime.strptime(args[0], "%Y-%m-%d").date() if args else date.today()
    out = generate(d, force=force)
    print(f"已生成: {out}")
    print("下一步: 打开填数值 -> python -m review_tool ingest -> python -m review_tool month")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
