"""DailyLumen · 每日复盘系统。

把每天的结构化复盘沉淀进 SQLite 单一数据源，再做周/月分析。
解析、四维评分自动化、入库与分析全部基于 Python 标准库（零依赖）。

典型用法:
    from review_tool import parse_text, compute_scores, init_db, upsert
    from review_tool import ingest_all, report_month

命令行入口:
    python -m review_tool ingest
    python -m review_tool week [ISO周]
    python -m review_tool month [YYYYMM]
    python -m review_tool new-day [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
"""
from __future__ import annotations

from .config import (
    BASE_DIR, PACKAGE_DIR, DB_PATH, SCHEMA_PATH, INPUT_DIR,
    TEMPLATE_PATH, HISTORY_SRC_DIR, DIMENSIONS, system_score_from,
)
from .db import (
    get_conn, init_db, upsert, fetch_all, count, COLUMNS,
)
from .parse import parse_text, parse_file
from .score import (
    compute_scores, compute_health_score, compute_work_score,
    compute_learn_score, compute_life_score,
)
from .ingest import ingest_path, ingest_all
from .analyze import report_week, report_month
from .new_day import generate as new_day
from .import_history import run as import_history_run

__version__ = "1.0.0"

__all__ = [
    # config
    "BASE_DIR", "PACKAGE_DIR", "DB_PATH", "SCHEMA_PATH", "INPUT_DIR",
    "TEMPLATE_PATH", "HISTORY_SRC_DIR", "DIMENSIONS", "system_score_from",
    # db
    "get_conn", "init_db", "upsert", "fetch_all", "count", "COLUMNS",
    # parse
    "parse_text", "parse_file",
    # score
    "compute_scores", "compute_health_score", "compute_work_score",
    "compute_learn_score", "compute_life_score",
    # ingest / analyze / new_day / import_history
    "ingest_path", "ingest_all", "report_week", "report_month",
    "new_day", "import_history_run",
    "__version__",
]
