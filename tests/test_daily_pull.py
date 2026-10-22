"""M33 daily-pull：dry-run 不打网 / --apply 编排顺序 / 失败继续 + 退出码。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from review_tool.pipeline import daily_pull


class TestDailyPull(unittest.TestCase):
    def test_dry_run_touches_nothing(self):
        """默认 dry-run：打印计划、不发网络请求、不写库。"""
        with mock.patch.object(daily_pull, "keepstrong_main") as ks, \
             mock.patch.object(daily_pull, "sync_main") as hs, \
             mock.patch.object(daily_pull, "ingest_main") as ig:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = daily_pull.main(["--date", "2026-10-22"])
            self.assertEqual(rc, 0)
            text = buf.getvalue()
            self.assertIn("dry-run", text)
            self.assertIn("--apply", text)
            self.assertIn("keepstrong --date 2026-10-22 --write --ingest", text)
            self.assertIn("habits --sync 2026-10-22", text)
            for fn in (ks, hs, ig):
                fn.assert_not_called()

    def test_apply_runs_steps_in_order(self):
        calls: list[str] = []

        def ks(argv):
            calls.append("keepstrong")
            return 0

        def hs(argv):
            calls.append("habits")
            return 0

        def ig(argv):
            calls.append("ingest")
            return 0

        with mock.patch.object(daily_pull, "keepstrong_main", ks), \
             mock.patch.object(daily_pull, "sync_main", hs), \
             mock.patch.object(daily_pull, "ingest_main", ig), \
             mock.patch.object(daily_pull, "_report", lambda day: None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = daily_pull.main(["--date", "2026-10-22", "--apply"])
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["keepstrong", "habits", "ingest"])
            self.assertIn("全部步骤完成", buf.getvalue())

    def test_keepstrong_args(self):
        """传给 keepstrong 的参数必须是 --write --ingest（G1：先落 md 再入库）。"""
        seen: list[list[str]] = []

        def ks(argv):
            seen.append(list(argv))
            return 0

        with mock.patch.object(daily_pull, "keepstrong_main", ks), \
             mock.patch.object(daily_pull, "sync_main", lambda a: 0), \
             mock.patch.object(daily_pull, "ingest_main", lambda a: 0), \
             mock.patch.object(daily_pull, "_report", lambda day: None):
            daily_pull.main(["--date", "2026-10-22", "--apply"])
        self.assertEqual(seen, [["--date", "2026-10-22", "--write", "--ingest"]])

    def test_failure_continues_and_rc_is_1(self):
        """keepstrong 失败（如 401）→ 显式报错、继续其余步骤、退出码 1。"""
        calls: list[str] = []

        def ks(argv):
            calls.append("keepstrong")
            return 1

        def hs(argv):
            calls.append("habits")
            return 0

        def ig(argv):
            calls.append("ingest")
            return 0

        with mock.patch.object(daily_pull, "keepstrong_main", ks), \
             mock.patch.object(daily_pull, "sync_main", hs), \
             mock.patch.object(daily_pull, "ingest_main", ig), \
             mock.patch.object(daily_pull, "_report", lambda day: None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = daily_pull.main(["--date", "2026-10-22", "--apply"])
            self.assertEqual(rc, 1)
            self.assertEqual(calls, ["keepstrong", "habits", "ingest"])
            self.assertIn("1 步失败", buf.getvalue())
            self.assertIn("换 Key", buf.getvalue())

    def test_default_day_is_today(self):
        """--date 缺省 = 今天。"""
        import datetime
        with mock.patch.object(daily_pull, "keepstrong_main") as ks, \
             mock.patch.object(daily_pull, "sync_main"), \
             mock.patch.object(daily_pull, "ingest_main"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = daily_pull.main([])
            self.assertEqual(rc, 0)
            today = datetime.date.today().isoformat()
            self.assertIn(today, buf.getvalue())
            ks.assert_not_called()

    def test_bad_args_rc_2(self):
        for argv in (["--date"], ["--date", "2026/10/22"], ["extra"]):
            rc = daily_pull.main(argv)
            self.assertEqual(rc, 2, argv)


class TestReport(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.environ["DAILYLUMEN_DB_PATH"] = os.path.join(self.root, "t.db")

    def tearDown(self):
        os.environ.pop("DAILYLUMEN_DB_PATH", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_report_on_empty_db_is_safe(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            daily_pull._report("2026-10-22")
        text = buf.getvalue()
        self.assertIn("2026-10-22", text)
        self.assertIn("复盘入库", text)
        self.assertIn("习惯快照", text)


if __name__ == "__main__":
    unittest.main()
