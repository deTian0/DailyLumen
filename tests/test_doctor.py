"""doctor 模块测试：对账、新鲜度、归一化、训练日口径。"""
import os
import shutil
import tempfile
import unittest

from review_tool import doctor
from review_tool.db import SCHEMA_VERSION, init_db, upsert, upsert_personal_track


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.md_dir = os.path.join(self.root, "每日复盘")
        os.makedirs(os.path.join(self.md_dir, "复盘", "2026-09"), exist_ok=True)
        os.makedirs(os.path.join(self.md_dir, "收件箱"), exist_ok=True)
        os.makedirs(os.path.join(self.md_dir, "历史源复盘"), exist_ok=True)
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _md(self, rel):
        p = os.path.join(self.md_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        return p

    def _run(self, **kw):
        return doctor.diagnose(db_path=self.db, input_dir=self.md_dir, **kw)


class TestDiagnoseBasics(_Fixture):
    def test_reports_schema_and_integrity(self):
        r = self._run(today="2026-09-22")
        self.assertEqual(r["schema_version"], SCHEMA_VERSION)
        self.assertEqual(r["schema_expected"], SCHEMA_VERSION)
        self.assertEqual(r["integrity"], "ok")

    def test_empty_db_has_no_latest(self):
        r = self._run(today="2026-09-22")
        self.assertEqual(r["rows"], 0)
        self.assertIsNone(r["latest_date"])
        self.assertIsNone(r["stale_days"])

    def test_freshness(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["stale_days"], 1)


class TestReconciliation(_Fixture):
    def test_detects_not_ingested(self):
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-22")
        self.assertIn("2026-09-21", r["not_ingested"])

    def test_detects_orphan_in_db(self):
        upsert(self.conn, {"date": "2026-09-01"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertIn("2026-09-01", r["orphan_in_db"])

    def test_inbox_and_archive_not_treated_as_standard_source(self):
        """收件箱/历史源复盘里的文件不算「标准源」，不得出现在 not_ingested。"""
        self._md("收件箱/2026-09-05.md")
        self._md("历史源复盘/2026-07-16.md")
        r = self._run(today="2026-09-22")
        self.assertNotIn("2026-09-05", r["not_ingested"])
        self.assertNotIn("2026-07-16", r["not_ingested"])

    def test_archive_only_reported(self):
        self._md("历史源复盘/2026-07-16.md")
        upsert(self.conn, {"date": "2026-07-16"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertIn("2026-07-16", r["archive_only"])
        self.assertNotIn("2026-07-16", r["orphan_in_db"])


class TestTrackNormalization(_Fixture):
    def test_unnormalized_flagged(self):
        upsert_personal_track(self.conn, "2026-09-21", "other:某新补剂", "服药",
                              "other:某新补剂", "某新补剂", 1)
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(r["unnormalized_tracks"])

    def test_normalized_not_flagged(self):
        upsert_personal_track(self.conn, "2026-09-21", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 1)
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["unnormalized_tracks"], [])


class TestTrainingDayDrift(_Fixture):
    def test_detects_drift(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 0})  # 周一应为训练日
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(any(d == "2026-09-21" for d, _ in r["training_day_drift"]))

    def test_detects_missing(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(any(d == "2026-09-21" for d, _ in r["training_day_drift"]))

    def test_consistent_no_drift(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 1})  # 周一=训练日
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["training_day_drift"], [])


class TestExerciseSources(_Fixture):
    """运动时长来源分布：填报 / 描述折算 / 未记录 必须分得开。"""

    def test_counts_by_source(self):
        upsert(self.conn, {"date": "2026-09-07", "exercise_min": 30,
                           "exercise_src": "record"})
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        upsert(self.conn, {"date": "2026-09-09", "exercise_min": None})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["exercise_sources"],
                         {"recorded": 1, "derived": 1, "missing": 1})

    def test_derivation_does_not_break_health(self):
        """折算只是来源差异，不应把体检判成不健康。"""
        self._md("复盘/2026-09/2026-09-08.md")
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(doctor.is_healthy(r))

    def test_render_lists_sources(self):
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        self.conn.commit()
        text = doctor.render(self._run(today="2026-09-22"))
        self.assertIn("[运动时长来源]", text)
        self.assertIn("描述折算 1 天", text)


class TestRender(_Fixture):
    def test_render_runs_and_reports_health(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 1,
                           "sleep_h": 7.0, "sleep_quality": 85, "bedtime": 1400,
                           "exercise_min": 30, "diet_kcal": 1800, "phone_h": 8.0,
                           "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 1.0})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        text = doctor.render(self._run(today="2026-09-22"))
        for token in ("DailyLumen 体检报告", "[数据库]", "[新鲜度]",
                      "[文件 ↔ 数据库对账]", "[数据完整度]", "[打卡归一化]",
                      "[运动时长来源]", "[训练日口径]", "结论:"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
