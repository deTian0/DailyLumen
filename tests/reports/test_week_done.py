"""M43 week-done：空周 / 有完成项 / 与单日三件事合计一致。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from review_tool.reports import week_done
from review_tool.storage.db import init_db, upsert

_MD = """# 每日复盘 · {day}

## 二、今日三件事

- 完成 A 方案
- 修好 B 模块

## 三、一个改进点

- 少刷手机
"""


class TestExtract(unittest.TestCase):
    def test_extract_bullets(self):
        items = week_done.extract_three_things(_MD.format(day="2026-11-03"))
        self.assertEqual(items, ["完成 A 方案", "修好 B 模块"])

    def test_empty_section(self):
        self.assertEqual(week_done.extract_three_things("# x\n"), [])


class TestCollectRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.md_dir = os.path.join(self.tmp, "复盘", "2026-11")
        os.makedirs(self.md_dir)
        self.conn = init_db(self.db)
        # ISO week for 2026-11-02 (Mon) .. 11-08 = 45
        for day, things in (
            ("2026-11-02", True),
            ("2026-11-03", True),
            ("2026-11-04", False),
        ):
            path = os.path.join(self.md_dir, f"{day}.md")
            body = _MD.format(day=day) if things else f"# {day}\n\n## 二、今日三件事\n\n"
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            upsert(self.conn, {
                "date": day, "weekday": "一",
                "iso_week": 45, "month": 202611,
                "raw_path": path,
                "health_score": 5, "work_score": 5,
                "learn_score": 5, "life_score": 5, "system_score": 5.0,
            })
        # clickup_done 两天
        self.conn.execute(
            "INSERT INTO clickup_done "
            "(date, task_id, list_id, name, owner, minutes, subject, is_self) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2026-11-02", "t1", "L1", "工单甲", "me", 30, "工作", 1),
        )
        self.conn.execute(
            "INSERT INTO clickup_done "
            "(date, task_id, list_id, name, owner, minutes, subject, is_self) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2026-11-03", "t2", "L1", "工单乙", "me", 45, "工作", 1),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_week(self):
        data = week_done.collect(self.conn, iso_week=1, year=2026)
        text = week_done.render(data)
        self.assertIn("两侧皆空", text)
        self.assertEqual(data["clickup_total"], 0)
        self.assertEqual(data["three_total"], 0)

    def test_with_items(self):
        data = week_done.collect(self.conn, iso_week=45, year=2026)
        self.assertEqual(data["clickup_total"], 2)
        self.assertEqual(data["three_total"], 4)  # 2 天 × 2 条
        text = week_done.render(data)
        self.assertIn("工单甲", text)
        self.assertIn("完成 A 方案", text)
        self.assertIn("本周做成了什么", text)

    def test_three_sum_matches_days(self):
        data = week_done.collect(self.conn, iso_week=45, year=2026)
        total = sum(len(d["items"]) for d in data["three_things"])
        self.assertEqual(total, data["three_total"])

    def test_main_and_route(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("week-done", ROUTES)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = week_done.main(["45", "--db", self.db])
        self.assertEqual(rc, 0)
        self.assertIn("W45", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
