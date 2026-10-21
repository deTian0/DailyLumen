"""v11 / D2：ClickUp 完成任务名解析（core.clickup_done，零 I/O）。

v1.37.1 归属口径：整张工时表都是本人执行记录，姓名位 = 下发人，
``is_self`` 恒为 True —— 不再有「排除同事前缀」的判定。
"""
from __future__ import annotations

import unittest

from review_tool.core.clickup_done import (
    parse_hours,
    parse_task_name,
    summarize,
    to_row,
)


class TestParseHours(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_hours("2h"), (120.0, True))
        self.assertEqual(parse_hours("8H"), (480.0, True))

    def test_decimal(self):
        self.assertEqual(parse_hours("0.5h"), (30.0, True))
        self.assertEqual(parse_hours("2.5h"), (150.0, True))

    def test_unknown_hours(self):
        # `xh` 是工时位但写不出数 —— 必须与「这段不是工时位」区分
        self.assertEqual(parse_hours("xh"), (None, True))
        self.assertEqual(parse_hours("xxh"), (None, True))

    def test_not_hours(self):
        self.assertEqual(parse_hours("李扬"), (None, False))
        self.assertEqual(parse_hours("其他任务"), (None, False))


class TestParseTaskName(unittest.TestCase):
    def test_name_hours_subject(self):
        r = parse_task_name("李扬-2h-排查开发环境和生产环境 502 问题")
        self.assertEqual(r["owner"], "李扬")  # 下发人
        self.assertEqual(r["minutes"], 120.0)
        self.assertEqual(r["subject"], "排查开发环境和生产环境 502 问题")

    def test_hours_subject_no_owner(self):
        r = parse_task_name("2h-更新及协调平果铝厂端站点配置")
        self.assertIsNone(r["owner"])
        self.assertEqual(r["minutes"], 120.0)
        self.assertEqual(r["subject"], "更新及协调平果铝厂端站点配置")

    def test_unknown_hours_keeps_owner(self):
        r = parse_task_name("常哲-xh-知识库底座需求会")
        self.assertEqual(r["owner"], "常哲")
        self.assertIsNone(r["minutes"])
        self.assertEqual(r["subject"], "知识库底座需求会")

    def test_plain_title(self):
        r = parse_task_name("每日复盘计划打卡")
        self.assertIsNone(r["owner"])
        self.assertIsNone(r["minutes"])
        self.assertEqual(r["subject"], "每日复盘计划打卡")

    def test_keeps_hyphens_in_subject(self):
        """只切前两刀 —— 描述里的连字符不能被当成字段分隔符。"""
        r = parse_task_name("梁帅-4h-修复 a-b 问题")
        self.assertEqual(r["owner"], "梁帅")
        self.assertEqual(r["minutes"], 240.0)
        self.assertEqual(r["subject"], "修复 a-b 问题")

    def test_fullwidth_separator(self):
        r = parse_task_name("梁帅－4h－写文档")
        self.assertEqual(r["owner"], "梁帅")
        self.assertEqual(r["minutes"], 240.0)

    def test_empty(self):
        r = parse_task_name("")
        self.assertIsNone(r["minutes"])
        self.assertIsNone(r["subject"])


class TestToRowAndSummarize(unittest.TestCase):
    def test_to_row_teammate_prefix_is_self(self):
        """同事前缀 = 同事下发的任务，实际执行是本人 → is_self 恒 True（v1.37.1）。"""
        t = {
            "id": "abc",
            "name": "李扬-2h-排查502",
            "status": {"status": "complete"},
            "assignees": [{"username": "detian"}],
        }
        row = to_row(t, "list-1", "2026-10-20")
        self.assertEqual(row["date"], "2026-10-20")
        self.assertEqual(row["task_id"], "abc")
        self.assertEqual(row["owner"], "李扬")  # 语义 = 下发人
        self.assertEqual(row["minutes"], 120.0)
        self.assertEqual(row["is_self"], True)
        self.assertEqual(row["status"], "complete")

    def test_to_row_no_prefix(self):
        t = {"id": "d1", "name": "2h-平果铝厂配置", "status": {"status": "complete"}}
        row = to_row(t, "list-1", "2026-10-20")
        self.assertIsNone(row["owner"])
        self.assertEqual(row["minutes"], 120.0)
        self.assertEqual(row["is_self"], True)

    def test_summarize_empty(self):
        s = summarize([])
        self.assertEqual(s["self_count"], 0)
        self.assertIsNone(s["self_max"])
        self.assertIsNone(s["self_sum"])

    def test_summarize_reports_max_not_only_sum(self):
        """多条工时只给「最长单条」和「合计」两个数，判定用前者。"""
        rows = [
            {"minutes": 480.0, "subject": "a"},
            {"minutes": 240.0, "subject": "b"},
        ]
        s = summarize(rows)
        self.assertEqual(s["self_count"], 2)
        self.assertEqual(s["self_max"], 480.0)
        self.assertEqual(s["self_sum"], 720.0)
        self.assertEqual(s["subjects"], ["a", "b"])

    def test_summarize_counts_rows_without_hours(self):
        s = summarize([{"minutes": None, "subject": "x"}])
        self.assertEqual(s["self_count"], 1)
        self.assertEqual(s["self_no_hours"], 1)
        self.assertIsNone(s["self_max"])


if __name__ == "__main__":
    unittest.main()
