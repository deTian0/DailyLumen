"""配置层自洽性测试：阈值结构、打卡项定义、版本一致性。

可配置层是「改一处即适配新用户」的承诺，必须有测试兜住，
否则改错配置只会静默产生错误分数。
"""
import os
import re
import unittest

from review_tool import __version__
from review_tool.config import (
    BODYWEIGHT_MOVES,
    CLICKUP_LISTS,
    FOOD_LIB,
    HABITS,
    LEARNING_LIST_IDS,
    LEARNING_TOPICS,
    NUTRITION_RULES,
    PERSONAL_ITEMS,
    PROFILE,
    SCORE_THRESHOLDS,
    SLOT_BY_CN,
    SLOT_CN,
    SPACED_REPEAT,
    TRAINING_MOVES,
    WEEKDAY_CN,
)
from review_tool.core.habits import resolve_habit
from review_tool.core.tracks import resolve_item
from review_tool.core.training import resolve_move


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

    def test_health_bands_sorted(self):
        """睡眠是「越大越好」（gte=True）：阈值与分值都必须降序。"""
        cfg = SCORE_THRESHOLDS["sleep"]
        self.assertTrue(cfg["gte"])
        thr = [x for x, _ in cfg["bands"]]
        sc = [s for _, s in cfg["bands"]]
        self.assertEqual(thr, sorted(thr, reverse=True))
        self.assertEqual(sc, sorted(sc, reverse=True))

    def test_phone_bands_sorted(self):
        """屏幕是「越小越好」（gte=False）：阈值升序、分值降序。"""
        cfg = SCORE_THRESHOLDS["phone"]
        self.assertFalse(cfg["gte"])
        thr = [x for x, _ in cfg["bands"]]
        sc = [s for _, s in cfg["bands"]]
        self.assertEqual(thr, sorted(thr))
        self.assertEqual(sc, sorted(sc, reverse=True))

    def test_bands_have_no_duplicate_scores(self):
        """同一子项里两个档不许同分 —— 同分即死档。

        v1.34.0 的三处病灶正是这个：入睡 89% 同分、屏幕 74% 同分、
        运动 69% 同分。这条测试把「不许再写出死档」钉死。
        """
        for key in ("sleep", "phone"):
            scores = [s for _, s in SCORE_THRESHOLDS[key]["bands"]]
            self.assertEqual(len(scores), len(set(scores)), key)
        for branch in ("train", "rest"):
            scores = [s for _, s in SCORE_THRESHOLDS["exercise"][branch]["bands"]]
            self.assertEqual(len(scores), len(set(scores)), branch)

    def test_duration_anchors_monotonic(self):
        """锚点必须双升序：原始值递增时，分值不能回头。"""
        for key in ("work", "learn", "life"):
            pts = SCORE_THRESHOLDS[key]["anchors"]
            xs = [x for x, _ in pts]
            ys = [y for _, y in pts]
            self.assertEqual(xs, sorted(xs), key)
            self.assertEqual(len(xs), len(set(xs)), key)
            self.assertEqual(ys, sorted(ys), key)

    def test_duration_anchors_cover_full_range(self):
        """锚点必须 0h=1 分起、10 分止 —— 否则顶格或地板不可达。"""
        for key in ("work", "learn", "life"):
            pts = sorted(SCORE_THRESHOLDS[key]["anchors"])
            self.assertEqual(pts[0][0], 0, f"{key} 未从 0 小时起")
            self.assertEqual(pts[0][1], 1, f"{key} 起点不是 1 分")
            self.assertEqual(pts[-1][1], 10, f"{key} 顶格不是 10 分")

    def test_diet_tolerance_ascending(self):
        d = SCORE_THRESHOLDS["diet"]
        tol = [x for x, _ in d["bands"]]
        self.assertEqual(tol, sorted(tol))
        self.assertLess(d["good_low"], d["good_high"])

    def test_bedtime_delay_axis_valid(self):
        b = SCORE_THRESHOLDS["bedtime"]
        self.assertLess(b["late_night_max"], b["ok_max"])
        self.assertLess(b["ok_max"], 1440)
        self.assertEqual(b["anchor_min"], 1350, "延迟轴零点应为 22:30")
        self.assertLess(b["anchor_min"], b["ok_max"])
        delays = [x for x, _ in b["bands"]]
        scores = [s for _, s in b["bands"]]
        self.assertEqual(delays, sorted(delays))
        self.assertEqual(scores, sorted(scores, reverse=True))


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


