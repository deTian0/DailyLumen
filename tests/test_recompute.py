"""recompute 模块测试：按规则重算四维 / 系统分（试算 + 落地）。"""
import os
import shutil
import tempfile
import unittest

from review_tool.db import init_db, upsert
from review_tool.recompute import apply_changes, main, plan, render, target_row


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _add(self, **row):
        row.setdefault("date", "2026-09-21")
        upsert(self.conn, row)
        self.conn.commit()


class TestTargetRow(unittest.TestCase):
    def test_computes_four_plus_system(self):
        t = target_row({"date": "2026-09-21", "deepwork_h": 4.0,
                        "learn_h": 1.0, "life_h": 1.0})
        self.assertEqual(t["work_score"], 7)
        self.assertEqual(t["learn_score"], 5)
        self.assertEqual(t["life_score"], 5)
        self.assertIsNone(t["health_score"])          # 无健康子指标
        self.assertIsNone(t["system_score"])          # 四维不齐 → 系统分 None

    def test_system_score_when_all_present(self):
        t = target_row({"date": "2026-09-21", "sleep_h": 8.0, "deepwork_h": 6.0,
                        "learn_h": 3.0, "life_h": 3.0})
        self.assertIsNotNone(t["health_score"])
        self.assertEqual(t["work_score"], 9)
        self.assertIsNotNone(t["system_score"])


class TestPlanAndApply(_Fixture):
    def test_no_change_when_consistent(self):
        t = target_row({"date": "2026-09-21", "deepwork_h": 4.0})
        self._add(deepwork_h=4.0, work_score=t["work_score"])
        self.assertEqual(plan(self.conn), [])

    def test_detects_and_applies(self):
        # learn_score 手填 9，但 learn_h=0.5 规则算出 3
        self._add(learn_h=0.5, learn_score=9)
        changes = plan(self.conn)
        self.assertEqual(len(changes), 1)
        date, col, old, new = changes[0]
        self.assertEqual((date, col, old, new), ("2026-09-21", "learn_score", 9, 3))
        self.assertEqual(apply_changes(self.conn, changes), 1)
        stored = self.conn.execute(
            "SELECT learn_score FROM daily_reviews WHERE date='2026-09-21'"
        ).fetchone()[0]
        self.assertEqual(stored, 3)
        self.assertEqual(plan(self.conn), [])   # 幂等

    def test_nulls_unsupported_hand_score(self):
        """字段不足支撑的维度一律置空（不保留旧手填值）。"""
        self._add(learn_score=8)   # 没有 learn_h
        changes = plan(self.conn)
        self.assertIn(("2026-09-21", "learn_score", 8, None), changes)
        apply_changes(self.conn, changes)
        stored = self.conn.execute(
            "SELECT learn_score FROM daily_reviews WHERE date='2026-09-21'"
        ).fetchone()[0]
        self.assertIsNone(stored)

    def test_apply_is_atomic_on_empty(self):
        self.assertEqual(apply_changes(self.conn, []), 0)


class TestRenderAndMain(_Fixture):
    def test_render_clean(self):
        text = render([], 49)
        self.assertIn("完全一致", text)

    def test_render_lists_changes_and_nulls(self):
        changes = [("2026-09-21", "learn_score", 9, 3),
                   ("2026-09-22", "life_score", 8, None)]
        text = render(changes, 49)
        self.assertIn("2026-09-21", text)
        self.assertIn("学习 9 → 3", text)
        self.assertIn("置空", text)

    def test_main_dry_run(self):
        self._add(learn_h=0.5, learn_score=9)
        rc = main(["--db", self.db])     # 试算，指定临时库避免触碰真库
        self.assertEqual(rc, 0)
        stored = self.conn.execute(
            "SELECT learn_score FROM daily_reviews WHERE date='2026-09-21'"
        ).fetchone()[0]
        self.assertEqual(stored, 9)   # 未写入

    def test_main_apply(self):
        self._add(learn_h=0.5, learn_score=9)
        self.assertEqual(main(["--db", self.db, "--apply"]), 0)
        stored = self.conn.execute(
            "SELECT learn_score FROM daily_reviews WHERE date='2026-09-21'"
        ).fetchone()[0]
        self.assertEqual(stored, 3)


if __name__ == "__main__":
    unittest.main()
