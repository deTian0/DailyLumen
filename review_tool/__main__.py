"""DailyLumen 统一命令行入口。

用法:
    python -m review_tool new-day    [YYYY-MM-DD] [--force]
    python -m review_tool ingest     [路径.md] [--overwrite]
    python -m review_tool week       [ISO周]
    python -m review_tool month      [YYYYMM]
    python -m review_tool ai-context [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
    python -m review_tool doctor
    python -m review_tool export     [--format csv|json] [--out DIR] [--stdout]
    python -m review_tool version

任意子命令加 ``-h`` 可查看该项参数。
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .ai_review import main as ai_context_main
from .analyze import main as analyze_main
from .doctor import diagnose, is_healthy
from .doctor import render as render_doctor
from .export import main as export_main
from .fuse import main as fuse_main
from .import_history import main as import_history_main
from .ingest import main as ingest_main
from .new_day import main as new_day_main
from .sync_docs import main as sync_docs_main

USAGE_HINT = (
    "子命令: new-day | ingest | week | month | ai-context | import-history"
    " | doctor | fuse | sync-docs | export | version"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m review_tool",
        description="DailyLumen · 每日复盘系统（解析 / 评分 / 入库 / 分析 / 体检 / 导出）",
        epilog=USAGE_HINT,
    )
    parser.add_argument("-v", "--version", action="version",
                        version=f"DailyLumen {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<子命令>")

    p = sub.add_parser("new-day", help="按模板生成当天复盘文件（复盘/YYYY-MM/）")
    p.add_argument("date", nargs="?", help="YYYY-MM-DD，默认今天")
    p.add_argument("--force", action="store_true", help="已存在时覆盖")

    p = sub.add_parser("ingest", help="解析并入库（默认只补空值，不擦已有数据）")
    p.add_argument("path", nargs="?", help="只入库指定文件；省略则扫描整个 每日复盘/")
    p.add_argument("--overwrite", "--force", dest="overwrite", action="store_true",
                   help="整行覆盖模式（会清空源文件中为空的字段）")

    p = sub.add_parser("week", help="周分析")
    p.add_argument("iso_week", nargs="?", type=int, help="ISO 周号；省略则输出全部周")

    p = sub.add_parser("month", help="月分析")
    p.add_argument("month", nargs="?", type=int, help="YYYYMM；省略则用最近一个月")

    p = sub.add_parser("ai-context", help="输出「七、AI 评价与建议」的确定性上下文")
    p.add_argument("date", nargs="?", help="YYYY-MM-DD，默认库中最近一天")

    p = sub.add_parser("import-history", help="把语雀历史文件转换为标准格式")
    p.add_argument("--check", action="store_true", help="只预览解析结果，不写文件")
    p.add_argument("--src", help="来源目录（也可用环境变量 DAILYLUMEN_HISTORY_SRC）")

    sub.add_parser("doctor", help="数据体检：对账 / 完整度 / 新鲜度 / 归一化")

    sub.add_parser("fuse", help="熔断检测：单维度持续走低 + 相对基线偏离")

    p = sub.add_parser("sync-docs", help="把库里的四维分回写到复盘 md（数据块 + 六章）")
    p.add_argument("--check", action="store_true", help="只报告差异，不写文件")

    p = sub.add_parser("export", help="导出 CSV / JSON")
    p.add_argument("--format", choices=("csv", "json"), default="csv")
    p.add_argument("--out", help="输出目录，默认 exports/")
    p.add_argument("--stdout", action="store_true", help="直接打印到终端（JSON）")

    sub.add_parser("version", help="打印版本号")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 1
    args = parser.parse_args(argv)
    cmd = args.command

    if cmd == "new-day":
        rest = [args.date] if args.date else []
        if args.force:
            rest.append("--force")
        return new_day_main(rest)

    if cmd == "ingest":
        rest = [args.path] if args.path else []
        if args.overwrite:
            rest.append("--overwrite")
        return ingest_main(rest)

    if cmd == "week":
        return analyze_main(["week"] + ([str(args.iso_week)] if args.iso_week else []))

    if cmd == "month":
        return analyze_main(["month"] + ([str(args.month)] if args.month else []))

    if cmd == "ai-context":
        return ai_context_main([args.date] if args.date else [])

    if cmd == "import-history":
        rest = []
        if args.check:
            rest.append("--check")
        if args.src:
            rest += ["--src", args.src]
        return import_history_main(rest)

    if cmd == "doctor":
        result = diagnose()
        print(render_doctor(result))
        return 0 if is_healthy(result) else 1

    if cmd == "sync-docs":
        return sync_docs_main(["--check"] if args.check else [])

    if cmd == "fuse":
        return fuse_main([])

    if cmd == "export":
        rest = ["--format", args.format]
        if args.out:
            rest += ["--out", args.out]
        if args.stdout:
            rest.append("--stdout")
        return export_main(rest)

    if cmd == "version":
        print(__version__)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
