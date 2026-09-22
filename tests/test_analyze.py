"""analyze 模块测试：训练日三态统计、字段完整度、周月报告。"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from review_tool.analyze import (
    _avg,
    completeness,
    derived_count,
    report_month,
    report_week,
    training_stats,
)
from review_tool.db import init_db, upsert


class _DB(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "t.db")
        self.conn = init_db(db_path=self.path)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)


class TestTrainingStats(_DB):
    """核心口径：必须把「未记录」和「未达标」分开。"""

    def _seed(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1, "exercise_min": 40})
        upsert(self.conn, {"date": "2026-09-08", "training_day": 1, "exercise_min": 0})
        upsert(self.conn, {"date": "2026-09-09", "training_day": 1, "exercise_min": None})
        upsert(self.conn, {"date": "2026-09-10", "training_day": 0, "exercise_min": 0})
        self.conn.commit()

    def test_three_states(self):
        self._seed()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["total"], 3)      # 训练日
        self.assertEqual(st["recorded"], 2)   # 有记录
        self.assertEqual(st["done"], 1)       # 真的运动了
        self.assertEqual(st["missing"], 1)    # 未记录

    def test_missing_not_counted_as_done(self):
        self._seed()
        st = training_stats(self.conn, "1=1", ())
        self.assertNotEqual(st["done"], st["total"])

    def test_no_training_day(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 0})
        self.conn.commit()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["total"], 0)
        self.assertEqual(st["missing"], 0)


class TestDerivedExercise(_DB):
    """运动时长来源必须可区分：字段填报 vs 描述折算。

    这是「徒手训练算不算运动时长」的验收点 —— 折算出来的值要真的让
    训练日计入达标，同时又要能被单独标出来，不能混进计时记录。
    """

    def _capture(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*a)
        return buf.getvalue()

    def test_derived_value_makes_training_day_count_as_done(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1,
                           "exercise_min": 10, "exercise_src": "derived"})
        self.conn.commit()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["recorded"], 1)
        self.assertEqual(st["done"], 1)
        self.assertEqual(st["missing"], 0)

    def test_derived_counted_separately_from_recorded(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1,
                           "exercise_min": 30, "exercise_src": "record"})
        upsert(self.conn, {"date": "2026-09-09", "training_day": 1,
                           "exercise_min": 10, "exercise_src": "derived"})
        self.conn.commit()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["recorded"], 2)
        self.assertEqual(st["derived"], 1)
        self.assertEqual(derived_count(self.conn, "1=1", ()), 1)

    def test_no_derived_by_default(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1, "exercise_min": 30})
        self.conn.commit()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["derived"], 0)
        self.assertEqual(derived_count(self.conn, "1=1", ()), 0)

    def test_week_report_labels_derivation(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1,
                           "exercise_min": 10, "exercise_src": "derived"})
        self.conn.commit()
        out = self._capture(report_week, self.conn)
        self.assertIn("描述折算", out)


class TestCompleteness(_DB):
    def test_full_row_is_complete(self):
        row = {c: 1 for c in ("training_day", "sleep_h", "sleep_quality", "bedtime",
                              "exercise_min", "diet_kcal", "phone_h", "deepwork_h",
                              "learn_h", "life_h")}
        row["date"] = "2026-09-07"
        upsert(self.conn, row)
        self.conn.commit()
        rate, missing = completeness(self.conn, "1=1", ())
        self.assertEqual(rate, 1.0)
        self.assertEqual(missing, [])

    def test_missing_sorted_desc(self):
        upsert(self.conn, {"date": "2026-09-07", "sleep_h": 7.0, "phone_h": 5.0})
        self.conn.commit()
        rate, missing = completeness(self.conn, "1=1", ())
        self.assertLess(rate, 1.0)
        counts = [n for _, n in missing]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_empty_scope(self):
        rate, missing = completeness(self.conn, "date='1999-01-01'", ())
        self.assertEqual(rate, 0.0)
        self.assertEqual(missing, [])


class TestAvg(_DB):
    def test_avg_skips_nulls(self):
        upsert(self.conn, {"date": "2026-09-07", "sleep_h": 6.0})
        upsert(self.conn, {"date": "2026-09-08", "sleep_h": 8.0})
        upsert(self.conn, {"date": "2026-09-09", "sleep_h": None})
        self.conn.commit()
        self.assertEqual(_avg(self.conn, "sleep_h"), 7.0)

    def test_rejects_unknown_column(self):
        with self.assertRaises(ValueError):
            _avg(self.conn, "sleep_h; DROP TABLE daily_reviews")


class TestReports(_DB):
    def setUp(self):
        super().setUp()
        for i, day in enumerate(("2026-09-07", "2026-09-08")):
            upsert(self.conn, {
                "date": day, "training_day": 1, "exercise_min": 30 if i else None,
                "sleep_h": 7.0, "phone_h": 9.0, "diet_kcal": 1800,
                "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 1.0,
            })
        self.conn.commit()

    def _capture(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*a)
        return buf.getvalue()

    def test_week_report_mentions_three_states(self):
        out = self._capture(report_week, self.conn)
        self.assertIn("训练日运动", out)
        self.assertIn("未记录", out)
        self.assertIn("数据完整度", out)

    def test_week_report_specific_week(self):
        out = self._capture(report_week, self.conn, 37)
        self.assertIn("ISO 周 37", out)

    def test_week_report_unknown_week(self):
        out = self._capture(report_week, self.conn, 99)
        self.assertIn("无可分析的周数据", out)

    def test_month_report(self):
        out = self._capture(report_month, self.conn, 202609)
        self.assertIn("月份 202609", out)

    def test_month_report_missing(self):
        out = self._capture(report_month, self.conn, 199901)
        self.assertIn("暂无数据", out)

    def test_month_trend_needs_previous(self):
        out = self._capture(report_month, self.conn, 202609)
        self.assertNotIn("系统分趋势", out)  # 无更早月份


class TestTrendRounding(_DB):
    """回归：差值必须取整，否则会打印 -0.010000000000000675 这种浮点尾差。"""

    def _capture(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*a)
        return buf.getvalue()

    def test_delta_is_rounded(self):
        base = {"health_score": 4, "work_score": 5, "learn_score": 5, "life_score": 5}
        upsert(self.conn, {"date": "2026-08-31", "system_score": 4.82, **base})
        upsert(self.conn, {"date": "2026-09-30", "system_score": 4.81, **base})
        self.conn.commit()
        out = self._capture(report_month, self.conn, 202609)
        self.assertIn("系统分趋势", out)
        self.assertIn("-0.01", out)
        self.assertNotIn("0000000", out)


if __name__ == "__main__":
    unittest.main()
