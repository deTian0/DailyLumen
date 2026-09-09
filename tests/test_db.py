"""db 模块测试：建表、upsert 幂等、CHECK 约束、派生字段自动计算。"""
import os
import sqlite3
import tempfile
import unittest

from review_tool.db import init_db, upsert, fetch_all, count, COLUMNS, upsert_personal_track


def _tmp_db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.db")
    return init_db(db_path=path), path


class TestUpsert(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_insert_and_fetch(self):
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 7.0})
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)
        rows = fetch_all(self.conn)
        self.assertEqual(rows[0]["date"], "2026-08-05")
        self.assertEqual(rows[0]["sleep_h"], 7.0)

    def test_upsert_idempotent(self):
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 7.0})
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 8.0})
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)  # 同日期不重复
        self.assertEqual(fetch_all(self.conn)[0]["sleep_h"], 8.0)

    def test_auto_iso_week_and_month(self):
        upsert(self.conn, {"date": "2026-08-05"})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertIsInstance(row["iso_week"], int)
        self.assertEqual(row["month"], 202608)

    def test_check_rejects_bad_score(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-06", "health_score": 99})
            self.conn.commit()

    def test_check_rejects_bad_bool(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-07", "training_day": 2})
            self.conn.commit()

    def test_all_columns_present(self):
        # 写入全 None 的行不应报错（CHECK 允许 NULL）
        row = {c: None for c in COLUMNS}
        row["date"] = "2026-08-08"
        upsert(self.conn, row)
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)

    def test_macro_columns_roundtrip(self):
        upsert(self.conn, {"date": "2026-08-05", "carbs_g": 150, "fat_g": 40, "protein_g": 55})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["carbs_g"], 150)
        self.assertEqual(row["fat_g"], 40)
        self.assertEqual(row["protein_g"], 55)

    def test_macro_check_rejects_negative(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-06", "carbs_g": -10})
            self.conn.commit()


class TestMigration(unittest.TestCase):
    """老库（schema 更新前建表）init_db 应无损补齐缺失宏量列。"""

    def test_adds_missing_macro_columns(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "old.db")
        conn = sqlite3.connect(path)
        # 仿「加宏量列之前」的真实历史 schema（含 iso_week/month，无 macros 列）
        conn.executescript("""
            CREATE TABLE daily_reviews (
                date     TEXT PRIMARY KEY,
                weekday  TEXT,
                iso_week INTEGER,
                month    INTEGER,
                training_day INTEGER,
                sleep_h  REAL,
                sleep_quality INTEGER,
                bedtime  INTEGER,
                exercise_min INTEGER,
                commute_done INTEGER,
                diet_kcal INTEGER,
                meals_count INTEGER,
                breakfast_on_time INTEGER,
                phone_h  REAL,
                deepwork_h REAL,
                learn_h  REAL,
                life_h   REAL,
                energy   TEXT,
                mood     TEXT,
                health_score INTEGER,
                work_score INTEGER,
                learn_score INTEGER,
                life_score INTEGER,
                system_score REAL,
                summary  TEXT,
                raw_path TEXT,
                ingested_at TEXT
            );
            INSERT INTO daily_reviews (date, diet_kcal) VALUES ('2026-08-05', 1500);
        """)
        conn.commit()
        conn.close()

        conn = init_db(db_path=path)  # 触发增量迁移
        cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")}
        for c in ("carbs_g", "fat_g", "protein_g"):
            self.assertIn(c, cols)
        # 老数据保留无损
        v = conn.execute(
            "SELECT diet_kcal FROM daily_reviews WHERE date='2026-08-05'"
        ).fetchone()[0]
        self.assertEqual(v, 1500)
        conn.close()
        os.remove(path)
        os.rmdir(d)


class TestPersonalTracks(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_upsert_and_fetch(self):
        upsert_personal_track(self.conn, "2026-08-05", "服药", "CoQ10", 1)
        upsert_personal_track(self.conn, "2026-08-05", "护肤", "护肤", 0)
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT category, item, done FROM personal_tracks ORDER BY category, item"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(tuple(rows[0]), ("护肤", "护肤", 0))
        self.assertEqual(tuple(rows[1]), ("服药", "CoQ10", 1))

    def test_upsert_idempotent(self):
        upsert_personal_track(self.conn, "2026-08-05", "服药", "CoQ10", 1)
        upsert_personal_track(self.conn, "2026-08-05", "服药", "CoQ10", 0)
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT done FROM personal_tracks WHERE date='2026-08-05' AND item='CoQ10'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["done"], 0)


if __name__ == "__main__":
    unittest.main()
