"""Web 看板 B15：clickup-habit 代勾（plan→confirm，全 mock，不对真 ClickUp 确认）。"""
from __future__ import annotations

import datetime
import unittest
import urllib.error
from io import BytesIO
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from tests.api.test_write_api import ENV, _WriteFixture
from tests.api.test_write_w10 import _FakeCU

DAY = "2026-11-08"
LIST_ID = "HL1"
TASK_ID = "hab1"


def _ms(y, m, d, hh=12):
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return str(int(datetime.datetime(y, m, d, hh, 0, tzinfo=tz).timestamp() * 1000))


def _task(tid=TASK_ID, *, closed=False, name="练练健身"):
    return {
        "id": tid,
        "name": name,
        "status": (
            {"status": "complete", "type": "closed"} if closed
            else {"status": "to do", "type": "open"}
        ),
        "date_closed": _ms(2026, 11, 8) if closed else None,
        "due_date": _ms(2026, 11, 8, 18),
    }


def _fetch(tasks):
    def fetch(path, key, *, timeout=None):
        if "/list/" in path:
            return {"tasks": list(tasks)}
        if path.startswith("/task/"):
            tid = path.split("/task/", 1)[1].split("?", 1)[0]
            for t in tasks:
                if t["id"] == tid:
                    return dict(t)
            return {}
        return {}
    return fetch


class _KsHint:
    def iter_training_records(self, a, b):
        return [{"status": "completed"}]


class TestClickupHabitWrite(_WriteFixture):
    def setUp(self):
        super().setUp()
        p = mock.patch("review_tool.config.HABITS_LIST_ID", LIST_ID)
        p.start()
        self.addCleanup(p.stop)

    def test_plan_then_confirm_complete(self):
        tasks = [_task()]
        plan = wo.plan_clickup_habit(
            self.tokens, habit="lianlian", day=DAY, env=ENV,
            fetch=_fetch(tasks), ks_client=_KsHint(),
        )
        self.assertEqual(plan["action"], "clickup_habit")
        self.assertIn("--apply", plan["cli"])
        self.assertEqual(plan["preview"]["action"], "would_complete")
        self.assertIn("habit_logs", plan["preview"]["does_not_write"])
        self.assertIn("训练", plan["preview"]["disclaimer"] + plan["preview"]["note"])

        cu = _FakeCU()
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=cu)
        self.assertEqual(out["action"], "clickup_habit")
        self.assertTrue(out["result"]["written"])
        self.assertFalse(out["result"]["db_changed"])
        self.assertEqual(cu.calls, [("status", TASK_ID, "complete")])

    def test_plan_skip_closed_idempotent(self):
        plan = wo.plan_clickup_habit(
            self.tokens, habit="lianlian", day=DAY, env=ENV,
            fetch=_fetch([_task(closed=True)]), check_keepstrong=False,
        )
        self.assertEqual(plan["preview"]["action"], "skip_closed")
        out = wo.confirm(self.tokens, plan["token"], env=ENV, cu_client=_FakeCU())
        self.assertTrue(out["result"]["skipped"])
        self.assertFalse(out["result"]["written"])

    def test_missing_task(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_clickup_habit(
                self.tokens, habit="lianlian", day=DAY, env=ENV,
                fetch=_fetch([_task(name="每日阅读 30 分钟")]),
                check_keepstrong=False,
            )
        self.assertEqual(cm.exception.code, "habit_task_missing")
        self.assertEqual(cm.exception.status, 404)

    def test_invalid_habit(self):
        with self.assertRaises(QueryError) as cm:
            wo.plan_clickup_habit(
                self.tokens, habit="reading_30", day=DAY, env=ENV,
                check_keepstrong=False,
            )
        self.assertEqual(cm.exception.code, "invalid_habit")

    def test_upstream_401(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.HTTPError(path, 401, "no", {}, BytesIO(b""))

        with self.assertRaises(QueryError) as cm:
            wo.plan_clickup_habit(
                self.tokens, habit="lianlian", day=DAY, env=ENV,
                fetch=boom, check_keepstrong=False,
            )
        self.assertEqual(cm.exception.code, "upstream_auth")

    def test_upstream_429(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.HTTPError(path, 429, "slow", {}, BytesIO(b""))

        with self.assertRaises(QueryError) as cm:
            wo.plan_clickup_habit(
                self.tokens, habit="lianlian", day=DAY, env=ENV,
                fetch=boom, check_keepstrong=False,
            )
        self.assertEqual(cm.exception.code, "rate_limited")

    def test_registered(self):
        self.assertIn("clickup_habit", wo.registered_actions())


if __name__ == "__main__":
    unittest.main()
