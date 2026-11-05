"""收工摘要 / 红绿灯纯规则。"""
from __future__ import annotations

import unittest

from review_tool.core import day_close as dc


class TestFormatCloseSummary(unittest.TestCase):
    def test_three_lines(self):
        text = dc.format_close_summary(
            read="饮食热量_kcal",
            empty="体重_kg",
            next_cmd="python -m review_tool llm-finalize 2099-01-01 --write",
        )
        lines = text.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("读到:"))
        self.assertTrue(lines[1].startswith("空缺:"))
        self.assertTrue(lines[2].startswith("下一条:"))


class TestClassifyDayReady(unittest.TestCase):
    def test_no_md_is_red(self):
        st = dc.classify_day_ready(
            md_exists=False, pending_draft=False, ingested=False,
        )
        self.assertEqual(st["light"], dc.LIGHT_RED)

    def test_pending_is_red(self):
        st = dc.classify_day_ready(
            md_exists=True, pending_draft=True, ingested=False,
            missing_focus=[],
        )
        self.assertEqual(st["light"], dc.LIGHT_RED)
        self.assertTrue(any("未定稿" in r for r in st["reasons"]))

    def test_not_ingested_yellow(self):
        st = dc.classify_day_ready(
            md_exists=True, pending_draft=False, ingested=False,
            missing_focus=[],
        )
        self.assertEqual(st["light"], dc.LIGHT_YELLOW)

    def test_green_when_ready(self):
        st = dc.classify_day_ready(
            md_exists=True, pending_draft=False, ingested=True,
            missing_focus=[], inbox_pending=False,
            optional_missing=["体脂率"],
        )
        self.assertEqual(st["light"], dc.LIGHT_GREEN)
        self.assertIn("体脂", " ".join(st["reasons"]))

    def test_body_fat_not_in_focus(self):
        self.assertNotIn("体脂率", dc.CLOSE_FOCUS_FIELDS)
        miss = dc.missing_focus_fields(["饮食热量_kcal", "睡眠时长_h"])
        self.assertIn("体重_kg", miss)
        self.assertIn("运动时长_min", miss)


class TestReadyLine(unittest.TestCase):
    def test_render(self):
        st = dc.classify_day_ready(
            md_exists=True, pending_draft=False, ingested=True,
        )
        line = dc.render_day_ready_line(st)
        self.assertIn("今日能否收工", line)
        self.assertIn("绿", line)


if __name__ == "__main__":
    unittest.main()
