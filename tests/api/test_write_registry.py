"""W13：写操作注册表（confirm 分派）——行为不变，只换分派方式。"""
from __future__ import annotations

import unittest

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from review_tool.api.writes import base

EXPECTED = {
    "habits_sync", "ai_draft", "finalize", "task_create", "task_status", "task_batch",
    "ingest", "vision", "inbox_archive", "clickup_pull",
    "keepstrong_sync", "daily_pull",
}


class TestRegistry(unittest.TestCase):
    def test_all_actions_registered(self):
        self.assertTrue(EXPECTED <= set(wo.registered_actions()))

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            base.register("habits_sync")(lambda p: {})

    def test_unknown_context_key_rejected(self):
        with self.assertRaises(ValueError):
            base.register("x_never", needs=("password",))

    def test_confirm_rejects_unknown_kwargs(self):
        with self.assertRaises(TypeError):
            wo.confirm(wo.TokenStore(), "t", nope=1)

    def test_plan_out_refuses_unregistered_action(self):
        with self.assertRaises(QueryError) as cm:
            base.plan_out(wo.TokenStore(), "not_registered", {"date": "2026-01-01"},
                          preview={}, cli="x")
        self.assertEqual(cm.exception.status, 500)

    def test_confirm_passes_only_declared_context(self):
        seen = {}

        @base.register("_test_ctx_only", needs=("db_path",))
        def _apply(p, *, db_path):
            seen["db_path"] = db_path
            return {"ok": True}

        self.addCleanup(base._REGISTRY.pop, "_test_ctx_only", None)
        st = wo.TokenStore()
        plan = base.plan_out(st, "_test_ctx_only", {"date": "2026-01-01"}, preview={}, cli="c")
        out = wo.confirm(st, plan["token"], db_path="X", env={"k": "v"})
        self.assertEqual(seen, {"db_path": "X"})
        self.assertEqual(out["result"], {"ok": True})
        self.assertEqual(out["cli"], "c")


if __name__ == "__main__":
    unittest.main()
