"""schema v10 → v11：clickup_done 快照表；既有表行级无损。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.storage.db import (
    SCHEMA_VERSION,
    clickup_self_day,
    count_clickup_days,
    init_db,
    load_clickup_done,
    migrate,
    replace_clickup_days,
)


def _make_v10_db(path: str) -> None:
    """构造假 v10 库（有 promises，无 clickup_done）。"""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE daily_reviews (
            date TEXT PRIMARY KEY,
            weekday TEXT,
            deepwork_h REAL,
            summary TEXT
        );
        CREATE TABLE promises (
            date TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('improvement', 'plan')),
            seq INTEGER NOT NULL CHECK (seq >= 0),
            text TEXT NOT NULL,
            bucket TEXT,
            PRIMARY KEY (date, kind, seq)
        );
        PRAGMA user_version = 10;
    """)
    conn.execute(
        "INSERT INTO daily_reviews (date, deepwork_h) VALUES ('2026-10-20', 4.5)"
    )
    conn.execute(
        "INSERT INTO promises (date, kind, seq, text, bucket) "
        "VALUES ('2026-10-20', 'plan', 0, '深度工作 5h', 'work')"
    )
    conn.commit()
    conn.close()


class TestMigrationV11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v10.db")
        _make_v10_db(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_creates_table_and_bumps_version(self):
        conn = self._conn()
        migrate(conn)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(clickup_done)")]
        self.assertEqual(
            cols,
            ["date", "task_id", "list_id", "name", "owner", "minutes",
             "subject", "is_self", "status"],
        )
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        conn.close()

    def test_idempotent(self):
        conn = self._conn()
        self.assertTrue(migrate(conn)["clickup_done_created"])
        self.assertFalse(migrate(conn)["clickup_done_created"])
        conn.close()

    def test_existing_rows_untouched(self):
        conn = self._conn()
        migrate(conn)
        row = conn.execute("SELECT * FROM daily_reviews").fetchone()
        self.assertEqual(row["deepwork_h"], 4.5)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0], 1
        )
        conn.close()

    def test_init_db_starts_at_current_version(self):
        fresh = os.path.join(self.tmp, "fresh.db")
        conn = init_db(fresh)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        conn.close()


class TestReplaceClickupDays(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = init_db(os.path.join(self.tmp, "db.db"))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _row(tid, *, minutes=120.0, is_self=1, subject="x"):
        return {
            "task_id": tid,
            "list_id": "L1",
            "name": f"梁帅-2h-{subject}",
            "owner": "梁帅",
            "minutes": minutes,
            "subject": subject,
            "is_self": is_self,
            "status": "complete",
        }

    def test_insert_and_load(self):
        got = replace_clickup_days(
            self.conn, {"2026-10-20": [self._row("a"), self._row("b")]}
        )
        self.assertEqual(got["2026-10-20"]["inserted"], 2)
        rows = load_clickup_done(self.conn, date="2026-10-20")
        self.assertEqual([r["task_id"] for r in rows], ["a", "b"])

    def test_replace_is_delete_then_insert(self):
        """任务被取消完成 / 改名后，重拉不该留幽灵行。"""
        replace_clickup_days(self.conn, {"2026-10-20": [self._row("a"), self._row("b")]})
        got = replace_clickup_days(self.conn, {"2026-10-20": [self._row("b")]})
        self.assertEqual(got["2026-10-20"], {"deleted": 2, "inserted": 1})
        self.assertEqual(
            [r["task_id"] for r in load_clickup_done(self.conn, date="2026-10-20")],
            ["b"],
        )

    def test_absent_date_untouched(self):
        replace_clickup_days(
            self.conn, {"2026-10-19": [self._row("a")], "2026-10-20": [self._row("b")]}
        )
        replace_clickup_days(self.conn, {"2026-10-20": [self._row("c")]})
        self.assertEqual(count_clickup_days(self.conn), 2)
        self.assertEqual(
            [r["task_id"] for r in load_clickup_done(self.conn, date="2026-10-19")],
            ["a"],
        )

    def test_empty_list_clears_that_date(self):
        replace_clickup_days(self.conn, {"2026-10-20": [self._row("a")]})
        replace_clickup_days(self.conn, {"2026-10-20": []})
        self.assertEqual(load_clickup_done(self.conn, date="2026-10-20"), [])

    def test_blank_task_id_skipped(self):
        got = replace_clickup_days(
            self.conn, {"2026-10-20": [self._row("a"), self._row("")]}
        )
        self.assertEqual(got["2026-10-20"]["inserted"], 1)

    def test_is_self_check_rejects_other_values(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO clickup_done (date, task_id, list_id, name, is_self) "
                "VALUES ('2026-10-20', 'x', 'L', 'n', 2)"
            )

    def test_self_day_distinguishes_empty_from_absent(self):
        """没有本人记录 → count 0 / max None；**不是 0 分钟**。"""
        replace_clickup_days(
            self.conn,
            {"2026-10-20": [self._row("a", is_self=0, minutes=300.0)]},
        )
        s = clickup_self_day(self.conn, "2026-10-20")
        self.assertEqual(s["count"], 0)
        self.assertIsNone(s["max_minutes"])

    def test_self_day_max_is_per_task_not_sum(self):
        """多条工时只取最长单条 —— 合计会因任务重叠而虚高。"""
        replace_clickup_days(
            self.conn,
            {
                "2026-10-20": [
                    self._row("a", minutes=480.0),
                    self._row("b", minutes=240.0),
                    self._row("c", minutes=600.0, is_self=0),
                ]
            },
        )
        self.assertEqual(clickup_self_day(self.conn, "2026-10-20")["max_minutes"], 480.0)

    def test_load_range(self):
        for d in ("2026-10-18", "2026-10-19", "2026-10-20"):
            replace_clickup_days(self.conn, {d: [self._row("t" + d)]})
        rows = load_clickup_done(self.conn, start="2026-10-19", end="2026-10-20")
        self.assertEqual([r["date"] for r in rows], ["2026-10-19", "2026-10-20"])


if __name__ == "__main__":
    unittest.main()
