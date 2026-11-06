"""Web 看板 W10：ClickUp 建任务 / 改状态（FR-J1）+ ingest 单文件（FR-K1）。

锁死：
1. 预览不触网、不写库；确认才调 clickup_task.run_create / run_status（写后回读）。
2. list 白名单、task id 校验；回读不符 → 502 ``writeback_failed``。
3. ingest 路径限定 INPUT_DIR 内（穿越 / 相对路径 / 非 .md 拒绝）；写库前备份；
   未定稿默认 409 ``ingest_skipped``，勾 allow_ai_draft 才入库；入库后回读。
"""
import os
import unittest
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from review_tool.core import ai_draft as ad
from review_tool.reports.llm_review import wrap_ai_draft
from tests.api.test_life_api import BASE, HAVE_WEB
from tests.api.test_write_api import ENV, _WriteFixture
from tests.reports.test_llm_finalize import SAMPLE

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

META = {"L1": {"id": "L1", "name": "日常事务"}}


class _FakeCU:
    def __init__(self, *, readback_status=None):
        self.calls = []
        self.readback_status = readback_status
        self.tasks = {}

    def create_task(self, list_id, name, **fields):
        self.calls.append(("create", list_id, name))
        self.tasks["t9"] = {"id": "t9", "name": name, "status": {"status": "to do"}}
        return {"id": "t9"}

    def set_task_status(self, task_id, status):
        self.calls.append(("status", task_id, status))
        self.tasks[task_id] = {"id": task_id, "name": "x",
                               "status": {"status": self.readback_status or status}}
        return {}

    def get_task(self, task_id):
        return self.tasks.get(task_id, {})


class _W10Fixture(_WriteFixture):
    def setUp(self):
        super().setUp()
        self.inbox = os.path.join(self.dir, "每日复盘")
        os.makedirs(os.path.join(self.inbox, "复盘", "2099-04"))
        self.rmd = os.path.join(self.inbox, "复盘", "2099-04", "2099-04-01.md")
        for target, value in (
            ("review_tool.config.CLICKUP_LIST_META", META),
            ("review_tool.config.LIST_DAILY", "L1"),
            ("review_tool.config.INPUT_DIR", self.inbox),
        ):
            p = mock.patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def _write_md(self, *, pending):
        sec = wrap_ai_draft("**评价**\n\n- 睡眠 7.5h\n", day="2099-04-01", generated_at="T")
        md = SAMPLE.format(section=sec)
        if pending:
            md = ad.stamp_llm_pending(md)
        else:
            md = ad.clear_llm_pending(ad.promote_ai_draft(md))
        with open(self.rmd, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)


class TestTaskWrite(_W10Fixture):
    def test_create_plan_then_confirm(self):
        cu = _FakeCU()
        plan = wo.plan_task_create(self.tokens, "买菜", env=ENV)
        self.assertEqual(cu.calls, [])  # 预览不触网
        self.assertIn("--create", plan["cli"])
        self.assertIn("--apply", plan["cli"])
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual(cu.calls, [("create", "L1", "买菜")])
        self.assertTrue(out["result"]["readback"])

    def test_list_whitelist_and_bad_input(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_task_create(self.tokens, "x", "L999", env=ENV)
        self.assertEqual(cm.exception.code, "invalid_list")
        with self.assertRaises(QueryError):
            wo.plan_task_create(self.tokens, "  ", env=ENV)
        with self.assertRaises(QueryError):
            wo.plan_task_status(self.tokens, "../x", "complete", env=ENV)

    def test_status_readback_mismatch(self):
        plan = wo.plan_task_status(self.tokens, "abc1", "complete", name="买菜", env=ENV)
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"], env=ENV,
                       cu_client=_FakeCU(readback_status="to do"))
        self.assertEqual(cm.exception.code, "writeback_failed")

    def test_status_ok(self):
        cu = _FakeCU()
        plan = wo.plan_task_status(self.tokens, "abc1", "complete", env=ENV)
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual(cu.calls, [("status", "abc1", "complete")])
        self.assertEqual(out["action"], "task_status")


class TestIngestWrite(_W10Fixture):
    def test_path_guard(self):
        self._write_md(pending=False)
        outside = os.path.join(self.dir, "x.md")
        open(outside, "w").close()
        for bad in (outside, "复盘/2099-04/2099-04-01.md",
                    os.path.join(self.inbox, "..", "x.md")):
            with self.assertRaises(QueryError) as cm:
                wo.plan_ingest(self.tokens, path=bad)
            self.assertIn(cm.exception.code, ("path_forbidden", "invalid_path"))

    def test_pending_skipped_then_allowed(self):
        self._write_md(pending=True)
        plan = wo.plan_ingest(self.tokens, path=self.rmd)
        self.assertTrue(plan["preview"]["will_skip"])
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertEqual(cm.exception.code, "ingest_skipped")
        plan = wo.plan_ingest(self.tokens, path=self.rmd, allow_ai_draft=True)
        self.assertIn("--allow-ai-draft", plan["cli"])
        out = wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertEqual(out["result"]["readback"]["date"], "2099-04-01")

    def test_finalized_ingest_backs_up_first(self):
        self._write_md(pending=False)
        plan = wo.plan_ingest(self.tokens, path=self.rmd)
        self.assertFalse(plan["preview"]["pending"])
        out = wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertTrue(os.path.isfile(os.path.join(self.bak, out["result"]["backup"])))
        self.assertEqual(out["result"]["readback"]["date"], "2099-04-01")

    def test_stale_md(self):
        self._write_md(pending=False)
        plan = wo.plan_ingest(self.tokens, path=self.rmd)
        with open(self.rmd, "a", encoding="utf-8") as f:
            f.write("\n手改\n")
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertEqual(cm.exception.code, "stale_plan")


@unittest.skipUnless(HAVE_WEB, "需要 fastapi")
class TestW10Routes(_W10Fixture):
    def test_routes(self):
        cu = _FakeCU()
        r = build_router(db_path=self.db, env=ENV, backup_dir=self.bak, cu_client=cu)
        tc = TestClient(create_app(dist_dir=self.dir, write_enabled=True, extra_routers=[r]),
                        base_url=BASE)
        p = tc.post("/api/write/task-create/plan", json={"name": "买菜"})
        self.assertEqual(p.status_code, 200, p.text)
        c = tc.post("/api/write/confirm", json={"token": p.json()["token"]})
        self.assertEqual(c.status_code, 200, c.text)
        bad = tc.post("/api/write/task-create/plan", json={"name": "x"},
                      headers={"Origin": "http://evil.example"})
        self.assertEqual(bad.status_code, 403)
        g = tc.post("/api/write/ingest/plan", json={"path": "C:/Windows/x.md"})
        self.assertEqual(g.status_code, 422)


if __name__ == "__main__":
    unittest.main()
