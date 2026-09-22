"""example 数据库守卫：空模板必须与当前 schema 同版（v1.4.1 新增）。

背景：``reviews.example.db`` 曾被落在 schema v2（缺 ``exercise_src``、CHECK 不含
``'zero'``）。新用户复制它当 reviews.db 后，第一次 ingest 写 ``exercise_src='zero'``
会被 CHECK 拒绝 —— 而且因为迁移能补列、却无法改 CHECK，问题会一直潜伏。
这里用只读断言把它钉在当前版本上。
"""
import os
import sqlite3
import unittest

from review_tool.config import PACKAGE_DIR
from review_tool.storage.db import COLUMNS, SCHEMA_VERSION

EXAMPLE_DB = os.path.join(PACKAGE_DIR, "reviews.example.db")


def _conn():
    return sqlite3.connect(EXAMPLE_DB)


def _ddl(conn, name):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
    return row[0] if row else ""


class TestExampleDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(EXAMPLE_DB):
            raise unittest.SkipTest("reviews.example.db 不存在")
        cls.conn = _conn()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_version_matches_schema(self):
        v = self.conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(v, SCHEMA_VERSION)

    def test_has_all_columns(self):
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(daily_reviews)")]
        self.assertEqual(cols, COLUMNS)

    def test_exercise_src_check_allows_zero(self):
        """v4 关键点：CHECK 必须放行 'zero'（训练日未记录按 0 计）。"""
        ddl = _ddl(self.conn, "daily_reviews")
        self.assertIn("exercise_src", ddl)
        self.assertIn("'zero'", ddl)
        self.assertIn("'derived'", ddl)

    def test_personal_tracks_has_track_key(self):
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(personal_tracks)")]
        self.assertIn("track_key", cols)
        self.assertIn("item_key", cols)

    def test_is_empty_template(self):
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0], 0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0], 0)

    def test_integrity_ok(self):
        self.assertEqual(
            self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_zero_write_accepted(self):
        """在拷贝上写入 exercise_src='zero' 不应被 CHECK 拒绝。"""
        import tempfile

        tmp = tempfile.mkdtemp()
        copy = os.path.join(tmp, "copy.db")
        try:
            dst = sqlite3.connect(copy)
            self.conn.backup(dst)
            dst.execute(
                "INSERT INTO daily_reviews (date, exercise_min, exercise_src) "
                "VALUES ('2026-01-01', 0, 'zero')"
            )
            dst.commit()
            got = dst.execute(
                "SELECT exercise_src FROM daily_reviews WHERE date='2026-01-01'"
            ).fetchone()[0]
            self.assertEqual(got, "zero")
            dst.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
