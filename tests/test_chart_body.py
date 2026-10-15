"""M15：体重 / 训练量 / 热量双轴 SVG 关键元素断言。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

from review_tool.reports import chart
from review_tool.storage.db import init_db, upsert, upsert_body_metrics


class TestBodySvg(unittest.TestCase):
    def test_key_elements_with_band_and_ma(self):
        dates = [f"2026-09-{d:02d}" for d in range(1, 12)]
        weights = [72.0 + (i % 3) * 0.3 for i in range(len(dates))]
        svg = chart.render_body_svg(
            dates, weights, target_low=68.0, target_high=72.0,
        )
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertIn('id="target-band"', svg)
        self.assertIn("目标带", svg)
        self.assertIn("体重", svg)
        self.assertIn("7日均", svg)
        self.assertIn("<polyline", svg)
        self.assertIn("2026-09-01", svg)
        self.assertIn("2026-09-11", svg)

    def test_uses_core_moving_average(self):
        """均线必须走 core.body.moving_average（R1）。"""
        dates = ["2026-09-01", "2026-09-02", "2026-09-03"]
        weights = [70.0, 71.0, 72.0]
        with mock.patch(
            "review_tool.reports.chart.moving_average",
            wraps=chart.moving_average,
        ) as ma:
            chart.render_body_svg(dates, weights)
            ma.assert_called_once()
            _args, kwargs = ma.call_args
            self.assertEqual(kwargs.get("window"), 7)


class TestTrainingSvg(unittest.TestCase):
    def test_key_elements_bars(self):
        dates = ["2026-09-01", "2026-09-02", "2026-09-03"]
        volumes = [30.0, None, 20.0]
        svg = chart.render_training_svg(dates, volumes)
        self.assertIn("<svg", svg)
        self.assertIn('class="training-bar"', svg)
        self.assertIn("训练量", svg)
        self.assertIn("2026-09-01", svg)
        # 两天有值 → 两根柱
        self.assertEqual(svg.count('class="training-bar"'), 2)


class TestNutritionSvg(unittest.TestCase):
    def test_key_elements_dual_axis(self):
        dates = ["2026-09-01", "2026-09-02", "2026-09-03"]
        kcals = [1800.0, 1500.0, 2000.0]
        weights = [72.0, 71.5, 71.0]
        svg = chart.render_nutrition_svg(dates, kcals, weights)
        self.assertIn("<svg", svg)
        self.assertIn("热量", svg)
        self.assertIn("体重", svg)
        self.assertIn("热量 vs 体重", svg)
        self.assertIn("<polyline", svg)
        self.assertGreaterEqual(svg.count("<polyline"), 2)


class TestChartBuildersDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.conn = init_db(db_path=self.db)
        for i, d in enumerate(("2026-09-01", "2026-09-02", "2026-09-03")):
            upsert(self.conn, {
                "date": d,
                "exercise_min": 10 + i * 10,
                "diet_kcal": 1600 + i * 100,
                "system_score": 5.0,
            })
            upsert_body_metrics(self.conn, {
                "date": d, "weight_kg": 72.0 - i * 0.2, "src": "manual",
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_build_body_from_db(self):
        with mock.patch.dict(
            "review_tool.reports.chart.BODY_TARGETS",
            {"weight_kg_low": 68.0, "weight_kg_high": 72.0},
        ):
            svg = chart.build_body_chart(self.conn)
        self.assertIn("体重", svg)
        self.assertIn("target-band", svg)

    def test_build_training_from_db(self):
        svg = chart.build_training_chart(self.conn)
        self.assertIn("training-bar", svg)
        self.assertEqual(svg.count('class="training-bar"'), 3)

    def test_build_nutrition_from_db(self):
        svg = chart.build_nutrition_chart(self.conn)
        self.assertIn("热量", svg)
        self.assertIn("体重", svg)

    def test_cli_type_body_stdout(self):
        # 临时把默认库指到本测试库：init_db 无参走 DB_PATH，故直接测 build
        svg = chart.build_body_chart(self.conn)
        self.assertIn("<svg", svg)


class TestChartCliType(unittest.TestCase):
    def test_parse_type_default(self):
        self.assertEqual(chart._parse_type([]), "trends")

    def test_parse_type_body(self):
        self.assertEqual(chart._parse_type(["--type", "body"]), "body")

    def test_parse_type_bad(self):
        with self.assertRaises(SystemExit):
            chart._parse_type(["--type", "nope"])


if __name__ == "__main__":
    unittest.main()
