"""Web 看板 W9：P2 写操作第一批（habits sync / AI 草稿写入 / 定稿）。

锁死：
1. 默认只读：``default_routers()`` 不挂 ``/api/write/*``（404）；``write_enabled=True`` 才挂。
2. 两段式：plan 不写任何东西（库 / md 字节不变）；confirm 用一次性 token，重放 409。
3. 跨站 Origin 的写请求 403（app 守卫）。
4. habits sync：只写 habit_logs、不碰 personal_tracks（R3）；写前整库备份、写后回读。
5. AI 草稿：写入七-A + 待人审标记；预览后 md 被改 → 409 stale_plan（不覆盖手改）。
6. 定稿：plan 给并排预览；confirm 后 pending 清除，响应给 ingest 下一步（先 md 再 ingest）。
"""
import datetime
import os
import sqlite3
import unittest
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from tests.api.test_ai_api import DAY, REPLY, _AiFixture, _client
from tests.api.test_life_api import BASE, HAVE_WEB, _sha

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routers import default_routers
    from review_tool.api.routes_write import build_router

ENV = {"CLICKUP_API_KEY": "pk_test_only"}
_CST = datetime.timezone(datetime.timedelta(hours=8))


def _ms(day, hh):
    d = datetime.datetime.fromisoformat(f"{day}T{hh:02d}:00:00").replace(tzinfo=_CST)
    return str(int(d.timestamp() * 1000))


def _fetch(calls):
    tasks = [{"id": "h1", "name": "每日阅读 30 分钟", "date_closed": _ms(DAY, 20),
              "status": {"status": "complete", "type": "closed"}}]

    def fetch(path, key, **kw):
        calls.append(path)
        return {"tasks": tasks if "page=0" in path else []}

    return fetch


class _WriteFixture(_AiFixture):
    def setUp(self):
        super().setUp()
        self.bak = os.path.join(self.dir, "bak")
        for target, value in (
            ("review_tool.config.INTEGRATIONS", {"clickup": True, "keepstrong": False, "deepseek": True}),
            ("review_tool.pipeline.clickup.CLICKUP_MCP_PATH", os.path.join(self.dir, "no-mcp.json")),
            ("review_tool.reports.llm_review.review_md_path", lambda _d: self.md),
        ):
            p = mock.patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.tokens = wo.TokenStore()

    def _rows(self, table):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            c.close()


class TestTokenStore(unittest.TestCase):
    def test_single_use_and_expiry(self):
        now = [0.0]
        st = wo.TokenStore(ttl_s=10, clock=lambda: now[0])
        t = st.issue("x", {"date": DAY})
        self.assertEqual(st.take(t)["action"], "x")
        with self.assertRaises(QueryError) as cm:
            st.take(t)
        self.assertEqual(cm.exception.code, "token_invalid")
        t2 = st.issue("x", {})
        now[0] = 11
        with self.assertRaises(QueryError) as cm:
            st.take(t2)
        self.assertEqual(cm.exception.code, "token_expired")


class TestHabitsSync(_WriteFixture):
    def test_plan_then_confirm(self):
        calls = []
        db0 = _sha(self.db)
        plan = wo.plan_habits_sync(self.tokens, DAY, fetch=_fetch(calls), env=ENV)
        self.assertEqual(_sha(self.db), db0, "plan 不得写库")
        self.assertEqual(plan["cli"], f"python -m review_tool habits --sync {DAY}")
        self.assertEqual(plan["preview"]["target_table"], "habit_logs")
        self.assertEqual([r["habit_key"] for r in plan["preview"]["rows"]], ["reading_30"])
        self.assertEqual(plan["preview"]["rows"][0]["done"], 1)
        pt0 = self._rows("personal_tracks")
        n_calls = len(calls)
        out = wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertEqual(len(calls), n_calls, "confirm 不得二次拉 ClickUp")
        self.assertEqual(out["result"]["written"], 1)
        self.assertEqual(self._rows("habit_logs"), 1)
        self.assertEqual(self._rows("personal_tracks"), pt0, "R3：不得碰 personal_tracks")
        self.assertEqual(len(os.listdir(self.bak)), 1, "写库前必须备份")
        with self.assertRaises(QueryError):
            wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)


