"""Web 看板 W17：练练写回（FR-J2）。

锁死：
1. 写回不落库：confirm 后库文件字节不变（``db_changed=False``）。
2. 两段式：plan 只校验 + 预览（零网络写，假 client 调用计数 = 0）；confirm 才 POST。
3. 六种动作全覆盖：set-weight / log-body / schedule / create-template /
   replace-template-actions / plan-command；预览回显等价 CLI。
4. 错误映射：CredError→503 credentials_missing；ApiKeyExpired→401 upstream_auth；
   SkillUpdateRequired→426；RateLimited→429；KeepStrongError→502 writeback_failed；
   URLError→504 upstream_unreachable。
5. 校验：weight=0 拒绝；非法 actionId / templateId / runningPlanId / metric / command 422。
6. 中文 URL 编码由 integrations.keepstrong.encode_query 负责（已有测试覆盖），本层不重测。
"""
import unittest
import urllib.error
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from tests.api.test_life_api import BASE, HAVE_WEB
from tests.api.test_write_api import _WriteFixture

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

ENV = {"KEEPSTRONG_API_KEY": "ks_test_only"}


class _FakeKS:
    """假练练 Client：记录调用、可控返回 / 异常。"""

    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail

    def set_action_weight(self, action_id, weight, *, user_confirmed=False,
                          weight_unit=None, template_id=None, right_weight=None):
        self.calls.append(("set_weight", action_id, weight, user_confirmed))
        if self.fail:
            raise self.fail
        return {"actionId": action_id, "weight": weight}, "idem-1"

    def log_body_metric(self, metric, value, *, unit, day_str, user_confirmed=False):
        self.calls.append(("log_body", metric, value, unit, day_str, user_confirmed))
        if self.fail:
            raise self.fail
        return {"metric": metric, "value": value, "dayStr": day_str}, "idem-2"

    def schedule_workout(self, day_str, name, actions, *, user_confirmed=False):
        self.calls.append(("schedule", day_str, name, user_confirmed))
        if self.fail:
            raise self.fail
        return {"dayStr": day_str, "name": name}, "idem-3"

    def create_template(self, name, actions, *, template_id=None, user_confirmed=False):
        self.calls.append(("create_template", name, template_id, user_confirmed))
        if self.fail:
            raise self.fail
        return {"templateId": template_id or "tpl-new", "name": name}, "idem-4"

    def replace_template_actions(self, template_id, actions, *, user_confirmed=False):
        self.calls.append(("replace_template", template_id, user_confirmed))
        if self.fail:
            raise self.fail
        return {"templateId": template_id}, "idem-5"

    def running_plan_command(self, running_plan_id, command, *, user_confirmed=False, **extra):
        self.calls.append(("plan_command", running_plan_id, command, user_confirmed))
        if self.fail:
            raise self.fail
        return {"runningPlanId": running_plan_id, "command": command}, "idem-6"


class _KsFixture(_WriteFixture):
    def setUp(self):
        super().setUp()
        # 启用 keepstrong 集成（父类默认关闭）
        p = mock.patch("review_tool.config.INTEGRATIONS",
                       {"clickup": True, "keepstrong": True, "deepseek": True})
        p.start()
        self.addCleanup(p.stop)

    def _sha_db(self):
        with open(self.db, "rb") as f:
            import hashlib
            return hashlib.sha256(f.read()).hexdigest()


