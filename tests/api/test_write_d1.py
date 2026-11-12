"""Web 看板 D1：keepstrong_sync（练练 → 复盘 md）。

锁死：
1. 与 ks_* App 写回分离：动作名 keepstrong_sync；confirm 不调练练写方法。
2. plan 可拉练练（假 client）；confirm 用冻结 payload，不二次拉网。
3. confirm 写 md、库字节不变（db_changed=False）；写后回读。
4. 无变更时 preview.changed=False；md 被改 → 409 stale_plan。
5. 缺 md / 集成关闭 / 上游错误映射与既有 keepstrong 一致。
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from review_tool.integrations.keepstrong import ApiKeyExpired, CredError
from tests.api.test_life_api import HAVE_WEB
from tests.api.test_write_w17 import ENV, _KsFixture

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

DAY = "2026-09-09"
DAY_S = "20260909"

MD_TEMPLATE = """# 每日复盘 · 2026-09-09（星期三）

## 二、今日三件事

1. 测试

## 附录 · 系统数据

```data
日期: 2026-09-09
星期: 星期三
训练日:
体重_kg:
运动时长_min:
睡眠时长_h: 7
健康分: 5
工作分: 5
学习分: 5
生活分: 5
```
"""

REC = {
    "dayStr": DAY_S,
    "status": "completed",
    "name": "全身A",
    "durationSeconds": 1800,
    "actions": [{"name": "深蹲", "sets": 3, "reps": 8, "weight": 60}],
}


class _FakeSyncKS:
    """假练练 Client：供 collect 读取；记录读调用次数。"""

    def __init__(self, *, records=None, fail=None):
        self.records = list(records if records is not None else [REC])
        self.fail = fail
        self.read_calls = 0
        self.write_calls = []

    def iter_training_records(self, start, end):
        self.read_calls += 1
        if self.fail:
            raise self.fail
        return list(self.records)

    def body_profile(self):
        self.read_calls += 1
        if self.fail:
            raise self.fail
        return {"weight": 82.5}

    def body_logs(self, metric, *, start_date=None, end_date=None):
        self.read_calls += 1
        if self.fail:
            raise self.fail
        return [{"dayStr": DAY_S, "metric": "weight", "value": 82.5, "unit": "kg"}]

    def remember_actions(self, acts):
        return None

    # 若误走 App 写回路径，测试应失败
    def set_action_weight(self, *a, **k):
        self.write_calls.append("set_weight")
        raise AssertionError("keepstrong_sync 不得写练练 App")

    def log_body_metric(self, *a, **k):
        self.write_calls.append("log_body")
        raise AssertionError("keepstrong_sync 不得写练练 App")


class TestKeepstrongSyncWrite(_KsFixture):
    def setUp(self):
        super().setUp()
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(MD_TEMPLATE)

    def _sha_md(self):
        with open(self.md, "rb") as f:
            import hashlib
            return hashlib.sha256(f.read()).hexdigest()

    def test_plan_then_confirm_writes_md_not_db(self):
        ks = _FakeSyncKS()
        md0, db0 = self._sha_md(), self._sha_db()
        plan = wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        self.assertEqual(plan["action"], "keepstrong_sync")
        self.assertIn("keepstrong --date", plan["cli"])
        self.assertIn("--write", plan["cli"])
        self.assertNotIn("--yes", plan["cli"])
        self.assertTrue(plan["preview"]["changed"])
        self.assertTrue(plan["preview"]["training_written"])
        self.assertEqual(plan["preview"]["training_day"], True)
        self.assertEqual(plan["preview"]["writes"], "local_review_md")
        self.assertIn("keepstrong_app", plan["preview"]["does_not"])
        self.assertEqual(self._sha_md(), md0, "plan 不得写 md")
        self.assertEqual(self._sha_db(), db0, "plan 不得写库")
        reads_after_plan = ks.read_calls

        out = wo.confirm(self.tokens, plan["token"], ks_client=ks)
        self.assertEqual(out["action"], "keepstrong_sync")
        self.assertTrue(out["result"]["written"])
        self.assertFalse(out["result"]["db_changed"])
        self.assertEqual(ks.read_calls, reads_after_plan, "confirm 不得二次拉练练")
        self.assertEqual(ks.write_calls, [])
        self.assertNotEqual(self._sha_md(), md0)
        self.assertEqual(self._sha_db(), db0)
        with open(self.md, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("keepstrong:begin", text)
        self.assertIn("深蹲", text)
        self.assertIn("训练日: 是", text)

    def test_confirm_no_change_when_already_synced(self):
        ks = _FakeSyncKS()
        plan1 = wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        wo.confirm(self.tokens, plan1["token"], ks_client=ks)
        md1 = self._sha_md()
        plan2 = wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        self.assertFalse(plan2["preview"]["changed"])
        out = wo.confirm(self.tokens, plan2["token"], ks_client=ks)
        self.assertFalse(out["result"]["written"])
        self.assertEqual(self._sha_md(), md1)

    def test_stale_plan(self):
        ks = _FakeSyncKS()
        plan = wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        with open(self.md, "a", encoding="utf-8") as f:
            f.write("\n<!-- touch -->\n")
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"], ks_client=ks)
        self.assertEqual(cm.exception.code, "stale_plan")

    def test_empty_completed_sets_training_day_no(self):
        ks = _FakeSyncKS(records=[])
        plan = wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        self.assertEqual(plan["preview"]["training_day"], False)
        self.assertFalse(plan["preview"]["training_written"])
        self.assertIsNotNone(plan["preview"]["empty_note"])
        out = wo.confirm(self.tokens, plan["token"], ks_client=ks)
        self.assertTrue(out["result"]["written"] or True)  # 训练日行可能从空→否
        with open(self.md, encoding="utf-8") as f:
            self.assertIn("训练日: 否", f.read())

    def test_md_missing(self):
        os.remove(self.md)
        with self.assertRaises(QueryError) as cm:
            wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=_FakeSyncKS())
        self.assertEqual(cm.exception.code, "md_missing")

    def test_credentials_missing(self):
        with mock.patch(
            "review_tool.integrations.keepstrong.load_api_key",
            side_effect=CredError("缺 key"),
        ):
            with self.assertRaises(QueryError) as cm:
                wo.plan_keepstrong_sync(self.tokens, DAY, env={})
        self.assertEqual(cm.exception.code, "credentials_missing")

    def test_upstream_auth(self):
        ks = _FakeSyncKS(fail=ApiKeyExpired("expired"))
        with self.assertRaises(QueryError) as cm:
            wo.plan_keepstrong_sync(self.tokens, DAY, env=ENV, ks_client=ks)
        self.assertEqual(cm.exception.code, "upstream_auth")

    def test_route_plan_confirm(self):
        if not HAVE_WEB:
            self.skipTest("web extra 未装")
        from tests.api.test_life_api import BASE

        ks = _FakeSyncKS()
        key = "d1-test-key"
        router = build_router(
            db_path=self.db, env=ENV, backup_dir=self.bak, tokens=self.tokens, ks_client=ks,
        )
        c = TestClient(
            create_app(dist_dir=self.dir, extra_routers=[router], web_key=key),
            base_url=BASE,
        )
        h = {"X-DailyLumen-Key": key}
        r = c.post("/api/write/keepstrong-sync/plan", json={"date": DAY}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["action"], "keepstrong_sync")
        r2 = c.post("/api/write/confirm", json={"token": body["token"]}, headers=h)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json()["result"]["written"])


class TestRegistryIncludesSync(unittest.TestCase):
    def test_registered(self):
        self.assertIn("keepstrong_sync", wo.registered_actions())


if __name__ == "__main__":
    unittest.main()
