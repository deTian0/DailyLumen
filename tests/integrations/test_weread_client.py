"""微信读书薄客户端单测（全 mock，不触网）。"""
from __future__ import annotations

import json
import unittest

from review_tool.integrations.weread import Client, CredError, WeReadError, load_api_key


class _Resp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestWeReadClient(unittest.TestCase):
    def test_load_api_key_missing(self):
        with self.assertRaises(CredError):
            load_api_key(env={}, settings=type("S", (), {"weread_api_key": ""})())

    def test_call_flat_body_and_skill_version(self):
        seen = {}

        def opener(req, timeout=0):
            seen["url"] = req.full_url
            seen["body"] = json.loads(req.data.decode("utf-8"))
            return _Resp({"errcode": 0, "books": []})

        c = Client("wrk-test", opener=opener, skill_version="1.0.6")
        out = c.shelf_sync()
        self.assertEqual(out.get("books"), [])
        self.assertEqual(seen["body"]["api_name"], "/shelf/sync")
        self.assertEqual(seen["body"]["skill_version"], "1.0.6")
        self.assertNotIn("params", seen["body"])

    def test_errcode_raises(self):
        def opener(req, timeout=0):
            return _Resp({"errcode": 1001, "errmsg": "bad"})

        c = Client("wrk-test", opener=opener)
        with self.assertRaises(WeReadError):
            c.readdata_detail(mode="weekly")


if __name__ == "__main__":
    unittest.main()
