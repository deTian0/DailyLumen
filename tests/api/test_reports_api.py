"""Web 看板 W4：报告与分析路由（周/月/ai-context/stats/doctor/fuse/chart）。

锁死：
1. 路由输出 = ``api.queries`` 同名函数输出（W2 已与 CLI collect/render 对拍）→ 传递得到 Web = CLI。
2. 下载（FR-F4）内容 = 页面 markdown，且带 ``Content-Disposition``。
3. 错误码：无数据 404 / 跨年周歧义 409 / 参数不合法 422 / 库缺失 503，均为统一错误体。
4. 只读：跑完全部只读路由后库文件字节不变。
"""
import hashlib
import os
import shutil
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_reports import build_router
    HAVE_WEB = True
except ImportError:
    HAVE_WEB = False

from review_tool.api import queries as q
from review_tool.storage.db import get_readonly_conn, init_db, upsert

BASE = "http://127.0.0.1:8765"


def _row(date, **kw):
    base = {
        "date": date, "training_day": 1, "exercise_min": 30,
        "health_score": 4, "work_score": 4, "learn_score": 4, "life_score": 4,
        "system_score": 4.0, "diet_kcal": 1800, "sleep_h": 7.0,
    }
    base.update(kw)
    return base


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class _Fixture(unittest.TestCase):
    DATES = ("2026-09-07", "2026-09-08", "2026-09-09")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t.db")
        self.md_root = os.path.join(self.dir, "md")
        os.makedirs(self.md_root)
        conn = init_db(db_path=self.db)
        for d in self.DATES:
            upsert(conn, _row(d))
        conn.commit()
        conn.close()
        router = build_router(db_path=self.db, input_dir=self.md_root)
        self.client = TestClient(
            create_app(dist_dir=self.dir, extra_routers=[router]), base_url=BASE,
        )

    def ro(self):
        conn = get_readonly_conn(self.db)
        self.addCleanup(conn.close)
        return conn


class TestWeekRoutes(_Fixture):
    def test_week_matches_queries(self):
        r = self.client.get("/api/reports/week", params={"year": 2026, "week": 37})
        self.assertEqual(r.status_code, 200)
        expected = q.week_report(self.ro(), 2026, 37)
        data = r.json()
        self.assertEqual(data["markdown"], expected["markdown"])
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["week"], 37)
        self.assertEqual(data["filename"], expected["filename"])
        self.assertEqual(data["summary"]["days"], expected["summary"]["days"])
        self.assertEqual(data["summary"]["system_avg"], expected["summary"]["system_avg"])

    def test_default_week_is_latest(self):
        r = self.client.get("/api/reports/week")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["year"], r.json()["week"]), (2026, 37))

    def test_week_md_download_equals_page(self):
        page = self.client.get("/api/reports/week", params={"week": 37}).json()["markdown"]
        r = self.client.get("/api/reports/week.md", params={"week": 37})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, page)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertTrue(r.headers["content-type"].startswith("text/markdown"))

    def test_weeks_list(self):
        r = self.client.get("/api/reports/weeks")
        self.assertEqual(r.json(), [{"year": 2026, "week": 37}])

    def test_unknown_week_404(self):
        r = self.client.get("/api/reports/week", params={"week": 10})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "no_data")

    def test_bad_week_422(self):
        r = self.client.get("/api/reports/week", params={"week": 60})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_week")

    def test_non_int_week_422_without_echo(self):
        r = self.client.get("/api/reports/week", params={"week": "abc<script>"})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn("<script>", r.text)


class TestCrossYearRoute(_Fixture):
    DATES = ("2025-09-08", "2026-09-07")

    def test_ambiguous_week_409(self):
        r = self.client.get("/api/reports/week", params={"year": 2026, "week": 37})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"]["code"], "ambiguous_week")

    def test_weeks_list_shows_both_years(self):
        r = self.client.get("/api/reports/weeks")
        self.assertEqual(r.json(), [{"year": 2026, "week": 37}, {"year": 2025, "week": 37}])


class TestMonthRoutes(_Fixture):
    def test_month_matches_queries(self):
        r = self.client.get("/api/reports/month", params={"month": 202609})
        self.assertEqual(r.status_code, 200)
        expected = q.month_report(self.ro(), 202609)
        self.assertEqual(r.json()["markdown"], expected["markdown"])
        self.assertEqual(r.json()["filename"], "月总结-202609.md")

    def test_default_month(self):
        self.assertEqual(self.client.get("/api/reports/month").json()["month"], 202609)

    def test_months_list(self):
        self.assertEqual(self.client.get("/api/reports/months").json(), [202609])

    def test_month_md_download(self):
        page = self.client.get("/api/reports/month").json()["markdown"]
        r = self.client.get("/api/reports/month.md")
        self.assertEqual(r.text, page)

    def test_bad_month_422(self):
        r = self.client.get("/api/reports/month", params={"month": 202613})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_month")


