"""Web 看板 W14：serve 最小鉴权（无 key / 错 key / 对 key / 未配置 key 启动）。"""
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    HAVE_WEB = True
except ImportError:
    HAVE_WEB = False

from review_tool.api import auth

KEY = "unit-test-key-Abc123_-"


class TestAuthHelpers(unittest.TestCase):
    def test_extract_bearer_and_custom_header(self):
        self.assertEqual(auth.extract_key({"authorization": f"Bearer {KEY}"}), KEY)
        self.assertEqual(auth.extract_key({"authorization": f"bearer   {KEY} "}), KEY)
        self.assertEqual(auth.extract_key({"x-dailylumen-key": KEY}), KEY)
        self.assertIsNone(auth.extract_key({"authorization": f"Basic {KEY}"}))
        self.assertIsNone(auth.extract_key({"authorization": "Bearer "}))
        self.assertIsNone(auth.extract_key({}))

    def test_key_matches_constant_time_and_fail_closed(self):
        self.assertTrue(auth.key_matches(KEY, KEY))
        self.assertFalse(auth.key_matches(KEY + "x", KEY))
        self.assertFalse(auth.key_matches(None, KEY))
        self.assertFalse(auth.key_matches("", ""))  # 未配置 → 一律拒绝
        self.assertFalse(auth.key_matches("中文", KEY))  # 非 ASCII 不抛异常
        with mock.patch.object(auth.hmac, "compare_digest", return_value=True) as cd:
            auth.key_matches("a", "b")
        cd.assert_called_once()

    def test_requires_key_paths(self):
        self.assertTrue(auth.requires_key("/api/health"))
        self.assertTrue(auth.requires_key("/api"))
        self.assertTrue(auth.requires_key("/api/write/confirm"))
        self.assertFalse(auth.requires_key("/api/ping"))
        self.assertFalse(auth.requires_key("/"))
        self.assertFalse(auth.requires_key("/assets/index.js"))
        self.assertFalse(auth.requires_key("/apix"))


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestAuthMiddleware(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        with open(f"{self.tmp.name}/index.html", "wb") as f:
            f.write(b"<html>INDEX</html>")
        self.client = TestClient(create_app(dist_dir=self.tmp.name, web_key=KEY),
                                 base_url="http://127.0.0.1:8765")

    def test_no_key_401(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "unauthorized")
        self.assertEqual(r.headers.get("www-authenticate"), "Bearer")

    def test_wrong_key_401_and_not_echoed(self):
        for h in ({"Authorization": "Bearer wrong"}, {"X-DailyLumen-Key": "wrong"}):
            r = self.client.get("/api/health", headers=h)
            self.assertEqual(r.status_code, 401, h)
            self.assertNotIn("wrong", r.text)
            self.assertNotIn(KEY, r.text)

    def test_right_key_200_both_headers(self):
        for h in ({"Authorization": f"Bearer {KEY}"}, {"X-DailyLumen-Key": KEY}):
            r = self.client.get("/api/health", headers=h)
            self.assertEqual(r.status_code, 200, h)
            self.assertNotIn(KEY, r.text)

    def test_unknown_api_also_needs_key(self):
        self.assertEqual(self.client.get("/api/nope").status_code, 401)
        self.assertEqual(self.client.get("/api/nope", headers={"X-DailyLumen-Key": KEY}).status_code, 404)

    def test_query_string_key_not_accepted(self):
        self.assertEqual(self.client.get(f"/api/health?key={KEY}").status_code, 401)

    def test_post_needs_key_too(self):
        r = self.client.post("/api/write/confirm", json={"token": "x"})
        self.assertEqual(r.status_code, 401)

    def test_ping_is_open_and_contentless(self):
        r = self.client.get("/api/ping")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})

    def test_static_dist_needs_no_key(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("INDEX", r.text)
        self.assertNotIn(KEY, r.text)

    def test_host_guard_still_first(self):
        r = self.client.get("/api/health", headers={"host": "evil.example.com", "X-DailyLumen-Key": KEY})
        self.assertEqual(r.status_code, 403)

    def test_origin_guard_still_applies(self):
        r = self.client.post("/api/anything", headers={"origin": "http://evil.example.com",
                                                        "X-DailyLumen-Key": KEY})
        self.assertEqual(r.status_code, 403)

    def test_empty_key_rejects_everything(self):
        c = TestClient(create_app(dist_dir=self.tmp.name, web_key=""), base_url="http://127.0.0.1:8765")
        self.assertEqual(c.get("/api/health", headers={"X-DailyLumen-Key": ""}).status_code, 401)
        self.assertEqual(c.get("/api/health", headers={"Authorization": "Bearer "}).status_code, 401)


@unittest.skipUnless(HAVE_WEB, "未安装 web extra")
class TestServeKey(unittest.TestCase):
    def test_refuses_to_start_without_key(self):
        from review_tool.api import serve

        err = io.StringIO()
        with mock.patch("uvicorn.run") as run, redirect_stderr(err), \
             mock.patch.object(serve, "load_web_key", return_value=""), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            rc = serve.main([])
        self.assertEqual(rc, 2)
        run.assert_not_called()
        self.assertIn("DAILYLUMEN_WEB_KEY", err.getvalue())
        self.assertIn("local/.env", err.getvalue())

    def test_starts_with_key_and_passes_it_to_app(self):
        from review_tool.api import serve

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("uvicorn.run") as run, redirect_stderr(err), \
             mock.patch.object(serve, "load_web_key", return_value=KEY), \
             mock.patch("sys.stdout", out):
            rc = serve.main(["--port", "9001"])
        self.assertEqual(rc, 0)
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())  # key 不进控制台
        app = run.call_args.args[0]
        c = TestClient(app, base_url="http://127.0.0.1:9001")
        self.assertEqual(c.get("/api/health").status_code, 401)
        self.assertEqual(c.get("/api/health", headers={"Authorization": f"Bearer {KEY}"}).status_code, 200)

    def test_load_web_key_reads_settings(self):
        from review_tool.api import serve
        from review_tool.settings import load_settings

        s = load_settings(env_path="", environ={"DAILYLUMEN_WEB_KEY": " abc "})
        self.assertEqual(s.web_key, " abc ")
        self.assertNotIn("abc", repr(s))
        with mock.patch("review_tool.settings.SETTINGS", s):
            self.assertEqual(serve.load_web_key(), "abc")


if __name__ == "__main__":
    unittest.main()
