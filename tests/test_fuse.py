"""fuse 模块测试：双条件低分判定、连续天数、历史最长、相对基线漂移、阈值失效提示。

v1.38.0（M32）起低分判定为双条件：当日分 < threshold **且** 低于此前
baseline_days 日自身均值 ≥ relative_drift。fixture 因此重构 —— 「稳定低位」
不再触发（test_stable_low_not_fused），「高位突降」才触发。
"""
import os
import shutil
import tempfile
import unittest

from review_tool.reports.fuse import find_fuses, has_active_fuse, render
from review_tool.storage.db import init_db, upsert

# baseline_days=6 给基线留足窗口（=3 时低位段会被「基线适应」很快打断，
# 连续段最多 3 天，构造不出 long_run 场景）；min_baseline_days=1 让
# 无基线的首日之外尽快可用，专注测双条件本身。
RULES = {"threshold": 6, "days": 3, "long_run_days": 4,
         "recent_days": 2, "baseline_days": 6, "drift": 1.0,
         "relative_drift": 1.0, "min_baseline_days": 1}


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _add(self, date, **scores):
        row = {"date": date, **scores}
        upsert(self.conn, row)
        self.conn.commit()

    def _run(self, rules=None):
        return find_fuses(self.conn, rules=rules or RULES)


class TestStreaks(_Fixture):
    def test_consecutive_run_at_tail_only(self):
        # 学习：8(高) 之后连续 3 天 3 分（显著低于基线）-> 触发
        self._add("2026-09-01", learn_score=8)
        for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
            self._add(d, learn_score=3)
        r = self._run()
        item = next(i for i in r["absolute"] if i["dim"] == "learn_score")
        self.assertEqual(item["run"], 3)
        self.assertEqual(item["since"], "2026-09-02")
        self.assertTrue(item["fused"])

    def test_interrupted_run_not_fused(self):
        # 新口径下只有 09-04 计低（基线 4.33）；09-01/02 基线不足或分数不低于基线
        self._add("2026-09-01", learn_score=3)
        self._add("2026-09-02", learn_score=3)
        self._add("2026-09-03", learn_score=7)   # 打断
        self._add("2026-09-04", learn_score=3)
        r = self._run()
        self.assertFalse(any(i["dim"] == "learn_score" for i in r["absolute"]))
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 1)
        self.assertEqual(quiet["longest"], 1)

    def test_missing_value_breaks_run(self):
        # 缺值打断连续段：09-02 无值，09-03 虽低（基线 8）也只能重新起算
        self._add("2026-09-01", learn_score=8)
        self._add("2026-09-02")                  # 该维度无值
        self._add("2026-09-03", learn_score=3)
        r = self._run()
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 1)

    def test_long_run_flagged(self):
        # 两天 8 分 + 连续 4 天 3 分（基线窗口内仍有 8 拉高基线）→ run=4 ≥ 4
        self._add("2026-09-01", learn_score=8)
        self._add("2026-09-02", learn_score=8)
        for i in range(3, 7):
            self._add(f"2026-09-{i:02d}", learn_score=3)
        r = self._run()
        item = next(i for i in r["absolute"] if i["dim"] == "learn_score")
        self.assertTrue(item["long_run"])        # run=4 >= long_run_days(4)

    def test_stable_low_not_fused(self):
        """核心新语义：一直低但稳定（基线≈自身）→ 永不计低、不熔断。"""
        for i in range(1, 9):
            self._add(f"2026-09-{i:02d}", learn_score=3)
        r = self._run()
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 0)
        self.assertEqual(quiet["longest"], 0)
        self.assertFalse(has_active_fuse(r))

    def test_min_baseline_days_guard(self):
        """基线样本不足 min_baseline_days → 不计低（建库初期不乱报）。"""
        rules = {**RULES, "min_baseline_days": 7}
        self._add("2026-09-01", learn_score=8)
        for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
            self._add(d, learn_score=3)
        r = self._run(rules)
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 0)

    def test_baseline_adapts_after_drop(self):
        """低位持续足够久后基线适应 → 连续段中断（不再无限累计）。"""
        self._add("2026-09-01", learn_score=8)
        for i in range(2, 8):                    # 6 天 3 分
            self._add(f"2026-09-{i:02d}", learn_score=3)
        r = self._run()
        item = next(i for i in r["quiet"] + r["absolute"]
                    if i["dim"] == "learn_score")
        # 09-02..05 计低（基线被 8 拉高），09-06 起基线 ≈4 → 3 不再显著低于基线
        self.assertEqual(item["longest"], 4)
        self.assertEqual(item["run"], 0)


