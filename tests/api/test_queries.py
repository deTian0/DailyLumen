"""Web 与 CLI 同源对拍（PRE-02 / PRE-05 / PRE-06）。

本组测试不碰 fastapi：只验证 ``review_tool/api/queries.py`` 的查询函数
与既有 reports 的 collect()/render() 输出**逐字节一致**，并验证 PRE-06
（跨年 ISO 周歧义）的显式报错行为。``get_readonly_conn`` 要求库文件已存在，
因此每个用例都先用 ``init_db`` 建库写数据、关闭连接，再用只读连接打开。
"""
import os
import shutil
import tempfile
import unittest

from review_tool.api import queries as q
from review_tool.reports.analyze import collect as analyze_collect
from review_tool.reports.analyze import render_month_md, render_week_md, week_highlights
from review_tool.reports.doctor import diagnose, is_healthy
from review_tool.reports.doctor import render as doctor_render
from review_tool.reports.fuse import find_fuses, has_active_fuse
from review_tool.storage.db import get_readonly_conn, init_db, upsert


class _ROFixture(unittest.TestCase):
    """建库 → 写数据 → 关闭 → 以只读连接重开（API 真实路径）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        conn = init_db(db_path=self.db)
        self.seed(conn)
        conn.commit()
        conn.close()
        self.ro = get_readonly_conn(self.db)

    def tearDown(self):
        self.ro.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def seed(self, conn):
        pass


def _row(date, **kw):
    base = {
        "date": date, "training_day": 1, "exercise_min": 30,
        "health_score": 4, "work_score": 4, "learn_score": 4, "life_score": 4,
        "system_score": 4.0, "diet_kcal": 1800, "sleep_h": 7.0,
    }
    base.update(kw)
    return base


class TestWeekReportParity(_ROFixture):
    def seed(self, conn):
        # 2026-09-07 (周一) 所在 ISO 周 = 37
        for d in ("2026-09-07", "2026-09-08", "2026-09-09"):
            upsert(conn, _row(d))

    def test_week_report_matches_cli_markdown_and_summary(self):
        out = q.week_report(self.ro, year=2026, week=37)
        expected_md = render_week_md(self.ro, 37)
        expected_summary = analyze_collect(self.ro, "iso_week=?", (37,), "ISO 周 37")
        expected_summary["highlights"] = week_highlights(self.ro, 37)
        self.assertEqual(out["markdown"], expected_md)
        self.assertEqual(out["summary"], expected_summary)
        self.assertEqual(out["week"], 37)
        self.assertEqual(out["year"], 2026)

    def test_default_week_is_latest_in_db(self):
        out = q.week_report(self.ro)
        self.assertEqual(out["week"], 37)

    def test_unknown_week_is_404(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, year=2026, week=1)
        self.assertEqual(ctx.exception.status, 404)

    def test_year_mismatch_is_404(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, year=2027, week=37)
        self.assertEqual(ctx.exception.status, 404)

    def test_bad_week_number_is_422(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, year=2026, week=99)
        self.assertEqual(ctx.exception.status, 422)

    def test_year_without_week_is_422(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, year=2026, week=None)
        self.assertEqual(ctx.exception.status, 422)


class TestWeekCrossYearAmbiguity(_ROFixture):
    """PRE-06：同一 iso_week 号跨两个不同年份时必须显式报歧义，不能静默挑一个。"""

    def seed(self, conn):
        # 2025-09-08 与 2026-09-07 都落在 ISO 第 37 周，但年份不同。
        upsert(conn, _row("2025-09-08"))
        upsert(conn, _row("2026-09-07"))

    def test_ambiguous_week_is_409(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, year=2026, week=37)
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "ambiguous_week")

    def test_ambiguous_week_without_year_is_also_409(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.week_report(self.ro, week=37)
        self.assertEqual(ctx.exception.status, 409)

    def test_week_iso_years_reports_both(self):
        from review_tool.reports.analyze import week_iso_years
        self.assertEqual(week_iso_years(self.ro, 37), [2025, 2026])


class TestMonthReportParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))
        upsert(conn, _row("2026-09-08"))

    def test_month_report_matches_cli(self):
        out = q.month_report(self.ro, month=202609)
        self.assertEqual(out["markdown"], render_month_md(self.ro, 202609))
        expected_summary = analyze_collect(self.ro, "month=?", (202609,), "月份 202609")
        self.assertEqual(out["summary"], expected_summary)

    def test_default_month_is_latest(self):
        out = q.month_report(self.ro)
        self.assertEqual(out["month"], 202609)

    def test_unknown_month_is_404(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.month_report(self.ro, month=202601)
        self.assertEqual(ctx.exception.status, 404)

    def test_bad_month_format_is_422(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.month_report(self.ro, month=13)
        self.assertEqual(ctx.exception.status, 422)


class TestAiContextParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))

    def test_matches_build_context_and_render_markdown(self):
        from review_tool.reports.ai_review import build_context, render_markdown

        out = q.ai_context(self.ro, "2026-09-07")
        expected_ctx = build_context("2026-09-07", conn=self.ro)
        self.assertEqual(out["context"], expected_ctx)
        self.assertEqual(out["markdown"], render_markdown(expected_ctx))

    def test_default_date_is_latest(self):
        out = q.ai_context(self.ro)
        self.assertEqual(out["date"], "2026-09-07")

    def test_bad_date_is_422(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.ai_context(self.ro, "2026-13-01")
        self.assertEqual(ctx.exception.status, 422)


class TestDoctorParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))

    def test_matches_diagnose_and_render(self):
        out = q.doctor(self.ro, today="2026-09-08")
        expected = diagnose(today="2026-09-08", conn=self.ro)
        self.assertEqual(out["result"], expected)
        self.assertEqual(out["healthy"], is_healthy(expected))
        self.assertEqual(out["text"], doctor_render(expected, encoding="utf-8"))

    def test_readonly_conn_never_mutates_db(self):
        """只读连接跑 doctor 不应改变库里任何一行（query_only 兜底 + 行为断言）。"""
        before = self.ro.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
        q.doctor(self.ro, today="2026-09-08")
        after = self.ro.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
        self.assertEqual(before, after)


class TestStatsParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))

    def test_matches_stats_collect(self):
        from review_tool.reports.stats import collect as stats_collect

        with tempfile.TemporaryDirectory() as md_root:
            out = q.stats(self.ro, input_dir=md_root, db_path=self.db)
            expected = stats_collect(self.ro, md_root, db_path=self.db)
        # generated_at 是当日日期，两次调用之间可能跨日的概率极低，直接比较即可；
        # 若偶发失败再忽略该字段比较。
        out.pop("generated_at", None)
        expected.pop("generated_at", None)
        self.assertEqual(out, expected)


class TestFuseParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))

    def test_matches_find_fuses(self):
        out = q.fuse(self.ro)
        expected = find_fuses(self.ro)
        self.assertEqual(out["result"], expected)
        self.assertEqual(out["active"], has_active_fuse(expected))


class TestChartParity(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))

    def test_each_kind_matches_builder(self):
        from review_tool.reports import chart

        builders = {
            "trends": chart.build_chart,
            "body": chart.build_body_chart,
            "training": chart.build_training_chart,
            "nutrition": chart.build_nutrition_chart,
        }
        for kind, fn in builders.items():
            with self.subTest(kind=kind):
                self.assertEqual(q.chart_svg(self.ro, kind), fn(self.ro))

    def test_unknown_kind_is_404(self):
        with self.assertRaises(q.QueryError) as ctx:
            q.chart_svg(self.ro, "unknown")
        self.assertEqual(ctx.exception.status, 404)


class TestAvailableWeeksMonths(_ROFixture):
    def seed(self, conn):
        upsert(conn, _row("2026-09-07"))
        upsert(conn, _row("2026-10-05"))

    def test_available_months_desc(self):
        self.assertEqual(q.available_months(self.ro), [202610, 202609])

    def test_available_weeks_desc(self):
        weeks = q.available_weeks(self.ro)
        self.assertEqual(weeks[0]["year"], 2026)
        self.assertGreaterEqual(len(weeks), 2)


class TestReadonlyMissingDb(unittest.TestCase):
    def test_missing_db_raises_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "no_such.db")
            with self.assertRaises(q.QueryError) as ctx:
                with q.readonly(missing) as conn:
                    conn.execute("SELECT 1")
            self.assertEqual(ctx.exception.status, 503)
            self.assertEqual(ctx.exception.code, "db_missing")


if __name__ == "__main__":
    unittest.main()
