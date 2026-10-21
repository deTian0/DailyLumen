"""core.body 纯规则 + reports.body 汇聚 / 渲染。"""
from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock

from review_tool.core import body as body_core
from review_tool.reports import body as body_report
from review_tool.storage.db import init_db, upsert_body_metrics


class TestBmi(unittest.TestCase):
    def test_height_none(self):
        self.assertIsNone(body_core.bmi(70.0, None))

    def test_weight_none(self):
        self.assertIsNone(body_core.bmi(None, 170.0))

    def test_normal(self):
        # 70kg / 1.75m ≈ 22.9 → 正常
        v = body_core.bmi(70.0, 175.0)
        self.assertEqual(v, 22.9)
        self.assertEqual(body_core.bmi_band(v), "正常")

    def test_overweight(self):
        # 80kg / 1.70m ≈ 27.7 → 超重
        v = body_core.bmi(80.0, 170.0)
        self.assertEqual(v, 27.7)
        self.assertEqual(body_core.bmi_band(v), "超重")

    def test_obese(self):
        # 90kg / 1.70m ≈ 31.1 → 肥胖
        v = body_core.bmi(90.0, 170.0)
        self.assertEqual(v, 31.1)
        self.assertEqual(body_core.bmi_band(v), "肥胖")

    def test_underweight(self):
        v = body_core.bmi(50.0, 175.0)
        self.assertEqual(body_core.bmi_band(v), "偏瘦")

    def test_band_none(self):
        self.assertIsNone(body_core.bmi_band(None))


class TestMovingAverage(unittest.TestCase):
    def test_skips_none_in_denominator(self):
        series = [70.0, None, 72.0]
        ma = body_core.moving_average(series, window=3)
        self.assertEqual(ma[0], 70.0)
        self.assertEqual(ma[1], 70.0)  # 只有一个非空
        self.assertEqual(ma[2], 71.0)  # (70+72)/2

    def test_all_none(self):
        self.assertEqual(body_core.moving_average([None, None], 7), [None, None])


class TestWeeklyDelta(unittest.TestCase):
    def test_basic(self):
        # 前 7 日均 70，后 7 日均 71 → +1
        prior = [70.0] * 7
        recent = [71.0] * 7
        self.assertEqual(body_core.weekly_delta(prior + recent), 1.0)

    def test_insufficient(self):
        self.assertIsNone(body_core.weekly_delta([70.0]))
        self.assertIsNone(body_core.weekly_delta([70.0] * 7))  # 无 prior


class TestDistanceAndEta(unittest.TestCase):
    def test_in_band(self):
        self.assertEqual(body_core.distance_to_target(72.0, 70.0, 75.0), 0.0)

    def test_below(self):
        self.assertEqual(body_core.distance_to_target(68.0, 70.0, 75.0), -2.0)

    def test_above(self):
        self.assertEqual(body_core.distance_to_target(78.0, 70.0, 75.0), 3.0)

    def test_unconfigured(self):
        self.assertIsNone(body_core.distance_to_target(70.0, None, 75.0))

    def test_eta_toward_target(self):
        # 80 → 75，每周 -1 → 5 周
        self.assertEqual(body_core.eta_weeks(80.0, 75.0, -1.0), 5.0)

    def test_eta_wrong_sign(self):
        self.assertIsNone(body_core.eta_weeks(80.0, 75.0, 1.0))

    def test_eta_zero_delta(self):
        self.assertIsNone(body_core.eta_weeks(80.0, 75.0, 0.0))


class TestBodyReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = self.tmp + "/t.db"
        self.conn = init_db(db_path=self.db)
        upsert_body_metrics(self.conn, {
            "date": "2026-10-01", "weight_kg": 72.0,
            "body_fat_pct": 18.0, "waist_cm": 80.0, "src": "manual",
        })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_collect_unconfigured_height(self):
        with mock.patch.dict("review_tool.reports.body.PROFILE", {"height_cm": None}):
            data = body_report.collect(self.conn)
        self.assertIsNone(data["bmi"])
        text = body_report.render(data)
        self.assertIn("未配置身高", text)

    def test_collect_with_height(self):
        with mock.patch.dict(
            "review_tool.reports.body.PROFILE", {"height_cm": 175.0}, clear=False
        ):
            # PROFILE 是 dict，patch.dict 合并
            data = body_report.collect(self.conn)
        self.assertEqual(data["bmi"], 23.5)
        self.assertEqual(data["bmi_band"], "正常")

    def test_json_roundtrip(self):
        data = body_report.collect(self.conn)
        raw = json.dumps(data, ensure_ascii=False)
        self.assertIn("weight_kg", raw)


