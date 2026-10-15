"""M17：练练健身素材渲染（纯函数、零 I/O）。"""
from __future__ import annotations

import unittest

from review_tool.pipeline.keepstrong_render import (
    PRODUCT_CN,
    render_body_section,
    render_material,
    render_plan_section,
    render_records_section,
)


class TestRenderRecords(unittest.TestCase):
    def test_empty_is_legal(self):
        lines = render_records_section([])
        text = "\n".join(lines)
        self.assertIn("无训练记录", text)

    def test_empty_actions_is_legal(self):
        rec = {
            "dayStr": "20261001",
            "trainingType": "temp",
            "durationSeconds": 161,
            "calorie": 9,
            "actions": [],
        }
        text = "\n".join(render_records_section([rec]))
        self.assertIn("2026-10-01", text)
        self.assertIn("2min41s", text)
        self.assertIn("空", text)
        self.assertIn("合法", text)

    def test_duration_formatting(self):
        rec = {"dayStr": "20261001", "name": "力量", "durationSeconds": 161, "actions": []}
        text = "\n".join(render_records_section([rec]))
        self.assertIn("2min41s", text)


class TestRenderBodyPlan(unittest.TestCase):
    def test_body_profile(self):
        text = "\n".join(
            render_body_section(
                {"weight": 82, "weightSource": "bodyLog", "dayStr": "20260920"},
                [{"dayStr": "20260920", "value": 82, "unit": "kg"}],
            )
        )
        self.assertIn("82", text)
        self.assertIn("2026-09-20", text)

    def test_plan_cycle(self):
        text = "\n".join(
            render_plan_section(
                {
                    "name": "一分化",
                    "planId": "9vMyLd",
                    "schedules": [
                        {"name": "全身A"},
                        {"name": "休息日"},
                    ],
                }
            )
        )
        self.assertIn("一分化", text)
        self.assertIn("9vMyLd", text)
        self.assertIn("全身A", text)


class TestRenderMaterial(unittest.TestCase):
    def test_product_name_and_no_secrets(self):
        bundle = {
            "start": "20261001",
            "end": "20261001",
            "records": [],
            "body_profile": None,
            "body_logs": [],
            "plan": None,
        }
        text = render_material(
            bundle,
            label_day="2026-10-01",
            generated_at="T",
            types={"records"},
        )
        self.assertIn(PRODUCT_CN, text)
        self.assertIn("练练健身", text)
        self.assertNotIn("KeepStrong", text)
        self.assertNotIn("LianLian", text)
        self.assertNotIn("Bearer", text)
        self.assertIn("不含", text)
        self.assertNotRegex(text, r"(?i)authorization\s*:")


if __name__ == "__main__":
    unittest.main()
