"""体征侧车：parse → ingest → body_metrics；重建回归逐字段 0 差异。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.pipeline.ingest import ingest_path
from review_tool.pipeline.parse import parse_text
from review_tool.storage.db import (
    BODY_COLUMNS,
    init_db,
    load_body_metrics,
    upsert_body_metrics,
)

_MD = """# 每日复盘 · 2026-10-10（星期五）

## 一、日常打卡
- [x] 护肤

## 附录 · 系统数据

```data
日期: 2026-10-10
星期: 星期五
训练日: 是
睡眠时长_h: 7.0
体重_kg: 72.5
体脂率: 18.2
腰围_cm: 81.0
```
"""

_MD_PARTIAL = """# 每日复盘 · 2026-10-11（星期六）

```data
日期: 2026-10-11
体重_kg: 72.0
```
"""


class TestParseBodySidecar(unittest.TestCase):
    def test_body_fields_go_to_sidecar_not_row(self):
        row = parse_text(_MD)
        self.assertNotIn("weight_kg", row)
        self.assertNotIn("body_fat_pct", row)
        self.assertNotIn("waist_cm", row)
        side = row["_body_metrics"]
        self.assertEqual(side["weight_kg"], 72.5)
        self.assertEqual(side["body_fat_pct"], 18.2)
        self.assertEqual(side["waist_cm"], 81.0)

    def test_empty_body_fields_no_sidecar(self):
        text = """```data
日期: 2026-10-12
体重_kg:
体脂率:
腰围_cm:
```"""
        row = parse_text(text)
        self.assertNotIn("_body_metrics", row)


class TestIngestBody(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)
        self.md = os.path.join(self.root, "2026-10-10.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(_MD)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ingest_writes_body_metrics(self):
        ok = ingest_path(self.conn, self.md)
        self.assertTrue(ok)
        rows = load_body_metrics(self.conn)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["date"], "2026-10-10")
        self.assertEqual(r["weight_kg"], 72.5)
        self.assertEqual(r["body_fat_pct"], 18.2)
        self.assertEqual(r["waist_cm"], 81.0)
        self.assertEqual(r["src"], "manual")
        # 不进 daily_reviews
        cols = {d[1] for d in self.conn.execute("PRAGMA table_info(daily_reviews)")}
        self.assertNotIn("weight_kg", cols)

    def test_coalesce_protects_existing(self):
        ingest_path(self.conn, self.md)
        # 重写 md：只留体重空 + 腰围新值 —— 保护模式下体重应保留
        partial = os.path.join(self.root, "2026-10-10b.md")
        with open(partial, "w", encoding="utf-8") as f:
            f.write("""```data
日期: 2026-10-10
腰围_cm: 82.0
```""")
        # 侧车只有腰围 → 仍会 upsert；体重应为 COALESCE 保留
        ingest_path(self.conn, partial)
        r = load_body_metrics(self.conn)[0]
        self.assertEqual(r["weight_kg"], 72.5)
        self.assertEqual(r["waist_cm"], 82.0)


class TestBodyRebuild(unittest.TestCase):
    """删库 → 只用 md 从零重建 → body_metrics 逐字段 0 差异。"""

    def test_rebuild_zero_diff(self):
        root = tempfile.mkdtemp()
        try:
            md_dir = os.path.join(root, "md")
            os.makedirs(md_dir)
            files = {
                "2026-10-10.md": _MD,
                "2026-10-11.md": _MD_PARTIAL,
            }
            for name, content in files.items():
                with open(os.path.join(md_dir, name), "w", encoding="utf-8") as f:
                    f.write(content)

            db1 = os.path.join(root, "a.db")
            conn1 = init_db(db_path=db1)
            for name in sorted(files):
                ingest_path(conn1, os.path.join(md_dir, name))
            snap1 = {
                tuple(r[c] for c in BODY_COLUMNS)
                for r in load_body_metrics(conn1)
            }
            conn1.close()

            db2 = os.path.join(root, "b.db")
            conn2 = init_db(db_path=db2)
            for name in sorted(files):
                ingest_path(conn2, os.path.join(md_dir, name))
            snap2 = {
                tuple(r[c] for c in BODY_COLUMNS)
                for r in load_body_metrics(conn2)
            }
            conn2.close()

            self.assertEqual(snap1, snap2)
            self.assertEqual(len(snap1), 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestUpsertBodyCoalesce(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.conn = init_db(db_path=os.path.join(self.root, "t.db"))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_none_does_not_erase(self):
        upsert_body_metrics(self.conn, {
            "date": "2026-10-01", "weight_kg": 70.0, "src": "scale",
        })
        upsert_body_metrics(self.conn, {
            "date": "2026-10-01", "weight_kg": None, "body_fat_pct": 20.0,
            "src": "manual",
        })
        self.conn.commit()
        r = load_body_metrics(self.conn)[0]
        self.assertEqual(r["weight_kg"], 70.0)
        self.assertEqual(r["body_fat_pct"], 20.0)
        self.assertEqual(r["src"], "manual")


if __name__ == "__main__":
    unittest.main()
