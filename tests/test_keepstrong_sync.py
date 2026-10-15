"""M18：练练 → md 同步（幂等 / 空数据 / 不碰手写）+ ingest 入库。"""
from __future__ import annotations

import os
import tempfile
import unittest

from review_tool.core.training import parse_section
from review_tool.pipeline.ingest import ingest_path
from review_tool.pipeline.keepstrong_sync import (
    BEGIN,
    END,
    apply_training_block,
    records_to_block,
    resolve_ks_item,
    seconds_to_min,
    sync_markdown,
    write_sync,
)
from review_tool.pipeline.parse import parse_text
from review_tool.storage.db import get_conn, init_db, load_training

SAMPLE_MD = """# 每日复盘 · 2026-10-01（星期四）

## 二、今日三件事

1. 测试

## 附录 · 系统数据

```data
日期: 2026-10-01
星期: 星期四
训练日: 1
运动时长_min:
睡眠时长_h: 7
健康分: 5
工作分: 5
学习分: 5
生活分: 5
```
"""

REC_OCT1 = {
    "dayStr": "20261001",
    "trainingType": "strength",
    "durationSeconds": 161,
    "calorie": 9,
    "actions": [],
}


class TestHelpers(unittest.TestCase):
    def test_seconds_to_min(self):
        self.assertEqual(seconds_to_min(161), 3)
        self.assertEqual(seconds_to_min(30), 1)
        self.assertIsNone(seconds_to_min(0))

    def test_resolve_ks_action_map_and_slugify(self):
        key, label = resolve_ks_item(
            "壶铃深蹲", "act_x", action_map={"act_x": "goblet_squat"}
        )
        self.assertEqual(key, "goblet_squat")
        key2, _ = resolve_ks_item("全新未知动作XYZ", None, action_map={})
        self.assertTrue(key2)
        self.assertNotEqual(key2, "unknown")


class TestRecordsToBlock(unittest.TestCase):
    def test_empty_records_returns_none(self):
        self.assertIsNone(records_to_block([]))
        self.assertIsNone(records_to_block(None))

    def test_empty_actions_emits_duration_line(self):
        block = records_to_block([REC_OCT1])
        self.assertIsNotNone(block)
        self.assertIn(BEGIN, block)
        self.assertIn(END, block)
        self.assertIn("来源：练练", block)
        self.assertIn("训练 3min", block)


class TestApplyIdempotent(unittest.TestCase):
    def test_replace_not_append(self):
        block1 = records_to_block([REC_OCT1])
        text1 = apply_training_block(SAMPLE_MD, block1)
        self.assertEqual(text1.count(BEGIN), 1)
        block2 = records_to_block([
            {**REC_OCT1, "durationSeconds": 300, "name": "加长"}
        ])
        text2 = apply_training_block(text1, block2)
        self.assertEqual(text2.count(BEGIN), 1)
        self.assertEqual(text2.count("来源：练练"), 1)
        self.assertIn("训练 5min", text2)
        self.assertNotIn("训练 3min", text2)

    def test_manual_section_untouched(self):
        manual = SAMPLE_MD.replace(
            "## 附录 · 系统数据",
            "## 附录 · 训练明细\n\n"
            "- 计划：自练｜来源：手填\n"
            "- 俯卧撑 3×10\n\n"
            "## 附录 · 系统数据",
        )
        block = records_to_block([REC_OCT1])
        out = apply_training_block(manual, block)
        self.assertIn("来源：手填", out)
        self.assertIn("俯卧撑 3×10", out)
        self.assertIn(BEGIN, out)
        self.assertIn("来源：练练", out)
        # 手写行仍在标记块之外
        self.assertLess(out.index("来源：手填"), out.index(BEGIN))

    def test_no_empty_section_when_no_records(self):
        out, summary = sync_markdown(SAMPLE_MD, records=[])
        self.assertFalse(summary["training_written"])
        self.assertNotIn("训练明细", out)


class TestSyncIngest(unittest.TestCase):
    def test_twice_no_dup_rows(self):
        with tempfile.TemporaryDirectory() as td:
            md = os.path.join(td, "2026-10-01.md")
            with open(md, "wb") as f:
                f.write(SAMPLE_MD.replace("\r\n", "\n").encode("utf-8"))
            db = os.path.join(td, "t.db")
            for _ in range(2):
                write_sync(md, records=[REC_OCT1], day_str="20261001", dry_run=False)
                conn = init_db(db)
                try:
                    ingest_path(conn, md)
                finally:
                    conn.close()
            with open(md, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text.count(BEGIN), 1)
            self.assertEqual(text.count("来源：练练"), 1)
            parsed = parse_section(text)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["src"], "lianlian")
            conn = get_conn(db)
            try:
                got = load_training(conn, date="2026-10-01")
            finally:
                conn.close()
            self.assertEqual(len(got["sessions"]), 1)
            self.assertEqual(got["sessions"][0]["src"], "lianlian")
            # 空 actions → 一行「训练」明细
            self.assertEqual(len(got["items"]), 1)

    def test_rebuild_from_md_zero_diff(self):
        with tempfile.TemporaryDirectory() as td:
            md = os.path.join(td, "2026-10-01.md")
            with open(md, "wb") as f:
                f.write(SAMPLE_MD.encode("utf-8"))
            write_sync(md, records=[REC_OCT1], day_str="20261001", dry_run=False)
            db1 = os.path.join(td, "a.db")
            db2 = os.path.join(td, "b.db")
            for db in (db1, db2):
                conn = init_db(db)
                try:
                    ingest_path(conn, md)
                finally:
                    conn.close()
            c1, c2 = get_conn(db1), get_conn(db2)
            try:
                a = load_training(c1, date="2026-10-01")
                b = load_training(c2, date="2026-10-01")
            finally:
                c1.close()
                c2.close()
            self.assertEqual(a["sessions"], b["sessions"])
            self.assertEqual(a["items"], b["items"])

    def test_r2_derive_only_when_exercise_empty(self):
        row = parse_text(
            apply_training_block(SAMPLE_MD, records_to_block([REC_OCT1]))
        )
        self.assertEqual(row.get("exercise_src"), "derived")
        self.assertEqual(row.get("exercise_min"), 3)
        filled = SAMPLE_MD.replace("运动时长_min:", "运动时长_min: 40")
        row2 = parse_text(
            apply_training_block(filled, records_to_block([REC_OCT1]))
        )
        self.assertEqual(row2.get("exercise_min"), 40)
        self.assertEqual(row2.get("exercise_src"), "record")


if __name__ == "__main__":
    unittest.main()
