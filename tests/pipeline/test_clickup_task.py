"""I2：clickup-task 薄写 CLI（全离线）。"""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from review_tool.pipeline import clickup_task as ct


class _FakeNet:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.comments: dict[str, list] = {}
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []
        self._next_id = 1

    def get(self, path, key, *, timeout=None):
        if path.startswith("/task/") and path.endswith("/comment"):
            tid = path.split("/task/", 1)[1].split("/", 1)[0]
            return {"comments": list(self.comments.get(tid) or [])}
        if path.startswith("/task/"):
            tid = path.split("/task/", 1)[1].split("?", 1)[0]
            return dict(self.tasks.get(tid) or {"id": tid, "name": "?"})
        return {}

    def put(self, path, key, body, *, timeout=None):
        self.puts.append((path, dict(body)))
        tid = path.split("/task/", 1)[1]
        cur = dict(self.tasks.get(tid) or {"id": tid, "name": "t"})
        if "status" in body:
            cur["status"] = {"status": body["status"], "type": "custom"}
        self.tasks[tid] = cur
        return dict(cur)

    def post(self, path, key, body, *, timeout=None):
        self.posts.append((path, dict(body)))
        if "/list/" in path and path.endswith("/task"):
            tid = f"t{self._next_id}"
            self._next_id += 1
            task = {"id": tid, "name": body.get("name"), "status": {"status": "open"}}
            self.tasks[tid] = task
            return dict(task)
        if path.endswith("/comment"):
            tid = path.split("/task/", 1)[1].split("/", 1)[0]
            cid = f"c{len(self.comments.get(tid) or []) + 1}"
            row = {"id": cid, "comment_text": body.get("comment_text")}
            self.comments.setdefault(tid, []).append(row)
            return dict(row)
        return {}


def _capture(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


class TestClickUpTaskCli(unittest.TestCase):
    def setUp(self):
        self.net = _FakeNet()

    def test_dry_run_create_no_network_write(self):
        rc, out, _err = _capture(
            ct.main,
            ["--create", "买菜", "--list", "L1"],
            key="k",
            get=self.net.get,
            put=self.net.put,
            post=self.net.post,
        )
        self.assertEqual(rc, 0)
        self.assertIn("dry-run", out)
        self.assertEqual(self.net.posts, [])

    def test_apply_create_and_status_and_comment(self):
        rc, out, _ = _capture(
            ct.main,
            ["--create", "买菜", "--list", "L1", "--apply"],
            key="k",
            get=self.net.get,
            put=self.net.put,
            post=self.net.post,
        )
        self.assertEqual(rc, 0)
        self.assertIn("已创建", out)
        tid = next(iter(self.net.tasks))

        rc2, out2, _ = _capture(
            ct.main,
            ["--status", tid, "complete", "--apply"],
            key="k",
            get=self.net.get,
            put=self.net.put,
            post=self.net.post,
        )
        self.assertEqual(rc2, 0)
        self.assertIn("回读校验通过", out2)

        rc3, out3, _ = _capture(
            ct.main,
            ["--comment", tid, "备注一下", "--apply"],
            key="k",
            get=self.net.get,
            put=self.net.put,
            post=self.net.post,
        )
        self.assertEqual(rc3, 0)
        self.assertIn("加评论", out3)

    def test_disabled_integration_no_network(self):
        with mock.patch.dict(
            "review_tool.config.INTEGRATIONS", {"clickup": False}, clear=False
        ):
            rc, _out, err = _capture(
                ct.main,
                ["--create", "x", "--list", "L1", "--apply"],
                key="k",
                post=self.net.post,
            )
        self.assertEqual(rc, 2)
        self.assertIn("INTEGRATION_CLICKUP", err)
        self.assertEqual(self.net.posts, [])

    def test_does_not_import_habit_or_track_storage(self):
        # 静态守卫：不 import storage / habit_logs 写入路径（文档提及边界名除外）
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(ct))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported.add(a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        joined = " ".join(imported)
        self.assertNotIn("storage", joined)
        self.assertNotIn("habit_sync", joined)
        self.assertNotIn("personal_tracks", joined)


if __name__ == "__main__":
    unittest.main()
