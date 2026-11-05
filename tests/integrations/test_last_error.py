"""I6：集成 last-error 落盘（无密钥）。"""
from __future__ import annotations

import os
import tempfile
import unittest

from review_tool.integrations import last_error as le


class TestLastError(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.path = os.path.join(self.root, "integration_last_error.json")

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        try:
            os.rmdir(self.root)
        except OSError:
            pass

    def test_write_read_and_strip_secrets(self):
        le.write_last_error(
            {
                "integration": "keepstrong",
                "command": "keepstrong",
                "ok": False,
                "error_kind": "ApiKeyExpired",
                "error_summary": "key dead",
                "http_code": 401,
                "api_key": "SHOULD_NOT_APPEAR",
                "hint": "x",
            },
            path=self.path,
        )
        got = le.read_last_error(path=self.path)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got["integration"], "keepstrong")
        self.assertEqual(got["http_code"], 401)
        self.assertNotIn("api_key", got)
        with open(self.path, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("SHOULD_NOT_APPEAR", raw)

    def test_hint_for_426(self):
        h = le.hint_for(http_code=426)
        self.assertIn("技能", h)

    def test_record_helper(self):
        p = le.record_integration_error(
            "clickup",
            command="clickup-task",
            error_kind="HTTPError",
            error_summary="HTTP 401",
            http_code=401,
            path=self.path,
        )
        self.assertEqual(p, self.path)
        got = le.read_last_error(path=self.path)
        self.assertIn("Key", got.get("hint") or "")


if __name__ == "__main__":
    unittest.main()
