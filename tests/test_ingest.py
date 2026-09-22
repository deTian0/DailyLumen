"""ingest 端到端测试：解析 -> 补全评分 -> upsert 入库。"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from review_tool.pipeline.ingest import ingest_all, ingest_path, iter_markdown
from review_tool.storage.db import count, fetch_all, init_db
from tests.sample_data import BODYWEIGHT_MD, EMPTY_EXERCISE_LINE, PROSE_MD, SAMPLE_MD


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


class TestTrackPrune(unittest.TestCase):
    """`--prune-tracks`：以源 md 为权威集合，清掉规范 ID 变化后残留的旧键。"""

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

    def _keys(self):
        return [r[0] for r in self.conn.execute(
            "SELECT track_key FROM personal_tracks WHERE date='2026-08-05' "
            "ORDER BY track_key")]

    def _stale_row(self, key="movefree"):
        self.conn.execute(
            "INSERT INTO personal_tracks (date, track_key, category, item_key, item, done) "
            "VALUES ('2026-08-05', ?, '服药', ?, 'Move Free 红色 ×1', 1)",
            (key, key),
        )
        self.conn.commit()

    def test_prune_removes_stale_but_keeps_parsed(self):
        ingest_path(self.conn, self.md)
        self._stale_row("movefree")
        self.assertIn("movefree", self._keys())

        row = ingest_path(self.conn, self.md, prune_tracks=True)
        self.assertNotIn("movefree", self._keys())
        self.assertEqual(self._keys(),
                         ["coq10@morning", "exia_am@morning", "skincare"])
        self.assertEqual(row["_pruned_tracks"], ["movefree"])

    def test_default_does_not_prune(self):
        ingest_path(self.conn, self.md)
        self._stale_row("movefree")
        ingest_path(self.conn, self.md)          # 默认不清理
        self.assertIn("movefree", self._keys())

    def test_no_section_means_no_prune(self):
        """打卡章节解析不到时不敢清理（否则解析失败会被当成「已删除」）。"""
        ingest_path(self.conn, self.md)
        self._stale_row("movefree")
        # 把打卡章节整体删掉，只留日期
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("## 二、今日三件事\n\n- 修 bug\n\n```data\n日期: 2026-08-05\n```\n")
        ingest_path(self.conn, self.md, prune_tracks=True)
        self.assertIn("movefree", self._keys())

    def test_idempotent(self):
        ingest_path(self.conn, self.md)
        self._stale_row("movefree")
        ingest_path(self.conn, self.md, prune_tracks=True)
        before = self._keys()
        ingest_path(self.conn, self.md, prune_tracks=True)
        self.assertEqual(self._keys(), before)

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


class TestIngestBodyweight(unittest.TestCase):
    """端到端：描述里的俯卧撑 -> 运动时长入库 -> 训练日计入达标。"""

    def setUp(self):
        self.conn, self.path = _tmp_db()
        self.indir = tempfile.mkdtemp()
        self.md = os.path.join(self.indir, "2026-09-21.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(BODYWEIGHT_MD)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.indir, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)

    def test_derived_minutes_ingested(self):
        ingest_path(self.conn, self.md)
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["exercise_min"], 10)
        self.assertEqual(row["exercise_src"], "derived")

    def test_rerun_does_not_duplicate_or_lose(self):
        ingest_path(self.conn, self.md)
        ingest_path(self.conn, self.md)
        rows = fetch_all(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exercise_min"], 10)

    def test_manual_value_wins_over_derivation(self):
        """数据块里填了运动时长后，折算不得叠加。"""
        p = os.path.join(self.indir, "manual.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(BODYWEIGHT_MD.replace(EMPTY_EXERCISE_LINE, "运动时长_min: 25"))
        ingest_path(self.conn, p)
        row = self.conn.execute(
            "SELECT exercise_min, exercise_src FROM daily_reviews WHERE date='2026-09-21'"
        ).fetchone()
        self.assertEqual(row[0], 25)
        self.assertEqual(row[1], "record")

    def test_ingest_all_reports_derived_count(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n = ingest_all(self.conn, self.indir)
        self.assertEqual(n, 1)
        self.assertIn("描述折算", buf.getvalue())


class TestZeroFill(unittest.TestCase):
    """v1.3.2 口径：训练日未记录按 0 计，非训练日不动。"""

    def setUp(self):
        self.conn, self.path = _tmp_db()
        self.indir = tempfile.mkdtemp()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.indir, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)

    def _write(self, name: str, text: str) -> str:
        p = os.path.join(self.indir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_training_day_without_exercise_records_zero(self):
        """训练日 + 无折算命中 -> exercise_min=0 / src=zero。"""
        # 2026-09-21 周一 = 训练日；把俯卧撑行换掉，折算不命中
        no_move = BODYWEIGHT_MD.replace("1. 做了二十个俯卧撑，而且有喝蛋白粉", "1. 写完周报")
        p = self._write("2026-09-21.md", no_move)
        ingest_path(self.conn, p)
        row = self.conn.execute(
            "SELECT training_day, exercise_min, exercise_src FROM daily_reviews"
        ).fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 0)
        self.assertEqual(row[2], "zero")

    def test_non_training_day_stays_null(self):
        """非训练日运动不是当天预期，exercise_min 保持 NULL。"""
        p = self._write("2026-08-10.md", PROSE_MD)  # 2026-08-10 周日
        ingest_path(self.conn, p)
        row = self.conn.execute(
            "SELECT training_day, exercise_min, exercise_src FROM daily_reviews"
        ).fetchone()
        self.assertEqual(row[0], 0)
        self.assertIsNone(row[1])
        self.assertIsNone(row[2])

    def test_explicit_zero_is_record_not_zero_src(self):
        """手填 0 是明确记录（src=record），不是口径兜底。"""
        no_move = BODYWEIGHT_MD.replace(
            EMPTY_EXERCISE_LINE, "运动时长_min: 0"
        ).replace("1. 做了二十个俯卧撑，而且有喝蛋白粉", "1. 写完周报")
        p = self._write("2026-09-21.md", no_move)
        ingest_path(self.conn, p)
        row = self.conn.execute(
            "SELECT exercise_min, exercise_src FROM daily_reviews"
        ).fetchone()
        self.assertEqual(row[0], 0)
        self.assertEqual(row[1], "record")


if __name__ == "__main__":
    unittest.main()
