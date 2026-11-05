"""收工摘要 I/O：llm-day / doctor 装配。"""
from __future__ import annotations

import os
import tempfile
import unittest

from review_tool.core.ai_draft import LLM_PENDING_HTML
from review_tool.reports import day_close as dcio
from review_tool.storage.db import init_db, upsert

_MD_GREEN = """# 复盘

```data
日期: 2099-02-02
体重_kg: 70
饮食热量_kcal: 1900
睡眠时长_h: 7
运动时长_min: 40
```
"""

_MD_PENDING = (
    f"{LLM_PENDING_HTML}\n# 复盘\n\n```data\n"
    "日期: 2099-02-01\n饮食热量_kcal: 1800\n```\n"
)


class TestAssessDayReady(unittest.TestCase):
    def test_pending_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "t.db")
            md = os.path.join(td, "2099-02-01.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write(_MD_PENDING)
            conn = init_db(db)
            conn.close()
            st = dcio.assess_day_ready(
                "2099-02-01", md_path=md, db_path=db, input_dir=td,
            )
            self.assertTrue(st["pending_draft"])
            self.assertFalse(st["ingested"])
            self.assertEqual(st["light"], "red")
            self.assertIn("体重_kg", st["missing_focus"])

    def test_green_path(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "t.db")
            md = os.path.join(td, "2099-02-02.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write(_MD_GREEN)
            conn = init_db(db)
            try:
                upsert(conn, {
                    "date": "2099-02-02",
                    "weekday": "日",
                    "iso_week": 5,
                    "month": 209902,
                })
                conn.commit()
            finally:
                conn.close()
            st = dcio.assess_day_ready(
                "2099-02-02", md_path=md, db_path=db, input_dir=td,
            )
            self.assertTrue(st["ingested"], st)
            self.assertIn("体重_kg", st["filled"], st)
            self.assertEqual(st["light"], "green", st)


class TestCloseSummaryHelpers(unittest.TestCase):
    def test_llm_day_summary(self):
        text = dcio.close_summary_for_llm_day({
            "day": "2099-02-03",
            "written": True,
            "fields": {"饮食热量_kcal": 1},
            "vision": {
                "images": ["a.png"],
                "written": True,
                "classification": {
                    "filled": ["饮食热量_kcal"],
                    "missing": ["睡眠时长_h"],
                    "optional_missing": ["体脂率"],
                },
            },
            "review": {"written": False},
        })
        self.assertIn("读到:", text)
        self.assertIn("体脂率（可选）", text)
        self.assertIn("llm-finalize", text)


if __name__ == "__main__":
    unittest.main()
