"""DailyLumen 统一命令行入口。

用法:
    python -m review_tool new-day    [YYYY-MM-DD] [--force]
    python -m review_tool ingest     [路径.md] [--overwrite]
    python -m review_tool week       [ISO周] [--json]
    python -m review_tool month      [YYYYMM] [--json]
    python -m review_tool ai-context [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
    python -m review_tool doctor
    python -m review_tool fuse
    python -m review_tool sync-docs  [--check]
    python -m review_tool recompute-scores [--apply] [--db PATH]
    python -m review_tool export     [--format csv|json] [--out DIR] [--stdout]
    python -m review_tool version

任意子命令加 ``-h`` 可查看该项用法。

设计（v1.4.1 起）
----------------
本模块**只做路由，不重复定义子命令参数**。此前顶层 argparse 与各模块的
``main(argv)`` 各写一遍参数，再由顶层把解析结果「翻译」回 argv —— 一旦两边
不同步，新增的参数会被顶层吞掉（模块收不到、也不报错，属静默丢参）。

现在参数只有一处来源：各模块自己的 ``main(argv)``。因此

    python -m review_tool  ingest --overwrite
    python -m review_tool.ingest --overwrite

行为完全一致；`ROUTES` 里的一行用法既是 `-h` 输出，也是 README 的对齐来源。
"""
from __future__ import annotations

import sys
from collections.abc import Callable

from . import __version__
from .pipeline.export import main as export_main
from .pipeline.import_history import main as import_history_main
from .pipeline.ingest import main as ingest_main
from .pipeline.new_day import main as new_day_main
from .pipeline.sync_docs import main as sync_docs_main
from .reports.ai_review import main as ai_context_main
from .reports.analyze import main as analyze_main
from .reports.doctor import main as doctor_main
from .reports.fuse import main as fuse_main
from .reports.recompute import main as recompute_main


def _week(rest: list[str]) -> int:
    return analyze_main(["week", *rest])


def _month(rest: list[str]) -> int:
    return analyze_main(["month", *rest])


def _version(_rest: list[str]) -> int:
    print(__version__)
    return 0


# 子命令 -> (处理函数, 一行用法)。顺序即帮助里的顺序。
ROUTES: dict[str, tuple[Callable[[list[str]], int], str]] = {
    "new-day": (new_day_main, "new-day [YYYY-MM-DD] [--force]"),
    "ingest": (ingest_main, "ingest [路径.md] [--overwrite]"),
    "week": (_week, "week [ISO周] [--json]"),
    "month": (_month, "month [YYYYMM] [--json]"),
    "ai-context": (ai_context_main, "ai-context [YYYY-MM-DD]"),
    "import-history": (
        import_history_main, "import-history [--check] [--src DIR]"),
    "doctor": (doctor_main, "doctor"),
    "fuse": (fuse_main, "fuse"),
    "sync-docs": (sync_docs_main, "sync-docs [--check]"),
    "recompute-scores": (
        recompute_main, "recompute-scores [--apply] [--db PATH]"),
    "export": (export_main, "export [--format csv|json] [--out DIR] [--stdout]"),
    "version": (_version, "version"),
}


def usage() -> str:
    """顶层帮助：列出所有子命令的一行用法。"""
    lines = ["DailyLumen · 每日复盘系统", "",
             "用法: python -m review_tool <子命令> [参数]", "", "子命令:"]
    lines += [f"  {u}" for _fn, u in ROUTES.values()]
    lines += ["", "子命令加 -h 查看该项用法。"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    if not argv:
        print(usage())
        return 1
    if argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0
    if argv[0] in ("-v", "--version"):
        print(__version__)
        return 0

    cmd, rest = argv[0], argv[1:]
    route = ROUTES.get(cmd)
    if route is None:
        print(f"未知子命令: {cmd}", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2

    fn, usage_line = route
    # 子命令 -h 由本层统一拦截：模块不一定有 argparse，直接放行可能被当成
    # 普通参数而触发真实执行（例如 `ingest -h` 会真的扫描全库）。
    if rest and rest[0] in ("-h", "--help"):
        print(f"用法: python -m review_tool {usage_line}")
        return 0

    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
