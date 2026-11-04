"""M19：练练写回 —— 无 --yes 零网络写；Idempotency-Key；返回体核对。"""
from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from review_tool.pipeline import keepstrong as ks


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestNoYesNoNetwork(unittest.TestCase):
    def test_set_weight_without_yes_does_not_call_urlopen(self):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(req)
            raise AssertionError("不应发网络请求")

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = ks.main(
                ["--set-weight", "act_abc", "60"],
                env={"KEEPSTRONG_API_KEY": "k"},
                urlopen=urlopen,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])
        self.assertIn("--yes", buf.getvalue())
        self.assertIn("60", buf.getvalue())

    def test_log_body_without_yes_no_network(self):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(req)
            return _FakeResp({})

        with mock.patch("sys.stdout", io.StringIO()):
            rc = ks.main(
                ["--log-body", "weight", "82", "--day", "20261015"],
                env={"KEEPSTRONG_API_KEY": "k"},
                urlopen=urlopen,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])


class TestClientWriteGuards(unittest.TestCase):
    def test_set_weight_requires_confirmed(self):
        client = ks.Client("k", urlopen=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("no net")
        ))
        with self.assertRaises(ks.KeepStrongError):
            client.set_action_weight("act_x", 40, user_confirmed=False)

    def test_weight_zero_rejected(self):
        client = ks.Client("k", urlopen=lambda *a, **k: None)
        with self.assertRaises(ks.KeepStrongError):
            client.set_action_weight("act_x", 0, user_confirmed=True)

    def test_empty_weight_sends_empty_string(self):
        seen = {}

        def urlopen(req, timeout=None):
            seen["body"] = json.loads(req.data.decode("utf-8"))
            seen["idem"] = req.headers.get("Idempotency-key") or req.headers.get(
                "Idempotency-Key"
            )
            return _FakeResp({"actionId": "act_x", "weight": ""})

        client = ks.Client("k", urlopen=urlopen, sleep=lambda s: None)
        resp, key = client.set_action_weight("act_x", None, user_confirmed=True)
        self.assertEqual(seen["body"]["weight"], "")
        self.assertTrue(seen["body"]["userConfirmed"])
        self.assertEqual(seen["idem"], key)
        self.assertTrue(key)


class TestIdempotencyAndVerify(unittest.TestCase):
    def test_keys_unique_across_calls(self):
        keys = {ks.new_idempotency_key() for _ in range(20)}
        self.assertEqual(len(keys), 20)

    def test_retry_reuses_same_key(self):
        keys_sent = []

        def urlopen(req, timeout=None):
            keys_sent.append(
                req.headers.get("Idempotency-key")
                or req.headers.get("Idempotency-Key")
            )
            return _FakeResp({"actionId": "act_1", "weight": "50"})

        client = ks.Client("k", urlopen=urlopen, sleep=lambda s: None)
        fixed = "same-key-for-retry"
        client.set_action_weight(
            "act_1", 50, user_confirmed=True, idempotency_key=fixed
        )
        client.set_action_weight(
            "act_1", 50, user_confirmed=True, idempotency_key=fixed
        )
        self.assertEqual(keys_sent, [fixed, fixed])

    def test_mismatched_response_fails(self):
        def urlopen(req, timeout=None):
            return _FakeResp({"actionId": "wrong", "weight": "50"})

        client = ks.Client("k", urlopen=urlopen, sleep=lambda s: None)
        with self.assertRaises(ks.KeepStrongError) as ctx:
            client.set_action_weight("act_1", 50, user_confirmed=True)
        self.assertIn("不一致", str(ctx.exception))

    def test_cli_yes_posts(self):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(req.get_method())
            body = json.loads(req.data.decode("utf-8"))
            return _FakeResp(
                {"actionId": "act_abc", "weight": body["weight"]}
            )

        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            rc = ks.main(
                ["--set-weight", "act_abc", "60", "--yes"],
                env={"KEEPSTRONG_API_KEY": "k"},
                urlopen=urlopen,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["POST"])
        self.assertIn("已写入", out.getvalue())


if __name__ == "__main__":
    unittest.main()
