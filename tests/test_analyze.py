"""analyze 模块测试：训练日三态统计、字段完整度、周月报告。"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from review_tool.reports.analyze import (
    _avg,
    collect,
    completeness,
    derived_count,
    report_month,
    report_week,
    track_adherence,
    training_stats,
)
from review_tool.storage.db import init_db, upsert, upsert_personal_track


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

    def test_zero_src_counted_separately(self):
        """src=zero 是口径兜底，与折算/填报互不混淆。"""
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1,
                           "exercise_min": 0, "exercise_src": "zero"})
        self.conn.commit()
        st = training_stats(self.conn, "1=1", ())
        self.assertEqual(st["zero"], 1)
        self.assertEqual(st["derived"], 0)
        self.assertEqual(st["done"], 0)

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
                "date": day, "training_day": 1,
                "exercise_min": 30 if i else 0,
                "exercise_src": None if i else "zero",
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


class TestJsonOutput(_DB):
    """`--json`：结构化输出与文本报告共用 `collect()`，口径不可能分歧。"""

    def setUp(self):
        super().setUp()
        for i, day in enumerate(("2026-09-07", "2026-09-08")):
            upsert(self.conn, {
                "date": day, "training_day": 1,
                "exercise_min": 30 if i else 0,
                "exercise_src": None if i else "zero",
                "sleep_h": 7.0, "sleep_quality": 80, "bedtime": 1400,
                "phone_h": 9.0, "diet_kcal": 1800, "carbs_g": 200,
                "fat_g": 50, "protein_g": 80,
                "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 1.0,
            })
        self.conn.commit()

    def _capture(self, fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = fn(*a, **kw)
        return ret, buf.getvalue()

    def test_month_json_is_parseable(self):
        import json
        s, out = self._capture(report_month, self.conn, 202609, as_json=True)
        data = json.loads(out)
        self.assertEqual(data["days"], 2)
        self.assertEqual(data["title"], "月份 202609")
        self.assertEqual(data["training"]["total"], 2)
        self.assertEqual(data["training"]["done"], 1)
        self.assertIn("健康", data["dims"])
        self.assertEqual(data["completeness"]["rate_pct"], 100)
        self.assertIsNotNone(s)

    def test_month_json_has_macros_and_worst(self):
        s, _out = self._capture(report_month, self.conn, 202609, as_json=True)
        self.assertEqual(s["macros"]["carbs_g"], 200)
        self.assertEqual(s["macros"]["kcal"], 4 * 200 + 9 * 50 + 4 * 80)
        self.assertIn("name", s["worst_dim"])

    def test_week_json_is_list(self):
        import json
        _s, out = self._capture(report_week, self.conn, 37, as_json=True)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "ISO 周 37")

    def test_month_json_missing_stays_quiet(self):
        """无数据时 JSON 模式不应往 stdout 混入散文。"""
        _s, out = self._capture(report_month, self.conn, 199901, as_json=True)
        self.assertEqual(out, "")

    def test_text_and_json_agree_on_days(self):
        s, out = self._capture(report_month, self.conn, 202609)
        self.assertIsNone(s)                      # 文本模式不返回
        self.assertIn("共 2 天", out)


class TestTrackAdherence(_DB):
    """个人打卡依从率进 week/month（v1.7.2）。"""

    def _seed_tracks(self):
        # 2026-09-07 / 09-08 同属 ISO 周 37；09-14 属周 38（用于周趋势）
        for d in ("2026-09-07", "2026-09-08", "2026-09-14"):
            upsert(self.conn, {"date": d, "month": 202609})
        # coq10: 2/2 done in W37 dates; 0/1 on 09-14
        upsert_personal_track(self.conn, "2026-09-07", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 1)
        upsert_personal_track(self.conn, "2026-09-08", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 1)
        upsert_personal_track(self.conn, "2026-09-14", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 0)
        # skincare: 1/2 in W37
        upsert_personal_track(self.conn, "2026-09-07", "skincare", "护肤",
                              "skincare", "护肤", 1)
        upsert_personal_track(self.conn, "2026-09-08", "skincare", "护肤",
                              "skincare", "护肤", 0)
        self.conn.commit()

    def test_rates_and_category_groups(self):
        self._seed_tracks()
        adh = track_adherence(self.conn, "iso_week=?", (37,))
        by_key = {it["item_key"]: it for it in adh["items"]}
        self.assertEqual(by_key["coq10"]["done"], 2)
        self.assertEqual(by_key["coq10"]["recorded"], 2)
        self.assertEqual(by_key["coq10"]["adherence"], 1.0)
        self.assertEqual(by_key["skincare"]["done"], 1)
        self.assertEqual(by_key["skincare"]["recorded"], 2)
        self.assertEqual(by_key["skincare"]["adherence"], 0.5)
        cats = {c["category"]: c for c in adh["categories"]}
        self.assertEqual(cats["服药"]["done"], 2)
        self.assertEqual(cats["服药"]["recorded"], 2)
        self.assertEqual(cats["护肤"]["adherence"], 0.5)

    def test_week_report_section(self):
        self._seed_tracks()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report_week(self.conn, 37)
        out = buf.getvalue()
        self.assertIn("个人打卡依从率", out)
        self.assertIn("coq10", out)
        self.assertIn("不计入四维评分", out)

    def test_month_collect_has_week_trend(self):
        self._seed_tracks()
        s = collect(self.conn, "month=?", (202609,), "月份 202609")
        self.assertIsNotNone(s)
        weeks = s["track_adherence"]["by_week"]
        self.assertGreaterEqual(len(weeks), 2)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report_month(self.conn, 202609)
        self.assertIn("周趋势", buf.getvalue())

    def test_empty_tracks_section(self):
        upsert(self.conn, {"date": "2026-09-07"})
        self.conn.commit()
        adh = track_adherence(self.conn, "iso_week=?", (37,))
        self.assertEqual(adh["items"], [])
        s = collect(self.conn, "iso_week=?", (37,), "ISO 周 37")
        text = __import__("review_tool.reports.analyze", fromlist=["render_summary"]).render_summary(s)
        self.assertIn("无 personal_tracks 记录", text)


class TestWriteMd(_DB):
    """week/month --write 落盘（v1.8.0）；只碰临时目录。"""

    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.dir, "复盘")
        os.makedirs(self.out, exist_ok=True)
        for d in ("2026-09-14", "2026-09-15"):
            upsert(self.conn, {
                "date": d, "training_day": 1, "health_score": 5,
                "work_score": 5, "learn_score": 3, "life_score": 3,
                "system_score": 4.0, "sleep_h": 7.0, "phone_h": 10.0,
                "deepwork_h": 3.0, "diet_kcal": 1800, "bedtime": 30,
            })
        self.conn.commit()

    def test_write_week_to_temp(self):
        from review_tool.reports.analyze import render_week_md, write_week_md
        text = render_week_md(self.conn, 38)
        self.assertIsNotNone(text)
        self.assertIn("周总结 · ISO 第 38 周", text)
        self.assertIn("## 一、四维总览", text)
        self.assertIn("## 二、每日明细", text)
        path, status = write_week_md(self.conn, 38, root=self.out)
        self.assertEqual(status, "written")
        self.assertTrue(os.path.isfile(path))
        self.assertIn("周总结-W38-", os.path.basename(path))
        with open(path, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("四维总览", body)
        # 幂等：不 --force 则跳过
        path2, status2 = write_week_md(self.conn, 38, root=self.out)
        self.assertEqual(status2, "skipped")
        # --force 覆盖
        _, status3 = write_week_md(self.conn, 38, root=self.out, force=True)
        self.assertEqual(status3, "written")
        # --check 一致
        _, status4 = write_week_md(self.conn, 38, root=self.out, check_only=True)
        self.assertEqual(status4, "ok")

    def test_write_month_to_temp(self):
        from review_tool.reports.analyze import render_month_md, write_month_md
        text = render_month_md(self.conn, 202609)
        self.assertIsNotNone(text)
        self.assertIn("月总结 · 2026 年 9 月", text)
        path, status = write_month_md(self.conn, 202609, root=self.out)
        self.assertEqual(status, "written")
        self.assertTrue(path.endswith("月总结-202609.md"))
        with open(path, encoding="utf-8") as f:
            self.assertIn("月度核心数字", f.read())


if __name__ == "__main__":
    unittest.main()