class TestAiWrite(_WriteFixture):
    def test_draft_plan_confirm(self):
        md0 = _sha(self.md)
        plan = wo.plan_ai_draft(self.tokens, self.ro(), DAY, client=_client([]), mode="deepseek")
        self.assertEqual(_sha(self.md), md0, "plan 不得写 md")
        self.assertIn("--write", plan["cli"])
        out = wo.confirm(self.tokens, plan["token"])
        self.assertTrue(out["result"]["written"])
        with open(self.md, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("七-A · AI 草稿（待人审）", text)
        self.assertIn("dailylumen:llm-pending-review", text)
        self.assertIn("训练按计划完成", text)

    def test_draft_gated_in_workbuddy(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_ai_draft(self.tokens, self.ro(), DAY, client=_client([]), mode="workbuddy")
        self.assertEqual(cm.exception.code, "mode_gated")

    def test_stale_plan(self):
        plan = wo.plan_ai_draft(self.tokens, self.ro(), DAY, client=_client([]), mode="deepseek")
        with open(self.md, "a", encoding="utf-8") as f:
            f.write("\n手改一行\n")
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"])
        self.assertEqual(cm.exception.code, "stale_plan")

    def test_finalize(self):
        d = wo.plan_ai_draft(self.tokens, self.ro(), DAY, client=_client([]), mode="deepseek")
        wo.confirm(self.tokens, d["token"])
        md0 = _sha(self.md)
        plan = wo.plan_finalize(self.tokens, DAY)
        self.assertEqual(_sha(self.md), md0)
        self.assertTrue(plan["preview"]["pending_before"])
        self.assertIn("定稿前并排预览", plan["preview"]["side_by_side"])
        out = wo.confirm(self.tokens, plan["token"])
        self.assertTrue(out["result"]["written"])
        self.assertFalse(out["result"]["pending_after"])
        self.assertIn("ingest", out["result"]["next"])
        with open(self.md, encoding="utf-8") as f:
            self.assertIn(REPLY.splitlines()[2].strip("- "), f.read())


@unittest.skipUnless(HAVE_WEB, "需要 fastapi")
class TestWriteRoutes(_WriteFixture):
    def _tc(self, routers):
        return TestClient(create_app(dist_dir=self.dir, write_enabled=True, extra_routers=routers),
                          base_url=BASE)

    def test_default_readonly_has_no_write_routes(self):
        tc = TestClient(create_app(dist_dir=self.dir, extra_routers=default_routers(db_path=self.db)),
                        base_url=BASE)
        self.assertEqual(tc.post("/api/write/confirm", json={"token": "x"}).status_code, 404)
        paths = {r.path for r in default_routers(db_path=self.db, write_enabled=True)[-1].routes}
        self.assertIn("/api/write/confirm", paths)

    def test_flow_and_guards(self):
        r = build_router(db_path=self.db, fetch=_fetch([]), env=ENV, backup_dir=self.bak,
                         tokens=self.tokens)
        tc = self._tc([r])
        bad = tc.post(f"/api/write/habits-sync/plan?date={DAY}", headers={"Origin": "http://evil.example"})
        self.assertEqual(bad.status_code, 403)
        plan = tc.post(f"/api/write/habits-sync/plan?date={DAY}", headers={"Origin": BASE})
        self.assertEqual(plan.status_code, 200)
        tok = plan.json()["token"]
        ok = tc.post("/api/write/confirm", json={"token": tok}, headers={"Origin": BASE})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["cli"], f"python -m review_tool habits --sync {DAY}")
        again = tc.post("/api/write/confirm", json={"token": tok}, headers={"Origin": BASE})
        self.assertEqual((again.status_code, again.json()["error"]["code"]), (409, "token_invalid"))
        self.assertNotIn(ENV["CLICKUP_API_KEY"], plan.text + ok.text)


if __name__ == "__main__":
    unittest.main()
