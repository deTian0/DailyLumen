"""schema v5 → v6：training_sessions / training_items；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import SCHEMA_VERSION, init_db, migrate


def _make_v5_db(path: str) -> None:
    """构造假 v5 库（有 body_metrics，无 training_*）。"""
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
        CREATE TABLE body_metrics (
            date         TEXT PRIMARY KEY,
            weight_kg    REAL
                CHECK (weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 400)),
            body_fat_pct REAL
                CHECK (body_fat_pct IS NULL OR (body_fat_pct BETWEEN 0 AND 70)),
            waist_cm     REAL
                CHECK (waist_cm IS NULL OR (waist_cm > 0 AND waist_cm < 300)),
            src          TEXT
                CHECK (src IS NULL OR src IN ('scale', 'manual')),
            note         TEXT
        );
        INSERT INTO daily_reviews (date, sleep_h, exercise_min, exercise_src,
                                   health_score, work_score, learn_score, life_score,
                                   system_score)
        VALUES ('2026-09-01', 7.0, 20, 'record', 7, 7, 7, 7, 7.0);
        INSERT INTO personal_tracks
            (date, track_key, category, item_key, item, done)
        VALUES ('2026-09-01', 'skincare', '护肤', 'skincare', '护肤', 1);
        INSERT INTO body_metrics (date, weight_kg, body_fat_pct, waist_cm, src)
        VALUES ('2026-09-01', 72.0, 18.0, 80.0, 'scale');
        PRAGMA user_version = 5;
    """)
    conn.commit()
    conn.close()


class TestMigrationV6(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "v5.db")
        _make_v5_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upgrade_creates_training_tables(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        dr_cols = ["date", "sleep_h", "exercise_min", "exercise_src",
                   "health_score", "work_score", "learn_score", "life_score",
                   "system_score"]
        pt_cols = ["date", "track_key", "category", "item_key", "item", "done"]
        bm_cols = ["date", "weight_kg", "body_fat_pct", "waist_cm", "src", "note"]
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
        before_bm = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(bm_cols)} FROM body_metrics ORDER BY date"
            ).fetchall()
        ]
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertNotIn("training_sessions", tables)
        self.assertNotIn("training_items", tables)

        summary = migrate(conn)
        conn.commit()
        self.assertEqual(summary["version_after"], 6)
        self.assertEqual(SCHEMA_VERSION, 6)
        self.assertTrue(summary.get("training_created"))
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 6)

        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("training_sessions", tables)
        self.assertIn("training_items", tables)

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
        after_bm = [
            tuple(r) for r in conn.execute(
                f"SELECT {', '.join(bm_cols)} FROM body_metrics ORDER BY date"
            ).fetchall()
        ]
        self.assertEqual(before_dr, after_dr)
        self.assertEqual(before_pt, after_pt)
        self.assertEqual(before_bm, after_bm)

        idxs = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_ts_date", idxs)
        self.assertIn("idx_ti_date", idxs)
        self.assertIn("idx_ti_item", idxs)
        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(self.db)
        migrate(conn)
        conn.commit()
        s2 = migrate(conn)
        conn.commit()
        self.assertFalse(s2.get("training_created"))
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 6)
        n = conn.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0]
        self.assertEqual(n, 0)
        conn.close()

    def test_init_db_on_fresh_is_v6(self):
        path = os.path.join(self.root, "fresh.db")
        conn = init_db(db_path=path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 6)
        sess_cols = [r[1] for r in conn.execute("PRAGMA table_info(training_sessions)")]
        self.assertEqual(
            sess_cols,
            ["date", "session_key", "plan_name", "src", "total_min", "note"],
        )
        item_cols = [r[1] for r in conn.execute("PRAGMA table_info(training_items)")]
        self.assertEqual(
            item_cols,
            ["date", "session_key", "item_key", "item", "sets", "reps",
             "minutes", "load_kg"],
        )
        conn.close()

    def test_src_check_rejects_bad(self):
        path = os.path.join(self.root, "chk.db")
        conn = init_db(db_path=path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO training_sessions "
                "(date, session_key, src) VALUES ('2026-01-01', 'main', 'bad')"
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
