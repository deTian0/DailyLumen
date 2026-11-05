"""day-help CLI：关键步骤出现在输出中。"""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from review_tool import __main__ as cli


def _capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class TestDayHelpCli(unittest.TestCase):
    def test_day_help_lists_pipeline_steps(self):
        with mock.patch(
            "review_tool.reports.day_help.get_llm_mode",
            return_value="workbuddy",
        ):
            rc, out = _capture(cli.main, ["day-help", "2099-06-01"])
        self.assertEqual(rc, 0)
        self.assertIn("一日三步", out)
        self.assertIn("投放收件箱", out)
        self.assertIn("llm-finalize", out)
        self.assertIn("ingest", out)
        self.assertIn("inbox-archive", out)
        self.assertIn("doctor", out)
        self.assertIn("llm-day", out)
        self.assertIn("2099-06-01", out)
        self.assertIn("mode=workbuddy", out)

    def test_day_help_in_routes(self):
        self.assertIn("day-help", cli.ROUTES)
        self.assertIn("day-help", cli.usage())


if __name__ == "__main__":
    unittest.main()
