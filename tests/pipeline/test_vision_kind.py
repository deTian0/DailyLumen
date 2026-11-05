"""llm-vision --kind 分模板：白名单裁剪 + prompt 分型。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from review_tool.pipeline import vision_intake as vi
from review_tool.pipeline import deepseek as ds

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

SAMPLE_MD = """# 每日复盘 · 2099-01-06（星期二）

## 附录 · 系统数据

```data
日期: 2099-01-06
星期: 星期二
睡眠时长_h:
饮食热量_kcal:
手机屏幕_h:
```
"""


def _vision_client(content: str) -> ds.Client:
    def urlopen(req, timeout=None):
        class R:
            def read(self_inner):
                return json.dumps({
                    "choices": [{"message": {"content": content}}],
                }).encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return R()

    return ds.Client("sk-fake", mode="deepseek", urlopen=urlopen)


class TestKindFilter(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(vi.normalize_vision_kind("DIET"), "diet")
        with self.assertRaises(ValueError):
            vi.normalize_vision_kind("food")

    def test_filter_drops_cross_fields(self):
        raw = {
            "饮食热量_kcal": 1800,
            "睡眠时长_h": 7.0,
            "手机屏幕_h": 3.5,
        }
        diet = vi.filter_fields_for_kind(raw, "diet")
        self.assertIn("饮食热量_kcal", diet)
        self.assertNotIn("睡眠时长_h", diet)
        self.assertNotIn("手机屏幕_h", diet)

        sleep = vi.filter_fields_for_kind(raw, "sleep")
        self.assertIn("睡眠时长_h", sleep)
        self.assertNotIn("饮食热量_kcal", sleep)

        screen = vi.filter_fields_for_kind(raw, "screen")
        self.assertEqual(set(screen), {"手机屏幕_h"})

    def test_prompts_mention_kind(self):
        sys_diet = vi._vision_system_for("diet")
        self.assertIn("diet", sys_diet)
        self.assertIn("饮食", sys_diet)
        self.assertIn("不要写睡眠", sys_diet)
        sys_screen = vi._vision_system_for("screen")
        self.assertIn("手机屏幕_h", sys_screen)


class TestKindIntake(unittest.TestCase):
    def test_screen_kind_keeps_only_phone(self):
        # 模型故意串了饮食字段；kind=screen 应裁掉
        payload = json.dumps({
            "手机屏幕_h": 4.2,
            "饮食热量_kcal": 2000,
            "睡眠时长_h": 8,
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as td:
            img = os.path.join(td, "a.png")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            md = os.path.join(td, "2099-01-06.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write(SAMPLE_MD)
            result = vi.run_vision_intake(
                img,
                "2099-01-06",
                md_path=md,
                write=False,
                mode="deepseek",
                client=_vision_client(payload),
                kind="screen",
                skip_runlog=True,
            )
            self.assertEqual(result["kind"], "screen")
            self.assertIn("手机屏幕_h", result["fields"])
            self.assertNotIn("饮食热量_kcal", result["fields"])
            self.assertNotIn("睡眠时长_h", result["fields"])

    def test_parse_kind_flag(self):
        opts = vi._parse([
            "--image", "x.png", "--date", "2099-01-06", "--kind", "sleep",
        ])
        self.assertEqual(opts["kind"], "sleep")

    def test_help_mentions_kind(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vi.main(["-h"])
        self.assertEqual(rc, 0)
        self.assertIn("--kind", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
