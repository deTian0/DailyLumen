"""score 模块测试：健康分加权、时长维锚点插值、跨午夜、缺失归一、只补空。

标尺 v2（v1.34.0）后：时长三维改为锚点插值（1~10 每个整数可达、随原始值单调），
健康六子项改为阈值分档并拆掉死档。本文件同时承担「标尺性质守卫」职责 ——
任何让分值出现空档、让单调性断裂的改动都会在这里先炸。
"""
import unittest

from review_tool.config import SCORE_THRESHOLDS
from review_tool.core.score import (
    balance_spread,
    compute_health_score,
    compute_learn_score,
    compute_life_score,
    compute_scores,
    compute_work_score,
    system_score_from,
    weakest_dimension,
)


class TestHealthScore(unittest.TestCase):
    def test_full_row(self):
        row = {
            "sleep_h": 8, "sleep_quality": 80, "bedtime": 1380,  # 23:00
            "exercise_min": 30, "training_day": 1,
            "diet_kcal": 1500, "phone_h": 3,
        }
        # 六子项权重和 1.00：
        # (10*.20 + 8*.08 + 9*.16 + 10*.26 + 10*.14 + 10*.16) / 1.00 = 9.68 -> 10
        self.assertEqual(compute_health_score(row), 10)

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

    def test_bedtime_monotonic_across_midnight(self):
        """延迟轴必须跨午夜连续：23:59 与 00:00 同分，不能跳变。"""
        late = compute_health_score({"bedtime": 1439})   # 23:59
        zero = compute_health_score({"bedtime": 0})      # 00:00
        self.assertEqual(late, zero)
        # 越晚越低
        seq = [1380, 1410, 1439, 30, 60, 90, 150, 210]   # 23:00 -> 03:30
        scores = [compute_health_score({"bedtime": b}) for b in seq]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_data_returns_none(self):
        self.assertIsNone(compute_health_score({}))


class TestWorkScore(unittest.TestCase):
    def test_anchor_values(self):
        self.assertEqual(compute_work_score({"deepwork_h": 2}), 5)
        self.assertEqual(compute_work_score({"deepwork_h": 3}), 6)
        self.assertEqual(compute_work_score({"deepwork_h": 4}), 7)
        self.assertEqual(compute_work_score({"deepwork_h": 5}), 8)
        self.assertEqual(compute_work_score({"deepwork_h": 6}), 9)
        self.assertEqual(compute_work_score({"deepwork_h": 7}), 10)

    def test_subthreshold_gradient(self):
        """未达标区细分：0/0.5/1/1.5 -> 1/2/3/4。"""
        for hours, expected in ((0, 1), (0.5, 2), (1, 3), (1.5, 4)):
            self.assertEqual(
                compute_work_score({"deepwork_h": hours}), expected, f"{hours}h"
            )

    def test_no_six_gap_anymore(self):
        """v1.34.0 之前 6 分不可达（分值集合 {1,2,3,4,5,7,9}），现在必须可达。"""
        reachable = {compute_work_score({"deepwork_h": h / 10}) for h in range(0, 81)}
        self.assertEqual(reachable, set(range(1, 11)))

    def test_missing(self):
        self.assertIsNone(compute_work_score({}))


class TestLearnLifeScore(unittest.TestCase):
    def test_learn_anchors(self):
        self.assertEqual(compute_learn_score({"learn_h": 0}), 1)
        self.assertEqual(compute_learn_score({"learn_h": 0.5}), 4)
        self.assertEqual(compute_learn_score({"learn_h": 1}), 6)
        self.assertEqual(compute_learn_score({"learn_h": 1.5}), 7)
        self.assertEqual(compute_learn_score({"learn_h": 2}), 8)
        self.assertEqual(compute_learn_score({"learn_h": 3}), 10)
        self.assertIsNone(compute_learn_score({}))

    def test_learn_monotonic(self):
        prev = 0
        for h in (0, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4):
            cur = compute_learn_score({"learn_h": h})
            self.assertGreaterEqual(cur, prev, f"{h}h 出现回头")
            prev = cur

    def test_life_anchors(self):
        self.assertEqual(compute_life_score({"life_h": 0}), 1)
        self.assertEqual(compute_life_score({"life_h": 0.5}), 3)
        self.assertEqual(compute_life_score({"life_h": 1}), 5)
        self.assertEqual(compute_life_score({"life_h": 2}), 7)
        self.assertEqual(compute_life_score({"life_h": 3}), 9)
        self.assertEqual(compute_life_score({"life_h": 4}), 10)
        self.assertIsNone(compute_life_score({}))

    def test_zero_distinguishable_from_half(self):
        """0h 与 0.5h 必须可区分（v1.4.0 之前的「一律最低档」曾把两者压平）。"""
        self.assertLess(
            compute_learn_score({"learn_h": 0}),
            compute_learn_score({"learn_h": 0.5}),
        )
        self.assertLess(
            compute_life_score({"life_h": 0}),
            compute_life_score({"life_h": 0.5}),
        )

    def test_anchors_are_configurable(self):
        """锚点是可配置层的调节阀，改了就应生效。"""
        import review_tool.core.score as sc
        original = sc.SCORE_THRESHOLDS["learn"]["anchors"]
        try:
            sc.SCORE_THRESHOLDS["learn"]["anchors"] = [(0, 1), (1, 10)]
            self.assertEqual(compute_learn_score({"learn_h": 0}), 1)
            self.assertEqual(compute_learn_score({"learn_h": 1}), 10)
        finally:
            sc.SCORE_THRESHOLDS["learn"]["anchors"] = original


