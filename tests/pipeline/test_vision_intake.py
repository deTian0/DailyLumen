"""DeepSeek 读图 intake：mock Vision；写 md 数据块；mode 门禁；多图冲突 / 部分失败。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from review_tool.core import llm_contract as lc
from review_tool.pipeline import deepseek as ds
from review_tool.pipeline import vision_intake as vi

# 最小合法 PNG（1x1）；测试用，非用户隐私截图
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
睡眠时长_h: 6.5
饮食热量_kcal:
碳水_g:
体重_kg:
体脂率:
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


def _vision_client_sequence(contents: list[str]) -> ds.Client:
    """按调用顺序返回不同 content；超出则报错（模拟单图失败）。"""
    state = {"i": 0}

    def urlopen(req, timeout=None):
        idx = state["i"]
        state["i"] += 1
        if idx >= len(contents):
            raise ds.DeepSeekError("mock vision exhausted", status=500, retryable=False)
        payload = contents[idx]
        if payload is None:
            raise ds.DeepSeekError("mock per-image fail", status=502, retryable=True)

        class R:
            def read(self_inner):
                return json.dumps({
                    "choices": [{"message": {"content": payload}}],
                }).encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return R()

    return ds.Client("sk-fake", mode="deepseek", urlopen=urlopen)


class TestMergeContractFields(unittest.TestCase):
    def test_merge_updates_and_appends(self):
        out = lc.merge_data_block_fields(
            SAMPLE_MD,
            {"饮食热量_kcal": 1850, "体重_kg": 70.5, "脂肪_g": ""},
        )
        self.assertIn("饮食热量_kcal: 1850", out)
        self.assertIn("体重_kg: 70.5", out)
        self.assertIn("睡眠时长_h: 6.5", out)
        body = out.split("```data")[1].split("```")[0]
        self.assertNotRegex(body, r"脂肪_g:\s+\S")
        self.assertNotRegex(body, r"体脂率:\s+\d")


class TestVisionModeGate(unittest.TestCase):
    def test_workbuddy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "smoke.png")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with self.assertRaises(ds.DeepSeekModeError) as ctx:
                vi.run_vision_intake(
                    img, "2099-01-06", mode="workbuddy",
                    client=_vision_client("{}"),
                )
            self.assertIn("宿主", str(ctx.exception))

    def test_main_workbuddy_rc2(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "smoke.png")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with mock.patch.object(vi, "get_llm_mode", return_value="workbuddy"):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = vi.main(["--image", img, "--date", "2099-01-06"])
                self.assertEqual(rc, 2)
                self.assertIn("workbuddy", err.getvalue().lower() + err.getvalue())


class TestVisionIntakeWrite(unittest.TestCase):
    def test_write_contract_fields(self):
        payload = json.dumps({
            "diet_kcal": 1850,
            "碳水_g": 200,
            "体重_kg": 70.5,
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "smoke.png")
            md = os.path.join(tmp, "2099-01-06.md")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            result = vi.run_vision_intake(
                img,
                "2099-01-06",
                md_path=md,
                write=True,
                mode="deepseek",
                client=_vision_client(payload),
                skip_runlog=True,
            )
            self.assertTrue(result["written"])
            self.assertEqual(result["fields"]["饮食热量_kcal"], 1850)
            self.assertNotIn("体脂率", result["fields"])
            self.assertIn("体脂率", result["classification"]["optional_missing"])
            with open(md, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("饮食热量_kcal: 1850", got)
            self.assertIn("碳水_g: 200", got)
            self.assertIn("体重_kg: 70.5", got)
            self.assertIn("睡眠时长_h: 6.5", got)
            self.assertNotRegex(got, r"体脂率:\s+\d")

    def test_dry_run_no_write(self):
        payload = '{"饮食热量_kcal": 1000}'
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "smoke.png")
            md = os.path.join(tmp, "2099-01-06.md")
            with open(img, "wb") as f:
                f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            result = vi.run_vision_intake(
                img, "2099-01-06", md_path=md, write=False,
                mode="deepseek", client=_vision_client(payload),
                skip_runlog=True,
            )
            self.assertFalse(result["written"])
            with open(md, encoding="utf-8") as f:
                self.assertNotIn("1000", f.read())

    def test_multi_image_later_wins_and_conflicts(self):
        """多图：后图覆盖 + conflicts 记录。"""
        p1 = json.dumps({"diet_kcal": 1000, "体重_kg": 70}, ensure_ascii=False)
        p2 = json.dumps({"diet_kcal": 2000, "睡眠时长_h": 7.5}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            img1 = os.path.join(tmp, "a.png")
            img2 = os.path.join(tmp, "b.png")
            md = os.path.join(tmp, "2099-01-06.md")
            log = os.path.join(tmp, "llm_last_run.json")
            for p in (img1, img2):
                with open(p, "wb") as f:
                    f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            result = vi.run_vision_intake(
                [img1, img2],
                "2099-01-06",
                md_path=md,
                write=True,
                mode="deepseek",
                client=_vision_client_sequence([p1, p2]),
                log_path=log,
            )
            self.assertTrue(result["written"])
            self.assertEqual(len(result["images"]), 2)
            self.assertEqual(result["fields"]["饮食热量_kcal"], 2000)
            self.assertEqual(result["fields"]["体重_kg"], 70)
            self.assertEqual(result["merge_strategy"], "later_wins")
            self.assertTrue(any(c["key"] == "饮食热量_kcal" for c in result["conflicts"]))
            with open(md, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("饮食热量_kcal: 2000", got)
            self.assertIn("睡眠时长_h: 7.5", got)
            self.assertNotRegex(got, r"体脂率:\s+\d")
            with open(log, encoding="utf-8") as f:
                log_text = f.read()
            self.assertIn('"ok": true', log_text)
            self.assertNotIn("sk-", log_text.lower())

    def test_partial_image_failure_merges_ok(self):
        """第二张失败：仍合并第一张成功字段。"""
        p1 = json.dumps({"diet_kcal": 1500, "体重_kg": 69}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            img1 = os.path.join(tmp, "ok.png")
            img2 = os.path.join(tmp, "bad.png")
            md = os.path.join(tmp, "2099-01-06.md")
            for p in (img1, img2):
                with open(p, "wb") as f:
                    f.write(_MIN_PNG)
            with open(md, "w", encoding="utf-8", newline="\n") as f:
                f.write(SAMPLE_MD)
            # Client retries on 502 — use non-retryable then exhaust, or patch max retries
            client = _vision_client_sequence([p1, None])
            # DeepSeek client retries retryable errors; force non-retryable on 2nd
            result = vi.run_vision_intake(
                [img1, img2],
                "2099-01-06",
                md_path=md,
                write=True,
                mode="deepseek",
                client=client,
                skip_runlog=True,
            )
            self.assertEqual(result["fields"]["饮食热量_kcal"], 1500)
            self.assertEqual(len(result["failed_images"]), 1)
            self.assertEqual(result["failed_images"][0]["path"], img2)
            self.assertEqual(result["ok_images"], [img1])
            with open(md, encoding="utf-8") as f:
                self.assertIn("饮食热量_kcal: 1500", f.read())

    def test_parse_multi_image_argv(self):
        opts = vi._parse([
            "--image", "a.png", "--image", "b.png",
            "--date", "2099-01-06", "--diff",
        ])
        self.assertEqual(opts["images"], ["a.png", "b.png"])
        self.assertTrue(opts["diff"])

    def test_prompt_forbids_invented_body_fat(self):
        self.assertIn("体脂率", vi.VISION_SYSTEM)
        self.assertIn("不要写", vi.VISION_SYSTEM)
        self.assertIn("编造", vi.VISION_SYSTEM)


if __name__ == "__main__":
    unittest.main()
