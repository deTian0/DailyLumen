"""B6：summarize(diagnose) 与 is_healthy / render 结论对拍。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.reports.doctor import diagnose, is_healthy, render, summarize
from review_tool.storage.db import init_db, upsert


class TestDoctorSummarize(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.md_dir = os.path.join(self.root, "每日复盘")
        os.makedirs(os.path.join(self.md_dir, "复盘", "2026-09"), exist_ok=True)
        os.makedirs(os.path.join(self.md_dir, "收件箱"), exist_ok=True)
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self, today="2026-09-22"):
        return diagnose(db_path=self.db, input_dir=self.md_dir, today=today)

    def test_empty_db_unhealthy_and_conclusion_matches_render(self):
        r = self._run()
        s = summarize(r)
        self.assertFalse(is_healthy(r))
        self.assertEqual(s["healthy"], is_healthy(r))
        self.assertEqual(s["conclusion"], "存在待处理项，见上方标记")
        text = render(r, encoding="utf-8")
        self.assertIn(s["conclusion"], text)
        by_id = {it["id"]: it for it in s["items"]}
        self.assertEqual(by_id["rows"]["status"], "crit")
        self.assertTrue(by_id["rows"]["affects_health"])

    def test_healthy_fixture_aligns_six_gates(self):
        day = "2026-09-21"
        path = os.path.join(self.md_dir, "复盘", "2026-09", f"{day}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# x\n")
        upsert(self.conn, {"date": day})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        s = summarize(r)
        self.assertEqual(s["healthy"], is_healthy(r))
        self.assertTrue(s["healthy"])
        self.assertEqual(s["conclusion"], "数据健康")
        text = render(r, encoding="utf-8")
        self.assertIn("数据健康", text)
        gates = {
            "integrity", "schema", "rows",
            "not_ingested", "orphan_in_db", "habit_track_overlap",
        }
        for it in s["items"]:
            if it["id"] in gates:
                self.assertEqual(it["status"], "ok", it)
                self.assertTrue(it["affects_health"], it["id"])

    def test_not_ingested_marks_gate_and_unhealthy(self):
        path = os.path.join(self.md_dir, "复盘", "2026-09", "2026-09-20.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# x\n")
        # 另有一条已入库，避免 rows=0 抢先
        upsert(self.conn, {"date": "2026-09-19"})
        day_md = os.path.join(self.md_dir, "复盘", "2026-09", "2026-09-19.md")
        with open(day_md, "w", encoding="utf-8") as f:
            f.write("# x\n")
        self.conn.commit()
        r = self._run()
        s = summarize(r)
        self.assertFalse(is_healthy(r))
        self.assertEqual(s["healthy"], False)
        by_id = {it["id"]: it for it in s["items"]}
        self.assertEqual(by_id["not_ingested"]["status"], "warn")
        self.assertGreater(by_id["not_ingested"]["count"], 0)
        self.assertIn("ingest", by_id["not_ingested"]["advice"] or "")


if __name__ == "__main__":
    unittest.main()
