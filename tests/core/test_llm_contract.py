"""LLM 结构化契约：JSON 抽取 / 字段归一 / 缺口分类（纯离线）。"""
from __future__ import annotations

import unittest

from review_tool.core import llm_contract as lc


class TestExtractAndNormalize(unittest.TestCase):
    def test_fence_json_and_aliases(self):
        text = """这是读图结果：
```json
{"diet_kcal": 1850, "碳水_g": 200, "protein": 120, "体重_kg": 70.5, "foo": 1}
```
"""
        fields, cls = lc.parse_model_structured(text)
        self.assertEqual(fields["饮食热量_kcal"], 1850)
        self.assertEqual(fields["碳水_g"], 200)
        self.assertEqual(fields["蛋白质_g"], 120)
        self.assertEqual(fields["体重_kg"], 70.5)
        self.assertIn("饮食热量_kcal", cls["filled"])
        self.assertIn("脂肪_g", cls["missing"])
        self.assertIn("foo", cls["unknown"])

    def test_bare_object(self):
        raw = lc.extract_json_object('前置 {"a": 1} 后置')
        self.assertEqual(raw, {"a": 1})

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            lc.extract_json_object("")

    def test_merge_contract_field_dicts(self):
        a = {"饮食热量_kcal": 1000, "碳水_g": 100, "_unknown": {"x": 1}}
        b = {"饮食热量_kcal": 1850, "脂肪_g": 60, "_unknown": {"y": 2}}
        m = lc.merge_contract_field_dicts(a, b)
        self.assertEqual(m["饮食热量_kcal"], 1850)
        self.assertEqual(m["碳水_g"], 100)
        self.assertEqual(m["脂肪_g"], 60)
        self.assertEqual(m["_unknown"]["x"], 1)
        self.assertEqual(m["_unknown"]["y"], 2)

    def test_render_data_block_lines(self):
        body = lc.render_data_block_lines(
            {"饮食热量_kcal": 1800, "体重_kg": 70},
            date="2099-01-03",
            weekday="星期六",
        )
        self.assertIn("日期: 2099-01-03", body)
        self.assertIn("饮食热量_kcal: 1800", body)
        self.assertIn("体重_kg: 70", body)
        self.assertNotIn("脂肪_g:", body)

    def test_contract_fields_cover_intake_core(self):
        for k in ("饮食热量_kcal", "碳水_g", "脂肪_g", "蛋白质_g", "体重_kg"):
            self.assertIn(k, lc.CONTRACT_DATA_FIELDS)

    def test_merge_data_block_fields(self):
        md = "```data\n日期: 2099-01-01\n饮食热量_kcal: 1\n```\n"
        out = lc.merge_data_block_fields(md, {"饮食热量_kcal": 1800, "体重_kg": 70})
        self.assertIn("饮食热量_kcal: 1800", out)
        self.assertIn("体重_kg: 70", out)


if __name__ == "__main__":
    unittest.main()
