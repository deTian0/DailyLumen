"""schema v4 → v5：body_metrics 新建；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import SCHEMA_VERSION, init_db, migrate


def _make_v4_db(path: str) -> None:
    """构造一个假 v4 库（有 daily_reviews / personal_tracks，无 body_metrics）。"""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE daily_reviews (
            date TEXT PRIMARY KEY,
            weekday TEXT,
            iso_week INTEGER,
            month INTEGER,
            training_day INTEGER,
            sleep_h REAL,
            exercise_min INTEGER,
            exercise_src TEXT
                CHECK (exercise_src IS NULL OR exercise_src IN
                       ('record', 'derived', 'zero')),
            health_score INTEGER,
            work_score INTEGER,
            learn_score INTEGER,
            life_score INTEGER,
            system_score REAL
        );
        CREATE TABLE personal_tracks (
            date TEXT NOT NULL,
            track_key TEXT NOT NULL,
            category TEXT NOT NULL,
            item_key TEXT NOT NULL,
            item TEXT NOT NULL,
            done INTEGER CHECK (done IS NULL OR done IN (0, 1)),
            note TEXT,
            PRIMARY KEY (date, track_key)
        );
        INSERT INTO daily_reviews (date, sleep_h, exercise_min, exercise_src,
                                   health_score, work_score, learn_score, life_score,
                                   system_score)
        VALUES ('2026-09-01', 7.0, 20, 'record', 7, 7, 7, 7, 7.0);
        INSERT INTO personal_tracks
            (date, track_key, category, item_key, item, done)
        VALUES ('2026-09-01', 'skincare', '护肤', 'skincare', '护肤', 1);
        PRAGMA user_version = 4;
    """)
    conn.commit()
    conn.close()


class TestMigrationV5(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "v4.db")
        _make_v4_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upgrade_creates_body_metrics_and_bumps_version(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        # 既有列逐字段快照（迁移可能 ADD COLUMN，但旧列值必须无损）
        dr_cols = ["date", "sleep_h", "exercise_min", "exercise_src",
                   "health_score", "work_score", "learn_score", "life_score",
                   "system_score"]
        pt_cols = ["date", "track_key", "category", "item_key", "item", "done"]
        before_dr = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(dr_cols)} FROM daily_reviews ORDER BY date"
            ).fetchall()
        ]
        before_pt = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(pt_cols)} FROM personal_tracks "
                "ORDER BY date, track_key"
            ).fetchall()
        ]
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertNotIn("body_metrics", tables)

        summary = migrate(conn)
        conn.commit()
        self.assertEqual(summary["version_after"], 5)
        self.assertEqual(SCHEMA_VERSION, 5)
        self.assertTrue(summary.get("body_metrics_created"))

        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("body_metrics", tables)

        after_dr = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(dr_cols)} FROM daily_reviews ORDER BY date"
            ).fetchall()
        ]
        after_pt = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(pt_cols)} FROM personal_tracks "
                "ORDER BY date, track_key"
            ).fetchall()
        ]
        self.assertEqual(before_dr, after_dr)
        self.assertEqual(before_pt, after_pt)

        # 索引存在
        idxs = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_body_date", idxs)
        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(self.db)
        migrate(conn)
        conn.commit()
        s2 = migrate(conn)
        conn.commit()
        self.assertFalse(s2.get("body_metrics_created"))
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
        n = conn.execute("SELECT COUNT(*) FROM body_metrics").fetchone()[0]
        self.assertEqual(n, 0)
        conn.close()

    def test_init_db_on_fresh_is_v5(self):
        path = os.path.join(self.root, "fresh.db")
        conn = init_db(db_path=path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(body_metrics)")]
        self.assertEqual(
            cols,
            ["date", "weight_kg", "body_fat_pct", "waist_cm", "src", "note"],
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
