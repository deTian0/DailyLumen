"""趋势图 SVG 测试（v1.10.0）：离线、零依赖。"""
import os
import shutil
import tempfile
import unittest

from review_tool.reports import chart
from review_tool.storage.db import init_db, upsert


class TestChart(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.conn = init_db(db_path=self.db)
        for i, d in enumerate(("2026-09-01", "2026-09-02", "2026-09-03")):
            upsert(self.conn, {
                "date": d,
                "system_score": 3.0 + i,
                "health_score": 4, "work_score": 5, "learn_score": 3, "life_score": 4,
                "sleep_h": 6.5 + i * 0.2, "phone_h": 10.0 - i,
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_svg_has_key_elements(self):
        svg = chart.build_chart(self.conn)
        self.assertIn("<svg", svg)
        self.assertIn("polyline", svg)
        self.assertIn("系统分", svg)
        self.assertIn("2026-09-01", svg)
        self.assertIn("2026-09-03", svg)
        self.assertIn("</svg>", svg)

    def test_write_and_reread(self):
        svg = chart.build_chart(self.conn)
        path = os.path.join(self.dir, "trends.svg")
        chart.write_chart(svg, path)
        with open(path, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("<polyline", body)
        self.assertEqual(body, svg)

    def test_empty_db_still_svg(self):
        empty = init_db(db_path=os.path.join(self.dir, "e.db"))
        try:
            svg = chart.build_chart(empty)
            self.assertIn("<svg", svg)
        finally:
            empty.close()


if __name__ == "__main__":
    unittest.main()
