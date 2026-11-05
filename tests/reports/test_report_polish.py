"""周月报 --polish：结构保护 + mode 门禁（mock）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock

from review_tool.pipeline import deepseek as ds
from review_tool.reports import report_polish as rp


SAMPLE = """# 周总结 · ISO 第 1 周

## 一、四维总览

| 维度 | 周均值 |
|------|--------|
| 系统 | **5.20** |

## 关键发现

本周睡眠偏短，需要早点睡。

## 九、自动生成说明

> 本文件由 CLI `--write` 落盘。

*生成时间：2099-01-01 12:00 ｜ 数据来源：local/reviews.db*
"""


def _chat_client(blocks_out: list[dict]) -> ds.Client:
    body = json.dumps({"blocks": blocks_out}, ensure_ascii=False)

    def urlopen(req, timeout=None):
        class R:
            def read(self_inner):
                return json.dumps({
                    "choices": [{"message": {"content": body}}],
                }).encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return R()

    return ds.Client("sk-fake", mode="deepseek", urlopen=urlopen)


class TestSplitBlocks(unittest.TestCase):
    def test_tables_protected(self):
        lines, blocks = rp.split_polish_blocks(SAMPLE)
        self.assertTrue(blocks)
        texts = "\n".join(b["text"] for b in blocks)
        self.assertIn("早点睡", texts)
        self.assertNotIn("| 系统 |", texts)
        fp = rp.structural_fingerprint(SAMPLE)
        self.assertIn("| 系统 | **5.20** |", fp)


class TestPolish(unittest.TestCase):
    def test_workbuddy_rejected(self):
        with self.assertRaises(ds.DeepSeekModeError):
            rp.polish_markdown(SAMPLE, mode="workbuddy")

    def test_polish_keeps_table(self):
        lines, blocks = rp.split_polish_blocks(SAMPLE)
        out_blocks = [
            {"id": b["id"], "text": b["text"].replace("偏短", "略短")}
            for b in blocks
        ]
        result = rp.polish_markdown(
            SAMPLE,
            mode="deepseek",
            client=_chat_client(out_blocks),
            kind="week",
        )
        self.assertTrue(result["changed"])
        self.assertIn("| 系统 | **5.20** |", result["polished"])
        self.assertIn("略短", result["polished"])
        self.assertEqual(
            rp.structural_fingerprint(SAMPLE),
            rp.structural_fingerprint(result["polished"]),
        )

    def test_reject_if_table_mutated(self):
        lines, blocks = rp.split_polish_blocks(SAMPLE)
        # 恶意：把数字改掉（通过改 prose 不够；直接伪造 fingerprint 失败）
        # 用 apply 后手动破坏受保护行来测校验
        bad = SAMPLE.replace("5.20", "9.99")
        with self.assertRaises(ValueError):
            # 直接调用校验路径：polish 内部 fingerprint 比对
            # 构造 client 返回原 blocks，但我们 monkeypatch apply 结果
            with mock.patch.object(
                rp, "apply_polished_blocks", return_value=bad,
            ):
                out_blocks = [{"id": b["id"], "text": b["text"]} for b in blocks]
                rp.polish_markdown(
                    SAMPLE,
                    mode="deepseek",
                    client=_chat_client(out_blocks),
                )


if __name__ == "__main__":
    unittest.main()
