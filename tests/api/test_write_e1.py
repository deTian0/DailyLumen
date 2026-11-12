"""Web 看板 E1 / FR-K3：候选草稿（promise / three-things / improve）落收件箱。

锁死：
1. plan 内存渲染零写盘（不碰收件箱、不打网写）。
2. confirm 把预览冻结的文本写入收件箱（临时目录）+ 写后回读；不入库。
3. 已存在同名草稿 → plan 预览标记 blocked；confirm 422 draft_exists（不覆盖）。
4. ClickUp 错误映射（401/403→upstream_auth、429→rate_limited、URLError→504）；
   improve 无库 → 503 db_missing。
5. 注册表可见三个动作；路由 plan 200。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.writes.base import TokenStore, registered_actions
from tests.api.test_life_api import BASE, HAVE_WEB

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

DAY = "2026-11-13"


def _task(tid: str, name: str, **kw) -> dict:
    return {"id": tid, "name": name, **kw}


def _group(name: str, **kw) -> dict:
    base = {"id": f"L-{name}", "name": name, "role": "",
            "done": [], "open": [], "in_progress": [], "overdue": [],
            "cross_day": []}
    base.update(kw)
    return base


class DraftsCase(unittest.TestCase):
    def setUp(self):
        self.tokens = TokenStore()
        self.inbox = tempfile.mkdtemp()
        patcher = mock.patch("review_tool.config.INBOX_DIR", self.inbox)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.inbox, ignore_errors=True)


class TestDraftWrites(DraftsCase):
    def test_registered(self):
        for a in ("promise_draft", "three_things_draft", "improve_draft"):
            self.assertIn(a, registered_actions())

    def test_promise_plan_memory_only(self):
        groups = [_group("工作", overdue=[_task("1", "看课 1.5h")])]
        with mock.patch("review_tool.api.writes.drafts._load_creds",
                        return_value=("pk_x", None)), \
             mock.patch("review_tool.pipeline.clickup.collect",
                        return_value=groups):
            out = wo.plan_promise_draft(self.tokens, DAY)
        self.assertEqual(out["action"], "promise_draft")
        self.assertEqual(out["preview"]["writes"], "inbox_md")
        self.assertEqual(out["preview"]["count"], 1)
        self.assertEqual(out["preview"]["candidates"][0]["name"], "看课 1.5h")
        self.assertFalse(out["preview"]["exists"])
        self.assertEqual(os.listdir(self.inbox), [])  # plan 零写盘

    def test_three_things_plan_sorted_candidates(self):
        groups = [_group("工作", done=[_task("9", "写周报 2 小时", date_closed="1730000000000"),
                                      _task("8", "整理房间", date_closed="1730000001000")])]
        with mock.patch("review_tool.api.writes.drafts._load_creds",
                        return_value=("pk_x", None)), \
             mock.patch("review_tool.pipeline.clickup.collect",
                        return_value=groups):
            out = wo.plan_three_things_draft(self.tokens, DAY)
        names = [c["name"] for c in out["preview"]["candidates"]]
        self.assertEqual(names, ["写周报 2 小时", "整理房间"])  # 有产出启发式优先
        self.assertEqual(os.listdir(self.inbox), [])

    def test_confirm_writes_inbox_and_reads_back(self):
        groups = [_group("工作", done=[_task("1", "A", date_closed=None)])]
        with mock.patch("review_tool.api.writes.drafts._load_creds",
                        return_value=("pk_x", None)), \
             mock.patch("review_tool.pipeline.clickup.collect",
                        return_value=groups):
            plan = wo.plan_three_things_draft(self.tokens, DAY)
        got = wo.confirm(self.tokens, plan["token"])
        self.assertEqual(got["action"], "three_things_draft")
        r = got["result"]
        self.assertFalse(r["db_changed"])
        path = os.path.join(self.inbox, f"三件事候选-{DAY}.md")
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as f:
            self.assertIn("- [ ] A（工作", f.read())

    def test_existing_draft_blocked(self):
        path = os.path.join(self.inbox, f"明日候选-{DAY}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("旧草稿")
        groups = [_group("工作", overdue=[_task("1", "A")])]
        with mock.patch("review_tool.api.writes.drafts._load_creds",
                        return_value=("pk_x", None)), \
             mock.patch("review_tool.pipeline.clickup.collect",
                        return_value=groups):
            plan = wo.plan_promise_draft(self.tokens, DAY)
        self.assertTrue(plan["preview"]["exists"])
        self.assertEqual(plan["preview"]["blocked_reason"], "draft_exists")
        with self.assertRaises(Exception) as cm:
            wo.confirm(self.tokens, plan["token"])
        self.assertEqual(getattr(cm.exception, "code", ""), "draft_exists")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "旧草稿")  # 未被覆盖

    def test_clickup_error_mapping(self):
        import urllib.error as ue

        cases = [
            (ue.HTTPError(DAY, 401, "unauth", None, None), 502, "upstream_auth"),
            (ue.HTTPError(DAY, 429, "rate", None, None), 429, "rate_limited"),
            (ue.URLError("down"), 504, "upstream_unreachable"),
        ]
        for exc, status, code in cases:
            with mock.patch("review_tool.api.writes.drafts._load_creds",
                            return_value=("pk_x", None)), \
                 mock.patch("review_tool.pipeline.clickup.collect", side_effect=exc):
                with self.assertRaises(Exception) as cm:
                    wo.plan_promise_draft(self.tokens, DAY)
            e = cm.exception
            self.assertEqual(e.status, status, code)
            self.assertEqual(e.code, code)

    def test_improve_plan_with_conn(self):
        ctx = {"date": DAY, "day": None, "recent": [], "concerns": []}
        with mock.patch("review_tool.reports.ai_review.build_context",
                        return_value=ctx), \
             mock.patch("review_tool.reports.ai_review.render_markdown",
                        return_value="# ctx"):
            out = wo.plan_improve_draft(self.tokens, DAY, conn=object())
        self.assertEqual(out["action"], "improve_draft")
        self.assertIn("改进点候选", out["preview"]["file"])
        self.assertEqual(os.listdir(self.inbox), [])


@unittest.skipUnless(HAVE_WEB, "未安装 web extra")
class TestDraftsRoute(unittest.TestCase):
    def test_plan_routes(self):
        key = "e1-test-key"
        env = {"CLICKUP_API_KEY": "pk_route_test"}  # 假凭据：绝无真网可能
        with mock.patch("review_tool.pipeline.clickup.fetch_tasks",
                        side_effect=urllib.error.URLError("down")), \
             mock.patch("review_tool.config.DB_PATH", "no-such-dir/nope.db"):
            client = TestClient(
                create_app(
                    dist_dir=".",
                    write_enabled=True,
                    web_key=key,
                    extra_routers=[build_router(tokens=TokenStore(), env=env,
                                                db_path="no-such-dir/nope.db")],
                ),
                base_url=BASE,
            )
            for action in ("promise-draft", "three-things-draft"):
                r = client.post(
                    f"/api/write/{action}/plan",
                    json={"date": DAY},
                    headers={"X-DailyLumen-Key": key},
                )
                self.assertEqual(r.status_code, 504, action)  # URLError → upstream_unreachable
                self.assertEqual(r.json()["error"]["code"], "upstream_unreachable")
            r = client.post("/api/write/improve-draft/plan", json={"date": DAY},
                            headers={"X-DailyLumen-Key": key})
            self.assertEqual(r.status_code, 503)  # 无库 → db_missing
            self.assertEqual(r.json()["error"]["code"], "db_missing")


if __name__ == "__main__":
    unittest.main()
