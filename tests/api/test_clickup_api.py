"""Web 看板 W3：ClickUp 今日 / 完成清单 / 素材预览 / 错误态（全部离线，假 fetch 注入）。

锁死：
1. 与 CLI 同源 —— 待办/已办集合 = ``pipeline.clickup.collect`` 的分组；完成清单 = ``clickup_done.collect``；
   素材 markdown = ``clickup.render``。
2. 「次日早上补勾」回拨在 Web 侧结果与 CLI 一致（10-14 有、10-15 没有，且标 ``rebated_to``）。
3. 错误态：集成关 / 缺凭据 / 401 / 网络不可达各一种结构化错误体；刷新失败回退旧数据并标 stale；
   任何响应都不含密钥。
"""
import datetime
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_clickup import build_router
    HAVE_WEB = True
except ImportError:
    HAVE_WEB = False

from review_tool.pipeline import clickup as cu
from review_tool.reports import clickup_done as cd
from review_tool.storage.db import init_db, replace_clickup_days

TZ = datetime.timezone(datetime.timedelta(hours=8))
DAY = "2026-10-14"
SECRET = "pk_secret_key_123456"
ENV = {"CLICKUP_API_KEY": SECRET, "CLICKUP_TEAM_ID": "team1"}
META = {
    "L1": {"id": "L1", "name": "日常事务", "role": "行为流水", "daily": True},
    "L2": {"id": "L2", "name": "工作", "role": "工作产出", "daily": True},
}


def _ms(iso: str) -> str:
    return str(int(datetime.datetime.fromisoformat(iso).replace(tzinfo=TZ).timestamp() * 1000))


def _task(tid, name, *, closed=None, due=None, status="complete", created=None):
    return {
        "id": tid,
        "name": name,
        "date_closed": _ms(closed) if closed else None,
        "due_date": _ms(due) if due else None,
        "date_created": _ms(created) if created else None,
        "status": {"status": status},
    }


