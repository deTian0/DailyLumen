"""M20：练练训练记录只保留 status==completed。"""
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


class TestIsCompleted(unittest.TestCase):
    def test_completed_only(self):
        self.assertTrue(ks.is_completed_record({"status": "completed"}))
        self.assertTrue(ks.is_completed_record({"status": " completed "}))

    def test_missing_or_unknown_excluded(self):
        self.assertFalse(ks.is_completed_record({}))
        self.assertFalse(ks.is_completed_record({"status": None}))
        self.assertFalse(ks.is_completed_record({"status": ""}))
        self.assertFalse(ks.is_completed_record({"status": "pending"}))
        self.assertFalse(ks.is_completed_record({"status": "Cancelled"}))
        self.assertFalse(ks.is_completed_record(None))
        self.assertFalse(ks.is_completed_record("completed"))  # type: ignore[arg-type]

    def test_filter_completed_records(self):
        rows = [
            {"id": "a", "status": "completed"},
            {"id": "b", "status": "pending"},
            {"id": "c"},  # 缺字段
            {"id": "d", "status": "unknown"},
            {"id": "e", "status": "completed"},
        ]
        got = ks.filter_completed_records(rows)
        self.assertEqual([r["id"] for r in got], ["a", "e"])
        self.assertEqual(ks.filter_completed_records(None), [])
        self.assertEqual(ks.filter_completed_records([]), [])


class TestIterFiltersStatus(unittest.TestCase):
    def test_iter_training_records_drops_non_completed(self):
        pages = {
            1: {
                "list": [
                    {"dayStr": "20261001", "status": "completed", "durationSeconds": 161},
                    {"dayStr": "20261001", "status": "pending", "durationSeconds": 999},
                    {"dayStr": "20261001", "durationSeconds": 50},  # 无 status
                ],
                "hasMore": False,
            },
        }

        def handler(req, timeout):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)
            return _FakeResp(pages[int(qs["page"][0])])

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        rows = client.iter_training_records("20261001", "20261001")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["durationSeconds"], 161)

    def test_collect_only_completed(self):
        def handler(req, timeout):
            path = urllib.parse.urlparse(req.full_url).path
            if path.endswith("/training/records"):
                return _FakeResp({
                    "list": [
                        {"dayStr": "20261001", "status": "completed", "actions": []},
                        {"dayStr": "20261001", "status": "skipped", "actions": []},
                    ],
                    "hasMore": False,
                })
            return _FakeResp({})

        client = ks.Client("k", urlopen=_urlopen_factory(handler), sleep=lambda s: None)
        bundle = ks.collect("20261001", "20261001", types={"records"}, client=client)
        self.assertEqual(len(bundle["records"]), 1)
        self.assertEqual(bundle["records"][0]["status"], "completed")


class TestOfflineFallbackHint(unittest.TestCase):
    def test_api_failure_prints_offline_fallback(self):
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
        msg = err.getvalue()
        self.assertIn("离线兜底", msg)
        self.assertIn("training_weekdays", msg)
        self.assertIn("未写入", msg)


if __name__ == "__main__":
    unittest.main()
