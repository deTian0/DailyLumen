"""Web 看板 W6：健康 / 学习 / 督导只读 API。

锁死：
1. 对拍（PRE-05 / R1）：``text`` = 对应 reports ``render(collect(...))``；``data`` = CLI ``--json`` 同口径。
2. 只读：跑完全部 W6 路由后库文件字节不变（含 tutor —— Web 固定 ``rebuild=False``）。
3. 错误：日期非法 422、slot 非法 422、``end`` 无 ``start`` 422、库缺失 503，均为统一错误体。
"""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_life import build_router
    HAVE_WEB = True
except ImportError:
    HAVE_WEB = False

from review_tool.api import life_queries as lq
from review_tool.storage.db import get_readonly_conn, init_db, upsert

BASE = "http://127.0.0.1:8765"


def _row(date, **kw):
    base = {
        "date": date, "training_day": 1, "exercise_min": 30,
        "health_score": 4, "work_score": 4, "learn_score": 4, "life_score": 4,
        "system_score": 4.0, "diet_kcal": 1800, "sleep_h": 7.0,
        "carbs_g": 220, "fat_g": 55, "protein_g": 70,
    }
    base.update(kw)
    return base


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _json(data):
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


class _DbFixture(unittest.TestCase):
    DATES = ("2026-09-07", "2026-09-08", "2026-09-09")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t.db")
        conn = init_db(db_path=self.db)
        for d in self.DATES:
            upsert(conn, _row(d))
        conn.commit()
        conn.close()

    def ro(self):
        conn = get_readonly_conn(self.db)
        self.addCleanup(conn.close)
        return conn


class TestLifeParity(_DbFixture):
    """life_queries 输出 = reports 层 collect/render（同一只读连接）。"""

    def _check(self, packed, module, **kw):
        data = module.collect(self.ro(), **kw)
        self.assertEqual(packed["text"], module.render(data))
        self.assertEqual(packed["data"], _json(data))

    def test_body(self):
        from review_tool.reports import body
        self._check(lq.body(self.ro()), body)

    def test_coach(self):
        from review_tool.reports import coach
        self._check(lq.coach(self.ro(), "2026-09-09"), coach, as_of="2026-09-09")

    def test_habits(self):
        from review_tool.reports import habits
        self._check(lq.habits(self.ro(), "2026-09-09"), habits, as_of="2026-09-09")

    def test_nutrition(self):
        from review_tool.reports import nutrition
        self._check(lq.nutrition(self.ro(), "2026-09-09"), nutrition, as_of="2026-09-09")

    def test_tutor_no_rebuild(self):
        from review_tool.reports import tutor
        out = lq.tutor(self.ro(), "2026-09-09")
        self.assertFalse(out["queue_rebuilt"])
        self._check(out, tutor, as_of="2026-09-09", rebuild=False)

    def test_promises_single_day_end_defaults_to_start(self):
        from review_tool.reports import promises
        self._check(lq.promises(self.ro(), "2026-09-08"), promises,
                    start="2026-09-08", end="2026-09-08")

    def test_correlate(self):
        from review_tool.reports import correlate
        self._check(lq.correlate(self.ro()), correlate, min_samples=correlate.MIN_SAMPLES)

    def test_steward_morning_and_week(self):
        from review_tool.reports import steward
        self._check(lq.steward(self.ro(), "morning", as_of="2026-09-09"), steward,
                    slot="morning", as_of="2026-09-09")
        wk = lq.steward(self.ro(), "week")
        self.assertEqual(wk["data"]["slot"], "week")

    def test_invalid_args(self):
        with self.assertRaises(lq.QueryError) as c:
            lq.coach(self.ro(), "2026-13-01")
        self.assertEqual(c.exception.status, 422)
        with self.assertRaises(lq.QueryError) as c:
            lq.steward(self.ro(), "noon")
        self.assertEqual(c.exception.code, "invalid_slot")
        with self.assertRaises(lq.QueryError):
            lq.promises(self.ro(), None, "2026-09-09")
        with self.assertRaises(lq.QueryError):
            lq.correlate(self.ro(), 1)


@unittest.skipUnless(HAVE_WEB, "未安装 web extra（fastapi/httpx）")
class TestLifeRoutes(_DbFixture):
    def setUp(self):
        super().setUp()
        self.client = TestClient(
            create_app(dist_dir=self.dir, extra_routers=[build_router(db_path=self.db)]),
            base_url=BASE,
        )

    def test_routes_ok_and_db_untouched(self):
        before = _sha(self.db)
        for path in ("/api/body", "/api/coach", "/api/habits", "/api/nutrition",
                     "/api/tutor", "/api/promises", "/api/correlate",
                     "/api/steward/morning", "/api/steward/evening", "/api/steward/week"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            body = r.json()
            self.assertIn("text", body)
            self.assertIsInstance(body["data"], dict)
        self.assertFalse(self.client.get("/api/tutor").json()["queue_rebuilt"])
        self.assertEqual(before, _sha(self.db), "W6 只读路由改动了库文件")

    def test_error_bodies(self):
        r = self.client.get("/api/coach?date=bad")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid_date")
        r = self.client.get("/api/steward/noon")
        self.assertEqual(r.json()["error"]["code"], "invalid_slot")

    def test_db_missing_503(self):
        c = TestClient(create_app(dist_dir=self.dir, extra_routers=[
            build_router(db_path=os.path.join(self.dir, "nope.db"))]), base_url=BASE)
        r = c.get("/api/body")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "db_missing")


if __name__ == "__main__":
    unittest.main()
