"""core.ai_draft：草稿标记检测、pending 戳记、定稿提升。"""
from __future__ import annotations

import unittest

from review_tool.core import ai_draft as ad
from review_tool.reports.llm_review import wrap_ai_draft


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


class TestPromoteAiDraft(unittest.TestCase):
    def test_promote_a_to_b_and_clear_pending(self):
        body = "**评价**\n\n- 睡眠不错\n\n**建议**\n\n1. **引领**：早睡\n"
        section = wrap_ai_draft(body, day="2099-01-02", generated_at="T")
        md = ad.stamp_llm_pending(
            f"# 每日复盘 · 2099-01-02\n\n{section}\n## 附录\n"
        )
        self.assertTrue(ad.is_ai_draft_pending(md))
        out = ad.promote_ai_draft(md)
        self.assertFalse(ad.is_ai_draft_pending(out))
        self.assertNotIn(ad.LLM_PENDING_HTML, out)
        self.assertIn("### 七-B · 定稿（人审通过）", out)
        self.assertIn("- 睡眠不错", out)
        self.assertIn("已定稿；原稿已提升至七-B", out)
        # 七-A 不应再含草稿标记
        self.assertNotIn(ad.AI_DRAFT_VISIBLE, out)

    def test_promote_idempotent(self):
        body = "**评价**\n\n- x\n"
        section = wrap_ai_draft(body, day="2099-01-03", generated_at="T")
        md = ad.stamp_llm_pending(f"# t\n\n{section}")
        once = ad.promote_ai_draft(md)
        twice = ad.promote_ai_draft(once)
        self.assertFalse(ad.is_ai_draft_pending(twice))
        self.assertIn("- x", twice)

    def test_promote_preserves_existing_b(self):
        md = (
            ad.LLM_PENDING_HTML + "\n"
            "# t\n\n"
            "## 七、AI 评价与建议\n\n"
            "### 七-A · AI 草稿（待人审）\n\n"
            "> ⚠️ **草稿 / 待人审**（x）\n\n"
            "**评价**\n\n- 草稿内容\n\n"
            "### 七-B · 定稿（人审通过）\n\n"
            "**评价**\n\n- 人已改过的定稿\n\n"
        )
        out = ad.promote_ai_draft(md)
        self.assertFalse(ad.is_ai_draft_pending(out))
        self.assertIn("- 人已改过的定稿", out)
        # 占位未命中时不覆盖七-B
        self.assertNotIn("- 草稿内容", out.split("### 七-B")[1])

    def test_pending_only_clears(self):
        md = ad.stamp_llm_pending("# only pending\n\n## 附录\n")
        out = ad.promote_ai_draft(md)
        self.assertFalse(ad.is_ai_draft_pending(out))
        self.assertIn("# only pending", out)


if __name__ == "__main__":
    unittest.main()
