"""DailyLumen 统一命令行入口。

用法:
    python -m review_tool new-day    [YYYY-MM-DD] [--force]
    python -m review_tool ingest     [路径.md] [--overwrite]
    python -m review_tool week       [ISO周] [--json] [--write] [--force] [--check]
    python -m review_tool month      [YYYYMM] [--json] [--write] [--force] [--check]
    python -m review_tool ai-context [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
    python -m review_tool clickup    [YYYY-MM-DD] [--out DIR] [--stdout] [--list ID] [--with-habits]
    python -m review_tool clickup-push [YYYY-MM-DD] [--apply] [--dry-run] [--list ID]
    python -m review_tool keepstrong [--date D] [--write] [--ingest] [--stdout]
    python -m review_tool doctor
    python -m review_tool body       [--json]
    python -m review_tool coach      [YYYY-MM-DD] [--json]
    python -m review_tool habits     [--json] [--sync ...]
    python -m review_tool nutrition  [YYYY-MM-DD] [--json]
    python -m review_tool tutor      [YYYY-MM-DD] [--json]
    python -m review_tool steward    --slot morning|evening|week […]
    python -m review_tool fuse
    python -m review_tool sync-docs  [--check]
    python -m review_tool recompute-scores [--apply] [--db PATH]
    python -m review_tool export     [--format csv|json] [--out DIR] [--stdout]
    python -m review_tool chart      [--type body|training|nutrition|all] [--out DIR] [--stdout]
    python -m review_tool correlate  [--json] [--min-samples N]
    python -m review_tool version

任意子命令加 ``-h`` 可查看该项用法。
被 ``config.FEATURES`` 关掉的命令会在帮助里标注「（已关闭）」，当前默认关闭 ``new-day``。

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
from .pipeline.clickup import main as clickup_main
from .pipeline.clickup_pull import main as clickup_pull_main
from .pipeline.clickup_sync import main as clickup_push_main
from .pipeline.export import main as export_main
from .pipeline.import_history import main as import_history_main
from .pipeline.ingest import main as ingest_main
from .pipeline.keepstrong import main as keepstrong_main
from .pipeline.new_day import is_enabled as _new_day_enabled
from .pipeline.new_day import main as new_day_main
from .pipeline.sync_docs import main as sync_docs_main
from .reports.ai_review import main as ai_context_main
from .reports.analyze import main as analyze_main
from .reports.body import main as body_main
from .reports.chart import main as chart_main
from .reports.clickup_done import main as clickup_done_main
from .reports.coach import main as coach_main
from .reports.correlate import main as correlate_main
from .reports.doctor import main as doctor_main
from .reports.fuse import main as fuse_main
from .reports.habits import main as habits_main
from .reports.nutrition import main as nutrition_main
from .reports.promises import main as promises_main
from .reports.recompute import main as recompute_main
from .reports.stats import main as stats_main
from .reports.steward import main as steward_main
from .reports.tutor import main as tutor_main


def ensure_utf8_stdio() -> None:
    """尽量把 stdout/stderr 固定为 UTF-8（Windows GBK 控台防炸）。

    对已关闭 / 非 TTY / 不支持 ``reconfigure`` 的流静默跳过，不改变行为。
    """
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if not callable(reconf):
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            # 管道重定向 / 冻结流等场景：保持原编码，靠渲染层 ASCII 降级兜底
            pass


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
    "ingest": (ingest_main, "ingest [路径.md] [--overwrite] [--prune-tracks]"),
    "week": (_week, "week [ISO周] [--json] [--write] [--force] [--check]"),
    "month": (_month, "month [YYYYMM] [--json] [--write] [--force] [--check] [--deep]"),
    "ai-context": (ai_context_main, "ai-context [YYYY-MM-DD]"),
    "import-history": (
        import_history_main, "import-history [--check] [--src DIR]"),
    "clickup": (
        clickup_main,
        "clickup [YYYY-MM-DD] [--out DIR] [--stdout] [--list ID] [--with-habits]"),
    "clickup-push": (
        clickup_push_main,
        "clickup-push [YYYY-MM-DD] [--apply] [--dry-run] [--list ID]"),
    "clickup-pull": (
        clickup_pull_main,
        "clickup-pull [--days N] [--list ID] [--dry-run]"),
    "clickup-done": (
        clickup_done_main,
        "clickup-done [YYYY-MM-DD] [结束日期] [--json]"),
    "keepstrong": (
        keepstrong_main,
        "keepstrong [--date D] [--write] [--ingest] | --set-weight/--log-body/--schedule --yes"),
    "doctor": (doctor_main, "doctor"),
    "body": (body_main, "body [--json]"),
    "coach": (coach_main, "coach [YYYY-MM-DD] [--json]"),
    "habits": (habits_main, "habits [--json] [--sync [YYYY-MM-DD] [--dry-run]]"),
    "nutrition": (nutrition_main, "nutrition [YYYY-MM-DD] [--json]"),
    "promises": (
        promises_main, "promises [起始日期] [结束日期] [--json]"),
    "tutor": (tutor_main, "tutor [YYYY-MM-DD] [--json]"),
    "steward": (
        steward_main,
        "steward --slot morning|evening|week [日期|ISO周] [--json] [--todo TEXT]"),
    "fuse": (fuse_main, "fuse"),
    "sync-docs": (sync_docs_main, "sync-docs [--check]"),
    "recompute-scores": (
        recompute_main, "recompute-scores [--apply] [--db PATH]"),
    "export": (export_main, "export [--format csv|json] [--out DIR] [--stdout]"),
    "stats": (stats_main, "stats [--json]"),
    "chart": (
        chart_main,
        "chart [--type body|training|nutrition|all] [--out DIR] [--stdout]"),
    "correlate": (
        correlate_main, "correlate [--json] [--min-samples N]"),
    "version": (_version, "version"),
}


def disabled_commands() -> set[str]:
    """当前被 ``config.FEATURES`` 关掉的子命令名（``usage()`` 里标注用）。

    与各模块的闸门读的是**同一份配置**，所以不会出现「帮助里说开着、一跑却拒绝」
    （或反过来）这种两处口径打架的情况。新增开关时在这里加一行即可。
    """
    off: set[str] = set()
    if not _new_day_enabled():
        off.add("new-day")
    return off


def usage() -> str:
    """顶层帮助：列出所有子命令的一行用法，并标注已被关掉的命令。"""
    off = disabled_commands()
    lines = ["DailyLumen · 每日复盘系统", "",
             "用法: python -m review_tool <子命令> [参数]", "", "子命令:"]
    lines += [f"  {u}" + ("（已关闭）" if name in off else "")
              for name, (_fn, u) in ROUTES.items()]
    lines += ["", "子命令加 -h 查看该项用法。"]
    if off:
        lines += [f"（已关闭）的命令默认不执行，开关在 config.FEATURES（当前关闭："
                  f"{'、'.join(sorted(off))}）。"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
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