class TestTrendDirection(unittest.TestCase):
    """M23：周变化 → 趋势定性（down / up / flat）。"""

    def test_down(self):
        self.assertEqual(body_core.trend_direction(-0.40), "down")

    def test_up(self):
        self.assertEqual(body_core.trend_direction(0.40), "up")

    def test_flat_at_threshold(self):
        self.assertEqual(body_core.trend_direction(0.15), "flat")
        self.assertEqual(body_core.trend_direction(-0.15), "flat")
        self.assertEqual(body_core.trend_direction(0.0), "flat")

    def test_none(self):
        self.assertIsNone(body_core.trend_direction(None))

    def test_custom_threshold(self):
        self.assertEqual(body_core.trend_direction(0.30, threshold_kg=0.5), "flat")


class TestBodyAdvice(unittest.TestCase):
    """建议段：每条带依据数字；六类场景（带内×3 / 带上 / 带下 / 样本不足）。

    目标带 patch 成受控值 70–75 kg —— 不依赖个人真实配置（config 可随时改）。
    """

    BAND = {"weight_kg_low": 70.0, "weight_kg_high": 75.0}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = self.tmp + "/t.db"
        self.conn = init_db(db_path=self.db)
        patcher = mock.patch.dict(
            "review_tool.reports.body.BODY_TARGETS", self.BAND, clear=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, weights, start="2026-09-14"):
        import datetime as dt
        d0 = dt.date.fromisoformat(start)
        for i, w in enumerate(weights):
            upsert_body_metrics(self.conn, {
                "date": (d0 + dt.timedelta(days=i)).isoformat(),
                "weight_kg": w, "src": "manual",
            })
        self.conn.commit()

    def _collect_and_text(self):
        data = body_report.collect(self.conn)
        return data, body_report.render(data)

    def test_in_band_flat(self):
        self._seed([72.0] * 14)  # 带内（假设目标带 70–75），delta=0
        data, text = self._collect_and_text()
        self.assertEqual(data["trend_direction"], "flat")
        self.assertIn("趋势平稳（平台期）", text)
        self.assertIn("保持当前节奏", text)

    def test_in_band_down_warns_lower_bound(self):
        # 前 7 点 72.0，后 7 点 71.5 → delta = -0.5，下行
        self._seed([72.0] * 7 + [71.5] * 7)
        data, text = self._collect_and_text()
        self.assertEqual(data["trend_direction"], "down")
        self.assertIn("跌破下限", text)
        self.assertIn("周变化 -0.50 kg", text)

    def test_above_band_with_eta(self):
        # 前 7 点 78.0，后 7 点 76.0 → delta = -2.0，高于上限 1 kg，外推 0.5 周
        self._seed([78.0] * 7 + [76.0] * 7)
        data, text = self._collect_and_text()
        self.assertEqual(data["distance_to_target"], 1.0)
        self.assertIn("高于上限 1.00 kg", text)
        self.assertIn("周回到目标带", text)

    def test_above_band_wrong_direction(self):
        self._seed([76.0] * 7 + [78.0] * 7)  # 上行且带外
        _, text = self._collect_and_text()
        self.assertIn("先让趋势转向下行", text)

    def test_below_band_wrong_direction(self):
        self._seed([68.0] * 7 + [66.0] * 7)  # 下行且低于下限
        _, text = self._collect_and_text()
        self.assertIn("先让趋势转向上行", text)

    def test_insufficient_samples(self):
        self._seed([78.0] * 3)  # 无 prior 侧 → delta None；带外
        data, text = self._collect_and_text()
        self.assertIsNone(data["weekly_delta"])
        # 样本不足但带外：仍给位置提醒，不给趋势建议。
        # 门槛报「8 个观测」而非「两周」——一周称 2 次时两周只有 4 个点。
        self.assertIn("共 8 个观测", text)
        self.assertIn("现有 3 次", text)
        self.assertIn("还差 5 次", text)
        self.assertNotIn("趋势下行", text)
        self.assertNotIn("趋势上行", text)

    def test_insufficient_samples_no_gap_when_enough_obs(self):
        # 7 个观测仍缺 prior 侧（delta 需 ≥8），文案不应出现「还差」负值
        self._seed([78.0] * 7)
        _, text = self._collect_and_text()
        self.assertIn("现有 7 次，还差 1 次", text)

    def test_advice_in_json(self):
        self._seed([72.0] * 14)
        data = body_report.collect(self.conn)
        self.assertIn("trend_direction", json.dumps(data, ensure_ascii=False))


class TestBodyCheckConstraints(unittest.TestCase):
    """body_metrics CHECK 反面样本（负体重 / 体脂 80%）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = self.tmp + "/t.db"
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_negative_weight_rejected(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO body_metrics (date, weight_kg) VALUES ('2026-01-01', -1)"
            )

    def test_body_fat_80_rejected(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO body_metrics (date, body_fat_pct) VALUES ('2026-01-01', 80)"
            )


if __name__ == "__main__":
    unittest.main()
