"""I3/I4：练练 Client 扩展读/写（全离线 mock）。"""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.parse

from review_tool.integrations.keepstrong import Client, KeepStrongError


class _FakeResp:
    def __init__(self, payload, *, code=200):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = code
        self.headers = {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_factory(handler):
    def urlopen(req, timeout=None):
        return handler(req, timeout)

    return urlopen


class TestActionHistoryAndTemplates(unittest.TestCase):
    def test_action_history_paginates_on_has_more(self):
        calls = []

        def handler(req, timeout):
            calls.append(req.full_url)
            qs = urllib.parse.urlparse(req.full_url).query
            page = int(urllib.parse.parse_qs(qs).get("page", ["1"])[0])
            if page == 1:
                return _FakeResp({"list": [{"set": 1}], "hasMore": True})
            return _FakeResp({"list": [{"set": 2}], "hasMore": False})

        c = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler))
        items = c.action_history("act_1", "2026-10-01", "2026-10-15")
        self.assertEqual(len(items), 2)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any("/actions/act_1/history" in u for u in calls))

    def test_templates_paginates(self):
        def handler(req, timeout):
            qs = urllib.parse.urlparse(req.full_url).query
            page = int(urllib.parse.parse_qs(qs).get("page", ["1"])[0])
            if page == 1:
                return _FakeResp({"list": [{"templateId": "A"}], "hasMore": True})
            return _FakeResp({"list": [{"templateId": "B"}], "hasMore": False})

        c = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler))
        items = c.templates()
        self.assertEqual([i["templateId"] for i in items], ["A", "B"])

    def test_food_search_encodes_chinese(self):
        seen = []

        def handler(req, timeout):
            seen.append(req.full_url)
            return _FakeResp({"list": [{"name": "米饭"}]})

        c = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler))
        items = c.food_search("米饭")
        self.assertEqual(len(items), 1)
        self.assertNotIn("米饭", seen[0])
        self.assertIn(urllib.parse.quote("米饭", safe=""), seen[0])


class TestTemplateWrites(unittest.TestCase):
    def test_create_template_requires_yes(self):
        c = Client("k", base_url="https://example.test", urlopen=lambda *a, **k: None)
        with self.assertRaises(KeepStrongError):
            c.create_template("课", [{"actionId": "a"}], user_confirmed=False)

    def test_create_and_replace_template(self):
        posts = []

        def handler(req, timeout):
            body = json.loads(req.data.decode("utf-8")) if req.data else {}
            posts.append((req.get_method(), req.full_url, body))
            if req.full_url.endswith("/templates"):
                return _FakeResp({"name": body["name"], "templateId": "T1"})
            return _FakeResp({"templateId": "T1", "ok": True})

        c = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler))
        resp, key = c.create_template(
            "全身A", [{"actionId": "a1"}], user_confirmed=True
        )
        self.assertEqual(resp["templateId"], "T1")
        self.assertTrue(key)
        self.assertTrue(posts[0][2].get("userConfirmed"))

        headers_seen = []

        def handler2(req, timeout):
            headers_seen.append({k.lower(): v for k, v in req.headers.items()})
            return _FakeResp({"templateId": "T1"})

        c2 = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler2))
        c2.replace_template_actions("T1", [{"actionId": "a2"}], user_confirmed=True)
        flat = {k: v for h in headers_seen for k, v in h.items()}
        self.assertTrue(
            any("idempotency-key" == k for k in flat)
            or any("Idempotency-Key" in str(h) for h in headers_seen)
            or "idempotency-key" in flat
        )

    def test_plan_command_rejects_unknown(self):
        c = Client("k", base_url="https://example.test", urlopen=lambda *a, **k: None)
        with self.assertRaises(KeepStrongError):
            c.running_plan_command("p1", "explode", user_confirmed=True)


class TestFoodLogsOptional(unittest.TestCase):
    def test_food_logs_single_day(self):
        def handler(req, timeout):
            self.assertIn("dayStr=20261015", req.full_url)
            return _FakeResp({"foodLogs": [], "exerciseLogs": []})

        c = Client("k", base_url="https://example.test", urlopen=_urlopen_factory(handler))
        data = c.food_logs("2026-10-15")
        self.assertEqual(data["foodLogs"], [])


if __name__ == "__main__":
    unittest.main()