class TestAiContextRoute(_Fixture):
    def test_matches_queries(self):
        r = self.client.get("/api/reports/ai-context", params={"date": "2026-09-08"})
        self.assertEqual(r.status_code, 200)
        expected = q.ai_context(self.ro(), "2026-09-08")
        self.assertEqual(r.json()["markdown"], expected["markdown"])
        self.assertEqual(r.json()["date"], "2026-09-08")

    def test_bad_date_422(self):
        r = self.client.get("/api/reports/ai-context", params={"date": "2026-13-40"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_date")


class TestAnalysisRoutes(_Fixture):
    def test_stats(self):
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["days"], 3)
        self.assertEqual(r.json()["latest_date"], "2026-09-09")

    def test_doctor_matches_is_healthy(self):
        r = self.client.get("/api/doctor")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data["healthy"], bool)
        self.assertEqual(data["result"]["rows"], 3)
        self.assertIn("day_ready", data["result"])

    def test_fuse(self):
        r = self.client.get("/api/fuse")
        self.assertEqual(r.status_code, 200)
        expected = q.fuse(self.ro())
        self.assertEqual(r.json()["active"], expected["active"])
        self.assertEqual(r.json()["text"], expected["text"])

    def test_charts(self):
        for kind in q.CHART_KINDS:
            r = self.client.get(f"/api/charts/{kind}")
            self.assertEqual(r.status_code, 200, kind)
            self.assertTrue(r.headers["content-type"].startswith("image/svg+xml"))
            self.assertEqual(r.text, q.chart_svg(self.ro(), kind))

    def test_unknown_chart_404(self):
        r = self.client.get("/api/charts/pie")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "unknown_chart")

    def test_chart_json_matches_series_source(self):
        """W16：/api/charts/{kind}.json 与 SVG 同源（复用 fetch_*_series）。"""
        for kind in q.CHART_KINDS:
            r = self.client.get(f"/api/charts/{kind}.json")
            self.assertEqual(r.status_code, 200, kind)
            self.assertEqual(r.headers["content-type"], "application/json")
            body = r.json()
            self.assertEqual(body["kind"], kind)
            self.assertIn("dates", body)
            self.assertIn("series", body)
            self.assertEqual(body, q.chart_series(self.ro(), kind))
            # 序列值数 = 日期数
            for s in body["series"]:
                self.assertEqual(len(s["values"]), len(body["dates"]), (kind, s["key"]))

    def test_chart_json_trends_values_match_svg_series(self):
        """对拍：trends JSON 的每个序列值 = SVG fetch_series 的对应列（R1 单源）。"""
        from review_tool.reports import chart

        cols = [m[0] for m in chart.DEFAULT_SERIES]
        dates, series = chart.fetch_series(self.ro(), cols)
        body = self.client.get("/api/charts/trends.json").json()
        self.assertEqual(body["dates"], dates)
        for (col, label, color, unit) in chart.DEFAULT_SERIES:
            got = next(s for s in body["series"] if s["key"] == col)
            self.assertEqual(got["values"], series[col])
            self.assertEqual(got["name"], label)
            self.assertEqual(got["color"], color)
            self.assertEqual(got["unit"], unit)

    def test_chart_json_body_includes_ma7_and_target(self):
        """body JSON 含 7 日均（复用 moving_average）与目标带（BODY_TARGETS）。"""
        from review_tool.config import BODY_TARGETS
        from review_tool.core.body import moving_average
        from review_tool.reports import chart

        dates, weights = chart.fetch_body_series(self.ro())
        body = self.client.get("/api/charts/body.json").json()
        self.assertEqual(body["dates"], dates)
        self.assertEqual(body["series"][0]["values"], weights)
        self.assertEqual(body["series"][1]["values"], moving_average(weights, window=7))
        self.assertTrue(body["series"][1].get("dash"))
        low = BODY_TARGETS.get("weight_kg_low")
        high = BODY_TARGETS.get("weight_kg_high")
        if low is not None and high is not None:
            self.assertEqual(body["target"], {"low": float(low), "high": float(high)})
        else:
            self.assertIsNone(body["target"])

    def test_chart_json_nutrition_dual_axis(self):
        body = self.client.get("/api/charts/nutrition.json").json()
        self.assertEqual(len(body["series"]), 2)
        self.assertEqual(body["series"][0]["yAxisIndex"], 0)
        self.assertEqual(body["series"][1]["yAxisIndex"], 1)

    def test_chart_json_unknown_404(self):
        r = self.client.get("/api/charts/pie.json")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "unknown_chart")

    def test_chart_json_route_not_shadowed_by_svg_route(self):
        """`.json` 路由须排在 `{kind}` 之前，否则会被吞成 kind='trends.json'。"""
        r = self.client.get("/api/charts/trends.json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["kind"], "trends")

    def test_readonly_routes_never_touch_db(self):
        before = _sha(self.db)
        for path in ("/api/reports/week", "/api/reports/month", "/api/reports/ai-context",
                     "/api/stats", "/api/doctor", "/api/fuse", "/api/charts/trends",
                     "/api/charts/trends.json", "/api/reports/weeks", "/api/reports/months"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(_sha(self.db), before)


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestMissingDb(unittest.TestCase):
    def test_all_routes_503_when_db_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "nope.db")
            router = build_router(db_path=missing, input_dir=tmp)
            client = TestClient(create_app(dist_dir=tmp, extra_routers=[router]), base_url=BASE)
            for path in ("/api/reports/week", "/api/doctor", "/api/stats", "/api/charts/trends"):
                r = client.get(path)
                self.assertEqual(r.status_code, 503, path)
                self.assertEqual(r.json()["error"]["code"], "db_missing")
            self.assertFalse(os.path.exists(missing), "只读路径不得顺手建库")


if __name__ == "__main__":
    unittest.main()
