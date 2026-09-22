"""ai_review 模块测试：入睡判定、关注点规则、趋势、上下文构建与渲染。"""
import os
import tempfile
import unittest

from review_tool.config import SCORE_THRESHOLDS
from review_tool.reports.ai_review import (
    _bedtime_is_late,
    attention_flags,
    build_context,
    clock,
    render_markdown,
)
from review_tool.storage.db import init_db, upsert


def _tmp_db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.db")
    return init_db(db_path=path), path, d


class TestClock(unittest.TestCase):
    def test_formats_minutes(self):
        self.assertEqual(clock(35), "00:35")
        self.assertEqual(clock(1408), "23:28")
        self.assertEqual(clock(0), "00:00")

    def test_none_is_dash(self):
        self.assertEqual(clock(None), "-")


class TestBedtimeIsLate(unittest.TestCase):
    """字段语义 = 距 00:00 分钟数，须与 score.py 判定一致。"""

    def test_late_night_segment(self):
        # 00:35 属 00:00-06:00 熬夜档
        self.assertTrue(_bedtime_is_late(35))
        self.assertTrue(_bedtime_is_late(360))  # 06:00 边界

    def test_ok_and_early_segments(self):
        self.assertFalse(_bedtime_is_late(361))   # 06:01 起不扣
        self.assertFalse(_bedtime_is_late(1350))  # 22:30
        self.assertFalse(_bedtime_is_late(1410))  # 23:30 边界不扣

    def test_late_evening_segment(self):
        self.assertTrue(_bedtime_is_late(1411))  # 23:31
        self.assertTrue(_bedtime_is_late(1439))  # 23:59

    def test_none(self):
        self.assertFalse(_bedtime_is_late(None))


DAY = {
    "date": "2026-09-15", "training_day": 0,
    "sleep_h": 7.17, "sleep_quality": 89, "bedtime": 35,
    "diet_kcal": 1175, "carbs_g": 160, "fat_g": 36, "protein_g": 59,
    "phone_h": 10.32, "deepwork_h": 3, "learn_h": 1, "life_h": 1,
    "work_score": 5, "learn_score": 5, "life_score": 5,
}


class TestAttentionFlags(unittest.TestCase):
    def _flags(self, day=None, recent=None, targets=None):
        return attention_flags(day or dict(DAY), recent or [], targets)

    def test_catches_late_bedtime(self):
        flags = self._flags()
        self.assertTrue(any("00:35" in f and "23:30" in f for f in flags))

    def test_catches_low_diet(self):
        flags = self._flags()
        self.assertTrue(any("1175kcal" in f and "低于" in f for f in flags))

    def test_macro_targets_from_arg(self):
        flags = self._flags(targets={"protein_g": 82})
        self.assertTrue(any("蛋白质 59g 低于目标 82g" in f for f in flags))
        # 未给目标时不检查碳水/脂肪
        self.assertFalse(any("碳水" in f for f in flags))

    def test_catches_high_phone(self):
        flags = self._flags()
        self.assertTrue(any("屏幕 10.32h" in f for f in flags))

    def test_catches_training_day_without_exercise(self):
        d = dict(DAY, training_day=1, exercise_min=None)
        flags = self._flags(day=d)
        self.assertTrue(any("训练日但未记录运动" in f for f in flags))

    def test_zero_src_flagged_with_convention_note(self):
        """src=zero：0 分钟要有「按口径记 0」的来源说明，AI 才不会当成计时事实。"""
        d = dict(DAY, training_day=1, exercise_min=0, exercise_src="zero")
        flags = self._flags(day=d)
        self.assertTrue(any("按口径记 0" in f for f in flags))

    def test_explicit_zero_record(self):
        """手填 0 是明确记录，文案不带口径说明。"""
        d = dict(DAY, training_day=1, exercise_min=0, exercise_src="record")
        flags = self._flags(day=d)
        self.assertTrue(any("运动 0 分钟" in f for f in flags))
        self.assertFalse(any("按口径记 0" in f for f in flags))

    def test_healthy_day_has_no_flags(self):
        good = {
            "date": "2026-09-16", "training_day": 0,
            "sleep_h": 8.0, "sleep_quality": 90, "bedtime": 1400,
            "diet_kcal": 1600, "carbs_g": 250, "fat_g": 55, "protein_g": 90,
            "phone_h": 5.0, "deepwork_h": 5, "learn_h": 2, "life_h": 2,
            "work_score": 7, "learn_score": 7, "life_score": 7,
        }
        self.assertEqual(attention_flags(good, [], {"carbs_g": 220, "protein_g": 82, "fat_g": 46}), [])

    def test_trend_streak_bedtime(self):
        recent = [dict(DAY, date=f"2026-09-{10 + i}") for i in range(3)]
        flags = attention_flags(dict(DAY), recent)
        self.assertTrue(any("连续 3 天入睡未在 23:30 前" in f for f in flags))

    def test_trend_streak_requires_consecutive(self):
        recent = [dict(DAY, date="2026-09-10"), dict(DAY, date="2026-09-11", bedtime=1400),
                  dict(DAY, date="2026-09-12")]
        flags = attention_flags(dict(DAY), recent)
        self.assertFalse(any("连续" in f and "入睡" in f for f in flags))

    def test_no_day_returns_empty(self):
        self.assertEqual(attention_flags({}, []), [])