class TestKsSetWeight(_KsFixture):
    def test_plan_no_network_then_confirm(self):
        ks = _FakeKS()
        plan = wo.plan_ks_set_weight(self.tokens, "act_abc123", 60, env=ENV)
        self.assertEqual(ks.calls, [])  # 预览不触网
        self.assertEqual(plan["preview"]["weight"], "60")
        self.assertIn("keepstrong --set-weight", plan["cli"])
        self.assertIn("--yes", plan["cli"])
        before = self._sha_db()
        out = wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls, [("set_weight", "act_abc123", "60", True)])
        self.assertTrue(out["result"]["written"])
        self.assertFalse(out["result"]["db_changed"])  # 写回不落库
        self.assertEqual(self._sha_db(), before)

    def test_empty_weight_means_use_history(self):
        ks = _FakeKS()
        plan = wo.plan_ks_set_weight(self.tokens, "act_abc123", None, env=ENV)
        self.assertEqual(plan["preview"]["weight"], "")
        wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][2], "")  # 空串传给 client

    def test_weight_zero_rejected(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_ks_set_weight(self.tokens, "act_abc123", 0, env=ENV)
        self.assertEqual(cm.exception.code, "invalid_param")

    def test_bad_action_id(self):
        with self.assertRaises(QueryError):
            wo.plan_ks_set_weight(self.tokens, "../x", 60, env=ENV)


class TestKsLogBody(_KsFixture):
    def test_plan_and_confirm_default_unit(self):
        ks = _FakeKS()
        plan = wo.plan_ks_log_body(self.tokens, "weight", 62.5, day="2026-11-06", env=ENV)
        self.assertEqual(plan["preview"]["unit"], "kg")  # weight 默认 kg
        self.assertEqual(plan["preview"]["dayStr"], "20261106")
        self.assertIn("--log-body weight", plan["cli"])
        out = wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][:5], ("log_body", "weight", "62.5", "kg", "20261106"))
        self.assertTrue(out["result"]["written"])

    def test_bad_metric(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_ks_log_body(self.tokens, "bmi", 22, env=ENV)
        self.assertEqual(cm.exception.code, "invalid_param")

    def test_bodyRound_requires_unit(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_ks_log_body(self.tokens, "bodyRound", 90, day="2026-11-06", env=ENV)
        self.assertEqual(cm.exception.code, "invalid_param")


class TestKsSchedule(_KsFixture):
    def test_plan_and_confirm(self):
        ks = _FakeKS()
        actions = [{"actionId": "act_x", "groups": [{"sets": 3}]}]
        plan = wo.plan_ks_schedule(self.tokens, "2026-11-06", "全身A", actions, env=ENV)
        self.assertEqual(plan["preview"]["dayStr"], "20261106")
        self.assertIn("全身A", plan["preview"]["name"])
        out = wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][1], "20261106")
        self.assertTrue(out["result"]["written"])

    def test_empty_actions_rejected(self):
        with self.assertRaises(QueryError):
            wo.plan_ks_schedule(self.tokens, "2026-11-06", "x", [], env=ENV)


class TestKsTemplate(_KsFixture):
    def test_create_template(self):
        ks = _FakeKS()
        actions = [{"actionId": "act_y"}]
        plan = wo.plan_ks_create_template(self.tokens, "下肢日", actions, env=ENV)
        self.assertIn("下肢日", plan["cli"])
        wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][1], "下肢日")

    def test_replace_template_actions(self):
        ks = _FakeKS()
        plan = wo.plan_ks_replace_template_actions(self.tokens, "tpl_abc1",
                                                    [{"actionId": "act_z"}], env=ENV)
        self.assertIn("tpl_abc1", plan["cli"])
        wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][1], "tpl_abc1")

    def test_bad_template_id(self):
        with self.assertRaises(QueryError):
            wo.plan_ks_replace_template_actions(self.tokens, "../x", [{"actionId": "a"}], env=ENV)


