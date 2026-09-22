"""DailyLumen · 每日复盘系统。

把每天的结构化复盘沉淀进 SQLite 单一数据源，再做周/月分析。
解析、四维评分自动化、入库、分析与体检全部基于 Python 标准库（零依赖）。

典型用法:
    from review_tool import parse_text, compute_scores, init_db, upsert
    from review_tool import ingest_all, report_month

命令行入口:
    python -m review_tool new-day    [YYYY-MM-DD]
    python -m review_tool ingest     [路径.md]
    python -m review_tool week       [ISO周]
    python -m review_tool month      [YYYYMM]
    python -m review_tool ai-context [YYYY-MM-DD]
    python -m review_tool import-history [--check] [--src DIR]
    python -m review_tool doctor
    python -m review_tool export     [--format csv|json] [--out DIR] [--stdout]

模块分工:
    config  路径 + 可配置层（PROFILE / PERSONAL_ITEMS / SCORE_THRESHOLDS / BODYWEIGHT_MOVES）
    util    时间与数值转换、slug 生成
    tracks  打卡项归一化（自由文本 -> 规范 ID）
    bodyweight  徒手训练折算（描述动作 -> 运动时长）
    db      SQLite 读写 + 带版本的增量迁移
    parse   md -> 结构化 dict（兼容三种格式）
    score   四维评分规则
    ingest  扫描 / 解析 / 评分 / 入库
    analyze 周月聚合报告
    new_day 按模板生成当天文件
    ai_review  「七、AI 评价与建议」的确定性上下文
    import_history  语雀历史文件转换
    doctor  数据体检（对账 / 完整度 / 新鲜度）
    export  CSV / JSON 导出
"""
from __future__ import annotations

from .ai_review import build_context as ai_context
from .ai_review import render_markdown as render_ai_context
from .analyze import report_month, report_week
from .bodyweight import estimate as bodyweight_minutes
from .bodyweight import extract as bodyweight_extract
from .config import (
    ARCHIVE_SRC_DIR,
    BASE_DIR,
    BODYWEIGHT_MOVES,
    BODYWEIGHT_RULES,
    DB_PATH,
    DIMENSIONS,
    GENERATED_DIR,
    HISTORY_SRC_DIR,
    INBOX_DIR,
    INPUT_DIR,
    PACKAGE_DIR,
    PERSONAL_ITEMS,
    PROFILE,
    SCHEMA_PATH,
    SCORE_THRESHOLDS,
    TEMPLATE_PATH,
)
from .db import (
    COLUMNS,
    SCHEMA_VERSION,
    count,
    count_tracks,
    fetch_all,
    get_conn,
    init_db,
    migrate,
    upsert,
    upsert_personal_track,
)
from .doctor import diagnose, is_healthy
from .doctor import render as render_doctor
from .export import export
from .import_history import run as import_history_run
from .ingest import ingest_all, ingest_path, iter_markdown
from .new_day import generate as generate_new_day
from .parse import parse_file, parse_text
from .score import (
    compute_health_score,
    compute_learn_score,
    compute_life_score,
    compute_scores,
    compute_work_score,
    system_score_from,
)
from .tracks import normalize_legacy_item, resolve_item, resolve_track
from .util import (
    clock_to_minutes,
    is_late_bedtime,
    minutes_to_clock,
    slugify,
    to_bool,
    to_float,
    to_int,
)

__version__ = "1.4.1"

__all__ = [
    # config
    "BASE_DIR", "PACKAGE_DIR", "DB_PATH", "SCHEMA_PATH", "INPUT_DIR",
    "GENERATED_DIR", "INBOX_DIR", "ARCHIVE_SRC_DIR",
    "TEMPLATE_PATH", "HISTORY_SRC_DIR", "DIMENSIONS",
    "PROFILE", "PERSONAL_ITEMS", "SCORE_THRESHOLDS",
    "BODYWEIGHT_MOVES", "BODYWEIGHT_RULES",
    # util
    "clock_to_minutes", "minutes_to_clock", "to_int", "to_float", "to_bool",
    "is_late_bedtime", "slugify",
    # tracks / bodyweight
    "resolve_item", "resolve_track", "normalize_legacy_item",
    "bodyweight_minutes", "bodyweight_extract",
    # db
    "get_conn", "init_db", "migrate", "upsert", "upsert_personal_track",
    "fetch_all", "count", "count_tracks", "COLUMNS", "SCHEMA_VERSION",
    # parse / score
    "parse_text", "parse_file",
    "compute_scores", "compute_health_score", "compute_work_score",
    "compute_learn_score", "compute_life_score", "system_score_from",
    # ingest / analyze / new_day / ai_context / import_history
    "ingest_path", "ingest_all", "iter_markdown",
    "report_week", "report_month",
    "generate_new_day", "ai_context", "render_ai_context", "import_history_run",
    # doctor / export
    "diagnose", "render_doctor", "is_healthy", "export",
    "__version__",
]
