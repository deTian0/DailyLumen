"""M12 营养缺口：core.nutrition 纯规则 + reports.nutrition + ai_review R1 同源。"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from review_tool.config import FOOD_LIB, NUTRITION_RULES, PROFILE
from review_tool.core.nutrition import (
    extreme_kcal_streak,
    format_extreme_flag,
    format_macro_below_flags,
    format_suggestion_line,
    gap_analysis,
    macros_below_target,
    meal_structure,
    scale_food,
    suggest_foods,
)
from review_tool.reports.ai_review import attention_flags
from review_tool.reports.nutrition import collect
from review_tool.reports.nutrition import main as nutrition_main
from review_tool.reports.nutrition import render as render_nutrition
from review_tool.storage.db import init_db, replace_nutrition_items, upsert

DAY = {
    "date": "2026-09-15",
    "diet_kcal": 1175,
    "carbs_g": 160,
    "fat_g": 36,
    "protein_g": 59,
    "meals_count": 2,
    "breakfast_on_time": 0,
}


class TestMacrosBelowTarget(unittest.TestCase):
    """与 ai_review 既有文案字节级对齐（R1）。"""

    def test_flag_text_matches_legacy(self):
        flags = format_macro_below_flags(DAY, {"protein_g": 82})
        self.assertEqual(flags, ["蛋白质 59g 低于目标 82g"])
        self.assertFalse(any("碳水" in f for f in flags))

    def test_full_targets(self):
        gaps = macros_below_target(DAY, PROFILE["macro_targets"])
        cols = {g["col"] for g in gaps}
        self.assertEqual(cols, {"carbs_g", "protein_g", "fat_g"})
        protein = next(g for g in gaps if g["col"] == "protein_g")
        self.assertEqual(protein["deficit"], 23)  # 82 - 59

    def test_met_target_excluded(self):
        day = dict(DAY, protein_g=90, carbs_g=230, fat_g=50)
        self.assertEqual(macros_below_target(day, PROFILE["macro_targets"]), [])

    def test_none_actual_skipped(self):
        day = {"protein_g": None, "carbs_g": 100}
        gaps = macros_below_target(day, {"protein_g": 82, "carbs_g": 220})
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["col"], "carbs_g")

    def test_ai_review_uses_shared(self):
        """attention_flags 宏量段必须走共享函数（行为不变）。"""
        flags = attention_flags(dict(DAY), [], {"protein_g": 82})
        self.assertTrue(any("蛋白质 59g 低于目标 82g" in f for f in flags))


class TestGapAndMeal(unittest.TestCase):
    def test_gap_analysis(self):
        g = gap_analysis(DAY)
        self.assertEqual(g["deficits"]["protein_g"], 23)
        self.assertGreater(g["deficits"]["carbs_g"], 0)

    def test_meal_structure_suggests_breakfast(self):
        ms = meal_structure(DAY)
        self.assertEqual(ms["suggest_slot"], "早餐")
        self.assertTrue(any("早餐" in n for n in ms["notes"]))

    def test_meal_structure_ok(self):
        ms = meal_structure({
            "meals_count": 3, "breakfast_on_time": 1,
        })
        self.assertEqual(ms["suggest_slot"], "晚餐")
        self.assertEqual(ms["notes"], [])


class TestExtremeKcal(unittest.TestCase):
    def test_triggered_at_three(self):
        recent = [
            {"date": "2026-10-13", "diet_kcal": 900},
            {"date": "2026-10-14", "diet_kcal": 850},
            {"date": "2026-10-15", "diet_kcal": 950},
        ]
        ext = extreme_kcal_streak(recent)
        self.assertTrue(ext["triggered"])
        self.assertEqual(ext["streak"], 3)
        msg = format_extreme_flag(ext)
        self.assertIn("连续 3 天", msg)
        self.assertIn("勿当「做得好」", msg)

    def test_broken_by_ok_day(self):
        recent = [
            {"date": "2026-10-13", "diet_kcal": 900},
            {"date": "2026-10-14", "diet_kcal": 1500},
            {"date": "2026-10-15", "diet_kcal": 900},
        ]
        ext = extreme_kcal_streak(recent)
        self.assertFalse(ext["triggered"])
        self.assertEqual(ext["streak"], 1)

    def test_null_breaks_streak(self):
        recent = [
            {"date": "2026-10-13", "diet_kcal": 900},
            {"date": "2026-10-14", "diet_kcal": None},
            {"date": "2026-10-15", "diet_kcal": 900},
        ]
        self.assertEqual(extreme_kcal_streak(recent)["streak"], 1)

    def test_ai_review_includes_extreme(self):
        recent = [
            {"date": "2026-10-13", "diet_kcal": 800, "bedtime": 1380},
            {"date": "2026-10-14", "diet_kcal": 800, "bedtime": 1380},
            dict(DAY, diet_kcal=800, bedtime=1380),
        ]
        flags = attention_flags(recent[-1], recent, {})
        self.assertTrue(any("极端偏低" in f for f in flags))


class TestSuggestFoods(unittest.TestCase):
    def test_max_three(self):
        deficits = {"protein_g": 40, "carbs_g": 80, "fat_g": 20}
        picks = suggest_foods(deficits)
        self.assertLessEqual(len(picks), NUTRITION_RULES["max_suggest_foods"])
        self.assertGreaterEqual(len(picks), 1)

    def test_recomputable_macros(self):
        """每条建议的宏量必须等于 scale_food(FOOD_LIB项, amount)。"""
        by_key = {f["key"]: f for f in FOOD_LIB}
        picks = suggest_foods({"protein_g": 27, "carbs_g": 40, "fat_g": 0})
        self.assertTrue(picks)
        for p in picks:
            food = by_key[p["key"]]
            expected = scale_food(food, p["amount"])
            self.assertEqual(p["protein"], expected["protein"])
            self.assertEqual(p["carbs"], expected["carbs"])
            self.assertEqual(p["fat"], expected["fat"])
            self.assertEqual(p["kcal"], expected["kcal"])

    def test_deterministic(self):
        d = {"protein_g": 27, "carbs_g": 40}
        a = suggest_foods(d)
        b = suggest_foods(d)
        self.assertEqual(a, b)

    def test_no_gap_empty(self):
        self.assertEqual(suggest_foods({"protein_g": 0, "carbs_g": -5}), [])

    def test_format_line_contains_name_and_amount(self):
        picks = suggest_foods({"protein_g": 27})
        line = format_suggestion_line(picks[0], slot="晚餐")
        self.assertIn(picks[0]["name"], line)
        self.assertIn(picks[0]["unit"], line)
        self.assertIn("晚餐加", line)

    def test_roadmap_example_shape(self):
        """缺口蛋白 27 + 碳水 40 → 建议含具体项与克数。"""
        picks = suggest_foods({"protein_g": 27, "carbs_g": 40, "fat_g": 0})
        self.assertGreaterEqual(len(picks), 1)
        self.assertLessEqual(len(picks), 3)
        # 最大缺口是碳水 40 或蛋白 27；首项应针对最大者
        first = picks[0]
        self.assertIn(first["for_gap"], ("carbs_g", "protein_g"))
        self.assertGreater(first["amount"], 0)


class TestFoodLibConfig(unittest.TestCase):
    def test_size_and_fields(self):
        self.assertGreaterEqual(len(FOOD_LIB), 20)
        self.assertLessEqual(len(FOOD_LIB), 30)
        keys = [f["key"] for f in FOOD_LIB]
        self.assertEqual(len(keys), len(set(keys)))
        for f in FOOD_LIB:
            for field in ("key", "name", "unit", "per", "kcal",
                          "carbs", "protein", "fat", "aliases"):
                self.assertIn(field, f, f"{f.get('key')} 缺 {field}")
            self.assertGreater(f["per"], 0)
            self.assertTrue(f["aliases"])

    def test_scale_chicken_breast(self):
        food = next(f for f in FOOD_LIB if f["key"] == "chicken_breast")
        m = scale_food(food, 200)
        # 200g ≈ 2×100g → 蛋白 ≈ 46.2
        self.assertAlmostEqual(m["protein"], 46.2, places=1)
        self.assertEqual(m["carbs"], 0.0)


class TestNutritionReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.conn = init_db(self.db)
        for i, kcal in enumerate((900, 850, 950), start=13):
            upsert(self.conn, {
                "date": f"2026-10-{i}",
                "diet_kcal": kcal,
                "carbs_g": 100,
                "fat_g": 20,
                "protein_g": 40,
                "meals_count": 2,
                "breakfast_on_time": 0,
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_collect_extreme_and_suggestions(self):
        data = collect(self.conn, as_of="2026-10-15")
        self.assertTrue(data["extreme"]["triggered"])
        self.assertTrue(data["suggestions"])
        text = render_nutrition(data)
        self.assertIn("强提示", text)
        self.assertIn("FOOD_LIB", text)
        # 建议含具体食物名
        self.assertTrue(any(p["name"] in text for p in data["suggestions"]))

    def test_cli_json(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = nutrition_main(["2026-10-15", "--json", self.db])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["as_of"], "2026-10-15")
        self.assertTrue(payload["extreme"]["triggered"])


class TestNutritionItemsDrilldown(unittest.TestCase):
    """v9 / M25：nutrition --date 下钻到当日食物明细（不参与评分）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.conn = init_db(self.db)
        upsert(self.conn, {
            "date": "2026-10-21",
            "diet_kcal": 1500,
            "carbs_g": 180,
            "fat_g": 50,
            "protein_g": 70,
            "meals_count": 3,
            "breakfast_on_time": 1,
        })
        replace_nutrition_items(self.conn, "2026-10-21", [
            {"meal": "breakfast", "item": "燕麦＋牛奶", "kcal": 380, "note": "估算"},
            {"meal": "lunch", "item": "食堂两荤一素", "kcal": 700},
            {"meal": "dinner", "item": "小米粥＋鸡蛋", "kcal": 420},
        ])
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_collect_exposes_items(self):
        data = collect(self.conn, as_of="2026-10-21")
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(data["items_total_kcal"], 1500.0)

    def test_render_lists_items_by_meal(self):
        text = render_nutrition(collect(self.conn, as_of="2026-10-21"))
        self.assertIn("当日明细", text)
        self.assertIn("燕麦＋牛奶", text)
        self.assertIn("早餐", text)
        self.assertIn("明细合计: 1500 kcal", text)
        # 与数据块对照（本例恰好相等）
        self.assertIn("数据块 1500 kcal", text)

    def test_render_marks_missing(self):
        text = render_nutrition(collect(self.conn, as_of="2026-10-13"))
        self.assertIn("该日无食物明细", text)

    def test_json_includes_items(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = nutrition_main(["2026-10-21", "--json", self.db])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items_total_kcal"], 1500.0)
        self.assertEqual(payload["items"][0]["item"], "燕麦＋牛奶")

    def test_items_do_not_change_gap(self):
        """明细不影响缺口判定（G5：不参与评分 / 不参与缺口）。"""
        before = collect(self.conn, as_of="2026-10-21")["day_gap"]
        replace_nutrition_items(self.conn, "2026-10-21", [])
        self.conn.commit()
        after = collect(self.conn, as_of="2026-10-21")["day_gap"]
        self.assertEqual(before["deficits"], after["deficits"])


if __name__ == "__main__":
    unittest.main()
