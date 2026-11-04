"""llm-day：一键日流程编排（mock；mode 门禁；无体脂闭环）。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from review_tool.pipeline import deepseek as ds
from review_tool.reports import llm_day as ld

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

SAMPLE_MD = """# 每日复盘 · 2099-03-01（星期五）

## 七、AI 评价与建议

**评价**

- 旧

## 附录 · 系统数据

```data
日期: 2099-03-01
星期: 星期五
饮食热量_kcal:
体重_kg:
体脂率:
睡眠时长_h:
```
"""


def _client_vision_then_chat(vision_json: str, review_text: str) -> ds.Client:
    state = {"n": 0}

    def urlopen(req, timeout=None):
        n = state["n"]
        state["n"] += 1
        # 第一次：vision；其后：chat（review）
        if n == 0:
            content = vision_json
        else:
            content = review_text

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


class TestLlmDayModeGate(unittest.TestCase):
    def test_workbuddy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "a.png")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with self.assertRaises(ds.DeepSeekModeError):
                ld.run_llm_day(
                    img, "2099-03-01", mode="workbuddy",
                    client=_client_vision_then_chat("{}", "x"),
                    skip_runlog=True,
                )

    def test_main_workbuddy_rc2(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "a.png")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with mock.patch.object(ld, "get_llm_mode", return_value="workbuddy"):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = ld.main(["--image", img, "--date", "2099-03-01"])
                self.assertEqual(rc, 2)


class TestLlmDayNoBodyFatE2E(unittest.TestCase):
    def test_write_vision_without_body_fat(self):
        vision = json.dumps({
            "diet_kcal": 1750,
            "weight_kg": 70.1,
            "sleep_h": 7.2,
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "diet.png")
            md = os.path.join(tmp, "2099-03-01.md")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            result = ld.run_llm_day(
                img,
                "2099-03-01",
                md_path=md,
                write=True,
                review=False,
                mode="deepseek",
                client=_client_vision_then_chat(vision, "unused"),
                skip_runlog=True,
            )
            self.assertTrue(result["vision"]["written"])
            self.assertNotIn("体脂率", result["fields"])
            with open(md, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("饮食热量_kcal: 1750", got)
            self.assertIn("体重_kg: 70.1", got)
            self.assertNotRegex(got, r"体脂率:\s+\d")
            # 冒烟清理：删除临时目录即可（with 退出）

    def test_review_flag_writes_ai_section(self):
        vision = '{"饮食热量_kcal": 1800}'
        review = "**评价**\n\n- 热量已记\n\n**建议**\n\n1. **明天**：照常记录"
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "a.png")
            md = os.path.join(tmp, "2099-03-01.md")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            with mock.patch(
                "review_tool.reports.llm_review.build_context",
                return_value={
                    "date": "2099-03-01",
                    "day": {"date": "2099-03-01", "diet_kcal": 1800},
                    "recent": [],
                    "recent_days": 0,
                    "avgs": {},
                    "flags": [],
                },
            ), mock.patch(
                "review_tool.reports.llm_review.render_markdown",
                return_value="# ctx\n- 热量 1800\n",
            ):
                result = ld.run_llm_day(
                    img,
                    "2099-03-01",
                    md_path=md,
                    write=True,
                    review=True,
                    mode="deepseek",
                    client=_client_vision_then_chat(vision, review),
                    now=lambda: "2099-03-01 22:00",
                    skip_runlog=True,
                )
            self.assertTrue(result["vision"]["written"])
            self.assertTrue((result["review"] or {}).get("written"))
            with open(md, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("草稿 / 待人审", got)
            self.assertIn("热量已记", got)
            ai = got.split("七、AI")[1].split("附录")[0]
            self.assertNotIn("体脂率", ai)

    def test_prompt_forbids_body_fat_invention(self):
        from review_tool.reports import llm_review as lr
        self.assertIn("体脂率", lr.SYSTEM_PROMPT)
        self.assertIn("禁止编造", lr.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
