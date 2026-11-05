"""ClickUp integrations 门面：mock HTTP，不提交真实 token。"""
from __future__ import annotations

import unittest
from unittest import mock

from review_tool.integrations.clickup import Client, fetch_tasks, http_get, http_put


class _FakeTransport:
    def __init__(self):
        self.gets: list[str] = []
        self.puts: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []
        self.deletes: list[str] = []

    def get(self, path, key, *, timeout=None):
        self.gets.append(path)
        if "/task/" in path and "/comment" in path:
            return {"comments": [{"id": "c1", "comment_text": "hi"}]}
        if path.startswith("/task/") and "/field/" not in path:
            return {"id": "t1", "name": "任务", "custom_fields": [{"id": "f1", "value": 1}]}
        if path.startswith("/list/") and "/task" not in path:
            return {"id": "L1", "name": "日常事务"}
        if "/list/" in path and "/task" in path:
            page = int(path.rsplit("page=", 1)[-1])
            if page == 0:
                return {"tasks": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}
            return {"tasks": []}
        return {}

    def put(self, path, key, body, *, timeout=None):
        self.puts.append((path, body))
        return {"id": "t1", **body}

    def post(self, path, key, body, *, timeout=None):
        self.posts.append((path, body))
        return {"id": "new", **body}

    def delete(self, path, key, *, timeout=None):
        self.deletes.append(path)
        return None


class TestClickUpClient(unittest.TestCase):
    def setUp(self):
        self.net = _FakeTransport()
        self.client = Client(
            "fake-key",
            get=self.net.get,
            put=self.net.put,
            post=self.net.post,
            delete=self.net.delete,
        )

    def test_list_tasks_paginates_and_dedupes(self):
        tasks = self.client.list_tasks("L1")
        self.assertEqual([t["id"] for t in tasks], ["a", "b"])
        self.assertTrue(any("include_closed=true" in p for p in self.net.gets))

    def test_get_update_create_task(self):
        t = self.client.get_task("t1")
        self.assertEqual(t["id"], "t1")
        self.client.update_task("t1", status="complete")
        self.assertEqual(self.net.puts[-1][1]["status"], "complete")
        self.client.create_task("L1", "新任务", priority=2)
        self.assertEqual(self.net.posts[-1][0], "/list/L1/task")
        self.assertEqual(self.net.posts[-1][1]["name"], "新任务")

    def test_comments_and_custom_field(self):
        comments = self.client.list_comments("t1")
        self.assertEqual(comments[0]["id"], "c1")
        self.client.add_comment("t1", "备注")
        self.assertIn("comment_text", self.net.posts[-1][1])
        self.client.set_custom_field("t1", "f1", "v")
        self.assertTrue(self.net.posts[-1][0].endswith("/field/f1"))
        fields = self.client.get_custom_fields(task_id="t1")
        self.assertEqual(fields[0]["id"], "f1")

    def test_delete_task_and_get_list(self):
        self.assertIsNone(self.client.delete_task("t1"))
        self.assertEqual(self.net.deletes[-1], "/task/t1")
        meta = self.client.get_list("L1")
        self.assertEqual(meta["name"], "日常事务")
        self.assertTrue(any(p == "/list/L1" for p in self.net.gets))

    def test_fetch_tasks_compat_with_injected_fetch(self):
        def fetch(path, key, *, timeout=None):
            if "page=0" in path:
                return {"tasks": [{"id": "x"}] * 3}
            return {"tasks": []}

        out = fetch_tasks("L", "k", fetch=fetch)
        self.assertEqual(len(out), 1)  # 按 id 去重


class TestClickUpHttpHelpers(unittest.TestCase):
    def test_http_get_put_use_auth_header(self):
        captured = {}

        class _Resp:
            def read(self):
                return b'{"ok":true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            captured["method"] = req.get_method()
            return _Resp()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            http_get("/task/1", "TOKEN", base_url="https://example.test")
            self.assertEqual(captured["headers"].get("Authorization"), "TOKEN")
            http_put("/task/1", "TOKEN", {"status": "complete"},
                     base_url="https://example.test")
            self.assertEqual(captured["method"], "PUT")


class TestIntegrationFlags(unittest.TestCase):
    def test_disabled_blocks_require(self):
        from review_tool.integrations.flags import (
            IntegrationDisabled,
            require_enabled,
        )

        with mock.patch.dict(
            "review_tool.config.INTEGRATIONS", {"clickup": False}, clear=False
        ):
            with self.assertRaises(IntegrationDisabled) as ctx:
                require_enabled("clickup")
            self.assertIn("INTEGRATION_CLICKUP_ENABLED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
