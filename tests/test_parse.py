"""parse 模块测试：三种格式解析、bedtime 分钟化、三餐计数、系统分。"""
import unittest

from review_tool.parse import parse_text

from tests.sample_data import SAMPLE_MD, PROSE_MD, EXPECTED_SAMPLE


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

    def test_personal_tracks(self):
        row = parse_text(SAMPLE_MD)
        # 「一、日常打卡」下 - [x] 补剂 -> 服药定制项；早餐为通用项不入库
        self.assertEqual(row.get("_personal_tracks"), [("服药", "补剂", 1)])

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
