"""SQLite 数据层：初始化、增量迁移、写入、查询。

所有公开函数都接收/返回 ``sqlite3.Connection``，便于测试时注入临时数据库。

两个安全设计：
- **迁移有版本**：``PRAGMA user_version`` 记录 schema 版本，``_MIGRATIONS`` 逐级升级，
  每次升级前检查目标列/表是否已就位，幂等且可重复执行。
- **upsert 默认不擦数据**：新值为 None 时保留库中旧值（COALESCE 语义），
  避免「重跑一次 ingest 把已有字段刷成空」；确需清空时显式传 ``overwrite=True``。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .config import DB_PATH, SCHEMA_PATH
from .tracks import normalize_legacy_item

# 当前 schema 版本（改动 schema.sql 结构时必须 +1 并新增对应迁移函数）
SCHEMA_VERSION = 3

# 数据表所有列（顺序即 upsert 列顺序）
COLUMNS = [
    "date", "weekday", "iso_week", "month", "training_day",
    "sleep_h", "sleep_quality", "bedtime", "exercise_min", "exercise_src",
    "commute_done",
    "diet_kcal", "carbs_g", "fat_g", "protein_g",
    "meals_count", "breakfast_on_time", "phone_h",
    "deepwork_h", "learn_h", "life_h", "energy", "mood",
    "health_score", "work_score", "learn_score", "life_score",
    "system_score", "summary", "raw_path", "ingested_at",
]

# 这些列在任何情况下都跟着新值走（元数据 / 派生值，不是用户填报值）
# exercise_src 也在此列：它由 parse 每次重新判定（record / derived / None），
# 若走 COALESCE 就会出现「用户改成手填了、来源还写着 derived」的陈旧标记。
_ALWAYS_OVERWRITE = {"raw_path", "ingested_at", "iso_week", "month", "exercise_src"}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


# ---------------------------------------------------------------------------
# 增量迁移
# ---------------------------------------------------------------------------

# 老库缺少的列: (列名, ALTER 语句)。只增不改，保证已有数据无损。
_ADD_COLUMNS = [
    ("carbs_g", "ALTER TABLE daily_reviews ADD COLUMN carbs_g INTEGER CHECK (carbs_g IS NULL OR carbs_g >= 0)"),
    ("fat_g", "ALTER TABLE daily_reviews ADD COLUMN fat_g INTEGER CHECK (fat_g IS NULL OR fat_g >= 0)"),
    ("protein_g", "ALTER TABLE daily_reviews ADD COLUMN protein_g INTEGER CHECK (protein_g IS NULL OR protein_g >= 0)"),
    ("exercise_src", "ALTER TABLE daily_reviews ADD COLUMN exercise_src TEXT"),
]

_TRACKS_DDL = """
CREATE TABLE personal_tracks (
    date      TEXT NOT NULL,
    track_key TEXT NOT NULL,
    category  TEXT NOT NULL,
    item_key  TEXT NOT NULL,
    item      TEXT NOT NULL,
    done      INTEGER CHECK (done IS NULL OR done IN (0, 1)),
    note      TEXT,
    PRIMARY KEY (date, track_key)
)
"""

# 索引统一在迁移完成后创建：老库的表在迁移前可能没有 item_key 列，
# 若把 CREATE INDEX 写进 schema.sql，升级途中会「引用尚不存在的列」而失败。
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_iso_week ON daily_reviews(iso_week)",
    "CREATE INDEX IF NOT EXISTS idx_month ON daily_reviews(month)",
    "CREATE INDEX IF NOT EXISTS idx_pt_date ON personal_tracks(date)",
    "CREATE INDEX IF NOT EXISTS idx_pt_item ON personal_tracks(item_key)",
]


def _create_indexes(conn: sqlite3.Connection) -> None:
    """建索引（幂等）。必须在结构与列齐备之后调用。"""
    for ddl in _INDEXES:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            # 极老的表可能缺少被索引的列，跳过即可（不影响功能）
            pass


def _migrate_daily_reviews(conn: sqlite3.Connection) -> None:
    """补齐 daily_reviews 缺失的列（幂等：表或列已存在则跳过）。

    新增 ``exercise_src`` 后，把**已有数值**的行标记为 ``'record'`` —— 因为
    在折算功能出现之前写进库的运动时长只可能来自字段填报。空值行保持 NULL。
    """
    if "daily_reviews" not in _table_names(conn):
        return
    cols = _table_columns(conn, "daily_reviews")
    for name, ddl in _ADD_COLUMNS:
        if name not in cols:
            conn.execute(ddl)

    # 回填前重新取列：极老的表可能连 exercise_min 都没有（本函数只补 _ADD_COLUMNS
    # 里列出的列），此时跳过回填，避免「引用不存在的列」而中断整个迁移。
    cols = _table_columns(conn, "daily_reviews")
    if {"exercise_min", "exercise_src"} <= cols:
        conn.execute(
            "UPDATE daily_reviews SET exercise_src='record' "
            "WHERE exercise_min IS NOT NULL AND exercise_src IS NULL"
        )


def _migrate_personal_tracks(conn: sqlite3.Connection) -> int:
    """把 personal_tracks 从「自由文本主键」升级为「规范 track_key 主键」。

    旧主键 ``(date, category, item)`` 让同一个规范项裂成多种形态，依从率无法聚合；
    此处按 ``tracks.normalize_legacy_item`` 重新归一化，**一条旧记录可能裂成多条**
    （例如「晨间-CoQ10 ×1 ＋ Exia 早3」→ coq10@morning + exia_am@morning）。

    返回迁移后的行数；无需迁移时返回 0。
    """
    if "personal_tracks" not in _table_names(conn):
        return 0
    if "track_key" in _table_columns(conn, "personal_tracks"):
        return 0

    old_rows = conn.execute(
        "SELECT date, category, item, done, note FROM personal_tracks"
    ).fetchall()

    merged: dict[tuple[str, str], dict] = {}
    for date, category, item, done, note in old_rows:
        for cat, track_key, item_key, item_label in normalize_legacy_item(item, category):
            key = (date, track_key)
            slot = merged.get(key)
            if slot is None:
                merged[key] = {
                    "category": cat, "item_key": item_key, "item": item_label,
                    "done": done, "note": note,
                }
            else:
                # 同一天同一项出现多条旧记录：任一条勾选即视为完成
                if done == 1:
                    slot["done"] = 1
                if slot["note"] is None and note is not None:
                    slot["note"] = note

    conn.execute("DROP TABLE personal_tracks")
    conn.execute(_TRACKS_DDL)
    conn.executemany(
        "INSERT INTO personal_tracks (date, track_key, category, item_key, item, done, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (date, track_key, v["category"], v["item_key"], v["item"], v["done"], v["note"])
            for (date, track_key), v in sorted(merged.items())
        ],
    )
    return len(merged)


def migrate(conn: sqlite3.Connection, *, verbose: bool = False) -> dict:
    """执行全部增量迁移（幂等）。返回本次迁移动作摘要。

    顺序：补列 -> 建表 -> 重建 personal_tracks -> 建索引 -> 记录版本。
    """
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    _migrate_daily_reviews(conn)
    tracks_rows = _migrate_personal_tracks(conn)
    _create_indexes(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    if verbose:
        print(f"  schema 版本: {version_before} -> {SCHEMA_VERSION}")
        if tracks_rows:
            print(f"  personal_tracks 归一化: {tracks_rows} 条规范记录")
    return {
        "version_before": version_before,
        "version_after": SCHEMA_VERSION,
        "tracks_migrated": tracks_rows,
    }


# ---------------------------------------------------------------------------
# 连接 / 建表
# ---------------------------------------------------------------------------

def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """打开数据库连接（row_factory=sqlite3.Row）。

    :param db_path: 指定数据库文件；省略则用 config.DB_PATH。
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None, schema_path: str | None = None,
            *, migrate_legacy: bool = True, verbose: bool = False) -> sqlite3.Connection:
    """建表 + 增量迁移。schema 默认读取 config.SCHEMA_PATH。

    :param db_path: 指定数据库文件；省略则用 config.DB_PATH。
    :param schema_path: 指定建表脚本；省略则用 config.SCHEMA_PATH。
    :param migrate_legacy: 是否对老库执行结构迁移（默认 True；测试可关闭）。
    """
    schema_path = schema_path or SCHEMA_PATH
    conn = get_conn(db_path)
    # 先补列、再建表/建索引：老库可能缺少新列，而索引可能引用它们。
    # 表不存在时 PRAGMA 返回空集，补列自动跳过，因此对全新库也安全。
    if migrate_legacy:
        _migrate_daily_reviews(conn)
    with open(schema_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    if migrate_legacy:
        migrate(conn, verbose=verbose)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------

def _upsert_sql(overwrite: bool) -> str:
    """生成 upsert 语句。

    overwrite=False（默认）：新值为 None 时保留旧值，防止误擦已有数据。
    overwrite=True：整行覆盖。
    """
    if overwrite:
        assigns = [f"{c}=excluded.{c}" for c in COLUMNS if c != "date"]
    else:
        assigns = [
            f"{c}=excluded.{c}" if c in _ALWAYS_OVERWRITE
            else f"{c}=COALESCE(excluded.{c}, daily_reviews.{c})"
            for c in COLUMNS if c != "date"
        ]
    return (
        f"INSERT INTO daily_reviews ({', '.join(COLUMNS)}) "
        f"VALUES ({', '.join(['?'] * len(COLUMNS))}) "
        f"ON CONFLICT(date) DO UPDATE SET {', '.join(assigns)}"
    )


def upsert(conn: sqlite3.Connection, row: dict, *, overwrite: bool = False) -> None:
    """按 date 主键写入或更新一行。row 必须含 date。

    自动补 iso_week / month / ingested_at（缺失时）。
    默认**不擦除**库中已有值（新值为 None 时保留旧值）；
    需要真正清空某字段时传 ``overwrite=True``。
    """
    if "iso_week" not in row or row["iso_week"] is None:
        d = datetime.strptime(row["date"], "%Y-%m-%d")
        row["iso_week"] = d.isocalendar()[1]
        row["month"] = d.year * 100 + d.month
    row.setdefault("ingested_at", datetime.now().isoformat(timespec="seconds"))
    conn.execute(_upsert_sql(overwrite), [row.get(c) for c in COLUMNS])


def upsert_personal_track(conn: sqlite3.Connection, date: str, track_key: str,
                          category: str, item_key: str, item: str,
                          done: int, note: str | None = None,
                          *, overwrite: bool = False) -> None:
    """写入/更新一条个人定制打卡（按 date + track_key 主键）。

    ``track_key`` 为归一化后的规范 ID（见 tracks 模块），保证同一规范项
    不会因为手写差异而裂成多条。
    """
    done_assign = "excluded.done" if overwrite else "COALESCE(excluded.done, personal_tracks.done)"
    sql = f"""
        INSERT INTO personal_tracks (date, track_key, category, item_key, item, done, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, track_key) DO UPDATE SET
            category=excluded.category,
            item_key=excluded.item_key,
            item=excluded.item,
            done={done_assign},
            note=COALESCE(excluded.note, personal_tracks.note)
    """
    conn.execute(sql, (date, track_key, category, item_key, item, done, note))


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def fetch_all(conn: sqlite3.Connection, order: str = "date ASC") -> list:
    """返回全部行（按 order 排序）。order 限定为「列名 [ASC|DESC]」。"""
    col, _, direction = order.partition(" ")
    direction = direction.strip().upper() or "ASC"
    if col not in COLUMNS or direction not in ("ASC", "DESC"):
        raise ValueError(f"非法排序参数: {order!r}（仅支持数据表列名 + ASC/DESC）")
    cur = conn.execute(f"SELECT * FROM daily_reviews ORDER BY {col} {direction}")
    return cur.fetchall()


def count(conn: sqlite3.Connection) -> int:
    """返回表中行数。"""
    return conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]


def count_tracks(conn: sqlite3.Connection) -> int:
    """返回个人打卡表行数。"""
    return conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]
