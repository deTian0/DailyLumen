"""CLI 路由测试：参数单一来源、原样透传、`-h` 不触发执行（v1.4.1）。"""
import contextlib
import io
import unittest

from review_tool import __main__ as cli


def _capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class _PatchedRoute(unittest.TestCase):
    """把某个子命令的处理函数临时换成探针。"""

    def setUp(self):
        self.calls: list[list[str]] = []
        self._orig = None

    def patch(self, name="ingest"):
        self._orig = cli.ROUTES[name]

        def probe(rest, _calls=self.calls):
            _calls.append(rest)
            return 0

        cli.ROUTES[name] = (probe, self._orig[1])

    def tearDown(self):
        if self._orig is not None:
            cli.ROUTES["ingest"] = self._orig


class TestRoutesTable(unittest.TestCase):
    def test_every_route_has_usage_line(self):
        for name, (fn, usage_line) in cli.ROUTES.items():
            self.assertTrue(callable(fn), name)
            self.assertTrue(usage_line.startswith(name), (name, usage_line))

    def test_usage_lists_all_subcommands(self):
        text = cli.usage()
        for name in cli.ROUTES:
            self.assertIn(name, text)


class TestTopLevel(unittest.TestCase):
    def test_empty_prints_usage_and_fails(self):
        rc, out = _capture(cli.main, [])
        self.assertEqual(rc, 1)
        self.assertIn("用法", out)

    def test_help_is_ok(self):
        for flag in ("-h", "--help", "help"):
            rc, out = _capture(cli.main, [flag])
            self.assertEqual(rc, 0)
            self.assertIn("子命令", out)

    def test_version_flag(self):
        rc, out = _capture(cli.main, ["--version"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.strip())

    def test_unknown_subcommand(self):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = cli.main(["nope"])
        self.assertEqual(rc, 2)
        self.assertIn("未知子命令", err.getvalue())


class TestPassthrough(_PatchedRoute):
    def test_forwards_raw_argv_without_translation(self):
        """顶层不得翻译/过滤参数 —— 原样交给模块（杜绝静默丢参）。"""
        self.patch("ingest")
        rc = cli.main(["ingest", "a.md", "--overwrite", "--whatever"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [["a.md", "--overwrite", "--whatever"]])

    def test_empty_rest(self):
        self.patch("ingest")
        cli.main(["ingest"])
        self.assertEqual(self.calls, [[]])

    def test_subcommand_h_does_not_execute(self):
        """`ingest -h` 绝不能真的跑一遍入库。"""
        self.patch("ingest")
        rc, out = _capture(cli.main, ["ingest", "-h"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [])
        self.assertIn("用法", out)


if __name__ == "__main__":
    unittest.main()