class TestScaleInvariants(unittest.TestCase):
    """标尺 v2 的三条设计判据 —— 改配置时最先炸的就是这里。"""

    def test_every_score_1_to_10_reachable(self):
        """判据 3：1~10 每个整数都必须可达，且随原始值单调。"""
        for key, field, fn in (
            ("work", "deepwork_h", compute_work_score),
            ("learn", "learn_h", compute_learn_score),
            ("life", "life_h", compute_life_score),
        ):
            top = max(x for x, _ in SCORE_THRESHOLDS[key]["anchors"])
            reachable = {fn({field: top * k / 80}) for k in range(0, 81)}
            self.assertEqual(reachable, set(range(1, 11)), f"{key} 有空档")

    def test_no_dead_zone_in_health_subscores(self):
        """判据 2：任何子项都不许出现「一个大区间只给一个分值」。"""
        for key in ("sleep", "phone"):
            cfg = SCORE_THRESHOLDS[key]
            scores = [s for _, s in cfg["bands"]]
            self.assertEqual(len(scores), len(set(scores)), f"{key} 存在同分死档")

    def test_top_score_is_attainable(self):
        """判据 1：满分档要可达（可达但稀少 ≠ 不可达）。"""
        self.assertEqual(compute_work_score({"deepwork_h": 7}), 10)
        self.assertEqual(compute_learn_score({"learn_h": 3}), 10)
        self.assertEqual(compute_life_score({"life_h": 4}), 10)


class TestSystemScoreHelpers(unittest.TestCase):
    def test_system_score_is_arithmetic_mean(self):
        row = {"health_score": 6, "work_score": 9, "learn_score": 1, "life_score": 1}
        self.assertEqual(system_score_from(row), 4.25)

    def test_system_score_none_if_any_missing(self):
        self.assertIsNone(system_score_from({"health_score": 6, "work_score": 9}))

    def test_weakest_dimension(self):
        row = {"health_score": 6, "work_score": 9, "learn_score": 1, "life_score": 5}
        self.assertEqual(weakest_dimension(row), ("learn_score", 1))

    def test_weakest_dimension_needs_all_four(self):
        self.assertIsNone(weakest_dimension({"health_score": 6, "work_score": 9}))

    def test_balance_spread(self):
        self.assertEqual(balance_spread(
            {"health_score": 6, "work_score": 9, "learn_score": 1, "life_score": 5}), 8)
        self.assertEqual(balance_spread(
            {"health_score": 5, "work_score": 5, "learn_score": 5, "life_score": 5}), 0)

    def test_balance_spread_none_if_any_missing(self):
        self.assertIsNone(balance_spread({"health_score": 6}))


class TestComputeScores(unittest.TestCase):
    def test_only_fill_none_keep_hand_filled(self):
        row = {
            "health_score": 4,           # 手填，应保留
            "deepwork_h": 5,             # 锚点 -> 工作分 8
            "learn_h": 2,                # 锚点 -> 学习分 8
            # life 无 life_h -> 留空
        }
        compute_scores(row)
        self.assertEqual(row["health_score"], 4)   # 未被覆盖
        self.assertEqual(row["work_score"], 8)
        self.assertEqual(row["learn_score"], 8)
        self.assertIsNone(row.get("life_score"))


if __name__ == "__main__":
    unittest.main()
