"""Web 看板 W12：批量完成 / 快照替换投影 / 收件箱缩略图。

锁死：
1. 批量：一次预览 = 一个 token = 一批；预览不触网；确认逐条 run_status（各自回读），
   单条失败不阻断其余条；去重；上限 MAX_BATCH；非法 id 422；token 用后作废。
2. clickup-pull 预览给出 replace_dates + 本周 before/after 投影（读库只读，库字节不变）。
3. 缩略图只收收件箱顶层文件名（穿越 422）；按文件头定 media type；非图 415。
"""
import os
import sqlite3
import unittest

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from tests.api.test_life_api import BASE, HAVE_WEB, _sha
from tests.api.test_write_api import ENV
from tests.api.test_write_w10 import _FakeCU, _W10Fixture
from tests.api.test_write_w11 import _pull_fetch, _W11Fixture
from tests.pipeline.test_vision_intake import _MIN_PNG

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router


class _FailOnce(_FakeCU):
    def set_task_status(self, task_id, status):
        if task_id == "bad1":
            self.calls.append(("status", task_id, status))
            self.tasks[task_id] = {"id": task_id, "status": {"status": "to do"}}  # 回读不符
            return {}
        return super().set_task_status(task_id, status)


class TestTaskBatch(_W10Fixture):
    def test_plan_one_token_then_confirm(self):
        cu = _FakeCU()
        items = [{"task_id": "a1", "name": "买菜"}, {"task_id": "a2", "name": "洗衣"},
                 {"task_id": "a1", "name": "重复"}]
        plan = wo.plan_task_batch(self.tokens, items, env=ENV)
        self.assertEqual(cu.calls, [])  # 预览不触网
        self.assertEqual(plan["preview"]["count"], 2)  # 去重
        self.assertEqual(len(plan["preview"]["clis"]), 2)
        self.assertTrue(all("--apply" in c for c in plan["preview"]["clis"]))
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual([c[1] for c in cu.calls], ["a1", "a2"])
        self.assertEqual(out["result"]["written"], 2)
        with self.assertRaises(QueryError) as cm:  # 一批一个 token，用后作废
            wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual(cm.exception.code, "token_invalid")

    def test_partial_failure_reported(self):
        cu = _FailOnce()
        plan = wo.plan_task_batch(self.tokens, [{"task_id": "bad1"}, {"task_id": "ok1"}], env=ENV)
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual(out["result"]["ok"], ["ok1"])
        self.assertEqual([f["task_id"] for f in out["result"]["failed"]], ["bad1"])

    def test_validation(self):
        with self.assertRaises(QueryError):
            wo.plan_task_batch(self.tokens, [], env=ENV)
        with self.assertRaises(QueryError):
            wo.plan_task_batch(self.tokens, [{"task_id": f"t{i}"} for i in range(wo.MAX_BATCH + 1)],
                               env=ENV)
        with self.assertRaises(QueryError) as cm:
            wo.plan_task_batch(self.tokens, [{"task_id": "../x"}], env=ENV)
        self.assertEqual(cm.exception.code, "invalid_task")


class TestPullProjection(_W11Fixture):
    def test_week_projection_readonly(self):
        import datetime

        day = datetime.date.today().isoformat()
        db0 = _sha(self.db)
        plan = wo.plan_clickup_pull(self.tokens, days=7, env=ENV, fetch=_pull_fetch([], day),
                                    db_path=self.db)
        p = plan["preview"]
        self.assertEqual(p["replace_dates"], [day])
        self.assertEqual(len(p["week"]), 7)
        today = [w for w in p["week"] if w["date"] == day][0]
        self.assertEqual((today["before"], today["after"], today["replaced"]), (0, 1, True))
        self.assertTrue(all(not w["replaced"] for w in p["week"] if w["date"] != day))
        self.assertEqual(_sha(self.db), db0)  # 预览读库只读


class TestInboxImage(_W11Fixture):
    def test_guard_and_media(self):
        with open(os.path.join(self.inbox, "a.png"), "wb") as f:
            f.write(_MIN_PNG)
        with open(os.path.join(self.inbox, "fake.png"), "wb") as f:
            f.write(b"not an image at all")
        path, media = wo.inbox_image("a.png")
        self.assertEqual(media, "image/png")
        self.assertTrue(path.endswith("a.png"))
        for bad in ("../a.png", "已处理/a.png", "..\\a.png"):
            with self.assertRaises(QueryError) as cm:
                wo.inbox_image(bad)
            self.assertEqual(cm.exception.code, "path_forbidden")
        with self.assertRaises(QueryError) as cm:
            wo.inbox_image("fake.png")
        self.assertEqual(cm.exception.code, "invalid_image")


@unittest.skipUnless(HAVE_WEB, "需要 fastapi")
class TestW12Routes(_W11Fixture):
    def test_routes(self):
        with open(os.path.join(self.inbox, "a.png"), "wb") as f:
            f.write(_MIN_PNG)
        r = build_router(db_path=self.db, env=ENV, backup_dir=self.bak, cu_client=_FakeCU(),
                         pull_fetch=_pull_fetch([], "2099-01-01"))
        tc = TestClient(create_app(dist_dir=self.dir, write_enabled=True, extra_routers=[r]),
                        base_url=BASE)
        img = tc.get("/api/write/inbox/image", params={"name": "a.png"})
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img.headers["content-type"], "image/png")
        self.assertEqual(tc.get("/api/write/inbox/image", params={"name": "../a.png"}).status_code, 422)
        p = tc.post("/api/write/task-batch/plan", json={"items": [{"task_id": "a1"}]})
        self.assertEqual(p.status_code, 200, p.text)
        bad = tc.post("/api/write/task-batch/plan", json={"items": [{"task_id": "a1"}]},
                      headers={"Origin": "http://evil.example"})
        self.assertEqual(bad.status_code, 403)
        c = sqlite3.connect(self.db)
        c.close()


if __name__ == "__main__":
    unittest.main()
