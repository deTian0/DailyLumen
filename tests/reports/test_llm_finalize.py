"""llm-finalize：本地定稿 CLI（不依赖 DeepSeek）。"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from review_tool.core import ai_draft as ad
from review_tool.pipeline.ingest import ingest_path
from review_tool.reports import llm_finalize as lf
from review_tool.reports.llm_review import wrap_ai_draft
from review_tool.storage.db import init_db

SAMPLE = """# 每日复盘 · 2099-04-01（星期一）

## 一、日常打卡

## 七、AI 评价与建议

{section}

## 附录 · 系统数据

```data
日期: 2099-04-01
星期: 星期一
饮食热量_kcal: 1600
睡眠时长_h: 7.5
体脂率:
```
"""


class TestLlmFinalize(unittest.TestCase):
    def test_dry_run_no_write(self):
        section = wrap_ai_draft(
            "**评价**\n\n- ok\n", day="2099-04-01", generated_at="T"
        )
        md = ad.stamp_llm_pending(SAMPLE.format(section=section))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-04-01.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = lf.main(["--md", path, "--dry-run"])
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("定稿前并排预览", text)
            self.assertIn("数据块", text)
            self.assertIn("七、AI", text)
            with open(path, encoding="utf-8") as f:
                self.assertTrue(ad.is_ai_draft_pending(f.read()))

    def test_preview_on_write(self):
        section = wrap_ai_draft(
            "**评价**\n\n- ok\n", day="2099-04-01", generated_at="T"
        )
        md = ad.stamp_llm_pending(SAMPLE.format(section=section))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-04-01.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = lf.main(["--md", path, "--write"])
            self.assertEqual(rc, 0)
            self.assertIn("定稿前并排预览", out.getvalue())
            self.assertIn("已定稿写入", out.getvalue())

    def test_write_then_ingest(self):
        section = wrap_ai_draft(
            "**评价**\n\n- 睡眠 7.5h\n\n**建议**\n\n1. **引领**：早睡\n",
            day="2099-04-01",
            generated_at="T",
        )
        md = ad.stamp_llm_pending(SAMPLE.format(section=section))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2099-04-01.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            # 未定稿 → ingest 跳过（返回 None）
            db_path = os.path.join(tmp, "t.db")
            conn = init_db(db_path=db_path)
            try:
                self.assertIsNone(ingest_path(conn, path))
            finally:
                conn.close()

            result = lf.run_llm_finalize(md_path=path, write=True)
            self.assertTrue(result["written"])
            self.assertFalse(result["pending_after"])
            with open(path, encoding="utf-8") as f:
                back = f.read()
            self.assertFalse(ad.is_ai_draft_pending(back))
            self.assertIn("睡眠 7.5h", back)

            conn = init_db(db_path=db_path)
            try:
                self.assertTrue(ingest_path(conn, path))
            finally:
                conn.close()

    def test_no_deepseek_mode_needed(self):
        """定稿是本地 md 变换，workbuddy 下也可跑。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(ad.stamp_llm_pending("# hi\n"))
            r = lf.run_llm_finalize(md_path=path, write=True)
            self.assertTrue(r["written"])
            self.assertFalse(r["pending_after"])


if __name__ == "__main__":
    unittest.main()
