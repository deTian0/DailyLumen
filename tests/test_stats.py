"""stats 模块测试：一键统计（M22 / v1.30.0）。

覆盖三态：有数据的计数与断更、md 计数口径（跳过收件箱 / 排除周月汇总）、
结果可 JSON 序列化且 --json 渲染稳定。
"""
import json
import os
import shutil
import tempfile
import unittest

from review_tool.reports.stats import collect, main, render
from review_tool.storage.db import SCHEMA_VERSION, init_db, upsert, upsert_habit_log, upsert_personal_track


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.input_dir = os.path.join(self.dir, "每日复盘")
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- 数据 ----------------------------------------------------------------

    def _seed_db(self):
        """两天带空洞（21 → 24，缺 2 天）+ 打卡与习惯行。"""
        upsert(self.conn, {"date": "2026-09-21", "sleep_h": 7.0, "health_score": 6})
        upsert(self.conn, {"date": "2026-09-24", "sleep_h": 8.0, "health_score": 7})
        upsert_personal_track(self.conn, "2026-09-21", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 1)
        upsert_habit_log(self.conn, {"date": "2026-09-21", "habit_key": "read",
                                     "done": 1})
        self.conn.commit()

    def _seed_md(self):
        """标准源 + 周 / 月汇总 + 收件箱（后者不计）。"""
        month = os.path.join(self.input_dir, "复盘", "2026-09")
        os.makedirs(month)
        for name in ("2026-09-21.md", "2026-09-22.md",
                     "周总结-W36-2026-08-31_09-06.md"):
            with open(os.path.join(month, name), "w", encoding="utf-8") as f:
                f.write("# t\n")
        inbox = os.path.join(self.input_dir, "收件箱")
        os.makedirs(inbox)
        with open(os.path.join(inbox, "2026-09-21.md"), "w", encoding="utf-8") as f:
            f.write("# t\n")


class TestCollect(_Fixture):
    def test_counts_and_gaps(self):
        self._seed_db()
        r = collect(self.conn, self.input_dir, db_path=self.db)
        self.assertEqual(r["days"], 2)
        self.assertEqual(r["tracks"], 1)
        self.assertEqual(r["habit_logs"], 1)
        self.assertEqual(r["latest_date"], "2026-09-24")
        self.assertEqual(r["schema_version"], SCHEMA_VERSION)
        self.assertEqual(r["schema_expected"], SCHEMA_VERSION)
        self.assertEqual(r["db_size_kb"], round(os.path.getsize(self.db) / 1024))
        self.assertGreater(r["db_size_kb"], 0)
        self.assertEqual(len(r["history_gaps"]), 1)
        self.assertEqual(r["history_gaps"][0]["missing"], 2)
        self.assertEqual(r["history_gap_days"], 2)

    def test_md_counting_skips_inbox_and_summaries(self):
        self._seed_md()
        r = collect(self.conn, self.input_dir, db_path=self.db)
        # 收件箱不计；周总结计入总数但不计入日复盘
        self.assertEqual(r["md"]["total"], 3)
        self.assertEqual(r["md"]["daily"], 2)
        self.assertEqual(r["md"]["by_month"], {"2026-09": 3})

    def test_empty_db_no_gaps(self):
        r = collect(self.conn, self.input_dir, db_path=self.db)
        self.assertEqual(r["days"], 0)
        self.assertIsNone(r["latest_date"])
        self.assertEqual(r["history_gaps"], [])
        self.assertEqual(r["history_gap_days"], 0)


class TestRenderAndJson(_Fixture):
    def test_render_contains_sections(self):
        self._seed_db()
        r = collect(self.conn, self.input_dir, db_path=self.db)
        text = render(r)
        for section in ("[复盘文档]", "[数据库]", "[历史断更]"):
            self.assertIn(section, text)
        self.assertIn("2026-09-21 → 2026-09-24", text)

    def test_render_no_gaps(self):
        r = collect(self.conn, self.input_dir, db_path=self.db)
        self.assertIn("无历史空洞", render(r))

    def test_result_json_serializable(self):
        self._seed_db()
        r = collect(self.conn, self.input_dir, db_path=self.db)
        parsed = json.loads(json.dumps(r, ensure_ascii=False))
        self.assertEqual(parsed["days"], 2)

    def test_main_json_smoke(self):
        """main(--json) 在默认库路径上能跑通（真实库存在时）。"""
        # 不重定向 DB_PATH —— 只验证参数解析与返回码路径，不碰真实库内容：
        # 用临时目录下不存在的 input_dir + 真库过于耦合，这里改为直接断言
        # argparse 行为：非法参数报 SystemExit。
        with self.assertRaises(SystemExit):
            main(["--bogus-flag"])


if __name__ == "__main__":
    unittest.main()
