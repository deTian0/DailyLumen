"""schema v11 → v12：睡眠结构扩展 4 列；既有行逐列无损、不参与评分。

用户 2026-11-17 拍板：精力/睡眠结构正式记录项，只做趋势、不评分、不催填。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.config import SCORE_THRESHOLDS
from review_tool.storage.db import (
    COLUMNS,
    SCHEMA_VERSION,
    init_db,
    migrate,
)


def _make_v11_db(path: str) -> None:
    """构造假 v11 库：有 clickup_done、睡眠三项，无睡眠结构列。"""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE daily_reviews (
            date TEXT PRIMARY KEY,
            weekday TEXT,
            training_day INTEGER,
            sleep_h REAL,
            sleep_quality INTEGER,
            bedtime INTEGER,
            energy TEXT,
            mood TEXT,
            health_score INTEGER,
            summary TEXT
        );
        CREATE TABLE clickup_done (
            date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            list_id TEXT NOT NULL,
            name TEXT NOT NULL,
            owner TEXT,
            minutes REAL,
            subject TEXT,
            is_self INTEGER CHECK (is_self IN (0, 1)),
            status TEXT,
            PRIMARY KEY (date, task_id)
        );
        PRAGMA user_version = 11;
    """)
    conn.execute(
        "INSERT INTO daily_reviews (date, sleep_h, sleep_quality, bedtime, energy, health_score) "
        "VALUES ('2026-11-16', 6.5, 80, 90, '中（下午困）', 5)"
    )
    conn.execute(
        "INSERT INTO clickup_done (date, task_id, list_id, name, is_self) "
        "VALUES ('2026-11-16', 't1', 'L', 'x', 1)"
    )
    conn.commit()
    conn.close()


class TestMigrationV12(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v11.db")
        _make_v11_db(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_adds_four_columns_and_bumps_version(self):
        conn = self._conn()
        migrate(conn)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")]
        for c in ("wake_time", "nap_min", "deep_sleep_pct", "awake_count"):
            self.assertIn(c, cols)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        conn.close()

    def test_existing_row_untouched_and_new_cols_null(self):
        conn = self._conn()
        migrate(conn)
        row = conn.execute("SELECT * FROM daily_reviews WHERE date='2026-11-16'").fetchone()
        self.assertEqual(row["sleep_h"], 6.5)
        self.assertEqual(row["sleep_quality"], 80)
        self.assertEqual(row["bedtime"], 90)
        self.assertEqual(row["energy"], "中（下午困）")
        self.assertEqual(row["health_score"], 5)
        self.assertIsNone(row["wake_time"])
        self.assertIsNone(row["nap_min"])
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM clickup_done").fetchone()[0], 1)
        conn.close()

    def test_idempotent(self):
        conn = self._conn()
        migrate(conn)
        before = [r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")]
        migrate(conn)
        after = [r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")]
        self.assertEqual(before, after)
        conn.close()

    def test_fresh_db_has_checks(self):
        fresh = os.path.join(self.tmp, "fresh.db")
        conn = init_db(fresh)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")]
        self.assertEqual(cols, COLUMNS)
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_reviews'"
        ).fetchone()[0]
        self.assertIn("deep_sleep_pct BETWEEN 0 AND 100", ddl)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO daily_reviews (date, deep_sleep_pct) VALUES ('2026-01-01', 120)"
            )
        conn.close()

    def test_not_in_scoring_weights(self):
        weights = SCORE_THRESHOLDS["weights"]
        for c in ("wake_time", "nap_min", "deep_sleep_pct", "awake_count", "energy", "mood"):
            self.assertNotIn(c, weights)


if __name__ == "__main__":
    unittest.main()
