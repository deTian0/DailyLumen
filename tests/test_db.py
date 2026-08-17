"""db 模块测试：建表、upsert 幂等、CHECK 约束、派生字段自动计算。"""
import os
import sqlite3
import tempfile
import unittest

from review_tool.db import init_db, upsert, fetch_all, count, COLUMNS


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


if __name__ == "__main__":
    unittest.main()
