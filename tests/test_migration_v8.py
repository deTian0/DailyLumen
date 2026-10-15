"""schema v7 → v8：learning_logs + review_queue；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import SCHEMA_VERSION, init_db, migrate


def _make_v7_db(path: str) -> None:
    """构造假 v7 库（有 habit_logs，无 learning_*）。"""
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
        CREATE TABLE training_sessions (
            date TEXT NOT NULL,
            session_key TEXT NOT NULL,
            plan_name TEXT,
            src TEXT CHECK (src IS NULL OR src IN ('lianlian', 'self')),
            total_min INTEGER CHECK (total_min IS NULL OR total_min >= 0),
            note TEXT,
            PRIMARY KEY (date, session_key)
        );
        CREATE TABLE training_items (
            date TEXT NOT NULL,
            session_key TEXT NOT NULL,
            item_key TEXT NOT NULL,
            item TEXT NOT NULL,
            sets INTEGER,
            reps INTEGER,
            minutes REAL,
            load_kg REAL,
            PRIMARY KEY (date, session_key, item_key)
        );
        CREATE TABLE habit_logs (
            date TEXT NOT NULL,
            habit_key TEXT NOT NULL,
            category TEXT NOT NULL,
            item TEXT NOT NULL,
            done INTEGER CHECK (done IS NULL OR done IN (0, 1)),
            src TEXT,
            note TEXT,
            PRIMARY KEY (date, habit_key)
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
        INSERT INTO training_sessions (date, session_key, plan_name, src, total_min)
        VALUES ('2026-09-01', 'main', 'A-胸背', 'self', 40);
        INSERT INTO training_items
            (date, session_key, item_key, item, sets, reps, minutes, load_kg)
        VALUES ('2026-09-01', 'main', 'pushup', '俯卧撑', 3, 15, NULL, NULL);
        INSERT INTO habit_logs
            (date, habit_key, category, item, done, src)
        VALUES ('2026-09-01', 'reading_30', '行为习惯', '每日阅读 30 分钟', 1, 'clickup');
        PRAGMA user_version = 7;
    """)
    conn.commit()
    conn.close()


class TestMigrationV8(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "v7.db")
        _make_v7_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upgrade_creates_learning_tables(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        dr_cols = ["date", "sleep_h", "exercise_min", "exercise_src",
                   "health_score", "work_score", "learn_score", "life_score",
                   "system_score"]
        pt_cols = ["date", "track_key", "category", "item_key", "item", "done"]
        bm_cols = ["date", "weight_kg", "body_fat_pct", "waist_cm", "src", "note"]
        ts_cols = ["date", "session_key", "plan_name", "src", "total_min", "note"]
        ti_cols = ["date", "session_key", "item_key", "item", "sets", "reps",
                   "minutes", "load_kg"]
        hl_cols = ["date", "habit_key", "category", "item", "done", "src", "note"]

        def snap(table, cols):
            order = ", ".join(cols[:2]) if len(cols) > 1 else cols[0]
            return [
                tuple(r) for r in conn.execute(
                    f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}"
                ).fetchall()
            ]

        before = {
            "dr": snap("daily_reviews", dr_cols),
            "pt": snap("personal_tracks", pt_cols),
            "bm": snap("body_metrics", bm_cols),
            "ts": snap("training_sessions", ts_cols),
            "ti": snap("training_items", ti_cols),
            "hl": snap("habit_logs", hl_cols),
        }
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 7)
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertNotIn("learning_logs", tables)
        self.assertNotIn("review_queue", tables)

        summary = migrate(conn)
        conn.commit()
        self.assertEqual(summary["version_after"], SCHEMA_VERSION)
        self.assertGreaterEqual(SCHEMA_VERSION, 8)
        self.assertTrue(summary.get("learning_created"))
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )

        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("learning_logs", tables)
        self.assertIn("review_queue", tables)

        after = {
            "dr": snap("daily_reviews", dr_cols),
            "pt": snap("personal_tracks", pt_cols),
            "bm": snap("body_metrics", bm_cols),
            "ts": snap("training_sessions", ts_cols),
            "ti": snap("training_items", ti_cols),
            "hl": snap("habit_logs", hl_cols),
        }
        self.assertEqual(before, after)

        idxs = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_ll_date", idxs)
        self.assertIn("idx_ll_topic", idxs)
        self.assertIn("idx_rq_due", idxs)
        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(self.db)
        migrate(conn)
        conn.commit()
        s2 = migrate(conn)
        conn.commit()
        self.assertFalse(s2.get("learning_created"))
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        n = conn.execute("SELECT COUNT(*) FROM learning_logs").fetchone()[0]
        self.assertEqual(n, 0)
        conn.close()

    def test_init_db_on_fresh_has_learning_tables(self):
        path = os.path.join(self.root, "fresh.db")
        conn = init_db(db_path=path)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        ll = [r[1] for r in conn.execute("PRAGMA table_info(learning_logs)")]
        self.assertEqual(
            ll,
            ["date", "topic_key", "topic", "minutes", "src", "artifact"],
        )
        rq = [r[1] for r in conn.execute("PRAGMA table_info(review_queue)")]
        self.assertEqual(
            rq,
            ["topic_key", "topic", "stage", "due_date", "last_seen", "note"],
        )
        conn.close()

    def test_src_check_rejects_bad(self):
        path = os.path.join(self.root, "chk.db")
        conn = init_db(db_path=path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO learning_logs "
                "(date, topic_key, topic, minutes, src) "
                "VALUES ('2026-01-01', 'python', 'Python', 10, 'bogus')"
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
