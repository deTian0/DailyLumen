"""M17：练练健身 HTTP 客户端（全离线，mock urlopen）。"""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest import mock

from review_tool.pipeline import keepstrong as ks


class _FakeResp:
    def __init__(self, payload, *, code=200, headers=None):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = code
        self.headers = headers or {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, payload, headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        super().__init__(
            "https://example.test", code, "err", headers or {}, io.BytesIO(raw)
        )


def _urlopen_factory(handler):
    def urlopen(req, timeout=None):
        return handler(req, timeout)

    return urlopen


class TestDateHelpers(unittest.TestCase):
    def test_to_day_str_accepts_both(self):
        self.assertEqual(ks.to_day_str("2026-10-01"), "20261001")
        self.assertEqual(ks.to_day_str("20261001"), "20261001")

    def test_bad_date_raises(self):
        with self.assertRaises(ValueError):
            ks.to_day_str("2026/10/01")


class TestEncodeQuery(unittest.TestCase):
    def test_chinese_keyword_is_percent_encoded(self):
        qs = ks.encode_query({"keyword": "深蹲", "page": 1})
        self.assertIn("keyword=", qs)
        self.assertNotIn("深蹲", qs)
        self.assertIn(urllib.parse.quote("深蹲", safe=""), qs)


class TestBuildHeaders(unittest.TestCase):
    def test_required_headers(self):
        h = ks.build_headers("secret-key", skill_version="1.28.0", agent_name="WorkBuddy")
        self.assertEqual(h["Authorization"], "Bearer secret-key")
        self.assertEqual(h["X-KeepStrong-Skill-Version"], "1.28.0")
        self.assertEqual(h["X-KeepStrong-Agent-Name"], "WorkBuddy")
        self.assertEqual(h["X-Timezone-Offset"], "480")
        self.assertNotIn("Idempotency-Key", h)


class TestClientErrors(unittest.TestCase):
    def test_401_api_key_expired(self):
        def handler(req, timeout):
            raise _FakeHTTPError(401, {"apiKeyExpired": True})

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        with self.assertRaises(ks.ApiKeyExpired) as ctx:
            client.get("/api/v1/ai/body/profile")
        self.assertIn("连接 AI", str(ctx.exception))
        self.assertIn("练练健身", str(ctx.exception))

    def test_426_skill_update(self):
        def handler(req, timeout):
            raise _FakeHTTPError(
                426, {"skillUpdateRequired": True, "skillUrl": "https://x/skill"}
            )

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        with self.assertRaises(ks.SkillUpdateRequired):
            client.get("/x")

    def test_429_respects_retry_after_once(self):
        calls = {"n": 0, "slept": []}

        def handler(req, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _FakeHTTPError(
                    429, {"error": "rate"}, headers={"Retry-After": "1.5"}
                )
            return _FakeResp({"ok": True})

        def sleep(s):
            calls["slept"].append(s)

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=sleep)
        got = client.get("/x")
        self.assertEqual(got, {"ok": True})
        self.assertEqual(calls["n"], 2)
        self.assertEqual(calls["slept"], [1.5])

    def test_429_no_tight_loop_without_retry_after(self):
        calls = {"n": 0}

        def handler(req, timeout):
            calls["n"] += 1
            raise _FakeHTTPError(429, {})

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        with self.assertRaises(ks.RateLimited):
            client.get("/x")
        self.assertEqual(calls["n"], 1)


class TestClientReads(unittest.TestCase):
    def test_records_pagination(self):
        pages = {
            1: {"list": [{"dayStr": "20261001", "durationSeconds": 161, "actions": []}],
                "hasMore": True},
            2: {"list": [{"dayStr": "20261002", "durationSeconds": 10, "actions": []}],
                "hasMore": False},
        }

        def handler(req, timeout):
            url = req.full_url
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            page = int(qs["page"][0])
            return _FakeResp(pages[page])

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        rows = client.iter_training_records("20261001", "20261007")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["dayStr"], "20261001")

    def test_search_actions_encodes_chinese_in_url(self):
        seen = []

        def handler(req, timeout):
            seen.append(req.full_url)
            return _FakeResp({"list": [], "hasMore": False})

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        client.search_actions("深蹲")
        self.assertTrue(seen)
        self.assertNotIn("深蹲", seen[0])
        self.assertIn(urllib.parse.quote("深蹲", safe=""), seen[0])


class TestLoadApiKey(unittest.TestCase):
    def test_missing_key_guides_user(self):
        with self.assertRaises(ks.CredError) as ctx:
            ks.load_api_key(env={}, settings=mock.Mock(keepstrong_api_key=""))
        msg = str(ctx.exception)
        self.assertIn("KEEPSTRONG_API_KEY", msg)
        self.assertIn("练练健身", msg)
        self.assertIn("连接 AI", msg)

    def test_env_wins(self):
        self.assertEqual(ks.load_api_key(env={"KEEPSTRONG_API_KEY": "abc"}), "abc")


class TestCli(unittest.TestCase):
    def test_help(self):
        rc = ks.main(["-h"])
        self.assertEqual(rc, 0)

    def test_no_key_exit_2(self):
        # 强制空 key：env 空 + 模块 SETTINGS 空（避免读到本机 .env）
        with mock.patch.object(ks, "SETTINGS", mock.Mock(keepstrong_api_key="")):
            err = io.StringIO()
            with mock.patch("sys.stderr", err):
                rc = ks.main(["--date", "20261001", "--stdout"], env={})
        self.assertEqual(rc, 2)
        self.assertIn("KEEPSTRONG_API_KEY", err.getvalue())

    def test_stdout_with_empty_records(self):
        def handler(req, timeout):
            path = urllib.parse.urlparse(req.full_url).path
            if path.endswith("/training/records"):
                return _FakeResp({"list": [], "hasMore": False})
            if path.endswith("/body/profile"):
                return _FakeResp({"weight": 82})
            if path.endswith("/body/logs"):
                return _FakeResp({"list": [], "hasMore": False})
            if path.endswith("/running-plans"):
                return _FakeResp({"list": []})
            return _FakeResp({})

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = ks.main(
                ["--date", "20261008", "--stdout", "--type", "records"],
                env={"KEEPSTRONG_API_KEY": "test-key"},
                urlopen=_urlopen_factory(handler),
                now=lambda: "T",
            )
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("练练健身", out)
        self.assertIn("无训练记录", out)
        self.assertNotIn("test-key", out)
        self.assertNotIn("Bearer", out)
        # 「Authorization」只允许出现在「不含 Authorization 头」声明里
        self.assertIn("不含", out)
        self.assertNotRegex(out, r"(?i)authorization\s*:")

    def test_expired_key_exit_1_with_guidance(self):
        def handler(req, timeout):
            raise _FakeHTTPError(401, {"apiKeyExpired": True})

        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            rc = ks.main(
                ["--date", "20261001", "--stdout", "--type", "records"],
                env={"KEEPSTRONG_API_KEY": "dead"},
                urlopen=_urlopen_factory(handler),
            )
        self.assertEqual(rc, 1)
        self.assertIn("连接 AI", err.getvalue())


if __name__ == "__main__":
    unittest.main()