class TestBuildContext(unittest.TestCase):
    def setUp(self):
        self.conn, self.path, self.dir = _tmp_db()
        for i, bt in enumerate((1400, 30, 35)):  # 9-13 正常, 9-14/9-15 熬夜
            upsert(self.conn, {
                "date": f"2026-09-{13 + i}", "weekday": "二", "bedtime": bt,
                "sleep_h": 7.0, "phone_h": 10.5, "diet_kcal": 1175,
                "carbs_g": 160, "protein_g": 59, "fat_g": 36,
                "deepwork_h": 3.0, "learn_h": 1.0, "life_h": 1.0,
            })
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        os.remove(self.path)
        os.rmdir(self.dir)

    def test_context_shape(self):
        ctx = build_context("2026-09-15", db_path=self.path)
        self.assertEqual(ctx["date"], "2026-09-15")
        self.assertEqual(ctx["day"]["date"], "2026-09-15")
        self.assertEqual(ctx["recent_days"], 3)
        # 四维被补齐
        self.assertIsNotNone(ctx["day"]["system_score"])
        self.assertEqual(ctx["avgs"]["phone_h"], 10.5)
        self.assertTrue(ctx["flags"])

    def test_default_date_is_latest(self):
        ctx = build_context(db_path=self.path)
        self.assertEqual(ctx["date"], "2026-09-15")

    def test_render_contains_sections(self):
        md = render_markdown(build_context("2026-09-15", db_path=self.path))
        for token in ("# AI 评价上下文 · 2026-09-15", "## 当日事实",
                      "## 近 3 日均值（含当日）", "## 规则命中的关注点", "撰写要求"):
            self.assertIn(token, md)

    def test_render_missing_day(self):
        md = render_markdown(build_context("2026-01-01", db_path=self.path))
        self.assertIn("库中无 2026-01-01 记录", md)


class TestThresholdsAreSourceOfTruth(unittest.TestCase):
    """关注点阈值须来自 config，改配置即改口径。"""

    def test_phone_threshold_from_config(self):
        d = dict(DAY, phone_h=SCORE_THRESHOLDS["phone"]["bad"] + 0.1)
        self.assertTrue(any("屏幕" in f for f in attention_flags(d, [])))
        d2 = dict(DAY, phone_h=SCORE_THRESHOLDS["phone"]["bad"] - 0.1)
        self.assertFalse(any("屏幕" in f for f in attention_flags(d2, [])))


if __name__ == "__main__":
    unittest.main()
