"""L-3：llm-review（mock DeepSeek；mode 门禁；只写 md 不写库）。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from review_tool.pipeline import deepseek as ds
from review_tool.reports import llm_review as lr


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


SAMPLE_MD = """# 每日复盘 · 2099-01-05（星期一）

## 六、四维评分

| 维度 | 分数 |
| -- | -- |

## 七、AI 评价与建议

**评价**

- 旧内容

**建议**

1. 旧建议

## 附录 · 系统数据

```data
日期: 2099-01-05
星期: 星期一
睡眠时长_h: 7
```
"""


def _client_ok(text: str = "**评价**\n\n- 睡眠 7h 达标\n\n**建议**\n\n1. **23:00 熄灯**：目标 23:30 前睡") -> ds.Client:
    def urlopen(req, timeout=None):
        return _FakeResp({
            "choices": [{"message": {"content": text}}],
        })

    return ds.Client(
        "sk-test-fake",
        mode="deepseek",
        urlopen=urlopen,
    )


class TestApplyAiSection(unittest.TestCase):
    def test_replace_existing(self):
        section = lr.wrap_ai_draft("**评价**\n\n- x", day="2099-01-05", generated_at="t")
        out = lr.apply_ai_section(SAMPLE_MD, section)
        self.assertIn("草稿 / 待人审", out)
        self.assertIn("- x", out)
        self.assertNotIn("旧内容", out)
        self.assertIn("## 附录 · 系统数据", out)

    def test_insert_when_missing(self):
        md = "# t\n\n## 附录 · 系统数据\n\n```data\n日期: 2099-01-01\n```\n"
        section = lr.wrap_ai_draft("- a", day="2099-01-01", generated_at="t")
        out = lr.apply_ai_section(md, section)
        self.assertIn("## 七、AI 评价与建议", out)
        self.assertLess(out.index("七、AI"), out.index("附录"))


class TestModeGate(unittest.TestCase):
    def test_workbuddy_rejected(self):
        with self.assertRaises(ds.DeepSeekModeError) as ctx:
            lr.run_llm_review(
                "2099-01-05",
                mode="workbuddy",
                client=_client_ok(),
            )
        msg = str(ctx.exception)
        self.assertIn("workbuddy", msg)
        self.assertIn("daily-review-intake", msg)

    def test_main_workbuddy_rc2(self):
        with mock.patch.object(lr, "get_llm_mode", return_value="workbuddy"):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = lr.main(["2099-01-05"])
            self.assertEqual(rc, 2)
            self.assertIn("宿主", buf.getvalue())


class TestLlmReviewWrite(unittest.TestCase):
    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-01-05.md")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            with mock.patch.object(
                lr, "build_context",
                return_value={
                    "date": "2099-01-05",
                    "day": {"date": "2099-01-05", "sleep_h": 7},
                    "recent": [],
                    "recent_days": 0,
                    "avgs": {},
                    "flags": [],
                },
            ), mock.patch.object(
                lr, "render_markdown", return_value="# ctx\n- 睡眠 7h\n"
            ):
                result = lr.run_llm_review(
                    "2099-01-05",
                    md_path=path,
                    write=False,
                    mode="deepseek",
                    client=_client_ok(),
                    now=lambda: "2099-01-05 12:00",
                    skip_runlog=True,
                )
            self.assertFalse(result["written"])
            with open(path, encoding="utf-8") as f:
                self.assertIn("旧内容", f.read())

    def test_write_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-01-05.md")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            with mock.patch.object(
                lr, "build_context",
                return_value={
                    "date": "2099-01-05",
                    "day": {"date": "2099-01-05"},
                    "recent": [],
                    "recent_days": 0,
                    "avgs": {},
                    "flags": ["睡眠偏低"],
                },
            ), mock.patch.object(
                lr, "render_markdown", return_value="# ctx\n"
            ):
                result = lr.run_llm_review(
                    "2099-01-05",
                    md_path=path,
                    write=True,
                    mode="deepseek",
                    client=_client_ok(),
                    now=lambda: "2099-01-05 12:00",
                    skip_runlog=True,
                )
            self.assertTrue(result["written"])
            with open(path, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("草稿 / 待人审", got)
            self.assertIn("睡眠 7h 达标", got)
            self.assertNotIn("旧内容", got)

    def test_diff_preview_and_prompt_aligns_ai_review(self):
        self.assertIn("关注点", lr.SYSTEM_PROMPT)
        self.assertIn("勿另造评分", lr.SYSTEM_PROMPT)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-01-05.md")
            log = os.path.join(tmp, "last.json")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            with mock.patch.object(
                lr, "build_context",
                return_value={
                    "date": "2099-01-05",
                    "day": {"date": "2099-01-05", "sleep_h": 7},
                    "recent": [],
                    "recent_days": 0,
                    "avgs": {},
                    "flags": ["睡眠 6h 低于 7h 良好线"],
                },
            ), mock.patch.object(
                lr, "render_markdown", return_value="# ctx\n- 睡眠 7h\n"
            ):
                result = lr.run_llm_review(
                    "2099-01-05",
                    md_path=path,
                    write=False,
                    mode="deepseek",
                    client=_client_ok(),
                    now=lambda: "2099-01-05 12:00",
                    log_path=log,
                )
            self.assertIn("七、AI", result["diff_text"])
            self.assertIn("旧内容", result["old_section"])
            self.assertIn("草稿", result["section"])
            with open(log, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("llm-review", text)
            self.assertNotIn("sk-test", text)


if __name__ == "__main__":
    unittest.main()
