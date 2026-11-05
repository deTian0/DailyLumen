"""一日三步文案 / day-help 纯规则。"""
from __future__ import annotations

import unittest

from review_tool.core import day_help as dh
from review_tool.core.llm_mode import LLM_MODE_DEEPSEEK, LLM_MODE_WORKBUDDY


class TestRenderDayHelp(unittest.TestCase):
    def test_contains_three_steps_and_commands(self):
        text = dh.render_day_help("2099-01-15", LLM_MODE_WORKBUDDY)
        self.assertIn("一日三步", text)
        self.assertIn("投放收件箱", text)
        self.assertIn("llm-finalize", text)
        self.assertIn("ingest", text)
        self.assertIn("doctor", text)
        self.assertIn("llm-day", text)
        self.assertIn(LLM_MODE_WORKBUDDY, text)
        self.assertIn(LLM_MODE_DEEPSEEK, text)
        self.assertIn("2099-01-15", text)
        self.assertIn("local/每日复盘/收件箱", text)

    def test_deepseek_highlight(self):
        text = dh.render_day_help("2099-01-15", LLM_MODE_DEEPSEEK)
        self.assertIn(f"当前 mode={LLM_MODE_DEEPSEEK}", text)
        self.assertIn("测完建议改回", text)

    def test_draft_next_hint_by_mode(self):
        wb = dh.draft_next_hint("2099-01-15", LLM_MODE_WORKBUDDY)
        self.assertIn("day-help", wb)
        self.assertNotIn("llm-day", wb)
        ds = dh.draft_next_hint("2099-01-15", LLM_MODE_DEEPSEEK)
        self.assertIn("llm-day", ds)


if __name__ == "__main__":
    unittest.main()
