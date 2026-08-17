"""SQLite 数据层：初始化、写入、查询。"""
import sqlite3
from datetime import datetime
import os
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(schema_path=None):
    """建表。schema 默认读取同目录 schema.sql。"""
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    conn = get_conn()
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def upsert(conn, row: dict):
    """按 date 主键写入或更新一行。row 必须含 date。"""
    # 自动补 iso_week / month
    if "iso_week" not in row or row["iso_week"] is None:
        d = datetime.strptime(row["date"], "%Y-%m-%d")
        row["iso_week"] = d.isocalendar()[1]
        row["month"] = d.year * 100 + d.month
    row.setdefault("ingested_at", datetime.now().isoformat(timespec="seconds"))
    cols = [
        "date", "weekday", "iso_week", "month", "training_day",
        "sleep_h", "sleep_quality", "bedtime", "supps_done", "exercise_min", "commute_done",
        "diet_kcal", "meals_count", "breakfast_on_time", "phone_h",
        "deepwork_h", "energy", "mood",
        "health_score", "work_score", "learn_score", "life_score",
        "system_score", "summary", "raw_path", "ingested_at",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    updates = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "date"])
    sql = f"""
        INSERT INTO daily_reviews ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(date) DO UPDATE SET {updates}
    """
    conn.execute(sql, [row.get(c) for c in cols])


def fetch_all(conn, order="date ASC"):
    cur = conn.execute(f"SELECT * FROM daily_reviews ORDER BY {order}")
    return cur.fetchall()


def count(conn):
    return conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
