"""sync_docs 测试：数据块分数行重写、六章表格重写、旧式原文跳过、幂等。"""
import os
import tempfile
import unittest

from review_tool.pipeline.sync_docs import (
    fmt_score,
    render_data_lines,
    render_six_section,
    rewrite_data_block,
    rewrite_six_section,
    sync_file,
)

SCORES = {
    "health_score": 6, "work_score": 7, "learn_score": 1,
    "life_score": None, "system_score": None,
}

DOC = """# 2026-09-19 复盘

## 二、今日三件事

1. 做事

## 六、四维评分

> 旧引语。

| 维度 | 分数 | 状态 | 待补字段 |
| -- | -- | -- | -- |
| 健康 | 5 | ✅ 已计算 | — |
| 工作 | 3 | ✅ 已计算 | — |

> 工作分拆解：深度工作 0h < ok 档(2.0) → **3**。

---

## 七、AI 评价与建议

正文。

## 附录 · 系统数据

```data
日期: 2026-09-19
星期: 星期六
深度工作_h: 0
学习投入_h: 0
一句话总结: 总结文本。
健康分: 5
工作分: 3
学习分: 3
生活分: 3
系统分: 3.75
```
"""

# 语雀九段式原文：六章标题带「（1 – 10）」，不参与回写
LEGACY = """## 六、四维评分（1 – 10）

| 维度 | 分数 |
|------|------|
| health（健康） | 7 |
| work（工作） | 10 |

> 今日系统分 = (7 + 10 + 7 + 5) / 4 = 7.25/10

## 七、偏离分析

```data
日期: 2026-07-16
健康分: 7
工作分: 10
```
"""


class TestFmtScore(unittest.TestCase):
    def test_int_float_none(self):
        self.assertEqual(fmt_score(6), "6")
        self.assertEqual(fmt_score(6.0), "6")
        self.assertEqual(fmt_score(4.75), "4.75")
        self.assertEqual(fmt_score(5.5), "5.5")
        self.assertEqual(fmt_score(None), "")


class TestDataBlock(unittest.TestCase):
    def test_render_lines(self):
        self.assertEqual(
            render_data_lines(SCORES),
            ["健康分: 6", "工作分: 7", "学习分: 1", "生活分: ", "系统分: "],
        )

    def test_lines_appended_after_summary(self):
        out = rewrite_data_block(DOC, SCORES)
        block = out.split("```data")[1].split("```")[0]
        idx_summary = block.index("一句话总结")
        idx_health = block.index("健康分")
        self.assertGreater(idx_health, idx_summary)
        # 旧分数行已被替换，不重复
        self.assertEqual(block.count("健康分:"), 1)
        self.assertIn("工作分: 7", block)
        self.assertIn("学习分: 1", block)

    def test_no_block_untouched(self):
        text = "# 无数据块\n\n正文"
        self.assertEqual(rewrite_data_block(text, SCORES), text)

    def test_idempotent(self):
        once = rewrite_data_block(DOC, SCORES)
        self.assertEqual(rewrite_data_block(once, SCORES), once)


class TestSixSection(unittest.TestCase):
    def test_missing_dimension_marked(self):
        out = render_six_section(SCORES)
        self.assertIn("| 健康 | 6 / 10 | ✅ 已评 | — |", out)
        self.assertIn("| 生活 | 无法评分 | ⚠️ 缺数据 | 生活投入_h |", out)
        self.assertIn("| 系统 | 无法评分 | ⚠️ 四维不全 | 生活 |", out)

    def test_rewrite_replaces_intro_table_and_breakdown(self):
        out = rewrite_six_section(DOC, SCORES)
        self.assertIn("标「无法评分」表示该维度缺少必要字段", out)
        self.assertIn("| 工作 | 7 / 10 | ✅ 已评 | — |", out)
        self.assertNotIn("拆解", out)          # 旧口径的拆解叙述被一并替换
        self.assertNotIn("> 旧引语。", out)
        self.assertIn("## 七、AI 评价与建议", out)   # 后续章节完好
        self.assertIn("---\n\n## 七、AI 评价与建议", out)  # 分隔线保留

    def test_legacy_nine_section_skipped(self):
        self.assertEqual(rewrite_six_section(LEGACY, SCORES), LEGACY)

    def test_idempotent(self):
        once = rewrite_six_section(DOC, SCORES)
        self.assertEqual(rewrite_six_section(once, SCORES), once)


class TestSyncFile(unittest.TestCase):
    def test_writes_only_when_changed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "2026-09-19.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(DOC)
            self.assertTrue(sync_file(path, SCORES))
            self.assertFalse(sync_file(path, SCORES))   # 第二次无需再写
            with open(path, encoding="utf-8") as f:
                self.assertIn("健康分: 6", f.read())

    def test_legacy_doc_only_block_synced(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "2026-07-16.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(LEGACY)
            self.assertTrue(sync_file(path, SCORES))
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("（1 – 10）", text)      # 六章原样
            self.assertIn("| work（工作） | 10 |", text)


if __name__ == "__main__":
    unittest.main()
