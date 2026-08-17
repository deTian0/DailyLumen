"""DailyLumen 统一命令行入口。

用法:
    python -m review_tool ingest [路径.md]
    python -m review_tool week  [ISO周]
    python -m review_tool month [YYYYMM]
    python -m review_tool new-day [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
"""
from __future__ import annotations

import sys

from .ingest import main as ingest_main
from .analyze import main as analyze_main
from .new_day import main as new_day_main
from .import_history import main as import_history_main

USAGE = (
    "用法: python -m review_tool [ingest|week|month|new-day|import-history] ...\n"
    "  ingest          入库「每日复盘/」全部 .md（或指定单个文件）\n"
    "  week  [ISO周]   周分析\n"
    "  month [YYYYMM]  月分析\n"
    "  new-day [日期]   生成当天/指定日期的复盘文件\n"
    "  import-history  将语雀历史文件转换导入（--check 仅预览，--src DIR 指定来源）"
)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if not argv:
        print(USAGE)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "ingest":
        return ingest_main(rest)
    if cmd in ("week", "month"):
        return analyze_main([cmd] + rest)
    if cmd == "new-day":
        return new_day_main(rest)
    if cmd == "import-history":
        return import_history_main(rest)
    print(f"未知命令: {cmd}\n{USAGE}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
