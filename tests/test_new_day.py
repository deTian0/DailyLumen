"""new_day 模块测试：输出目录、填值、清空规则、幂等。

重点回归：旧版靠硬编码正则清模板里的示例正文，模板一改就静默失效。
新版改为「通用 data 块清空 + <!--clear--> 标记」，本测试锁死这两条。
"""
import os
import shutil
import tempfile
import unittest
from datetime import date
from unittest import mock

from review_tool.pipeline import new_day as nd

TEMPLATE = """# 每日复盘 · YYYY-MM-DD（星期X）

## 一、日常打卡

**晨间（起床后）**

- [x] 补剂：CoQ10 ×1 ＋ Exia 早3
- [x] 护肤
- [ ] 早餐 08:00–09:00

<!--clear-->
这一段是模板示例，生成时必须清掉。
- 示例 bullet
<!--/clear-->

## 附录 · 系统数据

```data
日期: 2026-01-01
星期: 一
训练日: yes
睡眠时长_h: 7.5
一句话总结: 旧示例
```
"""


class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.tpl = os.path.join(self.dir, "模板.md")
        with open(self.tpl, "w", encoding="utf-8") as f:
            f.write(TEMPLATE)
        self.out = os.path.join(self.dir, "out")
        self._p1 = mock.patch.object(nd, "TEMPLATE_PATH", self.tpl)
        self._p2 = mock.patch.object(nd, "GENERATED_DIR", self.out)
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _gen(self, d=date(2026, 3, 5), **kw):
        path = nd.generate(d, **kw)
        with open(path, encoding="utf-8") as f:
            return path, f.read()

    def test_output_path_is_month_archived(self):
        """输出必须落到 复盘/YYYY-MM/，不能散落在根目录。"""
        path, _ = self._gen()
        self.assertEqual(
            os.path.normpath(path),
            os.path.normpath(os.path.join(self.out, "2026-03", "2026-03-05.md")),
        )

    def test_title_and_fields_filled(self):
        _, text = self._gen()
        self.assertIn("# 每日复盘 · 2026-03-05（星期四）", text)
        self.assertIn("日期: 2026-03-05", text)
        self.assertIn("星期: 四", text)

    def test_data_block_values_cleared(self):
        _, text = self._gen()
        for stale in ("训练日: yes", "睡眠时长_h: 7.5", "一句话总结: 旧示例", "日期: 2026-01-01"):
            self.assertNotIn(stale, text)
        # 键名必须保留，否则用户不知道要填什么
        for key in ("训练日:", "睡眠时长_h:", "一句话总结:"):
            self.assertIn(key, text)

    def test_checkboxes_reset(self):
        _, text = self._gen()
        self.assertNotIn("- [x]", text)
        self.assertIn("- [ ] 补剂：CoQ10 ×1 ＋ Exia 早3", text)
        self.assertIn("- [ ] 护肤", text)

    def test_clear_marker_blocks_removed(self):
        _, text = self._gen()
        self.assertNotIn("这一段是模板示例", text)
        self.assertNotIn("<!--clear-->", text)
        self.assertNotIn("示例 bullet", text)

    def test_skips_existing_without_force(self):
        first, text1 = self._gen()
        second, text2 = self._gen()
        self.assertEqual(first, second)
        self.assertEqual(text1, text2)

    def test_force_overwrites(self):
        path, _ = self._gen()
        with open(path, "w", encoding="utf-8") as f:
            f.write("被改坏了")
        _, text = self._gen(force=True)
        self.assertIn("# 每日复盘 · 2026-03-05", text)

    def test_generated_file_is_parsable(self):
        """生成的空文件应能被 parse 识别出日期（否则入库会静默跳过）。"""
        from review_tool.pipeline.parse import parse_text
        _, text = self._gen()
        row = parse_text(text)
        self.assertEqual(row["date"], "2026-03-05")
        self.assertEqual(row["weekday"], "四")

    def test_template_change_does_not_break_clearing(self):
        """改模板里 data 块的字段名，清空逻辑依然生效（不再依赖硬编码字段清单）。"""
        with open(self.tpl, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.replace(
                "睡眠时长_h: 7.5", "睡眠时长_h: 7.5\n全新字段_xx: 示例值"))
        _, text = self._gen()
        self.assertNotIn("示例值", text)
        self.assertIn("全新字段_xx:", text)


if __name__ == "__main__":
    unittest.main()
