"""ingest 端到端测试：解析 -> 补全评分 -> upsert 入库。"""
import os
import tempfile
import unittest

from review_tool.db import init_db, fetch_all, count
from review_tool.ingest import ingest_path, ingest_all

from tests.sample_data import SAMPLE_MD


def _tmp_db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.db")
    return init_db(db_path=path), path


class TestIngestPath(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()
        self.indir = tempfile.mkdtemp()
        self.md = os.path.join(self.indir, "2026-08-05.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(SAMPLE_MD)

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)
        os.remove(self.md)
        os.rmdir(self.indir)

    def test_ingest_single_file(self):
        ok = ingest_path(self.conn, self.md)
        self.assertTrue(ok)
        self.assertEqual(count(self.conn), 1)
        row = fetch_all(self.conn)[0]
        # 手填四维分保留
        self.assertEqual(row["health_score"], 4)
        self.assertEqual(row["work_score"], 6)
        # 系统分重算
        self.assertEqual(row["system_score"], 5.25)
        # 派生字段
        self.assertEqual(row["month"], 202608)

    def test_ingest_missing_date_skipped(self):
        bad = os.path.join(self.indir, "nodate.md")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("随便写点没有日期的内容\n")
        ok = ingest_path(self.conn, bad)
        self.assertFalse(ok)
        self.assertEqual(count(self.conn), 0)
        os.remove(bad)

    def test_ingest_writes_personal_tracks(self):
        ok = ingest_path(self.conn, self.md)
        self.assertTrue(ok)
        rows = self.conn.execute(
            "SELECT category, item, done FROM personal_tracks WHERE date='2026-08-05'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), ("服药", "补剂", 1))


class TestIngestAll(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()
        self.indir = tempfile.mkdtemp()
        for i, day in enumerate(("2026-08-05", "2026-08-06", "2026-08-07")):
            p = os.path.join(self.indir, f"{day}.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_MD.replace("2026-08-05", day))

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)
        for f in os.listdir(self.indir):
            os.remove(os.path.join(self.indir, f))
        os.rmdir(self.indir)

    def test_ingest_all(self):
        n = ingest_all(self.conn, self.indir)
        self.assertEqual(n, 3)
        self.assertEqual(count(self.conn), 3)


if __name__ == "__main__":
    unittest.main()
