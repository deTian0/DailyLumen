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

    def test_training_day_branch_in_render(self):
        yes = dh.render_day_help("2099-01-15", LLM_MODE_WORKBUDDY, training_day=True)
        self.assertIn("keepstrong --date 2099-01-15 --write", yes)
        self.assertIn("clickup-habit", yes)
        self.assertIn("须预览→确认", yes)
        no = dh.render_day_help("2099-01-15", LLM_MODE_WORKBUDDY, training_day=False)
        self.assertNotIn("keepstrong --date", no)
        none = dh.render_day_help("2099-01-15", LLM_MODE_WORKBUDDY, training_day=None)
        self.assertNotIn("训练日附加", none)

    def test_draft_next_hint_training_day(self):
        tip = dh.draft_next_hint("2099-01-15", LLM_MODE_DEEPSEEK, training_day=True)
        self.assertIn("keepstrong --date 2099-01-15 --write", tip)
        self.assertNotIn("llm-day", tip)

    def test_infer_training_day_hint(self):
        self.assertTrue(
            dh.infer_training_day_hint("2099-01-15", md_text="训练日: 是\n体重_kg: 80\n")
        )
        self.assertFalse(
            dh.infer_training_day_hint("2099-01-15", md_text="training_day: no\n")
        )
        self.assertIsNone(
            dh.infer_training_day_hint("2099-01-15", md_text="体重_kg: 80\n")
        )


if __name__ == "__main__":
    unittest.main()
