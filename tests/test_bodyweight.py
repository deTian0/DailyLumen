"""bodyweight 模块测试：中文数字、组×次识别、段落门控、上下限。"""
import unittest

from review_tool.core.bodyweight import cn_to_int, estimate, extract, section_body
from tests.sample_data import BODYWEIGHT_MD


def wrap(body: str) -> str:
    """把正文包进「二、今日三件事」段落，并接一个后续段落作边界。"""
    return f"## 二、今日三件事\n\n{body}\n\n## 三、一个改进点\n\n- 早点睡\n"


class TestCnToInt(unittest.TestCase):
    def test_arabic(self):
        self.assertEqual(cn_to_int("15"), 15)
        self.assertEqual(cn_to_int("100"), 100)

    def test_chinese_tens(self):
        self.assertEqual(cn_to_int("二十"), 20)
        self.assertEqual(cn_to_int("十五"), 15)
        self.assertEqual(cn_to_int("十"), 10)

    def test_chinese_hundreds(self):
        self.assertEqual(cn_to_int("一百"), 100)
        self.assertEqual(cn_to_int("一百二十"), 120)

    def test_fullwidth_digits(self):
        self.assertEqual(cn_to_int("２０"), 20)

    def test_invalid(self):
        self.assertIsNone(cn_to_int(""))
        self.assertIsNone(cn_to_int(None))
        self.assertIsNone(cn_to_int("很多"))


class TestSectionBody(unittest.TestCase):
    def test_extracts_only_that_section(self):
        text = "## 一、日常打卡\n\n- [x] 护肤\n\n## 二、今日三件事\n\n1. 做了俯卧撑\n\n## 三、改进\n\n- x\n"
        body = section_body(text)
        self.assertIn("俯卧撑", body)
        self.assertNotIn("护肤", body)

    def test_missing_section(self):
        self.assertEqual(section_body("## 一、日常打卡\n\n- [x] 护肤\n"), "")


class TestEstimate(unittest.TestCase):
    def test_reps_times_sets(self):
        """「10 * 10」= 10 次 × 10 组 = 100 次 -> 100/20 + 9×1 = 14min。"""
        minutes, detail = estimate(wrap("1. 10 * 10 个俯卧撑"))
        self.assertEqual(minutes, 14)
        self.assertIn("100 次", detail)
        self.assertIn("10 组", detail)

    def test_small_volume_hits_floor(self):
        """20 次净计时只有 1min，但单日下限 10min —— 避免如实记录反倒扣分。"""
        minutes, detail = estimate(wrap("1. 俯卧撑 10 * 2"))
        self.assertEqual(minutes, 10)
        self.assertIn("下限", detail)

    def test_chinese_numeral(self):
        minutes, _ = estimate(wrap("1. 做了二十个俯卧撑，而且有喝蛋白粉"))
        self.assertEqual(minutes, 10)

    def test_reps_after_keyword(self):
        minutes, _ = estimate(wrap("1. 俯卧撑 20 个"))
        self.assertEqual(minutes, 10)

    def test_group_and_reps_written_separately(self):
        """「一百个…分 10 组」应同时读出次数与组数。"""
        minutes, detail = estimate(wrap("1. 今天做了一百个俯卧撑，分 10 组"))
        self.assertEqual(minutes, 14)
        self.assertIn("10 组", detail)

    def test_noise_numbers_not_taken_as_reps(self):
        """「一组20个」「一共20个」里的「一」不是次数。"""
        for line in ("1. 俯卧撑一组20个", "1. 今日做了俯卧撑，一共20个"):
            with self.subTest(line=line):
                entries = extract(wrap(line))
                self.assertEqual(entries[0]["reps"], 20)

    def test_list_marker_not_taken_as_reps(self):
        self.assertEqual(extract(wrap("3. 10 * 10 个俯卧撑"))[0]["reps"], 100)

    def test_mention_without_number_uses_default(self):
        minutes, detail = estimate(wrap("1. 做了俯卧撑"))
        self.assertEqual(minutes, 10)
        self.assertIn("默认", detail)

    def test_upper_cap(self):
        """离谱的量被单日上限截断。"""
        minutes, _ = estimate(wrap("1. 1000 个俯卧撑"))
        self.assertEqual(minutes, 45)

    def test_absurd_reps_falls_back_to_default(self):
        """超出 max_reps 视为误写，回退默认量而非产生离谱时长。"""
        entries = extract(wrap("1. 2000 个俯卧撑"))
        self.assertEqual(entries[0]["reps"], 20)

    def test_negation_skipped(self):
        for line in ("1. 没做俯卧撑", "1. 未做俯卧撑", "1. 忘了做俯卧撑"):
            with self.subTest(line=line):
                self.assertIsNone(estimate(wrap(line))[0])

    def test_other_section_not_scanned(self):
        """「AI 评价」里引用别的日期不算当天 —— 这是真实出现过的误判来源。"""
        minutes, _ = estimate(BODYWEIGHT_MD.replace(
            "1. 做了二十个俯卧撑，而且有喝蛋白粉", "1. 完成了工作"
        ))
        self.assertIsNone(minutes)

    def test_other_move_not_enabled(self):
        """未在 config.BODYWEIGHT_MOVES 登记的动作不折算。"""
        self.assertIsNone(estimate(wrap("1. 深蹲 50 个"))[0])

    def test_no_section_returns_none(self):
        self.assertIsNone(estimate("## 一、日常打卡\n\n- [x] 护肤\n")[0])


class TestExtract(unittest.TestCase):
    def test_entry_shape(self):
        entries = extract(BODYWEIGHT_MD)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["move"], "俯卧撑")
        self.assertEqual(e["reps"], 20)
        self.assertEqual(e["sets"], 1)
        self.assertEqual(e["minutes"], 1.0)
        self.assertIn("20", e["source"])

    def test_empty_when_no_hit(self):
        self.assertEqual(extract("## 二、今日三件事\n\n1. 写代码\n"), [])


if __name__ == "__main__":
    unittest.main()
