"""schema v9 → v10：promises；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import (
    SCHEMA_VERSION,
    init_db,
    load_promises,
    migrate,
    replace_promises,
)


def _make_v9_db(path: str) -> None:
    """构造假 v9 库（有 nutrition_items，无 promises）。"""
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
            system_score INTEGER,
            summary TEXT,
            raw_path TEXT,
            ingested_at TEXT
        );
        CREATE TABLE personal_tracks (
            date TEXT NOT NULL,
            track_key TEXT NOT NULL,
            category TEXT,
            item_key TEXT NOT NULL,
            item TEXT,
            done INTEGER,
            note TEXT,
            PRIMARY KEY (date, track_key)
        );
        CREATE TABLE nutrition_items (
            date TEXT NOT NULL,
            seq INTEGER NOT NULL CHECK (seq >= 0),
            meal TEXT NOT NULL,
            item TEXT NOT NULL,
            kcal REAL,
            PRIMARY KEY (date, seq)
        );
        PRAGMA user_version = 9;
    """)
    conn.execute(
        "INSERT INTO daily_reviews (date, exercise_min, exercise_src) "
        "VALUES ('2026-10-20', 30, 'record')"
    )
    conn.execute(
        "INSERT INTO personal_tracks (date, track_key, item_key, item, done) "
        "VALUES ('2026-10-20', 'coq10@morning', 'coq10', 'CoQ10 ×1', 1)"
    )
    conn.execute(
        "INSERT INTO nutrition_items (date, seq, meal, item) "
        "VALUES ('2026-10-20', 0, 'lunch', '干锅肥肠')"
    )
    conn.commit()
    conn.close()


class TestMigrationV10(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v9.db")
        _make_v9_db(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_migrate_creates_table_and_bumps_version(self):
        conn = self._conn()
        migrate(conn)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(promises)")]
        self.assertEqual(cols, ["date", "kind", "seq", "text", "bucket"])
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        conn.close()

    def test_migrate_idempotent(self):
        conn = self._conn()
        first = migrate(conn)
        self.assertTrue(first["promises_created"])
        second = migrate(conn)
        self.assertFalse(second["promises_created"])
        conn.close()

    def test_existing_rows_untouched(self):
        conn = self._conn()
        migrate(conn)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0], 1
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0], 1
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM nutrition_items").fetchone()[0], 1
        )
        row = conn.execute("SELECT * FROM daily_reviews").fetchone()
        self.assertEqual(row["exercise_min"], 30)
        self.assertEqual(row["exercise_src"], "record")
        conn.close()

    def test_init_db_starts_at_current_version(self):
        fresh = os.path.join(self.tmp, "fresh.db")
        conn = init_db(fresh)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        conn.close()


class TestReplacePromises(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "db.db")
        self.conn = init_db(self.path)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_insert_and_read(self):
        got = replace_promises(
            self.conn,
            "2026-10-20",
            {
                "plan": [
                    {"text": "积极心理学 60min", "bucket": "learn"},
                    {"text": "脂肪 ≤70g", "bucket": "diet"},
                ]
            },
        )
        self.assertEqual(got["plan"]["inserted"], 2)
        rows = load_promises(self.conn, date="2026-10-20")
        self.assertEqual([r["seq"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["text"], "积极心理学 60min")
        self.assertEqual(rows[1]["bucket"], "diet")

    def test_replace_is_delete_then_insert(self):
        """权威是源 md：重跑要把已删除的行清掉，不是追加。"""
        replace_promises(
            self.conn, "2026-10-20",
            {"plan": [{"text": "A"}, {"text": "B"}]},
        )
        got = replace_promises(
            self.conn, "2026-10-20",
            {"plan": [{"text": "B"}]},
        )
        self.assertEqual(got["plan"], {"deleted": 2, "inserted": 1})
        rows = load_promises(self.conn, date="2026-10-20")
        self.assertEqual([r["text"] for r in rows], ["B"])

    def test_empty_list_clears_only_that_kind(self):
        replace_promises(
            self.conn, "2026-10-20",
            {"plan": [{"text": "A"}], "improvement": [{"text": "B"}]},
        )
        replace_promises(self.conn, "2026-10-20", {"plan": []})
        rows = load_promises(self.conn, date="2026-10-20")
        self.assertEqual([r["text"] for r in rows], ["B"])

    def test_absent_kind_untouched(self):
        """md 里删掉整段「明日 Top 3」→ 该 kind 不在字典里 → 库里旧行保留。"""
        replace_promises(
            self.conn, "2026-10-20",
            {"plan": [{"text": "A"}], "improvement": [{"text": "B"}]},
        )
        replace_promises(self.conn, "2026-10-20", {"improvement": [{"text": "B2"}]})
        rows = load_promises(self.conn, date="2026-10-20")
        self.assertEqual(sorted(r["text"] for r in rows), ["A", "B2"])

    def test_requires_date(self):
        with self.assertRaises(ValueError):
            replace_promises(self.conn, "", {"plan": []})

    def test_blank_text_skipped(self):
        got = replace_promises(
            self.conn, "2026-10-20",
            {"plan": [{"text": "A"}, {"text": "  "}]},
        )
        self.assertEqual(got["plan"]["inserted"], 1)

    def test_kind_check_rejects_unknown(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO promises (date, kind, seq, text) "
                "VALUES ('2026-10-20', 'todo', 0, 'x')"
            )

    def test_load_filters(self):
        for d in ("2026-10-19", "2026-10-20", "2026-10-21"):
            replace_promises(
                self.conn, d,
                {"plan": [{"text": "A"}], "improvement": [{"text": "B"}]},
            )
        self.assertEqual(len(load_promises(self.conn)), 6)
        self.assertEqual(len(load_promises(self.conn, kind="plan")), 3)
        self.assertEqual(
            len(load_promises(self.conn, start="2026-10-20", end="2026-10-20")), 2
        )


if __name__ == "__main__":
    unittest.main()