class TestKsPlanCommand(_KsFixture):
    def test_delay(self):
        ks = _FakeKS()
        plan = wo.plan_ks_plan_command(self.tokens, "pln_abc1", "delay", env=ENV)
        self.assertIn("delay", plan["cli"])
        wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        self.assertEqual(ks.calls[0][2], "delay")

    def test_bad_command(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_ks_plan_command(self.tokens, "pln_abc1", "skip", env=ENV)
        self.assertEqual(cm.exception.code, "invalid_param")

    def test_bad_plan_id(self):
        with self.assertRaises(QueryError):
            wo.plan_ks_plan_command(self.tokens, "x y", "delay", env=ENV)


class TestKsErrorMapping(_KsFixture):
    def test_credentials_missing(self):
        from review_tool.integrations.keepstrong import CredError
        with mock.patch("review_tool.integrations.keepstrong.load_api_key",
                       side_effect=CredError("no key")):
            with self.assertRaises(QueryError) as cm:
                wo.plan_ks_set_weight(self.tokens, "act_abc123", 60, env={})
        self.assertEqual(cm.exception.code, "credentials_missing")

    def test_integration_disabled(self):
        with mock.patch("review_tool.config.INTEGRATIONS",
                        {"clickup": True, "keepstrong": False, "deepseek": True}):
            with self.assertRaises(QueryError) as cm:
                wo.plan_ks_log_body(self.tokens, "weight", 62, env=ENV)
            self.assertEqual(cm.exception.code, "integration_disabled")

    def _confirm_with_fail(self, fail):
        ks = _FakeKS(fail=fail)
        plan = wo.plan_ks_set_weight(self.tokens, "act_abc123", 60, env=ENV)
        try:
            wo.confirm(self.tokens, plan["token"], env=ENV, ks_client=ks)
        except QueryError as e:
            return e
        raise AssertionError("应抛 QueryError")

    def test_api_key_expired(self):
        from review_tool.integrations.keepstrong import ApiKeyExpired
        e = self._confirm_with_fail(ApiKeyExpired("expired"))
        self.assertEqual(e.status, 401)
        self.assertEqual(e.code, "upstream_auth")

    def test_skill_update_required(self):
        from review_tool.integrations.keepstrong import SkillUpdateRequired
        e = self._confirm_with_fail(SkillUpdateRequired("update"))
        self.assertEqual(e.status, 426)
        self.assertEqual(e.code, "skill_update_required")

    def test_rate_limited(self):
        from review_tool.integrations.keepstrong import RateLimited
        e = self._confirm_with_fail(RateLimited("slow"))
        self.assertEqual(e.status, 429)
        self.assertEqual(e.code, "rate_limited")

    def test_keepstrong_error(self):
        from review_tool.integrations.keepstrong import KeepStrongError
        e = self._confirm_with_fail(KeepStrongError("boom"))
        self.assertEqual(e.status, 502)
        self.assertEqual(e.code, "writeback_failed")

    def test_url_error(self):
        e = self._confirm_with_fail(urllib.error.URLError("net"))
        self.assertEqual(e.status, 504)
        self.assertEqual(e.code, "upstream_unreachable")


@unittest.skipUnless(HAVE_WEB, "未安装 web extra")
class TestKsRoutes(_KsFixture):
    KEY = "test-key"

    def _client(self, ks):
        router = build_router(db_path=self.db, env=ENV, backup_dir=self.bak, ks_client=ks)
        return TestClient(create_app(dist_dir=self.dir, extra_routers=[router],
                                     web_key=self.KEY), base_url=BASE)

    def _h(self):
        return {"X-DailyLumen-Key": self.KEY}

    def test_route_plan_then_confirm(self):
        ks = _FakeKS()
        c = self._client(ks)
        r = c.post("/api/write/ks-log-body/plan",
                   json={"metric": "weight", "value": 62, "day": "2026-11-06"},
                   headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        tok = r.json()["token"]
        self.assertEqual(ks.calls, [])  # 预览不触网
        r2 = c.post("/api/write/confirm", json={"token": tok}, headers=self._h())
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json()["result"]["written"])

    def test_route_bad_param_422(self):
        c = self._client(_FakeKS())
        r = c.post("/api/write/ks-set-weight/plan",
                   json={"action_id": "../x", "weight": 60}, headers=self._h())
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_param")

    def test_route_credentials_missing_503(self):
        from review_tool.integrations.keepstrong import CredError
        router = build_router(db_path=self.db, env={}, backup_dir=self.bak)
        c = TestClient(create_app(dist_dir=self.dir, extra_routers=[router],
                                  web_key=self.KEY), base_url=BASE)
        with mock.patch("review_tool.integrations.keepstrong.load_api_key",
                       side_effect=CredError("no key")):
            r = c.post("/api/write/ks-log-body/plan",
                       json={"metric": "weight", "value": 62, "day": "2026-11-06"},
                       headers=self._h())
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "credentials_missing")

    def test_route_confirm_replay_409(self):
        ks = _FakeKS()
        c = self._client(ks)
        r = c.post("/api/write/ks-set-weight/plan",
                   json={"action_id": "act_abc123", "weight": 60}, headers=self._h())
        tok = r.json()["token"]
        self.assertEqual(c.post("/api/write/confirm", json={"token": tok},
                                 headers=self._h()).status_code, 200)
        # 重放同一 token → 409 token_invalid
        r2 = c.post("/api/write/confirm", json={"token": tok}, headers=self._h())
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.json()["error"]["code"], "token_invalid")

    def test_route_no_key_401(self):
        """W14 鉴权：不带 key 的写请求 401（W17 复用 W14 鉴权，不另开免 key 通道）。"""
        c = self._client(_FakeKS())
        r = c.post("/api/write/ks-set-weight/plan",
                   json={"action_id": "act_abc123", "weight": 60})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
