"""fuse 模块测试：连续天数、历史最长、相对基线漂移、阈值失效提示。"""
import os
import shutil
import tempfile
import unittest

from review_tool.db import init_db, upsert
from review_tool.fuse import find_fuses, render

RULES = {"threshold": 6, "days": 3, "long_run_days": 4,
         "recent_days": 2, "baseline_days": 3, "drift": 1.0}


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

    def _run(self):
        return find_fuses(self.conn, rules=RULES)


class TestStreaks(_Fixture):
    def test_consecutive_run_at_tail_only(self):
        # 学习：4(高) 之后连续 3 天低 -> 触发
        self._add("2026-09-01", learn_score=8)
        for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
            self._add(d, learn_score=3)
        r = self._run()
        item = next(i for i in r["absolute"] if i["dim"] == "learn_score")
        self.assertEqual(item["run"], 3)
        self.assertEqual(item["since"], "2026-09-02")
        self.assertTrue(item["fused"])

    def test_interrupted_run_not_fused(self):
        self._add("2026-09-01", learn_score=3)
        self._add("2026-09-02", learn_score=3)
        self._add("2026-09-03", learn_score=7)   # 打断
        self._add("2026-09-04", learn_score=3)
        r = self._run()
        self.assertFalse(any(i["dim"] == "learn_score" for i in r["absolute"]))
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 1)
        self.assertEqual(quiet["longest"], 2)

    def test_missing_value_breaks_run(self):
        self._add("2026-09-01", learn_score=3)
        self._add("2026-09-02")                  # 该维度无值
        self._add("2026-09-03", learn_score=3)
        r = self._run()
        quiet = next(i for i in r["quiet"] if i["dim"] == "learn_score")
        self.assertEqual(quiet["run"], 1)

    def test_long_run_flagged(self):
        for i in range(5):
            self._add(f"2026-09-{i + 1:02d}", learn_score=3)
        r = self._run()
        item = next(i for i in r["absolute"] if i["dim"] == "learn_score")
        self.assertTrue(item["long_run"])        # 5 >= long_run_days(4)


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
        for i in range(5):
            self._add(f"2026-09-{i + 1:02d}", learn_score=3, work_score=8)
        text = render(self._run())
        self.assertIn("熔断检测", text)
        self.assertIn("学习", text)
        self.assertIn("阈值失效提示", text)      # 连续 5 天 > long_run_days 4
        self.assertIn("相对基线", text)
        self.assertIn("结论:", text)

    def test_empty_db_is_safe(self):
        r = self._run()
        self.assertIsNone(r["as_of"])
        self.assertEqual(r["absolute"], [])
        self.assertIn("无维度触发熔断", render(r))


if __name__ == "__main__":
    unittest.main()