class _FakeAPI:
    """按 list id 返回固定任务；``error`` 非空时统一抛该异常。"""

    def __init__(self, by_list, error=None):
        self.by_list = by_list
        self.error = error
        self.calls = 0

    def __call__(self, path, key, *, timeout=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        for lid, tasks in self.by_list.items():
            if f"/list/{lid}/task" in path:
                return {"tasks": tasks}
        return {"tasks": []}


TASKS = {
    "L1": [
        _task("a", "晚上做的", closed="2026-10-14T21:32"),
        _task("b", "整理代办清单", closed="2026-10-15T08:41", due="2026-10-14T00:00"),
        _task("c", "今天到期没做", due="2026-10-14T09:00", status="to do"),
        _task("d", "逾期的事", due="2026-10-10T09:00", status="to do"),
    ],
    "L2": [_task("e", "写周报", closed="2026-10-14T10:00")],
}


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = os.path.join(self.tmp, "t.db")
        self.api = _FakeAPI(TASKS)
        for p in (
            mock.patch.object(cu, "CLICKUP_DAILY_IDS", ("L1", "L2")),
            mock.patch.object(cu, "CLICKUP_LIST_META", META),
            mock.patch.object(cu, "CLICKUP_MCP_PATH", os.path.join(self.tmp, "no-mcp.json")),
        ):
            p.start()
            self.addCleanup(p.stop)

    def client(self, *, env=ENV, fetch=None):
        router = build_router(fetch=fetch or self.api, env=env, db_path=self.db)
        app = create_app(dist_dir=self.tmp, extra_routers=[router])
        return TestClient(app, base_url="http://127.0.0.1:8765")

    @staticmethod
    def names(group, key):
        return [t["name"] for t in group[key]]


class TestTodayParity(_Base):
    def test_matches_cli_collect(self):
        r = self.client().get("/api/today", params={"date": DAY})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        cli = cu.collect(DAY, key="k", fetch=self.api, meta=META)
        self.assertEqual([g["id"] for g in data["groups"]], [g["id"] for g in cli])
        for web_g, cli_g in zip(data["groups"], cli, strict=True):
            for key in ("done", "open", "in_progress", "overdue", "cross_day"):
                self.assertEqual(
                    [t["id"] for t in web_g[key]], [t["id"] for t in cli_g[key]], key
                )
        self.assertFalse(data["stale"])

    def test_rebate_matches_cli(self):
        c = self.client()
        d14 = c.get("/api/today", params={"date": "2026-10-14"}).json()
        d15 = c.get("/api/today", params={"date": "2026-10-15"}).json()
        done14 = self.names(d14["groups"][0], "done")
        self.assertIn("整理代办清单", done14)
        self.assertNotIn("整理代办清单", self.names(d15["groups"][0], "done"))
        item = next(t for t in d14["groups"][0]["done"] if t["name"] == "整理代办清单")
        self.assertEqual(item["rebated_to"], "2026-10-14")
        self.assertEqual(d14["totals"]["rebated"], 1)

    def test_open_and_overdue_present(self):
        g = self.client().get("/api/today", params={"date": DAY}).json()["groups"][0]
        self.assertEqual(self.names(g, "open"), ["今天到期没做"])
        self.assertEqual(self.names(g, "overdue"), ["逾期的事"])

    def test_refresh_post_same_payload(self):
        c = self.client()
        a = c.get("/api/today", params={"date": DAY}).json()
        b = c.post("/api/today/refresh", params={"date": DAY}).json()
        self.assertEqual(a["groups"], b["groups"])
        self.assertEqual(a["totals"], b["totals"])

    def test_bad_date_is_422_not_stale(self):
        c = self.client()
        c.get("/api/today", params={"date": DAY})  # 先填缓存
        r = c.get("/api/today", params={"date": "2026-13-40"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_date")

    def test_response_has_no_secret(self):
        r = self.client().get("/api/today", params={"date": DAY})
        self.assertNotIn(SECRET, r.text)


class TestTodayErrors(_Base):
    def test_integration_disabled(self):
        with mock.patch("review_tool.config.INTEGRATIONS", {"clickup": False}):
            r = self.client().get("/api/today", params={"date": DAY})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "integration_disabled")
        self.assertEqual(self.api.calls, 0, "集成关闭时不得发网络请求")

    def test_credentials_missing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLICKUP_API_KEY", None)
            r = self.client(env={}).get("/api/today", params={"date": DAY})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "credentials_missing")
        self.assertEqual(self.api.calls, 0)

    def test_upstream_401(self):
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        r = self.client(fetch=_FakeAPI(TASKS, error=err)).get("/api/today", params={"date": DAY})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["code"], "upstream_auth")
        self.assertNotIn(SECRET, r.text)

    def test_upstream_unreachable(self):
        err = urllib.error.URLError("boom")
        r = self.client(fetch=_FakeAPI(TASKS, error=err)).get("/api/today", params={"date": DAY})
        self.assertEqual(r.status_code, 504)
        self.assertEqual(r.json()["error"]["code"], "upstream_unreachable")

    def test_refresh_failure_keeps_old_data_and_marks_stale(self):
        api = _FakeAPI(TASKS)
        c = self.client(fetch=api)
        ok = c.get("/api/today", params={"date": DAY}).json()
        api.error = urllib.error.URLError("down")
        r = c.post("/api/today/refresh", params={"date": DAY})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["stale"])
        self.assertEqual(data["stale_code"], "upstream_unreachable")
        self.assertEqual(data["groups"], ok["groups"])
        self.assertEqual(data["fetched_at"], ok["fetched_at"])


class TestMaterial(_Base):
    def test_matches_cli_render(self):
        r = self.client().get("/api/clickup/material", params={"date": DAY})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        groups = cu.collect(DAY, key="k", fetch=self.api, meta=META)
        expect = cu.render(DAY, groups, generated_at="X", workspace="team1")
        strip = lambda t: "\n".join(  # noqa: E731
            ln for ln in t.splitlines() if not ln.startswith("- 生成时间："))
        self.assertEqual(strip(data["markdown"]), strip(expect))
        self.assertNotIn(SECRET, data["markdown"])
        self.assertNotIn("- [x]", data["markdown"])

    def test_markdown_download_headers(self):
        r = self.client().get("/api/clickup/material.md", params={"date": DAY})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.headers["content-type"])
        self.assertIn("attachment", r.headers["content-disposition"])


