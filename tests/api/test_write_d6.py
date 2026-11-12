"""Web 看板 D6：daily_pull（夜间采集拉齐薄封装）。

锁死：
1. plan 零副作用（不调 keepstrong/habits/ingest main）。
2. confirm 调 pipeline.daily_pull.run_steps；失败继续 + 结构化 failures。
3. 动作名 daily_pull；不含代勾 / finalize；注册表可见。
4. 路由 POST /api/write/daily-pull/plan。
"""
from __future__ import annotations

import unittest
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.writes.base import TokenStore, registered_actions
from tests.api.test_life_api import BASE, HAVE_WEB

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

DAY = "2026-11-12"


class TestDailyPullWrite(unittest.TestCase):
    def setUp(self):
        self.tokens = TokenStore()

    def test_registered(self):
        self.assertIn("daily_pull", registered_actions())

    def test_plan_lists_steps_without_side_effects(self):
        with mock.patch("review_tool.pipeline.daily_pull.keepstrong_main") as ks, \
             mock.patch("review_tool.pipeline.daily_pull.sync_main") as hs, \
             mock.patch("review_tool.pipeline.daily_pull.ingest_main") as ig:
            out = wo.plan_daily_pull(self.tokens, DAY)
        self.assertEqual(out["action"], "daily_pull")
        self.assertEqual(out["preview"]["date"], DAY)
        self.assertEqual(out["preview"]["step_count"], 3)
        names = [s["name"] for s in out["preview"]["steps"]]
        self.assertEqual(len(names), 3)
        self.assertIn("练练", names[0])
        self.assertIn("习惯", names[1])
        self.assertIn("入库", names[2])
        self.assertIn("daily-pull", out["cli"])
        self.assertIn("--apply", out["cli"])
        self.assertIn("clickup_habit_auto", out["preview"]["does_not"])
        for fn in (ks, hs, ig):
            fn.assert_not_called()

    def test_confirm_runs_steps_and_reports_partial_failure(self):
        plan = wo.plan_daily_pull(self.tokens, DAY)

        def ks(_argv):
            return 1

        def hs(_argv):
            return 0

        def ig(_argv):
            return 0

        with mock.patch("review_tool.pipeline.daily_pull.keepstrong_main", ks), \
             mock.patch("review_tool.pipeline.daily_pull.sync_main", hs), \
             mock.patch("review_tool.pipeline.daily_pull.ingest_main", ig):
            got = wo.confirm(self.tokens, plan["token"])
        self.assertEqual(got["action"], "daily_pull")
        r = got["result"]
        self.assertFalse(r["ok"])
        self.assertEqual(r["failed"], 1)
        self.assertEqual(len(r["steps"]), 3)
        self.assertEqual(r["steps"][0]["rc"], 1)
        self.assertTrue(r["steps"][1]["ok"])
        self.assertTrue(r["steps"][2]["ok"])


@unittest.skipUnless(HAVE_WEB, "未安装 web extra")
class TestDailyPullRoute(unittest.TestCase):
    def test_plan_route(self):
        key = "d6-test-key"
        client = TestClient(
            create_app(
                dist_dir=".",
                write_enabled=True,
                web_key=key,
                extra_routers=[build_router(tokens=TokenStore())],
            ),
            base_url=BASE,
        )
        r = client.post(
            "/api/write/daily-pull/plan",
            json={"date": DAY},
            headers={"X-DailyLumen-Key": key},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["action"], "daily_pull")
        self.assertEqual(body["preview"]["step_count"], 3)


if __name__ == "__main__":
    unittest.main()
