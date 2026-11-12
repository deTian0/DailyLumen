"""CLI：``day-help`` —— 打印今日一日三步 + 按 mode 的可复制命令。"""
from __future__ import annotations

import argparse
import datetime
import sys

from ..config import get_llm_mode
from ..core.day_help import infer_training_day_hint, render_day_help


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m review_tool day-help",
        description="打印一日三步与可复制命令模板（workbuddy / deepseek）。",
    )
    p.add_argument(
        "date",
        nargs="?",
        default=None,
        help="复盘日 YYYY-MM-DD（默认今天）",
    )
    p.add_argument(
        "--date", "-d",
        dest="date_opt",
        default=None,
        help="同位置参数 date",
    )
    p.add_argument(
        "--mode",
        default=None,
        help="覆盖当前 DAILYLUMEN_LLM_MODE（仅影响本次输出高亮）",
    )
    ns = p.parse_args(list(argv) if argv is not None else None)
    day = ns.date_opt or ns.date or datetime.date.today().isoformat()
    mode = ns.mode if ns.mode is not None else get_llm_mode()
    # D7：仅当本地 md 标明训练日=是时追加 keepstrong / 代勾说明
    print(render_day_help(day, mode, training_day=infer_training_day_hint(day)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
