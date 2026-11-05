"""DailyLumen · 每日复盘系统。

把每天的结构化复盘沉淀进 SQLite 单一数据源，再做周/月分析。
解析、四维评分自动化、入库、分析与体检业务逻辑基于 Python 标准库；配置层使用 pydantic / pydantic-settings（M46）。

典型用法:
    from review_tool import parse_text, compute_scores, init_db, upsert
    from review_tool import ingest_all, report_month

命令行入口（40 子命令，详见 ``python -m review_tool -h``）:
    new-day / ingest / week / week-done / month / ai-context /
    llm-review / llm-vision / llm-day / llm-finalize / inbox-archive /
    import-history / clickup / clickup-push / clickup-task / clickup-pull / clickup-done /
    keepstrong / doctor / day-help / finalize / body / coach / habits / daily-pull /
    promise-draft / three-things-draft / improve-draft / nutrition / promises /
    tutor / steward / fuse / sync-docs / recompute-scores / export / stats /
    chart / correlate / version

分层（依赖只能自上而下，由 tests/architecture/test_architecture.py 强制）:
    core          领域层（零 I/O）：tracks / bodyweight / body / training / habits / …
    storage       持久化层：SQLite 唯一出入口
    integrations  第三方网关：clickup / keepstrong / deepseek（可被 pipeline/reports 调用）
    pipeline      数据流转层（md <-> 库 + 编排）：parse / ingest / clickup* / keepstrong / …
    reports       产出层（读库面向人）：analyze / doctor / llm-* / …
    config        包根可配置层；__main__ 纯路由

"""
from __future__ import annotations

from .config import (
    ARCHIVE_SRC_DIR,
    BASE_DIR,
    BODYWEIGHT_MOVES,
    BODYWEIGHT_RULES,
    DB_PATH,
    DIMENSIONS,
    EXPORT_DIR,
    GENERATED_DIR,
    HABITS,
    HISTORY_SRC_DIR,
    INBOX_DIR,
    INPUT_DIR,
    LOCAL_DIR,
    PACKAGE_DIR,
    PERSONAL_ITEMS,
    PROFILE,
    SCHEMA_PATH,
    SCORE_THRESHOLDS,
    TEMPLATE_PATH,
)
from .core.bodyweight import estimate as bodyweight_minutes
from .core.bodyweight import extract as bodyweight_extract
from .core.score import (
    compute_health_score,
    compute_learn_score,
    compute_life_score,
    compute_scores,
    compute_work_score,
    system_score_from,
)
from .core.tracks import normalize_item, normalize_legacy_item, resolve_item, resolve_track
from .core.util import (
    clock_to_minutes,
    is_late_bedtime,
    minutes_to_clock,
    slugify,
    to_bool,
    to_float,
    to_int,
)
from .pipeline.export import export
from .pipeline.import_history import run as import_history_run
from .pipeline.ingest import ingest_all, ingest_path, iter_markdown
from .pipeline.new_day import generate as generate_new_day
from .pipeline.parse import parse_file, parse_text
from .reports.ai_review import build_context as ai_context
from .reports.ai_review import render_markdown as render_ai_context
from .reports.analyze import report_month, report_week
from .reports.doctor import diagnose, is_healthy
from .reports.doctor import render as render_doctor
from .storage.db import (
    COLUMNS,
    SCHEMA_VERSION,
    count,
    count_tracks,
    fetch_all,
    get_conn,
    init_db,
    load_habit_logs,
    migrate,
    upsert,
    upsert_habit_log,
    upsert_personal_track,
)

__version__ = "1.60.0"

__all__ = [
    # config
    "BASE_DIR", "PACKAGE_DIR", "LOCAL_DIR", "DB_PATH", "SCHEMA_PATH", "INPUT_DIR",
    "GENERATED_DIR", "INBOX_DIR", "ARCHIVE_SRC_DIR", "EXPORT_DIR",
    "TEMPLATE_PATH", "HISTORY_SRC_DIR", "DIMENSIONS",
    "PROFILE", "PERSONAL_ITEMS", "HABITS", "SCORE_THRESHOLDS",
    "BODYWEIGHT_MOVES", "BODYWEIGHT_RULES",
    # util
    "clock_to_minutes", "minutes_to_clock", "to_int", "to_float", "to_bool",
    "is_late_bedtime", "slugify",
    # tracks / bodyweight
    "normalize_item", "resolve_item", "resolve_track", "normalize_legacy_item",
    "bodyweight_minutes", "bodyweight_extract",
    # db
    "get_conn", "init_db", "migrate", "upsert", "upsert_personal_track",
    "upsert_habit_log", "load_habit_logs",
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