class TestDrift(_Fixture):
    def test_improvement_shows_positive_delta(self):
        # 更早 3 天 = 3 分，最近 2 天 = 8 分 -> ▲ +5
        for i in range(3):
            self._add(f"2026-09-{i + 1:02d}", work_score=3)
        for i in range(3, 5):
            self._add(f"2026-09-{i + 1:02d}", work_score=8)
        r = self._run()
        d = next(x for x in r["drift"] if x["dim"] == "work_score")
        self.assertEqual(d["baseline"], 3.0)
        self.assertEqual(d["recent"], 8.0)
        self.assertAlmostEqual(d["delta"], 5.0)
        self.assertTrue(d["moved"])

    def test_small_delta_not_moved(self):
        for i in range(3):
            self._add(f"2026-09-{i + 1:02d}", work_score=5)
        for i in range(3, 5):
            self._add(f"2026-09-{i + 1:02d}", work_score=5)
        r = self._run()
        d = next(x for x in r["drift"] if x["dim"] == "work_score")
        self.assertFalse(d["moved"])


class TestRender(_Fixture):
    def test_render_mentions_triggered_and_fuse_hint(self):
        self._add("2026-09-01", learn_score=8, work_score=8)
        self._add("2026-09-02", learn_score=8, work_score=8)
        for i in range(3, 7):                    # 4 天低分 → run=4 ≥ long_run 4
            self._add(f"2026-09-{i:02d}", learn_score=3, work_score=8)
        text = render(self._run())
        self.assertIn("熔断检测", text)
        self.assertIn("学习", text)
        self.assertIn("阈值失效提示", text)      # 连续 4 天 > long_run_days 4
        self.assertIn("相对基线", text)
        self.assertIn("结论:", text)

    def test_rule_line_states_both_conditions(self):
        """规则行必须把双条件说全（防止文案退回单条件）。"""
        text = render(self._run())
        self.assertIn("低于自身 6 日基线", text)
        self.assertIn("≥1.0 分", text)

    def test_empty_db_is_safe(self):
        r = self._run()
        self.assertIsNone(r["as_of"])
        self.assertEqual(r["absolute"], [])
        self.assertIn("无维度触发熔断", render(r))

    def test_active_fuse_short_run(self):
        """3 天（< long_run_days 4）触发 → 仍算熔断态，退出码应为 1。"""
        self._add("2026-09-01", learn_score=8)
        for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
            self._add(d, learn_score=3)
        r = self._run()
        self.assertTrue(has_active_fuse(r))
        text = render(r)
        self.assertIn("处于熔断态（学习）", text)
        self.assertNotIn("长期低位", text)

    def test_long_run_not_counted_as_fuse(self):
        """4 天（≥ long_run_days 4）→ 阈值失效，不再算熔断态、不进退出码。"""
        self._add("2026-09-01", learn_score=8)
        self._add("2026-09-02", learn_score=8)
        for i in range(3, 7):
            self._add(f"2026-09-{i:02d}", learn_score=3)
        r = self._run()
        self.assertFalse(has_active_fuse(r))
        text = render(r)
        self.assertNotIn("处于熔断态", text)
        self.assertIn("长期低位", text)
        self.assertIn("阈值失效提示", text)


if __name__ == "__main__":
    unittest.main()
