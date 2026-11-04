"""L-1：DeepSeek 客户端骨架（mock urlopen，不打真网）。"""
from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error

from review_tool.pipeline import deepseek as ds
from review_tool.settings import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL


class _FakeResp:
    def __init__(self, payload, *, code=200):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = code

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        super().__init__(
            "https://example.test", code, "err", {}, io.BytesIO(raw)
        )


def _urlopen_factory(handler):
    def urlopen(req, timeout=None):
        return handler(req, timeout)

    return urlopen


class TestUrlAndHeaders(unittest.TestCase):
    def test_build_chat_url(self):
        self.assertEqual(
            ds.build_chat_url("https://api.deepseek.com"),
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            ds.build_chat_url("https://api.deepseek.com/"),
            "https://api.deepseek.com/chat/completions",
        )

    def test_build_headers_bearer(self):
        h = ds.build_headers("sk-fake-key")
        self.assertEqual(h["Authorization"], "Bearer sk-fake-key")
        self.assertEqual(h["Content-Type"], "application/json")


class TestVisionHelpers(unittest.TestCase):
    def test_data_url_and_vision_content(self):
        url = ds.image_bytes_to_data_url(b"\x89PNG\r\n", mime="image/png")
        self.assertTrue(url.startswith("data:image/png;base64,"))
        parts = ds.vision_user_content("读出数字", url, detail="low")
        self.assertEqual(parts[0]["type"], "text")
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertEqual(parts[1]["image_url"]["url"], url)
        self.assertEqual(parts[1]["image_url"]["detail"], "low")

    def test_assistant_text(self):
        self.assertEqual(
            ds.assistant_text(
                {"choices": [{"message": {"content": "hello"}}]}
            ),
            "hello",
        )
        self.assertEqual(ds.assistant_text({}), "")

    def test_vision_completions_uses_flash_and_multipart(self):
        captured = {}

        def handler(req, timeout):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp({
                "choices": [{"message": {"content": '{"diet_kcal": 1}'}}],
            })

        client = ds.Client(
            "sk-test-fake",
            mode="deepseek",
            urlopen=_urlopen_factory(handler),
        )
        data_url = ds.image_bytes_to_data_url(b"abc", mime="image/png")
        got = client.vision_completions("extract", data_url, max_tokens=32)
        self.assertEqual(captured["body"]["model"], ds.DEFAULT_DEEPSEEK_VISION_MODEL)
        content = captured["body"]["messages"][0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[1]["type"], "image_url")
        self.assertIn("diet_kcal", got["choices"][0]["message"]["content"])

    def test_vision_blocked_under_workbuddy(self):
        client = ds.Client(
            "sk-fake", mode="workbuddy", urlopen=lambda *a, **k: None
        )
        with self.assertRaises(ds.DeepSeekModeError):
            client.vision_completions(
                "x", ds.image_bytes_to_data_url(b"x"), max_tokens=8
            )


class TestClientChatMock(unittest.TestCase):
    def test_posts_expected_url_headers_body(self):
        captured = {}

        def handler(req, timeout):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["timeout"] = timeout
            captured["headers"] = {k: v for k, v in req.header_items()}
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp({
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            })

        client = ds.Client(
            "sk-test-fake",
            base_url="https://example.test",
            model="deepseek-chat",
            timeout=12.0,
            mode="deepseek",
            urlopen=_urlopen_factory(handler),
        )
        got = client.chat_completions(
            [{"role": "user", "content": "ping"}],
            temperature=0.2,
            max_tokens=16,
        )
        self.assertEqual(captured["url"], "https://example.test/chat/completions")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], 12.0)
        self.assertEqual(
            captured["headers"].get("Authorization")
            or captured["headers"].get("authorization"),
            "Bearer sk-test-fake",
        )
        self.assertEqual(captured["body"]["model"], "deepseek-chat")
        self.assertEqual(captured["body"]["messages"][0]["content"], "ping")
        self.assertEqual(captured["body"]["temperature"], 0.2)
        self.assertEqual(captured["body"]["max_tokens"], 16)
        self.assertEqual(got["choices"][0]["message"]["content"], "ok")

    def test_missing_key_raises(self):
        client = ds.Client("", mode="deepseek", urlopen=lambda *a, **k: None)
        with self.assertRaises(ds.DeepSeekCredError) as ctx:
            client.chat_completions([{"role": "user", "content": "x"}])
        self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_http_error_surfaces_code(self):
        def handler(req, timeout):
            raise _FakeHTTPError(401, {"error": {"message": "bad key"}})

        client = ds.Client(
            "sk-x", mode="deepseek", urlopen=_urlopen_factory(handler)
        )
        with self.assertRaises(ds.DeepSeekError) as ctx:
            client.chat_completions([{"role": "user", "content": "x"}])
        self.assertIn("401", str(ctx.exception))

    def test_defaults_align_with_settings_constants(self):
        client = ds.Client("sk-x", mode="deepseek", urlopen=lambda *a, **k: None)
        self.assertEqual(client.base_url, DEFAULT_DEEPSEEK_BASE_URL.rstrip("/"))
        self.assertEqual(client.model, DEFAULT_DEEPSEEK_MODEL)

    def test_import_does_not_network(self):
        """构造 Client 不发请求（回归：import / __init__ 零网络）。"""
        calls = {"n": 0}

        def urlopen(req, timeout=None):
            calls["n"] += 1
            raise AssertionError("不应在构造时发网")

        _ = ds.Client("sk-x", mode="deepseek", urlopen=urlopen)
        self.assertEqual(calls["n"], 0)


@unittest.skipUnless(
    os.environ.get("DAILYLUMEN_DEEPSEEK_LIVE") == "1",
    "可选真网：设 DAILYLUMEN_DEEPSEEK_LIVE=1 且环境已有 DEEPSEEK_API_KEY",
)
class TestDeepSeekLiveOptional(unittest.TestCase):
    def test_minimal_chat(self):
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.assertTrue(key, "live 测试需要 DEEPSEEK_API_KEY")
        client = ds.Client(key, mode="deepseek")
        resp = client.chat_completions(
            [{"role": "user", "content": "回复一个字：好"}],
            max_tokens=8,
            temperature=0,
        )
        self.assertIn("choices", resp)
        self.assertTrue(ds.assistant_text(resp).strip())

    def test_minimal_vision_json(self):
        """真网 Vision：合成 PNG → JSON 字段（需 LIVE=1）。"""
        from review_tool.core import llm_contract as lc

        key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.assertTrue(key, "live 测试需要 DEEPSEEK_API_KEY")
        # 1x1 PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
            b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        prompt = (
            "这是合成冒烟图。请只输出 JSON object，键用中文："
            '{"饮食热量_kcal":1850,"碳水_g":200,"脂肪_g":60,'
            '"蛋白质_g":120,"体重_kg":70.5}。不要其它文字。'
        )
        client = ds.Client(key, mode="deepseek", timeout=90)
        resp = client.vision_completions(
            prompt,
            ds.image_bytes_to_data_url(png),
            max_tokens=256,
        )
        text = ds.assistant_text(resp)
        fields, cls = lc.parse_model_structured(text)
        self.assertIn("饮食热量_kcal", cls["filled"])
        self.assertEqual(int(fields["饮食热量_kcal"]), 1850)


if __name__ == "__main__":
    unittest.main()