class TestHabitsCatalog(unittest.TestCase):
    """HABITS 目录守卫（M11）：结构 + 与 PERSONAL_ITEMS aliases 不冲突。"""

    def test_keys_unique_and_fields(self):
        keys = [h["key"] for h in HABITS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(HABITS), 6)
        for h in HABITS:
            for field in ("key", "label", "aliases", "target_per_week", "alert_days"):
                self.assertIn(field, h, f"{h.get('key')} 缺 {field}")
            self.assertTrue(h["aliases"])
            self.assertGreater(h["target_per_week"], 0)
            self.assertGreater(h["alert_days"], 0)

    def test_aliases_resolve_back_to_owner(self):
        for h in HABITS:
            for alias in h["aliases"]:
                got = resolve_habit(alias)
                self.assertIsNotNone(got, f"alias {alias!r} 无法解析")
                self.assertEqual(
                    got["key"], h["key"],
                    f"alias {alias!r} 被 {got['key']} 抢走了",
                )

    def test_aliases_no_conflict_with_personal_items(self):
        """HABITS aliases 与 PERSONAL_ITEMS aliases 不得冲突（R3）。"""
        personal = {
            a for item in PERSONAL_ITEMS for a in item["aliases"]
        }
        habit = {a for h in HABITS for a in h["aliases"]}
        clash = personal & habit
        self.assertFalse(
            clash,
            f"HABITS 与 PERSONAL_ITEMS aliases 冲突: {clash}",
        )
        # key 本身也不得交叉
        pkeys = {i["key"] for i in PERSONAL_ITEMS}
        hkeys = {h["key"] for h in HABITS}
        self.assertFalse(
            pkeys & hkeys,
            f"HABITS key 与 PERSONAL_ITEMS key 冲突: {pkeys & hkeys}",
        )


class TestFoodLibCatalog(unittest.TestCase):
    """FOOD_LIB 目录守卫（M12）：结构 + key 唯一 + 宏量为非负。"""

    def test_size_and_required_fields(self):
        self.assertGreaterEqual(len(FOOD_LIB), 20)
        self.assertLessEqual(len(FOOD_LIB), 30)
        keys = [f["key"] for f in FOOD_LIB]
        self.assertEqual(len(keys), len(set(keys)))
        for f in FOOD_LIB:
            for field in ("key", "name", "unit", "per", "kcal",
                          "carbs", "protein", "fat", "aliases"):
                self.assertIn(field, f, f"{f.get('key')} 缺 {field}")
            self.assertGreater(f["per"], 0)
            for m in ("kcal", "carbs", "protein", "fat"):
                self.assertGreaterEqual(f[m], 0, f"{f['key']}.{m}")
            self.assertTrue(f["aliases"])

    def test_nutrition_rules_sane(self):
        self.assertGreater(NUTRITION_RULES["extreme_kcal"], 0)
        self.assertGreaterEqual(NUTRITION_RULES["extreme_streak_days"], 2)
        self.assertGreaterEqual(NUTRITION_RULES["max_suggest_foods"], 1)
        self.assertLessEqual(NUTRITION_RULES["max_suggest_foods"], 5)


class TestTrainingMovesCatalog(unittest.TestCase):
    """TRAINING_MOVES ↔ BODYWEIGHT_MOVES 守卫（M10）。"""

    def test_bodyweight_keys_subset_of_training(self):
        missing = set(BODYWEIGHT_MOVES) - set(TRAINING_MOVES)
        self.assertFalse(
            missing,
            f"BODYWEIGHT_MOVES key 必须在 TRAINING_MOVES 里: {missing}",
        )

    def test_training_aliases_no_cross_grab(self):
        """每个 TRAINING_MOVES alias 必须解析回所属 key（不得互抢）。"""
        for key, spec in TRAINING_MOVES.items():
            for alias in spec.get("aliases") or [key]:
                got_key, _, _ = resolve_move(alias)
                self.assertEqual(
                    got_key, key,
                    f"alias {alias!r} 被 {got_key!r} 抢走（期望 {key!r}）",
                )

    def test_bodyweight_aliases_resolve_same_owner(self):
        """BODYWEIGHT alias 经 TRAINING 解析仍归同一动作名。"""
        for key, spec in BODYWEIGHT_MOVES.items():
            for alias in spec.get("aliases") or [key]:
                got_key, _, _ = resolve_move(alias)
                self.assertEqual(
                    got_key, key,
                    f"BODYWEIGHT alias {alias!r} → {got_key!r}，期望 {key!r}",
                )


class TestLearningCatalog(unittest.TestCase):
    """LEARNING_TOPICS / SPACED_REPEAT 守卫（M13）。"""

    def test_topics_structure(self):
        keys = [t["key"] for t in LEARNING_TOPICS]
        self.assertEqual(len(keys), len(set(keys)))
        for t in LEARNING_TOPICS:
            self.assertIn("key", t)
            self.assertIn("label", t)
            self.assertTrue(t.get("aliases"))

    def test_spaced_repeat_intervals(self):
        iv = SPACED_REPEAT.get("intervals") or []
        self.assertEqual(iv, [1, 3, 7, 16])
        self.assertTrue(all(isinstance(x, int) and x > 0 for x in iv))

    def test_learning_list_ids(self):
        # v1.24.0：成长课/阅读与学习两个 list 并入日常事务，证据链收敛到单一 list
        self.assertEqual(LEARNING_LIST_IDS, ("901422213138",))

    def test_clickup_lists_merged(self):
        """v1.24.0：被并入日常事务的两个旧 list 不得残留在注册表里。"""
        ids = {item["id"] for item in CLICKUP_LISTS}
        self.assertNotIn("901422213140", ids)
        self.assertNotIn("901422213142", ids)
        self.assertIn("901422213138", ids)


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

