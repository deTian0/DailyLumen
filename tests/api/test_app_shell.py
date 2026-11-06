"""Web 看板 W1：app 壳（health / Host+Origin 守卫 / 统一错误体 / SPA / serve 缺依赖提示）。"""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    HAVE_WEB = True
except ImportError:  # 未装 web extra 时整组跳过
    HAVE_WEB = False

LOCAL = {"host": "127.0.0.1:8765"}


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestHealth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = TestClient(create_app(dist_dir=self.tmp.name), base_url="http://127.0.0.1:8765")

    def test_health_shape_and_no_secrets(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(
            set(data),
            {"status", "version", "llm_mode", "integrations", "ai_enabled", "db_present", "readonly"},
        )
        self.assertEqual(set(data["integrations"]), {"clickup", "keepstrong", "deepseek"})
        self.assertTrue(data["readonly"])
        blob = r.text.lower()
        for bad in ("api_key", "token", "secret", "password", os.sep):
            self.assertNotIn(bad, blob)

    def test_health_version_matches_package(self):
        from review_tool import __version__

        self.assertEqual(self.client.get("/api/health").json()["version"], __version__)

    def test_ai_enabled_requires_mode_and_flag(self):
        from review_tool.api import health

        with mock.patch.object(health, "get_llm_mode", return_value="deepseek"), \
             mock.patch.object(health, "is_enabled", side_effect=lambda n: n == "deepseek"):
            self.assertTrue(health.build_health()["ai_enabled"])
        with mock.patch.object(health, "get_llm_mode", return_value="workbuddy"), \
             mock.patch.object(health, "is_enabled", return_value=True):
            self.assertFalse(health.build_health()["ai_enabled"])
        with mock.patch.object(health, "get_llm_mode", return_value="deepseek"), \
             mock.patch.object(health, "is_enabled", return_value=False):
            self.assertFalse(health.build_health()["ai_enabled"])

    def test_write_enabled_flag_reflected(self):
        c = TestClient(create_app(dist_dir=self.tmp.name, write_enabled=True),
                       base_url="http://127.0.0.1:8765")
        self.assertFalse(c.get("/api/health").json()["readonly"])


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app(dist_dir=self.tmp.name)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8765")

    def test_foreign_host_rejected(self):
        r = self.client.get("/api/health", headers={"host": "evil.example.com"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"]["code"], "bad_host")

    def test_localhost_and_ipv6_hosts_allowed(self):
        for h in ("localhost:8765", "127.0.0.1", "[::1]:8765"):
            r = self.client.get("/api/health", headers={"host": h})
            self.assertEqual(r.status_code, 200, h)

    def test_cross_origin_write_rejected(self):
        r = self.client.post("/api/anything", headers={"origin": "http://evil.example.com"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"]["code"], "bad_origin")

    def test_same_origin_write_passes_guard(self):
        r = self.client.post("/api/anything", headers={"origin": "http://127.0.0.1:8765"})
        self.assertEqual(r.status_code, 404)  # 过了守卫，落到统一 404

    def test_custom_allowed_host(self):
        app = create_app(dist_dir=self.tmp.name, allowed_hosts=frozenset({"127.0.0.1", "my.lan"}))
        c = TestClient(app, base_url="http://my.lan:8765")
        self.assertEqual(c.get("/api/health").status_code, 200)

    def test_unknown_api_uses_error_envelope(self):
        r = self.client.get("/api/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(set(r.json()), {"error"})
        self.assertEqual(set(r.json()["error"]), {"code", "message"})

    def test_extra_router_not_shadowed_by_spa(self):
        """W3 起业务路由经 extra_routers 接入，必须排在 SPA 通配之前。"""
        from fastapi import APIRouter

        router = APIRouter()
        router.add_api_route("/api/_ping", lambda: {"pong": True})
        app = create_app(dist_dir=self.tmp.name, extra_routers=[router])
        c = TestClient(app, base_url="http://127.0.0.1:8765")
        self.assertEqual(c.get("/api/_ping").json(), {"pong": True})

    def test_unhandled_error_does_not_leak(self):
        def boom():
            raise RuntimeError("secret-key-123 at C:\\Users\\me")

        from fastapi import APIRouter

        router = APIRouter()
        router.add_api_route("/api/_boom", boom)
        app = create_app(dist_dir=self.tmp.name, extra_routers=[router])
        c = TestClient(app, base_url="http://127.0.0.1:8765", raise_server_exceptions=False)
        r = c.get("/api/_boom")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret", r.text)
        self.assertNotIn("Users", r.text)


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestSpa(unittest.TestCase):
    def test_no_dist_shows_hint(self):
        with tempfile.TemporaryDirectory() as d:
            c = TestClient(create_app(dist_dir=os.path.join(d, "missing")),
                           base_url="http://127.0.0.1:8765")
            r = c.get("/")
            self.assertEqual(r.status_code, 503)
            self.assertIn("前端尚未构建", r.text)
            self.assertEqual(c.get("/api/health").status_code, 200)  # API 不受影响

    def test_spa_fallback_and_assets_and_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            dist = os.path.join(d, "dist")
            os.makedirs(os.path.join(dist, "assets"))
            with open(os.path.join(dist, "index.html"), "wb") as f:
                f.write(b"<html>INDEX</html>")
            with open(os.path.join(dist, "assets", "a.js"), "wb") as f:
                f.write(b"console.log(1)")
            with open(os.path.join(d, "secret.txt"), "wb") as f:
                f.write(b"TOPSECRET")
            c = TestClient(create_app(dist_dir=dist), base_url="http://127.0.0.1:8765")
            self.assertIn("INDEX", c.get("/").text)
            self.assertIn("INDEX", c.get("/reports/week").text)  # 前端路由刷新不 404
            self.assertEqual(c.get("/assets/a.js").status_code, 200)
            for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
                self.assertNotIn("TOPSECRET", c.get(p).text, p)


class TestServeCli(unittest.TestCase):
    def test_missing_deps_friendly_exit(self):
        from review_tool.api import serve

        real_import = __import__

        def fake_import(name, *a, **kw):
            if name == "uvicorn":
                raise ImportError("no uvicorn")
            return real_import(name, *a, **kw)

        err = io.StringIO()
        with mock.patch("builtins.__import__", side_effect=fake_import), redirect_stderr(err):
            rc = serve.main([])
        self.assertEqual(rc, 2)
        self.assertIn("uv sync --extra web", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    @unittest.skipUnless(HAVE_WEB, "未安装 web extra")
    def test_non_loopback_warns_and_defaults_readonly(self):
        from review_tool.api import serve

        err = io.StringIO()
        with mock.patch("uvicorn.run") as run, redirect_stderr(err), \
             mock.patch.object(serve, "load_web_key", return_value="k-test"), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            rc = serve.main(["--host", "0.0.0.0", "--port", "9000"])
        self.assertEqual(rc, 0)
        self.assertIn("不是回环地址", err.getvalue())
        app = run.call_args.args[0]
        self.assertFalse(app.state.write_enabled)

    def test_defaults(self):
        from review_tool.api import serve

        self.assertEqual(serve.DEFAULT_HOST, "127.0.0.1")
        self.assertEqual(serve.DEFAULT_PORT, 8765)

    def test_route_registered(self):
        from review_tool import __main__ as cli

        self.assertIn("serve", cli.ROUTES)


class TestReadonlyConn(unittest.TestCase):
    def test_readonly_rejects_writes_and_missing_db(self):
        from review_tool.storage.db import get_conn, get_readonly_conn

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.db")
            with self.assertRaises(FileNotFoundError):
                get_readonly_conn(p)
            self.assertFalse(os.path.exists(p))  # 不会顺手建库
            c = get_conn(p)
            c.execute("create table t(x)")
            c.commit()
            c.close()
            ro = get_readonly_conn(p)
            self.assertEqual(ro.execute("select count(*) from t").fetchone()[0], 0)
            import sqlite3

            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("insert into t values (1)")
            ro.close()


if __name__ == "__main__":
    unittest.main()
