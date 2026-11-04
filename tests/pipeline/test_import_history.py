"""import_history 模块测试：前置块解析、日期元信息、渲染与输出路径。"""
import os
import shutil
import tempfile
import unittest

from review_tool.pipeline.import_history import (
    build_row,
    date_meta,
    out_path,
    parse_frontmatter,
    parse_prose_721,
    render,
    run,
)

FRONTMATTER_MD = """---
date: 2026-07-23
sleep_h: 6.83
sleep_quality: 88
exercise_min: 0
commute_done: no
diet_kcal: 1380
meals_count: 3
breakfast_on_time: yes
phone_h: 9.03
deepwork_h: 0
health_score: 4
work_score: 3
learn_score: 3
life_score: 5
---

## 一些正文

| 项目 | 值 |
| --- | --- |
| 入睡时间 | 00:13 |
"""

PROSE_MD = """# 每日复盘 · 2026-07-21

| 项目 | 值 |
| --- | --- |
| 睡眠时长 | 7.2 |
| 睡眠质量 | 未显示 |
| 运动时长 | 0 |
| 饮食热量 | 1500 |
| 三餐 | 早✓午✓晚✗ |
| 手机屏幕 | 8.5 |
| 通勤 | 完成 |

深度工作：3h

- [x] 早餐

| health（健康） | **5** |
| work（工作） | **5** |
| learn（学习） | **3** |
| life（生活） | **5** |
"""


class TestParseFrontmatter(unittest.TestCase):
    def test_extracts_fields(self):
        fm = parse_frontmatter(FRONTMATTER_MD)
        self.assertEqual(fm["date"], "2026-07-23")
        self.assertEqual(fm["sleep_h"], "6.83")

    def test_no_frontmatter(self):
        self.assertEqual(parse_frontmatter(PROSE_MD), {})


class TestDateMeta(unittest.TestCase):
    def test_training_day_from_config(self):
        # 2026-07-22 是周三 -> 训练日
        wd, train = date_meta("2026-07-22")
        self.assertEqual(wd, "星期三")
        self.assertEqual(train, 1)

    def test_rest_day(self):
        # 2026-07-23 是周四 -> 休息日
        wd, train = date_meta("2026-07-23")
        self.assertEqual(wd, "星期四")
        self.assertEqual(train, 0)


class TestBuildRow(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_frontmatter_row(self):
        row, _ = build_row(self._write("2026-07-23.md", FRONTMATTER_MD))
        self.assertEqual(row["date"], "2026-07-23")
        self.assertEqual(row["sleep_h"], 6.83)
        self.assertEqual(row["commute_done"], 0)
        self.assertEqual(row["bedtime"], 13)   # 00:13
        self.assertEqual(row["training_day"], 0)

    def test_prose_row(self):
        path = self._write("2026-07-21.md", PROSE_MD)
        row, _ = build_row(path)
        self.assertEqual(row["date"], "2026-07-21")
        self.assertEqual(row["meals_count"], 2)
        self.assertEqual(row["health_score"], 5)
        self.assertEqual(row["learn_score"], 3)
        self.assertIsNone(row["sleep_quality"])   # 「未显示」应转 None

    def test_unparsable_date(self):
        row, _ = build_row(self._write("no-date.md", "随便写点"))
        self.assertIsNone(row)

    def test_prose_helper_directly(self):
        row = parse_prose_721(PROSE_MD)
        self.assertEqual(row["phone_h"], 8.5)
        self.assertEqual(row["deepwork_h"], 3.0)


class TestRenderAndPath(unittest.TestCase):
    def test_out_path_is_month_archived(self):
        p = out_path("2026-07-23")
        parts = p.replace("\\", "/").split("/")
        self.assertEqual(parts[-2], "2026-07")     # 月份目录
        self.assertEqual(parts[-1], "2026-07-23.md")

    def test_render_contains_data_block(self):
        row = {
            "date": "2026-07-23", "weekday": "星期四", "training_day": 0,
            "sleep_h": 6.83, "bedtime": 13, "diet_kcal": 1380,
            "health_score": 4, "work_score": 3,
        }
        md = render(row, "原始正文")
        self.assertIn("```data", md)
        self.assertIn("日期: 2026-07-23", md)
        self.assertIn("入睡时间: 00:13", md)
        self.assertIn("原始正文", md)

    def test_rendered_is_parsable(self):
        from review_tool.pipeline.parse import parse_text
        row = {"date": "2026-07-23", "weekday": "星期四", "training_day": 0,
               "sleep_h": 6.83, "bedtime": 13}
        parsed = parse_text(render(row, "正文"))
        self.assertEqual(parsed["date"], "2026-07-23")
        self.assertEqual(parsed["bedtime"], 13)
        self.assertEqual(parsed["sleep_h"], 6.83)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.out = tempfile.mkdtemp()
        with open(os.path.join(self.src, "2026-07-23.md"), "w", encoding="utf-8") as f:
            f.write(FRONTMATTER_MD)

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)

    def test_check_only_writes_nothing(self):
        run(source_dir=self.src, check_only=True, out_root=self.out)
        self.assertEqual(os.listdir(self.out), [])

    def test_writes_file(self):
        run(source_dir=self.src, check_only=False, out_root=self.out)
        self.assertEqual(os.listdir(self.out), ["2026-07-23.md"])

    def test_missing_source_dir_returns_error(self):
        self.assertEqual(run(source_dir="", check_only=True), 2)


if __name__ == "__main__":
    unittest.main()
