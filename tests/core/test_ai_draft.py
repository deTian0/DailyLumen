"""core.ai_draft：草稿标记检测与 pending 戳记。"""
from __future__ import annotations

import unittest

from review_tool.core import ai_draft as ad


class TestAiDraftMarkers(unittest.TestCase):
    def test_pending_visible_and_html(self):
        self.assertTrue(ad.is_ai_draft_pending("> ⚠️ **草稿 / 待人审**（x）"))
        self.assertTrue(
            ad.is_ai_draft_pending(ad.LLM_PENDING_HTML + "\n# title\n")
        )
        self.assertFalse(ad.is_ai_draft_pending("# 定稿\n**评价**\n- ok\n"))

    def test_stamp_idempotent(self):
        md = "# 每日复盘\n\n## 附录\n"
        once = ad.stamp_llm_pending(md)
        self.assertTrue(once.startswith(ad.LLM_PENDING_HTML))
        twice = ad.stamp_llm_pending(once)
        self.assertEqual(once.count(ad.LLM_PENDING_HTML), 1)
        self.assertEqual(twice, once)

    def test_clear_pending(self):
        md = ad.stamp_llm_pending("# hi\n")
        cleared = ad.clear_llm_pending(md)
        self.assertNotIn(ad.LLM_PENDING_HTML, cleared)
        self.assertIn("# hi", cleared)


if __name__ == "__main__":
    unittest.main()
