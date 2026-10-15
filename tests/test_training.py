"""训练明细解析 / 合计 / exercise_min 派生（M10）。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.core.training import (
    parse_item_line,
    parse_meta_line,
    parse_section,
    sum_minutes,
    volume_stable,
    week_completion_ok,
)
from review_tool.pipeline.ingest import ingest_path
from review_tool.pipeline.parse import parse_text
from review_tool.storage.db import (
    ITEM_COLUMNS,
    SESSION_COLUMNS,
    init_db,
    load_training,
)


class TestParseItemFormats(unittest.TestCase):
    """五种明细行格式各一例。"""

    def test_sets_reps(self):
        it = parse_item_line("- 俯卧撑 4×20")
        self.assertIsNotNone(it)
        self.assertEqual(it["item_key"], "俯卧撑")
        self.assertEqual(it["sets"], 4)
        self.assertEqual(it["reps"], 20)
        self.assertIsNone(it["load_kg"])
        self.assertIsNotNone(it["minutes"])  # 由 per_minute 折算

    def test_sets_reps_load(self):
        it = parse_item_line("- 卧推 3×12 @40kg")
        self.assertIsNotNone(it)
        self.assertEqual(it["item_key"], "卧推")
        self.assertEqual(it["sets"], 3)
        self.assertEqual(it["reps"], 12)
        self.assertEqual(it["load_kg"], 40.0)

    def test_minutes_min(self):
        it = parse_item_line("- 跑步 20min")
        self.assertIsNotNone(it)
        self.assertEqual(it["item_key"], "跑步")
        self.assertEqual(it["minutes"], 20.0)
        self.assertIsNone(it["sets"])

    def test_minutes_cn(self):
        it = parse_item_line("跑步 20分钟")
        self.assertIsNotNone(it)
        self.assertEqual(it["minutes"], 20.0)

    def test_sets_seconds(self):
        it = parse_item_line("- 平板支撑 3×60s")
        self.assertIsNotNone(it)
        self.assertEqual(it["item_key"], "平板支撑")
        self.assertEqual(it["sets"], 3)
        self.assertEqual(it["minutes"], 3.0)  # 3×60s = 3min

    def test_meta_line(self):
        meta = parse_meta_line("- 计划：A-胸背｜来源：练练")
        self.assertEqual(meta["plan_name"], "A-胸背")
        self.assertEqual(meta["src"], "lianlian")


_SECTION = """# 每日复盘 · 2026-10-14（星期二）

## 二、今日三件事
- 其他事

## 附录 · 训练明细

- 计划：A-胸背｜来源：练练
- 俯卧撑 4×20
- 卧推 3×12 @40kg
- 平板支撑 3×60s
- 跑步 20min

## 附录 · 系统数据

```data
日期: 2026-10-14
星期: 星期二
训练日: 是
睡眠时长_h: 7.0
运动时长_min:
```
"""

_SECTION_WITH_EXERCISE = """# 每日复盘 · 2026-10-15（星期三）

## 附录 · 训练明细

- 计划：B-腿｜来源：手填
- 深蹲 3×15
- 跑步 30min

```data
日期: 2026-10-15
训练日: 是
运动时长_min: 45
```
"""


class TestParseSection(unittest.TestCase):
    def test_full_section(self):
        sess = parse_section(_SECTION)
        self.assertIsNotNone(sess)
        self.assertEqual(sess["plan_name"], "A-胸背")
        self.assertEqual(sess["src"], "lianlian")
        self.assertEqual(len(sess["items"]), 4)
        self.assertIsNotNone(sess["total_min"])
        self.assertGreater(sess["total_min"], 0)

    def test_sum_minutes(self):
        items = [
            {"minutes": 3.0},
            {"minutes": 20.0},
            {"minutes": None},
        ]
        self.assertEqual(sum_minutes(items), 23)


class TestExerciseDerive(unittest.TestCase):
    """R2：字段为空 → derived；字段有值 → 不叠加、src=record。"""

    def test_empty_field_derives_from_training(self):
        row = parse_text(_SECTION)
        self.assertIn("_training", row)
        self.assertEqual(row["exercise_src"], "derived")
        self.assertEqual(row["exercise_min"], row["_training"]["total_min"])
        self.assertIn("训练明细合计", row.get("_exercise_detail", ""))

    def test_filled_field_not_overlaid(self):
        row = parse_text(_SECTION_WITH_EXERCISE)
        self.assertEqual(row["exercise_src"], "record")
        self.assertEqual(row["exercise_min"], 45)
        # 明细仍解析，但不改时长
        self.assertIn("_training", row)
        self.assertNotEqual(row["_training"]["total_min"], 45)


class TestIngestTraining(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)
        self.md = os.path.join(self.root, "2026-10-14.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(_SECTION)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ingest_writes_two_tables(self):
        ok = ingest_path(self.conn, self.md)
        self.assertTrue(ok)
        data = load_training(self.conn, date="2026-10-14")
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["plan_name"], "A-胸背")
        self.assertEqual(data["sessions"][0]["src"], "lianlian")
        self.assertEqual(len(data["items"]), 4)
        keys = {r["item_key"] for r in data["items"]}
        self.assertEqual(keys, {"俯卧撑", "卧推", "平板支撑", "跑步"})

    def test_rebuild_zero_diff(self):
        """两表重建逐字段 0 差异。"""
        root = tempfile.mkdtemp()
        try:
            md = os.path.join(root, "day.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write(_SECTION)
            snaps = []
            for name in ("a.db", "b.db"):
                path = os.path.join(root, name)
                conn = init_db(db_path=path)
                ingest_path(conn, md)
                data = load_training(conn)
                sess = {
                    tuple(r[c] for c in SESSION_COLUMNS)
                    for r in data["sessions"]
                }
                items = {
                    tuple(r[c] for c in ITEM_COLUMNS)
                    for r in data["items"]
                }
                snaps.append((sess, items))
                conn.close()
            self.assertEqual(snaps[0], snaps[1])
            self.assertEqual(len(snaps[0][0]), 1)
            self.assertEqual(len(snaps[0][1]), 4)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestCoachHelpers(unittest.TestCase):
    def test_volume_stable(self):
        self.assertTrue(volume_stable([100, 100, 100]))
        self.assertFalse(volume_stable([100, 200, 50]))

    def test_week_completion(self):
        ok = week_completion_ok(4, 5, min_ratio=0.8)
        self.assertTrue(ok["ok"])
        no = week_completion_ok(2, 5, min_ratio=0.8)
        self.assertFalse(no["ok"])


if __name__ == "__main__":
    unittest.main()
