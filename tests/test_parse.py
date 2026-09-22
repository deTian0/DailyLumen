"""parse 模块测试：三种格式解析、bedtime 分钟化、三餐计数、系统分。"""
import unittest

from review_tool.parse import parse_text
from tests.sample_data import (
    BODYWEIGHT_MD,
    EMPTY_EXERCISE_LINE,
    EXPECTED_SAMPLE,
    LEGACY_TRACKS_MD,
    PROSE_MD,
    SAMPLE_MD,
)


class TestParseDataBlock(unittest.TestCase):
    def test_basic_fields(self):
        row = parse_text(SAMPLE_MD)
        for k, v in EXPECTED_SAMPLE.items():
            self.assertEqual(row.get(k), v, msg=f"字段 {k} 解析不符")

    def test_bedtime_minutes(self):
        row = parse_text(SAMPLE_MD)
        # 00:39 -> 39
        self.assertEqual(row["bedtime"], 39)

    def test_meals_count_from_checkmarks(self):
        row = parse_text(SAMPLE_MD)
        # 早✓午✓晚✗ -> 2
        self.assertEqual(row["meals_count"], 2)

    def test_bool_yes(self):
        row = parse_text(SAMPLE_MD)
        self.assertEqual(row["breakfast_on_time"], 1)

    def test_macros_parsed(self):
        row = parse_text(SAMPLE_MD)
        # 三大营养素克数（中文字段 -> carbs_g/fat_g/protein_g）
        self.assertEqual(row["carbs_g"], 150)
        self.assertEqual(row["fat_g"], 40)
        self.assertEqual(row["protein_g"], 55)

    def test_macros_english_alias(self):
        row = parse_text("```data\n日期: 2026-08-05\ncarbs_g: 180\nfat_g: 60\nprotein_g: 90\n```")
        self.assertEqual(row["carbs_g"], 180)
        self.assertEqual(row["fat_g"], 60)
        self.assertEqual(row["protein_g"], 90)

    def test_personal_tracks(self):
        row = parse_text(SAMPLE_MD)
        # 「一、日常打卡」下：
        #   - [x] 补剂：CoQ10 ×1 ＋ Exia 早3 -> 裂成两个规范项
        #   - [x] 护肤 -> 命中规范项 skincare
        #   - [ ] 早餐 -> 通用项（有独立字段），不进 personal_tracks
        self.assertEqual(row.get("_personal_tracks"), EXPECTED_SAMPLE["_personal_tracks"])

    def test_personal_tracks_legacy_writing(self):
        """手写变体（无时段标题 / 无空格 / 别名）必须归一到同一批规范 key。"""
        row = parse_text(LEGACY_TRACKS_MD)
        got = {(key, done) for _, key, _, _, done in row["_personal_tracks"]}
        self.assertIn(("vitb@noon", 1), got)        # 复合维生素B族 -> vitb（项定义兜底时段）
        self.assertIn(("movefree", 1), got)         # MoveFree 无时段 -> 裸 key
        self.assertIn(("exia_pm@evening", 0), got)  # Exia晚3 -> exia_pm（未勾选）

    def test_personal_tracks_one_line_multiple_items(self):
        """一行两项应产出两条记录，而不是一条。"""
        row = parse_text(SAMPLE_MD)
        keys = [key for _, key, _, _, _ in row["_personal_tracks"]]
        self.assertEqual(len(keys), len(set(keys)))  # 同日不重复
        self.assertGreaterEqual(len(keys), 3)

    def test_generic_checkboxes_not_tracked(self):
        """早餐/通勤等通用打卡项不得进入 personal_tracks。"""
        row = parse_text(SAMPLE_MD)
        items = [item for _, _, _, item, _ in row["_personal_tracks"]]
        self.assertFalse(any("早餐" in i or "通勤" in i for i in items))

    def test_system_score_computed(self):
        row = parse_text(SAMPLE_MD)
        # (4+6+6+5)/4 = 5.25
        self.assertEqual(row["system_score"], 5.25)


class TestParseProseFallback(unittest.TestCase):
    def test_fallback_key_value(self):
        row = parse_text(PROSE_MD)
        self.assertEqual(row["date"], "2026-08-10")
        self.assertEqual(row["sleep_h"], 7.5)
        self.assertEqual(row["weekday"], "日")
        self.assertEqual(row["training_day"], 0)

    def test_no_date_returns_empty_date(self):
        row = parse_text("一些无关文本\n没有日期字段\n")
        self.assertNotIn("date", row)


class TestBodyweightDerivation(unittest.TestCase):
    """运动时长为空时，由「三件事」描述折算补全，并标记来源。"""

    def test_fills_when_field_empty(self):
        row = parse_text(BODYWEIGHT_MD)
        self.assertEqual(row["exercise_min"], 10)
        self.assertEqual(row["exercise_src"], "derived")
        self.assertIn("俯卧撑", row["_exercise_detail"])

    def test_field_wins_and_no_double_count(self):
        """字段已有数值时以字段为准 —— 不叠加，避免同一份运动算两次。"""
        md = BODYWEIGHT_MD.replace(EMPTY_EXERCISE_LINE, "运动时长_min: 25")
        row = parse_text(md)
        self.assertEqual(row["exercise_min"], 25)
        self.assertEqual(row["exercise_src"], "record")

    def test_marks_record_when_field_present(self):
        row = parse_text(SAMPLE_MD)
        self.assertEqual(row["exercise_min"], 0)
        self.assertEqual(row["exercise_src"], "record")

    def test_no_mark_when_no_exercise_info(self):
        row = parse_text(PROSE_MD)
        self.assertNotIn("exercise_min", row)
        self.assertNotIn("exercise_src", row)


class TestBedtimeEdge(unittest.TestCase):
    def test_cross_midnight(self):
        text = "```data\n日期: 2026-08-01\n入睡时间: 00:39\n```"
        row = parse_text(text)
        self.assertEqual(row["bedtime"], 39)

    def test_evening(self):
        text = "```data\n日期: 2026-08-01\n入睡时间: 23:10\n```"
        row = parse_text(text)
        self.assertEqual(row["bedtime"], 1390)


if __name__ == "__main__":
    unittest.main()
