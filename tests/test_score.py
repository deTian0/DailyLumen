"""score 模块测试：健康分加权、工作/学习/生活分档、跨午夜、缺失归一、只补空。"""
import unittest

from review_tool.score import (
    compute_health_score, compute_work_score,
    compute_learn_score, compute_life_score, compute_scores,
)


class TestHealthScore(unittest.TestCase):
    def test_full_row(self):
        row = {
            "sleep_h": 8, "sleep_quality": 80, "bedtime": 1380,  # 23:00
            "exercise_min": 30, "training_day": 1,
            "diet_kcal": 1500, "phone_h": 3,
        }
        # 服药依从已移出通用评分；剩余权重和 0.95 归一：
        # (10*.18 + 8*.12 + 8*.15 + 10*.25 + 8*.10 + 10*.15) / 0.95 = 9.22 -> 9
        self.assertEqual(compute_health_score(row), 9)

    def test_sleep_full_at_8h(self):
        row = {"sleep_h": 8.0}
        self.assertEqual(compute_health_score(row), 10)

    def test_single_field_renormalize(self):
        # 仅睡眠 8h -> 权重全归一 -> 10
        row = {"sleep_h": 8.0}
        self.assertEqual(compute_health_score(row), 10)

    def test_cross_midnight_priority(self):
        base = {"sleep_h": 8.0}
        midnight = compute_health_score({**base, "bedtime": 39})       # 00:39
        evening = compute_health_score({**base, "bedtime": 1380})      # 23:00
        # 跨午夜应判为熬夜(低分)，低于当晚早睡
        self.assertLess(midnight, evening)

    def test_no_data_returns_none(self):
        self.assertIsNone(compute_health_score({}))


class TestWorkScore(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(compute_work_score({"deepwork_h": 6}), 9)
        self.assertEqual(compute_work_score({"deepwork_h": 4}), 7)
        self.assertEqual(compute_work_score({"deepwork_h": 2}), 5)
        self.assertEqual(compute_work_score({"deepwork_h": 0.5}), 3)

    def test_missing(self):
        self.assertIsNone(compute_work_score({}))


class TestLearnLifeScore(unittest.TestCase):
    def test_learn_thresholds(self):
        self.assertEqual(compute_learn_score({"learn_h": 3}), 9)
        self.assertEqual(compute_learn_score({"learn_h": 2}), 7)
        self.assertEqual(compute_learn_score({"learn_h": 1}), 5)
        self.assertEqual(compute_learn_score({"learn_h": 0.5}), 3)
        self.assertIsNone(compute_learn_score({}))

    def test_life_thresholds(self):
        self.assertEqual(compute_life_score({"life_h": 3}), 9)
        self.assertEqual(compute_life_score({"life_h": 2}), 7)
        self.assertEqual(compute_life_score({"life_h": 1}), 5)
        self.assertEqual(compute_life_score({"life_h": 0.5}), 3)
        self.assertIsNone(compute_life_score({}))


class TestComputeScores(unittest.TestCase):
    def test_only_fill_none_keep_hand_filled(self):
        row = {
            "health_score": 4,           # 手填，应保留
            "deepwork_h": 5,             # 应生成工作分 7
            "learn_h": 2,                # 应生成学习分 7
            # life 无 life_h -> 留空
        }
        compute_scores(row)
        self.assertEqual(row["health_score"], 4)   # 未被覆盖
        self.assertEqual(row["work_score"], 7)
        self.assertEqual(row["learn_score"], 7)
        self.assertIsNone(row.get("life_score"))


if __name__ == "__main__":
    unittest.main()
