"""Web 看板 W8：AI 评价预览 + mode 门禁。

锁死：
1. 门禁：mode=workbuddy 时 409 ``mode_gated``，且**不触网**（mock client 调用计数 = 0）。
2. 预览 = ``llm-review --dry-run`` 同源：section / diff 与 run_llm_review(write=False) 一致。
3. 不落盘：库文件字节不变、md 文件字节不变；外部连接 + write=True 被下层拒绝。
4. 上游失败只回固定中文文案，不回显异常原文。
"""
import json
import os
import unittest
from unittest import mock

from review_tool.api import ai_queries as aq
from review_tool.api.queries import QueryError
from review_tool.pipeline import deepseek as ds
from review_tool.reports import llm_review as lr
from tests.api.test_life_api import BASE, HAVE_WEB, _DbFixture, _sha

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_ai import build_router

DAY = "2026-09-09"
REPLY = "**评价**\n\n- 训练按计划完成。\n\n**建议**\n\n1. **引领**：23:30 前熄灯。\n"


def _client(calls, *, fail=None):
    def urlopen(req, timeout=None):
        calls.append(1)
        if fail is not None:
            raise fail

        class R:
            def read(self_inner):
                return json.dumps({"choices": [{"message": {"content": REPLY}}]}).encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return R()

    return ds.Client("sk-fake", mode="deepseek", urlopen=urlopen)


class _AiFixture(_DbFixture):
    def setUp(self):
        super().setUp()
        self.md = os.path.join(self.dir, f"{DAY}.md")
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 复盘\n\n## 七、AI 评价与建议\n\n旧内容\n\n## 八、其他\n")
        for target, value in (
            ("review_tool.reports.llm_review.review_md_path", lambda _d: self.md),
            ("review_tool.reports.llm_review.write_llm_last_run", lambda *a, **k: None),
        ):
            p = mock.patch(target, value)
            p.start()
            self.addCleanup(p.stop)


class TestAiQueries(_AiFixture):
    def test_gate_workbuddy_no_network(self):
        calls = []
        with self.assertRaises(QueryError) as cm:
            aq.review_preview(self.ro(), DAY, client=_client(calls), mode="workbuddy")
        self.assertEqual((cm.exception.status, cm.exception.code), (409, "mode_gated"))
        self.assertEqual(calls, [])

    def test_preview_parity_and_no_write(self):
        db0, md0 = _sha(self.db), _sha(self.md)
        r = aq.review_preview(self.ro(), DAY, client=_client([]), mode="deepseek")
        ref = lr.run_llm_review(DAY, write=False, conn=self.ro(), client=_client([]),
                                mode="deepseek", now=lambda: "x")
        self.assertFalse(r["written"])
        self.assertIn("训练按计划完成", r["section"])
        self.assertEqual(r["old_section"], ref["old_section"])
        self.assertIn("旧内容", r["old_section"])
        self.assertTrue(r["diff_text"])
        self.assertEqual((db0, md0), (_sha(self.db), _sha(self.md)))

    def test_external_conn_rejects_write(self):
        with self.assertRaises(ValueError):
            lr.run_llm_review(DAY, write=True, conn=self.ro(), client=_client([]), mode="deepseek")

    def test_upstream_error_fixed_message(self):
        err = OSError("secret-ish detail sk-abcdefghijklmnopqrstu")
        with self.assertRaises(QueryError) as cm:
            aq.review_preview(self.ro(), DAY, client=_client([], fail=err), mode="deepseek")
        self.assertIn(cm.exception.status, (502, 503))
        self.assertNotIn("sk-", cm.exception.message)

    def test_status_has_no_secret(self):
        st = aq.ai_status()
        self.assertEqual(set(st), {"mode", "allowed", "reason"})


@unittest.skipUnless(HAVE_WEB, "需要 fastapi")
class TestAiRoutes(_AiFixture):
    def _tc(self, mode):
        app = create_app(dist_dir=self.dir, extra_routers=[
            build_router(db_path=self.db, client=_client([]), mode=mode)])
        return TestClient(app, base_url=BASE)

    def test_post_preview(self):
        db0 = _sha(self.db)
        r = self._tc("deepseek").post(f"/api/ai/review-preview?date={DAY}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["written"])
        self.assertEqual(db0, _sha(self.db))

    def test_gated_409(self):
        r = self._tc("workbuddy").post(f"/api/ai/review-preview?date={DAY}")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"]["code"], "mode_gated")

    def test_cross_origin_blocked(self):
        r = self._tc("deepseek").post(f"/api/ai/review-preview?date={DAY}",
                                     headers={"Origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_bad_date(self):
        r = self._tc("deepseek").post("/api/ai/review-preview?date=2026-13-40")
        self.assertEqual(r.status_code, 422)

    def test_status(self):
        r = self._tc("deepseek").get("/api/ai/status")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("sk-", r.text)


if __name__ == "__main__":
    unittest.main()
