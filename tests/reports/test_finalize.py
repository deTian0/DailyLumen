"""M38 finalize：dry-run / 指定日收口 / 不触及未点名日。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from review_tool.reports import finalize
from review_tool.storage.db import init_db, upsert


def _md(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


_DAY_TMPL = """# 每日复盘 · {day}（星期一）

```
日期: {day}
健康分: {h}
工作分: {w}
学习分: {l}
生活分: {lf}
系统分: {s}
```

## 六、四维评分

| 维度 | 分数 | 状态 | 待补字段 |
| --- | --- | --- | --- |
| 健康 | {h} | - | - |
| 工作 | {w} | - | - |
| 学习 | {l} | - | - |
| 生活 | {lf} | - | - |
"""


class TestFinalize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.md_dir = os.path.join(self.tmp, "复盘", "2026-11")
        self.conn = init_db(self.db)
        # 字段足以重算：故意把库分写成与字段不符
        upsert(self.conn, {
            "date": "2026-11-01", "weekday": "星期日",
            "sleep_h": 7.5, "sleep_quality": 90, "bedtime": 1350,
            "phone_h": 2.0, "exercise_min": 30, "training_day": 1,
            "diet_kcal": 1800, "carbs_g": 200, "fat_g": 50, "protein_g": 100,
            "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 2.0,
            "health_score": 1, "work_score": 1, "learn_score": 1,
            "life_score": 1, "system_score": 1.0,  # 故意错
            "raw_path": os.path.join(self.md_dir, "2026-11-01.md"),
        })
        upsert(self.conn, {
            "date": "2026-11-02", "weekday": "星期一",
            "sleep_h": 7.5, "sleep_quality": 90, "bedtime": 1350,
            "phone_h": 2.0, "exercise_min": 30, "training_day": 1,
            "diet_kcal": 1800, "carbs_g": 200, "fat_g": 50, "protein_g": 100,
            "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 2.0,
            "health_score": 1, "work_score": 1, "learn_score": 1,
            "life_score": 1, "system_score": 1.0,
            "raw_path": os.path.join(self.md_dir, "2026-11-02.md"),
        })
        self.conn.commit()
        for day in ("2026-11-01", "2026-11-02"):
            _md(os.path.join(self.md_dir, f"{day}.md"),
                _DAY_TMPL.format(day=day, h=1, w=1, l=1, lf=1, s=1.0))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_no_write(self):
        before = dict(self.conn.execute(
            "SELECT date, system_score FROM daily_reviews").fetchall())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = finalize.main([
                "--date", "2026-11-01", "--db", self.db,
                "--input-dir", self.tmp,
            ])
        self.assertEqual(rc, 0)
        self.assertIn("试算模式", buf.getvalue())
        after = dict(self.conn.execute(
            "SELECT date, system_score FROM daily_reviews").fetchall())
        self.assertEqual(before, after)

    def test_apply_only_named_day(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = finalize.main([
                "--date", "2026-11-01", "--apply", "--db", self.db,
                "--input-dir", self.tmp,
            ])
        self.assertEqual(rc, 0)
        # 重新打开看库（apply 用的是另一连接）
        conn = init_db(self.db)
        s1 = conn.execute(
            "SELECT system_score FROM daily_reviews WHERE date='2026-11-01'"
        ).fetchone()[0]
        s2 = conn.execute(
            "SELECT system_score FROM daily_reviews WHERE date='2026-11-02'"
        ).fetchone()[0]
        conn.close()
        self.assertNotEqual(s1, 1.0)  # 已收口
        self.assertEqual(s2, 1.0)     # 未点名日不动

    def test_missing_day_rc_1(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = finalize.main([
                "--date", "2026-01-01", "--db", self.db,
                "--input-dir", self.tmp,
            ])
        self.assertEqual(rc, 1)

    def test_route_registered(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("finalize", ROUTES)


if __name__ == "__main__":
    unittest.main()
