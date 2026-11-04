"""schema v8 → v9：nutrition_items；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import (
    SCHEMA_VERSION,
    init_db,
    load_nutrition_items,
    migrate,
    replace_nutrition_items,
)


def _make_v8_db(path: str) -> None:
    """构造假 v8 库（有 learning_*，无 nutrition_items）。"""
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
        CREATE TABLE learning_logs (
            date TEXT NOT NULL,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            minutes REAL
                CHECK (minutes IS NULL OR minutes >= 0),
            src TEXT
                CHECK (src IS NULL OR src IN ('clickup', 'self', 'course')),
            artifact TEXT,
            PRIMARY KEY (date, topic_key)
        );
        INSERT INTO daily_reviews (date, sleep_h, exercise_min, exercise_src,
                                   health_score, work_score, learn_score, life_score,
                                   system_score)
        VALUES ('2026-10-01', 7.0, 20, 'record', 7, 7, 7, 7, 7.0);
        INSERT INTO personal_tracks
            (date, track_key, category, item_key, item, done)
        VALUES ('2026-10-01', 'skincare', '护肤', 'skincare', '护肤', 1);
        INSERT INTO learning_logs (date, topic_key, topic, minutes, src)
        VALUES ('2026-10-01', 'python', 'Python', 45, 'self');
        PRAGMA user_version = 8;
    """)
    conn.commit()
    conn.close()


class TestMigrationV9(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "v8.db")
        _make_v8_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _tables(self, conn):
        return {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def test_upgrade_creates_nutrition_items(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        before = {
            "dr": [tuple(r) for r in conn.execute(
                "SELECT date, sleep_h, exercise_min, exercise_src, system_score "
                "FROM daily_reviews ORDER BY date")],
            "pt": [tuple(r) for r in conn.execute(
                "SELECT date, track_key, item, done FROM personal_tracks "
                "ORDER BY date, track_key")],
            "ll": [tuple(r) for r in conn.execute(
                "SELECT date, topic_key, minutes, src FROM learning_logs "
                "ORDER BY date, topic_key")],
        }
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 8)
        self.assertNotIn("nutrition_items", self._tables(conn))

        summary = migrate(conn)
        conn.commit()
        self.assertEqual(summary["version_after"], SCHEMA_VERSION)
        self.assertGreaterEqual(SCHEMA_VERSION, 9)
        self.assertTrue(summary.get("nutrition_created"))
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        self.assertIn("nutrition_items", self._tables(conn))

        after = {
            "dr": [tuple(r) for r in conn.execute(
                "SELECT date, sleep_h, exercise_min, exercise_src, system_score "
                "FROM daily_reviews ORDER BY date")],
            "pt": [tuple(r) for r in conn.execute(
                "SELECT date, track_key, item, done FROM personal_tracks "
                "ORDER BY date, track_key")],
            "ll": [tuple(r) for r in conn.execute(
                "SELECT date, topic_key, minutes, src FROM learning_logs "
                "ORDER BY date, topic_key")],
        }
        self.assertEqual(before, after)

        idxs = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_ni_date", idxs)
        self.assertIn("idx_ni_meal", idxs)
        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(self.db)
        migrate(conn)
        conn.commit()
        s2 = migrate(conn)
        conn.commit()
        self.assertFalse(s2.get("nutrition_created"))
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM nutrition_items").fetchone()[0], 0
        )
        conn.close()

    def test_init_db_on_fresh_has_nutrition_table(self):
        path = os.path.join(self.root, "fresh.db")
        conn = init_db(db_path=path)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(nutrition_items)")]
        self.assertEqual(
            cols,
            ["date", "seq", "meal", "item", "kcal",
             "protein_g", "carb_g", "fat_g", "note"],
        )
        conn.close()

    def test_meal_check_rejects_bad(self):
        path = os.path.join(self.root, "chk.db")
        conn = init_db(db_path=path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO nutrition_items (date, seq, meal, item) "
                "VALUES ('2026-01-01', 0, 'brunch', 'x')"
            )
        conn.close()

    def test_kcal_check_rejects_negative_and_absurd(self):
        path = os.path.join(self.root, "chk2.db")
        conn = init_db(db_path=path)
        for bad in (-1, 6000):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO nutrition_items (date, seq, meal, item, kcal) "
                    "VALUES ('2026-01-01', 0, 'lunch', 'x', ?)", (bad,)
                )
        conn.close()

    def test_replace_is_delete_then_insert(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        migrate(conn)
        conn.commit()
        replace_nutrition_items(conn, "2026-10-02", [
            {"meal": "breakfast", "item": "包子", "kcal": 200},
            {"meal": "lunch", "item": "盖饭", "kcal": 700},
        ])
        replace_nutrition_items(conn, "2026-10-02", [
            {"meal": "dinner", "item": "面条", "kcal": 600},
        ])
        conn.commit()
        rows = [dict(r) for r in load_nutrition_items(conn, date="2026-10-02")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item"], "面条")
        self.assertEqual(rows[0]["seq"], 0)
        conn.close()

    def test_replace_empty_clears_day(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        migrate(conn)
        conn.commit()
        replace_nutrition_items(conn, "2026-10-03", [
            {"meal": "lunch", "item": "牛肉面", "kcal": 650},
        ])
        conn.commit()
        result = replace_nutrition_items(conn, "2026-10-03", [])
        conn.commit()
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(load_nutrition_items(conn, date="2026-10-03"), [])
        conn.close()

    def test_replace_skips_blank_item(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        migrate(conn)
        conn.commit()
        result = replace_nutrition_items(conn, "2026-10-04", [
            {"meal": "lunch", "item": "  ", "kcal": 100},
            {"meal": "lunch", "item": "鸡腿", "kcal": 300},
        ])
        conn.commit()
        self.assertEqual(result["inserted"], 1)
        rows = [dict(r) for r in load_nutrition_items(conn, date="2026-10-04")]
        self.assertEqual(rows[0]["seq"], 0)
        conn.close()

    def test_replace_requires_date(self):
        conn = sqlite3.connect(self.db)
        with self.assertRaises(ValueError):
            replace_nutrition_items(conn, "", [])
        conn.close()


if __name__ == "__main__":
    unittest.main()
