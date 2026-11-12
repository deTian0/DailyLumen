"""D2：今日训练日只读状态聚合。"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from review_tool.api import training_day as td
from review_tool.pipeline.keepstrong_sync import BEGIN, END

DAY = "2026-11-12"

MD = f"""# 每日复盘 · {DAY}

## 附录 · 系统数据

```data
日期: {DAY}
训练日:
```
"""

MD_SYNCED = MD + f"\n{BEGIN}\n- 计划：全身A｜来源：练练\n{END}\n"


class _Ks:
    def __init__(self, n=1):
        self.n = n

    def iter_training_records(self, a, b):
        return [{"status": "completed"}] * self.n


class TestTrainingDayStatus(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.md = os.path.join(self.dir, f"{DAY}.md")
        p = mock.patch(
            "review_tool.pipeline.keepstrong_sync.review_md_path",
            lambda _d, root=None: self.md,
        )
        p.start()
        self.addCleanup(p.stop)

    def test_completed_needs_sync(self):
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(MD)
        out = td.training_day_status(DAY, ks_client=_Ks(1))
        self.assertTrue(out["keepstrong"]["completed"])
        self.assertTrue(out["md_exists"])
        self.assertFalse(out["md_synced"])
        self.assertEqual(out["next"], "sync_md")
        self.assertIn("focus=keepstrong-sync", out["links"]["sync"])

    def test_synced_habit_optional(self):
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(MD_SYNCED)
        out = td.training_day_status(DAY, ks_client=_Ks(1))
        self.assertTrue(out["md_synced"])
        self.assertEqual(out["next"], "habit_optional")
        self.assertIn("focus=clickup-habit", out["links"]["habit"])

    def test_no_completed_no_habit_nudge(self):
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(MD_SYNCED)
        out = td.training_day_status(DAY, ks_client=_Ks(0))
        self.assertFalse(out["keepstrong"]["completed"])
        self.assertEqual(out["next"], "none")

    def test_missing_md(self):
        out = td.training_day_status(DAY, ks_client=_Ks(1))
        self.assertFalse(out["md_exists"])
        self.assertEqual(out["next"], "create_md")


if __name__ == "__main__":
    unittest.main()
