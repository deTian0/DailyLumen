"""配置层自洽性测试：阈值结构、打卡项定义、版本一致性。

可配置层是「改一处即适配新用户」的承诺，必须有测试兜住，
否则改错配置只会静默产生错误分数。
"""
import os
import re
import unittest

from review_tool import __version__
from review_tool.config import (
    PERSONAL_ITEMS,
    PROFILE,
    SCORE_THRESHOLDS,
    SLOT_BY_CN,
    SLOT_CN,
    WEEKDAY_CN,
)
from review_tool.core.tracks import resolve_item


class TestScoreThresholds(unittest.TestCase):
    def test_all_sections_present(self):
        for key in ("sleep", "bedtime", "exercise", "diet", "phone",
                    "work", "learn", "life", "weights"):
            self.assertIn(key, SCORE_THRESHOLDS)

    def test_weights_within_one(self):
        w = SCORE_THRESHOLDS["weights"]
        self.assertLessEqual(sum(w.values()), 1.0 + 1e-9)
        self.assertGreater(sum(w.values()), 0.0)

    def test_health_subweights_match_health_components(self):
        """健康分权重必须与 compute_health_score 实际使用的子项一一对应。"""
        import inspect

        from review_tool.core.score import compute_health_score
        src = inspect.getsource(compute_health_score)
        for key in SCORE_THRESHOLDS["weights"]:
            self.assertIn(f'w["{key}"]', src, f"权重 {key} 未被健康分使用")

    def test_sleep_thresholds_descending(self):
        s = SCORE_THRESHOLDS["sleep"]
        self.assertGreater(s["full"], s["good"])
        self.assertGreater(s["good"], s["ok"])
        self.assertGreater(s["ok"], s["low"])

    def test_duration_bands_descending(self):
        for key in ("work", "learn", "life"):
            t = SCORE_THRESHOLDS[key]
            self.assertGreater(t["full"], t["good"], key)
            self.assertGreater(t["good"], t["ok"], key)

    def test_duration_sub_ok_knobs_sane(self):
        """未达标区细分档的上下界必须存在且递增、且不越过达标区首档 5。"""
        for key in ("work", "learn", "life"):
            t = SCORE_THRESHOLDS[key]
            self.assertIn("sub_floor", t, key)
            self.assertIn("sub_ceil", t, key)
            self.assertGreaterEqual(t["sub_floor"], 1, key)
            self.assertGreater(t["sub_ceil"], t["sub_floor"], key)
            self.assertLess(t["sub_ceil"], 5, key)

    def test_phone_thresholds_ascending(self):
        p = SCORE_THRESHOLDS["phone"]
        self.assertLess(p["ideal"], p["good"])
        self.assertLess(p["good"], p["ok"])
        self.assertLess(p["ok"], p["bad"])

    def test_diet_range_valid(self):
        d = SCORE_THRESHOLDS["diet"]
        self.assertLess(d["ok_low"], d["good_low"])
        self.assertLess(d["good_low"], d["good_high"])
        self.assertLess(d["good_high"], d["ok_high"])

    def test_bedtime_thresholds_valid(self):
        b = SCORE_THRESHOLDS["bedtime"]
        self.assertLess(b["late_night_max"], b["early_max"])
        self.assertLess(b["early_max"], b["ok_max"])
        self.assertLess(b["ok_max"], 1440)


class TestProfile(unittest.TestCase):
    def test_training_weekdays_valid(self):
        wds = PROFILE["training_weekdays"]
        self.assertTrue(wds)
        for d in wds:
            self.assertIn(d, range(7))

    def test_macro_targets_positive(self):
        for k, v in PROFILE["macro_targets"].items():
            self.assertGreater(v, 0, k)

    def test_weekday_cn_has_seven(self):
        self.assertEqual(len(WEEKDAY_CN), 7)


class TestPersonalItems(unittest.TestCase):
    def test_keys_unique(self):
        keys = [i["key"] for i in PERSONAL_ITEMS]
        self.assertEqual(len(keys), len(set(keys)), "规范项 key 必须唯一")

    def test_every_item_has_required_fields(self):
        for item in PERSONAL_ITEMS:
            for field in ("category", "key", "per_slot", "slot", "label", "aliases"):
                self.assertIn(field, item, f"{item.get('key')} 缺字段 {field}")
            self.assertTrue(item["aliases"])
            self.assertIn(item["slot"], ("morning", "noon", "evening", None))

    def test_non_per_slot_item_slot_is_canonical(self):
        for item in PERSONAL_ITEMS:
            if not item["per_slot"] and item["slot"] is not None:
                self.assertIn(item["slot"], SLOT_CN)

    def test_aliases_resolve_back_to_owner(self):
        """每个 alias 都必须解析回它所属的规范项（防止别名互相抢匹配）。"""
        for item in PERSONAL_ITEMS:
            for alias in item["aliases"]:
                got = resolve_item(alias)
                self.assertIsNotNone(got, f"alias {alias!r} 无法解析")
                self.assertEqual(got["key"], item["key"],
                                 f"alias {alias!r} 被 {got['key']} 抢走了")

    def test_slot_maps_are_consistent(self):
        for key, cn in SLOT_CN.items():
            self.assertEqual(SLOT_BY_CN[cn], key)


class TestVersionConsistency(unittest.TestCase):
    """pyproject 与包内 __version__ 必须一致，否则发布版本会撒谎。"""

    def test_pyproject_matches_package_version(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        self.assertIsNotNone(m, "pyproject.toml 未找到 version")
        self.assertEqual(m.group(1), __version__)

    def test_version_is_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
