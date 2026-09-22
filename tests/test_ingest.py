"""ingest 端到端测试：解析 -> 补全评分 -> upsert 入库。"""
import os
import shutil
import tempfile
import unittest

from review_tool.db import count, fetch_all, init_db
from review_tool.ingest import ingest_all, ingest_path, iter_markdown
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
        shutil.rmtree(self.indir, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)

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
        # 三大营养素入库
        self.assertEqual(row["carbs_g"], 150)
        self.assertEqual(row["fat_g"], 40)
        self.assertEqual(row["protein_g"], 55)

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
            "SELECT track_key, category, item_key, done FROM personal_tracks "
            "WHERE date='2026-08-05' ORDER BY track_key"
        ).fetchall()
        got = [tuple(r) for r in rows]
        self.assertEqual(got, [
            ("coq10@morning", "服药", "coq10", 1),
            ("exia_am@morning", "服药", "exia_am", 1),
            ("skincare", "护肤", "skincare", 1),
        ])

    def test_ingest_fills_missing_training_day(self):
        """training_day 空着时按 config 的训练日约定兜底，不留 NULL。"""
        md = os.path.join(self.indir, "2026-08-12.md")  # 周三 = 训练日
        with open(md, "w", encoding="utf-8") as f:
            f.write(SAMPLE_MD.replace("2026-08-05", "2026-08-12")
                    .replace("训练日: yes", "训练日: "))
        ingest_path(self.conn, md)
        row = self.conn.execute(
            "SELECT training_day FROM daily_reviews WHERE date='2026-08-12'"
        ).fetchone()
        self.assertEqual(row[0], 1)

    def test_ingest_does_not_erase_existing_on_rerun(self):
        """重跑 ingest 时，源文件里为空的字段不得把库中已有值刷掉。"""
        ingest_path(self.conn, self.md)
        # 模拟「AI 章节写完后手动补的 summary」存在于库中
        self.conn.execute(
            "UPDATE daily_reviews SET summary='人工补充的总结' WHERE date='2026-08-05'"
        )
        self.conn.commit()
        # 源文件里 summary 是「测试样例」，此处用一份不含 summary 的版本重跑
        lean = SAMPLE_MD.replace("一句话总结: 测试样例", "一句话总结: ")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(lean)
        ingest_path(self.conn, self.md)
        row = self.conn.execute(
            "SELECT summary FROM daily_reviews WHERE date='2026-08-05'"
        ).fetchone()
        self.assertEqual(row[0], "人工补充的总结")

    def test_ingest_overwrite_mode_erases(self):
        ingest_path(self.conn, self.md)
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(SAMPLE_MD.replace("一句话总结: 测试样例", "一句话总结: "))
        ingest_path(self.conn, self.md, overwrite=True)
        row = self.conn.execute(
            "SELECT summary FROM daily_reviews WHERE date='2026-08-05'"
        ).fetchone()
        self.assertIsNone(row[0])


class TestIterMarkdown(unittest.TestCase):
    """扫描范围：递归收集，但跳过收件箱与历史源复盘。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        for sub in ("复盘/2026-08", "收件箱", "历史源复盘"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        for rel in ("复盘/2026-08/2026-08-05.md", "收件箱/截图.md",
                    "历史源复盘/2026-07-16.md", "根目录.md"):
            with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
                f.write("x")

    def tearDown(self):
        for root, dirs, files in os.walk(self.root, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.root)

    def test_skips_inbox_and_archive(self):
        names = [os.path.basename(p) for p in iter_markdown(self.root)]
        self.assertIn("2026-08-05.md", names)
        self.assertIn("根目录.md", names)
        self.assertNotIn("截图.md", names)          # 收件箱跳过
        self.assertNotIn("2026-07-16.md", names)    # 历史源复盘跳过


class TestIngestAll(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()
        self.indir = tempfile.mkdtemp()
        for day in ("2026-08-05", "2026-08-06", "2026-08-07"):
            p = os.path.join(self.indir, f"{day}.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_MD.replace("2026-08-05", day))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.indir, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)

    def test_ingest_all(self):
        n = ingest_all(self.conn, self.indir)
        self.assertEqual(n, 3)
        self.assertEqual(count(self.conn), 3)


if __name__ == "__main__":
    unittest.main()
