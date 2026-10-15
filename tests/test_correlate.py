"""M15：跨维关联 — 样本门槛 + Pearson 脚本计算 + 相关≠因果。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from review_tool.reports import correlate
from review_tool.storage.db import init_db, upsert, upsert_body_metrics


class TestPearson(unittest.TestCase):
    def test_perfect_positive(self):
        r = correlate.pearson([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r, 1.0, places=6)

    def test_perfect_negative(self):
        r = correlate.pearson([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
        self.assertAlmostEqual(r, -1.0, places=6)

    def test_degenerate(self):
        self.assertIsNone(correlate.pearson([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]))
        self.assertIsNone(correlate.pearson([1.0], [2.0]))


class TestCorrelateInsufficient(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.conn = init_db(db_path=self.db)
        # 仅 5 天配对 —— 低于门槛 10
        for i in range(5):
            d = f"2026-09-{i + 1:02d}"
            upsert(self.conn, {
                "date": d,
                "sleep_h": 6.0 + i * 0.2,
                "exercise_min": 10 * i,
                "diet_kcal": 1500 + i * 50,
                "learn_h": 0.5 + i * 0.1,
            })
            upsert_body_metrics(self.conn, {
                "date": d, "weight_kg": 72.0 - i * 0.1, "src": "manual",
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_collect_marks_insufficient(self):
        data = correlate.collect(self.conn, min_samples=10)
        self.assertTrue(data["pairs"])
        for p in data["pairs"]:
            self.assertLess(p["n"], 10)
            self.assertFalse(p["sufficient"])
            self.assertIsNone(p["r"])
            self.assertIsNone(p["strength"])

    def test_render_observation_no_numeric_conclusion(self):
        data = correlate.collect(self.conn, min_samples=10)
        text = correlate.render(data)
        self.assertIn("样本不足，仅作观察", text)
        self.assertIn("相关≠因果", text)
        # 不得出现相关系数数字结论
        self.assertNotIn("相关系数 r=", text)
        self.assertNotIn("r=+", text)
        self.assertNotIn("r=-", text)


class TestCorrelateSufficient(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.conn = init_db(db_path=self.db)
        # 12 天：睡眠与训练量正相关
        for i in range(12):
            d = f"2026-09-{i + 1:02d}"
            upsert(self.conn, {
                "date": d,
                "sleep_h": 6.0 + i * 0.15,
                "exercise_min": 5.0 + i * 3.0,
                "diet_kcal": 1800.0,
                "learn_h": 1.0,
            })
            upsert_body_metrics(self.conn, {
                "date": d, "weight_kg": 72.0, "src": "manual",
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_collect_emits_scripted_r(self):
        data = correlate.collect(self.conn, min_samples=10)
        sleep_ex = next(
            p for p in data["pairs"] if p["label"] == "睡眠 ↔ 训练量"
        )
        self.assertTrue(sleep_ex["sufficient"])
        self.assertEqual(sleep_ex["n"], 12)
        self.assertIsNotNone(sleep_ex["r"])
        # 独立复算：不得手写数字进断言期望以外的「文案」
        xs = [6.0 + i * 0.15 for i in range(12)]
        ys = [5.0 + i * 3.0 for i in range(12)]
        expected = correlate.pearson(xs, ys)
        self.assertAlmostEqual(sleep_ex["r"], round(expected, 3), places=3)

    def test_render_has_r_when_sufficient(self):
        text = correlate.render(correlate.collect(self.conn))
        self.assertIn("相关系数 r=", text)
        self.assertIn("相关不等于因果", text)
        self.assertNotIn("样本不足，仅作观察", text)


class TestCorrelateCli(unittest.TestCase):
    def test_route_registered(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("correlate", ROUTES)

    def test_main_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = correlate.main(["-h"])
        self.assertEqual(rc, 0)
        self.assertIn("correlate", buf.getvalue())

    def test_main_json_with_temp_db(self):
        d = tempfile.mkdtemp()
        try:
            db = os.path.join(d, "t.db")
            conn = init_db(db_path=db)
            upsert(conn, {"date": "2026-09-01", "sleep_h": 7.0})
            conn.commit()
            conn.close()
            with mock.patch(
                "review_tool.reports.correlate.init_db",
                lambda: init_db(db_path=db),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = correlate.main(["--json"])
                self.assertEqual(rc, 0)
                out = buf.getvalue()
                self.assertIn('"pairs"', out)
                self.assertIn('"sufficient": false', out)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
