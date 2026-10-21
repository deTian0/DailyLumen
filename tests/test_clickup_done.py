"""v11 / D2：ClickUp 完成任务名解析与归属判定（core.clickup_done，零 I/O）。"""
from __future__ import annotations

import unittest

from review_tool.core.clickup_done import (
    is_self_task,
    parse_hours,
    parse_task_name,
    summarize,
    to_row,
)

SELF = ("梁帅",)
MATES = ("李扬", "常哲")


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
        self.assertEqual(r["owner"], "李扬")
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


class TestIsSelf(unittest.TestCase):
    """归属只看姓名位，**不看 assignee**（实测工作 list 全部任务 assignee 都是本人）。"""

    def _task(self, name, assignees=None):
        return {"name": name, "assignees": assignees or []}

    def test_self_by_name_prefix(self):
        t = self._task("梁帅-8h-国庆请假")
        self.assertTrue(is_self_task(t, parse_task_name(t["name"]),
                                     self_names=SELF, teammates=MATES))

    def test_teammate_is_not_self_even_if_assignee_is_me(self):
        """同事的工时挂在我名下 —— 不能算我的证据。"""
        t = self._task("李扬-2h-排查502", [{"username": "detian"}])
        self.assertFalse(is_self_task(t, parse_task_name(t["name"]),
                                      self_names=SELF, teammates=MATES))

    def test_no_prefix_is_self(self):
        t = self._task("2h-平果铝厂配置")
        self.assertTrue(is_self_task(t, parse_task_name(t["name"]),
                                     self_names=SELF, teammates=MATES))

    def test_label_prefix_is_self(self):
        """`其他任务` / `开发任务` 是分类标签，不是人名。"""
        for name in ("其他任务-3h-杂项", "开发任务-8h-迭代"):
            t = self._task(name)
            self.assertTrue(is_self_task(t, parse_task_name(name),
                                         self_names=SELF, teammates=MATES), name)


class TestToRowAndSummarize(unittest.TestCase):
    def test_to_row(self):
        t = {
            "id": "abc",
            "name": "梁帅-2h-修复登录",
            "status": {"status": "complete"},
        }
        row = to_row(t, "list-1", "2026-10-20",
                     self_spec={"self_names": SELF, "teammates": MATES})
        self.assertEqual(row["date"], "2026-10-20")
        self.assertEqual(row["task_id"], "abc")
        self.assertEqual(row["minutes"], 120.0)
        self.assertEqual(row["is_self"], 1)
        self.assertEqual(row["status"], "complete")

    def test_summarize_no_self_records(self):
        rows = [{"is_self": 0, "minutes": 120.0, "subject": "同事的活"},
                {"is_self": 1, "minutes": None, "subject": "无工时"}]
        s = summarize([rows[0]])
        self.assertEqual(s["self_count"], 0)
        self.assertIsNone(s["self_max"])
        self.assertIsNone(s["self_sum"])

    def test_summarize_reports_max_not_only_sum(self):
        """多条工时只给「最长单条」和「合计」两个数，判定用前者。"""
        rows = [
            {"is_self": 1, "minutes": 480.0, "subject": "a"},
            {"is_self": 1, "minutes": 240.0, "subject": "b"},
            {"is_self": 0, "minutes": 600.0, "subject": "同事"},
        ]
        s = summarize(rows)
        self.assertEqual(s["self_count"], 2)
        self.assertEqual(s["self_max"], 480.0)
        self.assertEqual(s["self_sum"], 720.0)
        self.assertEqual(s["subjects"], ["a", "b"])

    def test_summarize_counts_rows_without_hours(self):
        s = summarize([{"is_self": 1, "minutes": None, "subject": "x"}])
        self.assertEqual(s["self_count"], 1)
        self.assertEqual(s["self_no_hours"], 1)
        self.assertIsNone(s["self_max"])


if __name__ == "__main__":
    unittest.main()
