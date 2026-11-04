"""monthly 深评聚合测试（M27 / v1.33.0）：聚合段、月窗口、图表落盘。"""
import os
import tempfile
import unittest

from review_tool.reports.analyze import collect as analyze_collect
from review_tool.reports.correlate import collect as correlate_collect
from review_tool.reports.fuse import find_fuses
from review_tool.reports.monthly import build_month_deep
from review_tool.storage.db import init_db, upsert


def _seed(conn):
    """两天数据（同月 202610）：分数 + 客观字段，足够出聚合与熔断窗口。"""
    upsert(conn, {"date": "2026-10-12", "health_score": 4, "work_score": 7,
                  "learn_score": 3, "life_score": 5, "system_score": 4.75,
                  "sleep_h": 6.13, "phone_h": 13.12, "deepwork_h": 4.0,
                  "diet_kcal": 1637, "learn_h": 0.5})
    upsert(conn, {"date": "2026-10-13", "health_score": 6, "work_score": 7,
                  "learn_score": 3, "life_score": 3, "system_score": 4.75,
                  "sleep_h": 8.80, "phone_h": 11.10, "deepwork_h": 4.0,
                  "diet_kcal": 1658, "learn_h": 0.5})
    conn.commit()


class TestMonthlyDeep(unittest.TestCase):
    """build_month_deep：段落齐全、图表落盘、数字可溯源。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.conn = init_db(db_path=self.db)
        _seed(self.conn)
        self.out = os.path.join(self.tmp, "exports")
        self.res = build_month_deep(self.conn, 202610, input_dir=self.tmp,
                                    db_path=self.db, out_dir=self.out)

    def tearDown(self):
        self.conn.close()

    def test_returns_paths_and_files_exist(self):
        self.assertIsNotNone(self.res)
        self.assertTrue(os.path.isfile(self.res["md_path"]))
        self.assertTrue(os.path.isfile(self.res["chart_path"]))
        self.assertEqual(os.path.basename(self.res["md_path"]), "month-deep-202610.md")
        self.assertEqual(
            os.path.basename(self.res["chart_path"]), "month-202610.svg")
        self.assertTrue(os.path.isdir(os.path.join(self.out, "charts")))

    def test_md_sections_and_md_reference(self):
        md = self.res["md"]
        for sec in ("## 一、月份概览", "## 二、本月趋势图",
                    "## 三、月窗口跨维相关", "## 四、熔断信号", "## 五、库快照"):
            self.assertIn(sec, md)
        self.assertIn("](charts/month-202610.svg)", md)  # 相对引用
        self.assertIn("month 202610 --deep", md)         # 复现命令
        self.assertIn("相关≠因果", md)                    # correlate 免责声明沿用

    def test_numbers_traceable_to_single_commands(self):
        md = self.res["md"]
        s = analyze_collect(self.conn, "month=?", (202610,), "月份 202610")
        self.assertIn(f"**{s['days']} 天**", md)
        sys_txt = f"{s['system_avg']:.2f}".rstrip("0").rstrip(".")
        self.assertIn(f"**{sys_txt}**", md)
        snap_days = self.conn.execute(
            "SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
        self.assertIn(f"入库 **{snap_days}** 天", md)

    def test_month_window_correlate_and_fuse(self):
        # 月窗口与全窗口在本种子上：correlate date_count 不同（月内 2 天）
        cor_m = correlate_collect(self.conn, month=202610)
        self.assertEqual(cor_m["date_count"], 2)
        fz_m = find_fuses(self.conn, month=202610)
        self.assertEqual(fz_m["records"], 2)
        # 空月窗口：无记录、无信号
        fz_empty = find_fuses(self.conn, month=202501)
        self.assertEqual(fz_empty["records"], 0)
        self.assertEqual(fz_empty["absolute"], [])

    def test_no_data_month_returns_none(self):
        self.assertIsNone(build_month_deep(
            self.conn, 202501, input_dir=self.tmp, db_path=self.db,
            out_dir=self.out))

    def test_chart_svg_contains_month_dates(self):
        with open(self.res["chart_path"], encoding="utf-8") as f:
            svg = f.read()
        self.assertIn("2026-10-12", svg)
        self.assertNotIn("2026-09-", svg)  # 窗口只含本月
        self.assertTrue(svg.lstrip().startswith("<svg"))


if __name__ == "__main__":
    unittest.main()
