"""M34 promise-draft：约束抽取 / 候选池去重 / 草稿渲染 / dry 语义 / CLI 编排。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from review_tool.pipeline import promise_draft


def _fake_fetch(tasks):
    """按 clickup.fetch_tasks 的约定返回 {"tasks": [...]}（分页：少于 PAGE_SIZE 即停）。"""
    return lambda path, key, **kw: {"tasks": tasks}


def _task(tid: str, name: str, **kw) -> dict:
    return {"id": tid, "name": name, **kw}


def _group(name: str, **kw) -> dict:
    base = {"id": f"L-{name}", "name": name, "role": "",
            "done": [], "open": [], "in_progress": [], "overdue": [],
            "cross_day": []}
    base.update(kw)
    return base


class TestExtractConstraint(unittest.TestCase):
    def test_time_patterns(self):
        self.assertEqual(promise_draft.extract_constraint("阅读 30min"), "约 30min")
        self.assertEqual(promise_draft.extract_constraint("运动 45 分钟"), "约 45min")
        self.assertEqual(promise_draft.extract_constraint("看课 1.5h"), "约 1.5h")
        self.assertEqual(promise_draft.extract_constraint("写周报 2 小时"), "约 2h")

    def test_limit_pattern(self):
        self.assertEqual(promise_draft.extract_constraint("脂肪≤70g"), "≤70g")

    def test_no_number_returns_none(self):
        self.assertIsNone(promise_draft.extract_constraint("migration 文件夹彻底修复"))
        self.assertIsNone(promise_draft.extract_constraint("整理房间"))


class TestCandidatePool(unittest.TestCase):
    def test_merge_and_dedup(self):
        groups = [
            _group("工作", open=[_task("1", "A")],
                   overdue=[_task("1", "A"), _task("2", "B")],
                   in_progress=[_task("3", "C")]),
        ]
        pool = promise_draft.candidate_pool("2026-10-23", groups)
        ids = [it["task"]["id"] for it in pool]
        self.assertEqual(ids, ["1", "2", "3"])

    def test_empty_pool(self):
        self.assertEqual(promise_draft.candidate_pool("2026-10-23", []), [])


class TestBuildDraft(unittest.TestCase):
    def test_draft_has_bounds_and_hints(self):
        groups = [
            _group("工作", overdue=[_task("1", "看课 1.5h"),
                                    _task("2", "migration 彻底修复")]),
        ]
        text = promise_draft.build_draft(
            "2026-10-23", promise_draft.candidate_pool("2026-10-23", groups),
            generated_at="2026-10-22 22:00")
        self.assertIn("明日 Top 3 候选（2026-10-23）", text)
        self.assertIn("不入库", text)
        self.assertIn("- [ ] 看课 1.5h（约 1.5h）", text)
        self.assertIn("无数字约束", text)
        self.assertIn("≤3 条", text)
        self.assertIn("今天不设", text)

    def test_empty_pool_draft(self):
        text = promise_draft.build_draft("2026-10-23", [], generated_at="x")
        self.assertIn("候选池为空", text)
        self.assertIn("今天不设", text)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stdout_dry(self):
        fetch = _fake_fetch([_task("1", "阅读 30min", due_date="1730123456000",
                                   date_closed=None)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = promise_draft.main(["--date", "2026-10-23", "--stdout"],
                                    fetch=fetch, env={"CLICKUP_API_KEY": "pk_x"})
        self.assertEqual(rc, 0)
        self.assertIn("阅读 30min", buf.getvalue())

    def test_writes_to_out_dir(self):
        fetch = _fake_fetch([_task("1", "阅读 30min", due_date="1730123456000",
                                   date_closed=None)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = promise_draft.main(["--date", "2026-10-23", "--out", self.tmp],
                                    fetch=fetch, env={"CLICKUP_API_KEY": "pk_x"})
        self.assertEqual(rc, 0)
        out = os.path.join(self.tmp, "明日候选-2026-10-23.md")
        self.assertTrue(os.path.isfile(out))
        self.assertIn("阅读 30min", open(out, encoding="utf-8").read())

    def test_missing_creds_rc_2(self):
        from review_tool.pipeline.clickup import CredError
        with mock.patch.object(
                promise_draft, "load_creds",
                side_effect=CredError("无凭据")):
            rc = promise_draft.main(["--date", "2026-10-23"])
        self.assertEqual(rc, 2)

    def test_bad_args_rc_2(self):
        for argv in (["--date"], ["--date", "23-10-22"], ["extra"]):
            rc = promise_draft.main(argv, env={"CLICKUP_API_KEY": "pk_x"})
            self.assertEqual(rc, 2, argv)


if __name__ == "__main__":
    unittest.main()
