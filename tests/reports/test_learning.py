"""M13：学习记录 + 间隔重复队列（core / ingest / tutor / 重建回归）。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.core.learning import (
    build_queue,
    classify_hours_source,
    due_from_last,
    due_status,
    hours_fallback,
    parse_section,
    queue_entry_from_dates,
    resolve_topic,
    stage_from_count,
    week_rollup,
)
from review_tool.pipeline.ingest import ingest_path
from review_tool.pipeline.parse import parse_text
from review_tool.reports.analyze import learning_week
from review_tool.reports.tutor import (
    booklist_evidence,
    collect,
    render,
    week_section_lines,
)
from review_tool.storage.db import (
    init_db,
    load_learning_logs,
    load_review_queue,
    rebuild_review_queue,
    upsert,
    upsert_learning_log,
)

_SECTION = """
## 附录 · 学习记录

- 主题：Python｜时长：45min｜来源：self｜产出：笔记-asyncio
- 主题：系统设计｜时长：30min｜来源：course｜产出：章节3
"""


class TestResolveAndParse(unittest.TestCase):
    def test_resolve_catalog(self):
        r = resolve_topic("Python 异步")
        self.assertEqual(r["key"], "python")

    def test_resolve_slug_fallback(self):
        r = resolve_topic("量子计算入门")
        self.assertEqual(r["key"], "量子计算入门")
        self.assertEqual(r["label"], "量子计算入门")

    def test_parse_section(self):
        items = parse_section(_SECTION)
        self.assertIsNotNone(items)
        self.assertEqual(len(items), 2)
        by = {i["topic_key"]: i for i in items}
        self.assertEqual(by["python"]["minutes"], 45.0)
        self.assertEqual(by["python"]["src"], "self")
        self.assertEqual(by["python"]["artifact"], "笔记-asyncio")
        self.assertEqual(by["system_design"]["src"], "course")

    def test_parse_sidecar_in_parse_text(self):
        text = (
            "```data\n日期: 2026-10-14\n学习投入_h: 1.5\n```\n"
            + _SECTION
        )
        row = parse_text(text)
        self.assertIn("_learning", row)
        self.assertEqual(len(row["_learning"]), 2)

    def test_blockquote_prose_skipped(self):
        """附录里的 `> 填写指引` 不是数据 —— 否则每写一行说明就多一条假记录。"""
        text = (
            "## 附录 · 学习记录\n\n"
            "> 今天学了什么，一行一条。\n"
            "> 来源写 self / course。\n\n"
            "- 主题：Python｜时长：45min\n"
        )
        items = parse_section(text)
        self.assertEqual([i["topic_key"] for i in items], ["python"])

    def test_blockquote_list_still_parsed(self):
        """`> - 主题：X` 是引用块里的列表，仍是数据。"""
        text = "## 附录 · 学习记录\n\n> - 主题：Python｜时长：30min\n"
        items = parse_section(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["minutes"], 30.0)

    def test_empty_section_is_empty_list(self):
        text = "## 附录 · 学习记录\n\n> 只有说明\n"
        self.assertEqual(parse_section(text), [])


class TestSpacedRepeat(unittest.TestCase):
    def test_stage_from_count(self):
        iv = [1, 3, 7, 16]
        self.assertEqual(stage_from_count(1, iv), 0)
        self.assertEqual(stage_from_count(2, iv), 1)
        self.assertEqual(stage_from_count(3, iv), 2)
        self.assertEqual(stage_from_count(4, iv), 3)
        self.assertEqual(stage_from_count(10, iv), 3)

    def test_due_pending_overdue(self):
        # 学 1 次 → stage0 → +1d
        entry = queue_entry_from_dates(
            "python", "Python", ["2026-10-10"], intervals=[1, 3, 7, 16]
        )
        self.assertEqual(entry["stage"], 0)
        self.assertEqual(entry["due_date"], "2026-10-11")
        self.assertEqual(entry["last_seen"], "2026-10-10")
        self.assertIsNone(entry["note"])

        self.assertEqual(due_status("2026-10-10", entry["due_date"]), "pending")
        self.assertEqual(due_status("2026-10-11", entry["due_date"]), "due")
        self.assertEqual(due_status("2026-10-12", entry["due_date"]), "overdue")

    def test_multi_learn_advances_stage(self):
        entry = queue_entry_from_dates(
            "python", "Python",
            ["2026-10-01", "2026-10-05", "2026-10-10"],
            intervals=[1, 3, 7, 16],
        )
        self.assertEqual(entry["stage"], 2)
        self.assertEqual(entry["due_date"], due_from_last("2026-10-10", 2, [1, 3, 7, 16]))
        self.assertEqual(entry["due_date"], "2026-10-17")

    def test_build_queue_sorted(self):
        logs = [
            {"date": "2026-10-10", "topic_key": "b", "topic": "B"},
            {"date": "2026-10-11", "topic_key": "a", "topic": "A"},
            {"date": "2026-10-12", "topic_key": "a", "topic": "A"},
        ]
        q = build_queue(logs, intervals=[1, 3, 7, 16])
        self.assertEqual([x["topic_key"] for x in q], ["a", "b"])
        self.assertEqual(q[0]["stage"], 1)  # 2 次
        self.assertEqual(q[1]["stage"], 0)


class TestIngestAndRebuild(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.md = os.path.join(self.root, "2026-10-14.md")
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "```data\n日期: 2026-10-14\n学习投入_h: 1.25\n```\n"
                + _SECTION
            )
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ingest_writes_logs_and_queue(self):
        row = ingest_path(self.conn, self.md)
        self.assertIsNotNone(row)
        logs = [dict(r) for r in load_learning_logs(self.conn, date="2026-10-14")]
        self.assertEqual(len(logs), 2)
        q = [dict(r) for r in load_review_queue(self.conn)]
        self.assertEqual(len(q), 2)
        keys = {x["topic_key"] for x in q}
        self.assertEqual(keys, {"python", "system_design"})

    def test_queue_rebuild_zero_diff(self):
        """硬验收：删 review_queue 后从 learning_logs 完全重建，逐字段 0 差异。"""
        # 多日历史
        for d, key, topic in [
            ("2026-10-01", "python", "Python"),
            ("2026-10-05", "python", "Python"),
            ("2026-10-10", "english", "英语"),
            ("2026-10-14", "python", "Python"),
        ]:
            upsert_learning_log(self.conn, {
                "date": d, "topic_key": key, "topic": topic,
                "minutes": 30, "src": "self", "artifact": None,
            })
        rebuild_review_queue(self.conn)
        self.conn.commit()

        cols = ["topic_key", "topic", "stage", "due_date", "last_seen", "note"]

        def snap():
            return [
                tuple(r[c] for c in cols)
                for r in load_review_queue(self.conn)
            ]

        before = snap()
        self.assertGreaterEqual(len(before), 2)

        self.conn.execute("DELETE FROM review_queue")
        self.conn.commit()
        self.assertEqual(len(load_review_queue(self.conn)), 0)

        n = rebuild_review_queue(self.conn)
        self.conn.commit()
        after = snap()
        self.assertEqual(n, len(before))
        self.assertEqual(before, after)


class TestTutorReport(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)
        # 10-10 学一次 → due 10-11；再 10-14 学一次 → stage1 due 10-17
        upsert_learning_log(self.conn, {
            "date": "2026-10-10", "topic_key": "python", "topic": "Python",
            "minutes": 40, "src": "self", "artifact": "笔记A",
        })
        upsert_learning_log(self.conn, {
            "date": "2026-10-14", "topic_key": "python", "topic": "Python",
            "minutes": 50, "src": "self", "artifact": "笔记B",
        })
        upsert_learning_log(self.conn, {
            "date": "2026-10-13", "topic_key": "reading", "topic": "阅读",
            "minutes": 30, "src": "clickup", "artifact": "第3章",
        })
        rebuild_review_queue(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_collect_due_and_week(self):
        # as_of=10-17 → python due；reading last 10-13 stage0 due 10-14 → overdue
        data = collect(self.conn, as_of="2026-10-17", rebuild=True)
        due_keys = {x["topic_key"] for x in data["due_today"]}
        over_keys = {x["topic_key"] for x in data["overdue"]}
        self.assertIn("python", due_keys)
        self.assertIn("reading", over_keys)
        week = data["week"]
        self.assertGreaterEqual(week["entries"], 2)
        self.assertTrue(any("笔记" in a or "章" in a for a in week["artifacts"]))

    def test_render_contains_sections(self):
        data = collect(self.conn, as_of="2026-10-17", rebuild=False)
        text = render(data)
        self.assertIn("今日待复习", text)
        self.assertIn("本周主题", text)
        self.assertIn("产出物", text)

    def test_week_rollup(self):
        logs = [
            {"date": "2026-10-14", "topic_key": "python", "topic": "Python",
             "minutes": 45, "artifact": "A"},
            {"date": "2026-10-15", "topic_key": "python", "topic": "Python",
             "minutes": 15, "artifact": None},
        ]
        w = week_rollup(logs)
        self.assertEqual(w["total_minutes"], 60.0)
        self.assertEqual(w["entries"], 2)
        self.assertEqual(w["topics"][0]["minutes"], 60.0)

    def test_collect_learn_h_fallback_without_logs(self):
        """logs 空 + 有 learn_h → hours_source=learn_h，文案标明来源。"""
        # ISO 周 2026-W43：10-19(一) ~ 10-25(日)
        for d, h in (("2026-10-20", 0.75), ("2026-10-21", 1.0)):
            upsert(self.conn, {"date": d, "learn_h": h}, overwrite=True)
        self.conn.commit()
        data = collect(
            self.conn, as_of="2026-10-22", rebuild=False, include_booklist=False,
        )
        week = data["week"]
        self.assertEqual(week["hours_source"], "learn_h")
        self.assertEqual(week["learn_h_used_days"], 2)
        self.assertAlmostEqual(week["learn_h_used_total"], 1.75)
        text = "\n".join(week_section_lines(week))
        self.assertIn("learn_h", text)
        self.assertIn("本周无 learning_logs", text)

    def test_collect_mixed_no_double_count(self):
        """同日 logs + learn_h 不双计；另一空日 learn_h 计入 → mixed。"""
        upsert(self.conn, {"date": "2026-10-20", "learn_h": 1.0}, overwrite=True)
        upsert(self.conn, {"date": "2026-10-21", "learn_h": 0.5}, overwrite=True)
        upsert_learning_log(self.conn, {
            "date": "2026-10-20", "topic_key": "python", "topic": "Python",
            "minutes": 45, "src": "self", "artifact": None,
        })
        self.conn.commit()
        data = collect(
            self.conn, as_of="2026-10-22", rebuild=False, include_booklist=False,
        )
        week = data["week"]
        self.assertEqual(week["hours_source"], "mixed")
        self.assertEqual(week["logs_minutes"], 45.0)
        # 10-20 被 logs 吞掉，只剩 10-21 的 0.5h
        self.assertAlmostEqual(week["learn_h_used_total"], 0.5)
        self.assertEqual(week["learn_h_used_days"], 1)


class TestHoursFallback(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(
            hours_fallback([]),
            {"total": None, "days": 0, "daily_avg": None},
        )
        self.assertEqual(
            hours_fallback([None, {"learn_h": None}]),
            {"total": None, "days": 0, "daily_avg": None},
        )

    def test_values(self):
        r = hours_fallback([0.5, None, 1.5])
        self.assertEqual(r["days"], 2)
        self.assertAlmostEqual(r["total"], 2.0)
        self.assertAlmostEqual(r["daily_avg"], 1.0)

    def test_same_day_logs_win(self):
        r = classify_hours_source(
            logs_minutes=45.0,
            log_dates_with_minutes={"2026-10-20"},
            learn_h_rows=[
                {"date": "2026-10-20", "learn_h": 0.75},
                {"date": "2026-10-21", "learn_h": 1.0},
            ],
        )
        self.assertEqual(r["hours_source"], "mixed")
        self.assertAlmostEqual(r["learn_h_used_total"], 1.0)
        self.assertEqual(r["learn_h_used_days"], 1)


class TestBooklistSoftFail(unittest.TestCase):
    def test_no_creds_still_ok(self):
        from unittest.mock import patch

        from review_tool.integrations import weread as wr
        from review_tool.integrations.clickup import CredError as CuCred

        def _raise_wr(*, env=None, settings=None, opener=None):
            raise wr.CredError("no key")

        with patch(
            "review_tool.integrations.weread.client_from_settings",
            side_effect=_raise_wr,
        ), patch(
            "review_tool.integrations.clickup.load_creds",
            side_effect=CuCred("no key"),
        ):
            bl = booklist_evidence(
                as_of="2026-10-22", include=True, env={},
            )
        self.assertEqual(bl["weread"]["error_kind"], "CredError")
        self.assertEqual(bl["clickup"]["error_kind"], "CredError")
        self.assertFalse(bl["weread"]["checked"])

    def test_weread_mock_titles(self):
        class _Fake:
            def readdata_detail(self, **_kw):
                return {
                    "readLongest": [
                        {"book": {"title": "三体"}, "readTime": 3600},
                    ],
                }

            def shelf_sync(self):
                return {"books": []}

        bl = booklist_evidence(
            as_of="2026-10-22",
            include=True,
            weread_client=_Fake(),
            env={},
        )
        self.assertTrue(bl["weread"]["checked"])
        self.assertEqual(bl["weread"]["titles"], ["三体"])


class TestAnalyzeLearningWeek(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_enrich_hours(self):
        upsert(self.conn, {"date": "2026-10-20", "learn_h": 1.25}, overwrite=True)
        self.conn.commit()
        week = learning_week(
            self.conn, "date BETWEEN ? AND ?", ("2026-10-19", "2026-10-25"),
        )
        self.assertEqual(week["hours_source"], "learn_h")
        self.assertAlmostEqual(week["learn_h_used_total"], 1.25)


if __name__ == "__main__":
    unittest.main()
