"""new_day 模块测试：输出目录、填值、清空规则、幂等。

重点回归：旧版靠硬编码正则清模板里的示例正文，模板一改就静默失效。
新版改为「通用 data 块清空 + <!--clear--> 标记」，本测试锁死这两条。
"""
import contextlib
import io
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
        self.assertIn("星期: 星期四", text)

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
        self.assertEqual(row["weekday"], "星期四")

    def test_data_block_weekday_matches_title(self):
        """数据块星期必须与标题同为全称 —— 它直接落 DB 的 weekday 字段，
        单字会与归档文件（全称）和报告分组口径打架。"""
        _, text = self._gen()
        self.assertIn("# 每日复盘 · 2026-03-05（星期四）", text)
        self.assertIn("星期: 星期四", text)
        self.assertNotIn("星期: 四\n", text)

    def test_template_change_does_not_break_clearing(self):
        """改模板里 data 块的字段名，清空逻辑依然生效（不再依赖硬编码字段清单）。"""
        with open(self.tpl, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.replace(
                "睡眠时长_h: 7.5", "睡眠时长_h: 7.5\n全新字段_xx: 示例值"))
        _, text = self._gen()
        self.assertNotIn("示例值", text)
        self.assertIn("全新字段_xx:", text)


class TestFeatureSwitch(unittest.TestCase):
    """new-day 默认关闭（``config.FEATURES['new_day'] = False``，v1.6.1）。

    关闭时闸门必须**零副作用**：直接报错能被看见，而静默生成一份空模板不会 ——
    后者会让人以为「今天已经起了模板」，其实内容是空的。
    """

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

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = nd.main(argv)
        return rc, buf.getvalue()

    def test_disabled_by_default(self):
        """开关的默认态就是本次需求本身：默认关闭。"""
        from review_tool.config import FEATURES
        self.assertIs(FEATURES["new_day"], False)

    def test_main_refuses_and_writes_nothing_when_disabled(self):
        with mock.patch.dict(nd.FEATURES, {"new_day": False}):
            rc, out = self._run(["2026-03-05"])
        self.assertEqual(rc, 2, "关闭时应以非零退出码表明「没执行」")
        self.assertIn("已关闭", out)
        self.assertFalse(os.path.exists(self.out),
                         "关闭状态下不得创建任何目录或文件")

    def test_hint_points_at_manual_path_and_switch(self):
        """提示要能自解释：既说清手动怎么做，也说清去哪打开。"""
        self.assertIn("每日复盘模板.md", nd.DISABLED_HINT)
        self.assertIn("FEATURES", nd.DISABLED_HINT)

    def test_main_generates_when_enabled(self):
        with mock.patch.dict(nd.FEATURES, {"new_day": True}):
            rc, out = self._run(["2026-03-05"])
        self.assertEqual(rc, 0)
        self.assertIn("已生成", out)
        self.assertTrue(os.path.isfile(
            os.path.join(self.out, "2026-03", "2026-03-05.md")))

    def test_is_enabled_follows_config(self):
        with mock.patch.dict(nd.FEATURES, {"new_day": False}):
            self.assertFalse(nd.is_enabled())
        with mock.patch.dict(nd.FEATURES, {"new_day": True}):
            self.assertTrue(nd.is_enabled())

    def test_is_enabled_defaults_to_false_when_key_missing(self):
        """配置项被误删时按「关闭」处理 —— 宁可跑不动，也不要静默跑通。"""
        with mock.patch.dict(nd.FEATURES, {}, clear=True):
            self.assertFalse(nd.is_enabled())

    def test_generate_itself_is_not_gated(self):
        """闸门只装在命令入口；generate() 是纯函数，测试与调用方仍可直接复用。"""
        with mock.patch.dict(nd.FEATURES, {"new_day": False}):
            path = nd.generate(date(2026, 3, 6))
        self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
