"""M25 食物明细解析：core.nutrition_items 纯规则（零 I/O）。"""
from __future__ import annotations

import unittest

from review_tool.core.nutrition_items import (
    MEAL_LABELS,
    group_by_meal,
    normalize_meal,
    parse_section,
    parse_table,
    section_body,
    total_kcal,
)

SECTION = """
## 附录 · 食物明细（可选）

> 试记窗口说明段，不应被当成表格。

| 餐次 | 食物 | 估算 kcal | 备注 |
|------|------|-----------|------|
| 早 | 燕麦 40g ＋ 牛奶 250ml | 380 | 估算 |
| 午 | 食堂两荤一素 | 约 700 | 干锅肥肠 |
|  |  |  |  |
| 晚 | 小米粥 ＋ 鸡蛋 | ≈420 | |
| 夜宵 | 无糖酸奶 |  | 猜不出 |

## 附录 · 系统数据
"""


class TestSectionBody(unittest.TestCase):
    def test_extracts_only_nutrition_section(self):
        body = section_body(SECTION)
        self.assertIn("燕麦", body)
        self.assertNotIn("系统数据", body)

    def test_missing_section_returns_empty(self):
        self.assertEqual(section_body("## 附录 · 系统数据\n| a | b |\n"), "")


class TestNormalizeMeal(unittest.TestCase):
    def test_chinese_aliases(self):
        self.assertEqual(normalize_meal("早"), "breakfast")
        self.assertEqual(normalize_meal("早餐"), "breakfast")
        self.assertEqual(normalize_meal("午饭"), "lunch")
        self.assertEqual(normalize_meal("晚餐"), "dinner")
        self.assertEqual(normalize_meal("夜宵"), "snack")
        self.assertEqual(normalize_meal("零食"), "snack")

    def test_english_and_unknown(self):
        self.assertEqual(normalize_meal("breakfast"), "breakfast")
        self.assertEqual(normalize_meal("Lunch"), "lunch")
        self.assertEqual(normalize_meal(""), "other")
        self.assertEqual(normalize_meal(None), "other")
        self.assertEqual(normalize_meal("下午茶"), "other")

    def test_all_codes_have_label(self):
        for code in ("breakfast", "lunch", "dinner", "snack", "other"):
            self.assertIn(code, MEAL_LABELS)


class TestParseTable(unittest.TestCase):
    def test_parses_rows_in_order(self):
        items = parse_table(section_body(SECTION))
        self.assertEqual([i["desc"] for i in items], [
            "燕麦 40g ＋ 牛奶 250ml", "食堂两荤一素", "小米粥 ＋ 鸡蛋", "无糖酸奶",
        ])
        self.assertEqual([i["meal"] for i in items],
                         ["breakfast", "lunch", "dinner", "snack"])
        self.assertEqual([i["seq"] for i in items], [0, 1, 2, 3])

    def test_kcal_variants(self):
        items = parse_table(section_body(SECTION))
        self.assertEqual(items[0]["kcal"], 380.0)   # 纯数字
        self.assertEqual(items[1]["kcal"], 700.0)   # 「约 700」
        self.assertEqual(items[2]["kcal"], 420.0)   # 「≈420」
        self.assertIsNone(items[3]["kcal"])         # 留空不编

    def test_empty_rows_skipped(self):
        items = parse_table(section_body(SECTION))
        self.assertTrue(all(i["desc"].strip() for i in items))
        self.assertEqual(len(items), 4)

    def test_note_captured(self):
        items = parse_table(section_body(SECTION))
        self.assertEqual(items[0]["note"], "估算")
        self.assertEqual(items[1]["note"], "干锅肥肠")
        self.assertIsNone(items[2]["note"])

    def test_column_order_flexible(self):
        body = (
            "| 食物 | kcal | 餐次 |\n"
            "|------|------|------|\n"
            "| 全麦面包 | 250 | 早 |\n"
        )
        items = parse_table(body)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["desc"], "全麦面包")
        self.assertEqual(items[0]["meal"], "breakfast")
        self.assertEqual(items[0]["kcal"], 250.0)

    def test_macro_columns_optional(self):
        body = (
            "| 餐次 | 食物 | 蛋白 | 碳水 | 脂肪 |\n"
            "|---|---|---|---|---|\n"
            "| 午 | 鸡胸肉 150g | 46 | 0 | 5 |\n"
        )
        items = parse_table(body)
        self.assertEqual(items[0]["protein_g"], 46.0)
        self.assertEqual(items[0]["carb_g"], 0.0)
        self.assertEqual(items[0]["fat_g"], 5.0)

    def test_no_header_returns_empty(self):
        self.assertEqual(parse_table("随便写点东西\n没有表格\n"), [])

    def test_header_without_food_column_ignored(self):
        body = "| 餐次 | 备注 |\n|---|---|\n| 早 | 无 |\n"
        self.assertEqual(parse_table(body), [])


class TestParseSection(unittest.TestCase):
    def test_returns_items(self):
        items = parse_section(SECTION)
        self.assertIsNotNone(items)
        self.assertEqual(len(items), 4)

    def test_section_without_table_returns_empty_list(self):
        """章节存在但表为空 ≠ 无该附录：前者要清空该日旧行。"""
        text = "## 附录 · 食物明细（可选）\n\n| 餐次 | 食物 | 估算 kcal | 备注 |\n|---|---|---|---|\n| 早 |  |  |  |\n"
        self.assertEqual(parse_section(text), [])

    def test_missing_section_returns_none(self):
        self.assertIsNone(parse_section("## 附录 · 系统数据\n\n| a | b |\n"))


class TestAggregates(unittest.TestCase):
    def test_total_kcal_sums_known(self):
        items = parse_table(section_body(SECTION))
        self.assertEqual(total_kcal(items), 1500.0)

    def test_total_kcal_none_when_all_blank(self):
        self.assertIsNone(total_kcal([{"kcal": None}, {"kcal": None}]))
        self.assertIsNone(total_kcal([]))

    def test_group_by_meal_follows_meal_order(self):
        items = parse_table(section_body(SECTION))
        groups = group_by_meal(items)
        self.assertEqual([code for code, _ in groups],
                         ["breakfast", "lunch", "dinner", "snack"])
        self.assertEqual(len(groups[0][1]), 1)


if __name__ == "__main__":
    unittest.main()
