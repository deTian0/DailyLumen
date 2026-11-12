"""Web 看板 W7：报表增强只读 API（week-done / streaks / day-help）。

锁死：
1. 对拍：``text`` = reports/core 既有 render（与 CLI 同源）。
2. week-done 的 ISO 年显式传入 collect（跨年不取错窗口）。
3. 只读：跑完路由后库文件字节不变；参数非法 422。
"""
import unittest

from review_tool.api import life_queries as lq
from review_tool.api.queries import QueryError
from tests.api.test_life_api import BASE, HAVE_WEB, _DbFixture, _json, _sha

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_life import build_router


class TestW7Parity(_DbFixture):
    def test_week_done(self):
        from review_tool.reports import week_done as m

        r = lq.week_done(self.ro())
        self.assertEqual((r["year"], r["week"]), (2026, 37))
        data = m.collect(self.ro(), iso_week=37, year=2026)
        self.assertEqual(r["text"], m.render(data))
        self.assertEqual(r["data"], _json(data))

    def test_streaks(self):
        from review_tool.reports.streak import render_streaks, summarize_streaks

        r = lq.streaks(self.ro())
        data = summarize_streaks(self.ro())
        self.assertEqual(r["text"], render_streaks(data))
        self.assertEqual(r["data"], _json(data))

    def test_day_help(self):
        from review_tool.core.day_help import infer_training_day_hint, render_day_help

        r = lq.day_help("2026-09-09", "deepseek")
        td = infer_training_day_hint("2026-09-09")
        self.assertEqual(r["training_day"], td)
        self.assertEqual(
            r["text"],
            render_day_help("2026-09-09", "deepseek", training_day=td),
        )

    def test_invalid(self):
        for call in (lambda: lq.day_help("2026-13-01"),
                     lambda: lq.day_help(None, "evil"),
                     lambda: lq.streaks(self.ro(), "bad")):
            with self.assertRaises(QueryError) as cm:
                call()
            self.assertEqual(cm.exception.status, 422)


@unittest.skipUnless(HAVE_WEB, "未安装 web extra")
class TestW7Routes(_DbFixture):
    def setUp(self):
        super().setUp()
        self.client = TestClient(
            create_app(dist_dir=self.dir, extra_routers=[build_router(db_path=self.db)]),
            base_url=BASE,
        )

    def test_routes_ok_and_db_untouched(self):
        before = _sha(self.db)
        for path in ("/api/week-done", "/api/week-done?year=2026&week=37",
                     "/api/streaks", "/api/day-help?date=2026-09-09&mode=workbuddy"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(_sha(self.db), before)

    def test_errors(self):
        r = self.client.get("/api/week-done?year=2025&week=37")
        self.assertEqual(r.status_code, 404)
        r = self.client.get("/api/day-help?mode=evil")
        self.assertEqual(r.json()["error"]["code"], "invalid_mode")


if __name__ == "__main__":
    unittest.main()