class TestDone(_Base):
    def seed(self):
        conn = init_db(db_path=self.db)
        try:
            replace_clickup_days(conn, {
                DAY: [
                    {"task_id": "t1", "list_id": "L2", "name": "Me-2h-修复", "owner": "Me",
                     "minutes": 120, "subject": "修复", "is_self": True, "status": "complete"},
                    {"task_id": "t2", "list_id": "L2", "name": "杂事", "owner": None,
                     "minutes": None, "subject": None, "is_self": True, "status": "complete"},
                ],
            })
            conn.commit()
        finally:
            conn.close()

    def test_matches_cli_collect_and_render(self):
        self.seed()
        r = self.client().get("/api/clickup/done", params={"date": DAY})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        conn = init_db(db_path=self.db)
        try:
            cli = cd.collect(conn, start=DAY, end=DAY)
        finally:
            conn.close()
        self.assertEqual(data["total"], cli["total"])
        self.assertEqual(data["self_total"], cli["self_total"])
        self.assertEqual(data["text"], cd.render(cli))
        self.assertEqual(
            [i["name"] for i in data["days"][0]["items"]],
            [i["name"] for i in cli["days"][0]["items"]],
        )

    def test_range_and_bad_range(self):
        self.seed()
        c = self.client()
        ok = c.get("/api/clickup/done", params={"date": DAY, "end": "2026-10-16"})
        self.assertEqual(ok.status_code, 200)
        bad = c.get("/api/clickup/done", params={"date": "2026-10-16", "end": DAY})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["error"]["code"], "invalid_range")

    def test_missing_db_is_503_and_not_created(self):
        r = self.client().get("/api/clickup/done", params={"date": DAY})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "db_missing")
        self.assertFalse(os.path.exists(self.db), "只读路由不得顺手建库")

    def test_no_network_for_done(self):
        self.seed()
        self.client().get("/api/clickup/done", params={"date": DAY})
        self.assertEqual(self.api.calls, 0)


class TestIntegrationErrors(_Base):
    def test_returns_sanitized_summary(self):
        from review_tool.integrations import last_error as le

        path = os.path.join(self.tmp, "err.json")
        le.record_integration_error(
            "clickup", command="clickup", error_kind="HTTPError",
            error_summary="HTTP 401", http_code=401, path=path,
        )
        with mock.patch.object(le, "default_last_error_path", return_value=path):
            r = self.client().get("/api/integrations/errors")
        self.assertEqual(r.status_code, 200)
        last = r.json()["last"]
        self.assertEqual(last["integration"], "clickup")
        self.assertEqual(last["http_code"], 401)
        self.assertNotIn(SECRET, r.text)

    def test_none_when_no_record(self):
        from review_tool.integrations import last_error as le

        with mock.patch.object(le, "default_last_error_path",
                               return_value=os.path.join(self.tmp, "none.json")):
            r = self.client().get("/api/integrations/errors")
        self.assertIsNone(r.json()["last"])


class TestRouterPrecedence(_Base):
    def test_unknown_api_path_is_json_404(self):
        r = self.client().get("/api/clickup/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.json())


class TestRateLimit(unittest.TestCase):
    """429 限流：有上限地等待重试；耗尽后抛出，由路由映射为 rate_limited 并回退旧数据。"""

    @staticmethod
    def _resp(body: bytes):
        class _R:
            def read(self):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _R()

    def test_429_then_success_retries_once(self):
        from review_tool.integrations.clickup.client import http_get

        calls = []

        def opener(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many", {"X-RateLimit-Reset": "0"}, None)
            return self._resp(b'{"tasks": []}')

        with mock.patch("review_tool.integrations.clickup.client.time.sleep") as sleep:
            out = http_get("/list/L1/task", "k", urlopen=opener)
        self.assertEqual(out, {"tasks": []})
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once()
        self.assertEqual(sleep.call_args[0][0], 1.0)  # 夹在 [1, 60] 秒

    def test_429_exhausted_raises_after_bounded_retries(self):
        from review_tool.integrations.clickup.client import RATE_LIMIT_RETRIES, http_get

        calls = []

        def opener(req, timeout=None):
            calls.append(req)
            raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)

        with mock.patch("review_tool.integrations.clickup.client.time.sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                http_get("/x", "k", urlopen=opener)
        self.assertEqual(len(calls), RATE_LIMIT_RETRIES + 1)

    def test_non_429_not_retried(self):
        from review_tool.integrations.clickup.client import http_get

        calls = []

        def opener(req, timeout=None):
            calls.append(req)
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            http_get("/x", "k", urlopen=opener)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
