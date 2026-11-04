"""M36 three-things-draft：有产出排序 / 候选池 / 草稿渲染 / 与 promise-draft 分文件。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from review_tool.pipeline import promise_draft, three_things_draft


def _fake_fetch(tasks):
    return lambda path, key, **kw: {"tasks": tasks}


def _task(tid: str, name: str, **kw) -> dict:
    return {"id": tid, "name": name, **kw}


def _group(name: str, **kw) -> dict:
    base = {"id": f"L-{name}", "name": name, "role": "",
            "done": [], "open": [], "in_progress": [], "overdue": [],
            "cross_day": []}
    base.update(kw)
    return base


class TestProductivityRank(unittest.TestCase):
    def test_deliverable_beats_plain(self):
        self.assertGreater(
            three_things_draft.productivity_rank("周报交付"),
            three_things_draft.productivity_rank("整理房间"),
        )

    def test_time_number_beats_plain(self):
        self.assertGreater(
            three_things_draft.productivity_rank("看课 1.5h"),
            three_things_draft.productivity_rank("整理房间"),
        )


class TestCandidatePool(unittest.TestCase):
    def test_uses_done_only_and_dedup(self):
        groups = [
            _group("工作",
                   done=[_task("1", "A", date_closed="100"),
                         _task("1", "A", date_closed="100"),
                         _task("2", "周报交付", date_closed="50")],
                   open=[_task("3", "不该出现", date_closed=None)]),
        ]
        pool = three_things_draft.candidate_pool("2026-11-03", groups)
        ids = [it["task"]["id"] for it in pool]
        self.assertEqual(ids, ["2", "1"])  # 交付物优先，再关闭时间

    def test_empty_pool(self):
        self.assertEqual(three_things_draft.candidate_pool("2026-11-03", []), [])


class TestBuildDraft(unittest.TestCase):
    def test_draft_bounds(self):
        groups = [
            _group("工作", done=[_task("1", "方案提交", date_closed="100")]),
        ]
        text = three_things_draft.build_draft(
            "2026-11-03",
            three_things_draft.candidate_pool("2026-11-03", groups),
            generated_at="2026-11-03 22:00")
        self.assertIn("今日三件事候选（2026-11-03）", text)
        self.assertIn("不入库", text)
        self.assertIn("方案提交", text)
        self.assertIn("≤3 条", text)
        self.assertIn("二、今日三件事", text)

    def test_empty_pool_draft(self):
        text = three_things_draft.build_draft("2026-11-03", [], generated_at="x")
        self.assertIn("候选池为空", text)


class TestSeparateFromPromiseDraft(unittest.TestCase):
    def test_prefixes_differ(self):
        self.assertNotEqual(
            three_things_draft.INBOX_PREFIX, promise_draft.INBOX_PREFIX)

    def test_same_day_files_coexist(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        day = "2026-11-03"
        p1 = os.path.join(tmp, f"{promise_draft.INBOX_PREFIX}-{day}.md")
        p2 = os.path.join(tmp, f"{three_things_draft.INBOX_PREFIX}-{day}.md")
        open(p1, "w", encoding="utf-8", newline="\n").write("a\n")
        open(p2, "w", encoding="utf-8", newline="\n").write("b\n")
        self.assertTrue(os.path.isfile(p1))
        self.assertTrue(os.path.isfile(p2))
        self.assertNotEqual(p1, p2)


class TestNotIngested(unittest.TestCase):
    def test_inbox_prefix_skipped_by_iter(self):
        """收件箱下的候选草稿不参与 ingest 扫描（与其它 inbox 素材同规约）。"""
        from review_tool.pipeline.ingest import iter_markdown
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        inbox = os.path.join(tmp, "收件箱")
        review = os.path.join(tmp, "复盘", "2026-11")
        os.makedirs(inbox)
        os.makedirs(review)
        draft = os.path.join(inbox, "三件事候选-2026-11-03.md")
        real = os.path.join(review, "2026-11-03.md")
        open(draft, "w", encoding="utf-8", newline="\n").write("# draft\n")
        open(real, "w", encoding="utf-8", newline="\n").write("# real\n")
        names = [os.path.basename(p) for p in iter_markdown(tmp)]
        self.assertIn("2026-11-03.md", names)
        self.assertNotIn("三件事候选-2026-11-03.md", names)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stdout_dry(self):
        # date_closed 毫秒戳：2026-11-03 12:00 CST ≈ 1762142400000
        fetch = _fake_fetch([
            _task("1", "方案提交", date_closed="1793678400000",
                  status={"status": "complete", "type": "closed"}),
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = three_things_draft.main(
                ["--date", "2026-11-03", "--stdout"],
                fetch=fetch, env={"CLICKUP_API_KEY": "pk_x"})
        self.assertEqual(rc, 0)
        self.assertIn("方案提交", buf.getvalue())

    def test_writes_to_out_dir(self):
        fetch = _fake_fetch([
            _task("1", "方案提交", date_closed="1793678400000",
                  status={"status": "complete", "type": "closed"}),
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = three_things_draft.main(
                ["--date", "2026-11-03", "--out", self.tmp],
                fetch=fetch, env={"CLICKUP_API_KEY": "pk_x"})
        self.assertEqual(rc, 0)
        out = os.path.join(self.tmp, "三件事候选-2026-11-03.md")
        self.assertTrue(os.path.isfile(out))
        body = open(out, encoding="utf-8").read()
        self.assertIn("方案提交", body)
        self.assertIn("不入库", body)

    def test_missing_creds_rc_2(self):
        from review_tool.pipeline.clickup import CredError
        with mock.patch.object(
                three_things_draft, "load_creds",
                side_effect=CredError("无凭据")):
            rc = three_things_draft.main(["--date", "2026-11-03"])
        self.assertEqual(rc, 2)

    def test_bad_args_rc_2(self):
        for argv in (["--date"], ["--date", "23-10-22"], ["extra"]):
            rc = three_things_draft.main(argv, env={"CLICKUP_API_KEY": "pk_x"})
            self.assertEqual(rc, 2, argv)

    def test_route_registered(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("three-things-draft", ROUTES)


if __name__ == "__main__":
    unittest.main()
