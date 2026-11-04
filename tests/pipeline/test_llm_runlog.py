"""llm_last_run 摘要：允许字段 / 密钥红线 / 回读。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from review_tool.pipeline import llm_runlog as rl


class TestSanitizeAndWrite(unittest.TestCase):
    def test_strips_forbidden_and_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "llm_last_run.json")
            dest = rl.write_llm_last_run(
                {
                    "command": "llm-vision",
                    "mode": "deepseek",
                    "ok": True,
                    "day": "2099-01-06",
                    "api_key": "sk-SHOULD-NOT-APPEAR",
                    "raw_text": "隐私大段不应落盘",
                    "section": "## 七、AI …",
                    "missing_fields": ["脂肪_g", "腰围_cm"],
                    "filled_fields": ["饮食热量_kcal"],
                    "image_count": 2,
                },
                path=path,
            )
            self.assertEqual(dest, path)
            with open(path, encoding="utf-8") as f:
                text = f.read()
                data = json.loads(text)
            self.assertEqual(data["command"], "llm-vision")
            self.assertNotIn("api_key", data)
            self.assertNotIn("raw_text", data)
            self.assertNotIn("section", data)
            self.assertNotIn("sk-", text.lower())
            self.assertNotIn("隐私", text)
            got = rl.read_llm_last_run(path)
            self.assertIsNotNone(got)
            self.assertEqual(got["missing_fields"], ["脂肪_g", "腰围_cm"])

    def test_sanitize_drops_key_like_strings(self):
        clean = rl.sanitize_run_record({
            "command": "llm-review",
            "mode": "workbuddy",
            "ok": False,
            "error_summary": "mode gate",
            "prompt": "should drop",
        })
        self.assertNotIn("prompt", clean)
        self.assertEqual(clean["error_summary"], "mode gate")


if __name__ == "__main__":
    unittest.main()
