"""SQLite 数据层：初始化、写入、查询。

所有公开函数都接收/返回 ``sqlite3.Connection``，便于测试时注入临时数据库。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from .config import DB_PATH, SCHEMA_PATH

# 数据表所有列（顺序即 upsert 列顺序）
COLUMNS = [
    "date", "weekday", "iso_week", "month", "training_day",
    "sleep_h", "sleep_quality", "bedtime", "supps_done", "exercise_min", "commute_done",
    "diet_kcal", "meals_count", "breakfast_on_time", "phone_h",
    "deepwork_h", "learn_h", "life_h", "energy", "mood",
    "health_score", "work_score", "learn_score", "life_score",
    "system_score", "summary", "raw_path", "ingested_at",
]


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """打开数据库连接（row_factory=sqlite3.Row）。

    :param db_path: 指定数据库文件；省略则用 config.DB_PATH。
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None, schema_path: str | None = None) -> sqlite3.Connection:
    """建表。schema 默认读取 config.SCHEMA_PATH。

    :param db_path: 指定数据库文件；省略则用 config.DB_PATH。
    :param schema_path: 指定建表脚本；省略则用 config.SCHEMA_PATH。
    """
    schema_path = schema_path or SCHEMA_PATH
    conn = get_conn(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def upsert(conn: sqlite3.Connection, row: dict) -> None:
    """按 date 主键写入或更新一行。row 必须含 date。

    自动补 iso_week / month / ingested_at（缺失时）。
    """
    if "iso_week" not in row or row["iso_week"] is None:
        d = datetime.strptime(row["date"], "%Y-%m-%d")
        row["iso_week"] = d.isocalendar()[1]
        row["month"] = d.year * 100 + d.month
    row.setdefault("ingested_at", datetime.now().isoformat(timespec="seconds"))

    placeholders = ", ".join(["?"] * len(COLUMNS))
    updates = ", ".join([f"{c}=excluded.{c}" for c in COLUMNS if c != "date"])
    sql = f"""
        INSERT INTO daily_reviews ({', '.join(COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(date) DO UPDATE SET {updates}
    """
    conn.execute(sql, [row.get(c) for c in COLUMNS])


def fetch_all(conn: sqlite3.Connection, order: str = "date ASC") -> list:
    """返回全部行（按 order 排序）。"""
    cur = conn.execute(f"SELECT * FROM daily_reviews ORDER BY {order}")
    return cur.fetchall()


def count(conn: sqlite3.Connection) -> int:
    """返回表中行数。"""
    return conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
