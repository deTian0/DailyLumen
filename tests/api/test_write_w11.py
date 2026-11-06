"""Web 看板 W11：读图日流程（FR-I2）+ 收件箱归档 + clickup-pull 快照。

锁死：
1. mode 门禁在任何 I/O 之前（workbuddy → 409，不触网、不落临时文件）。
2. 上传限张数 / 大小 / 真实类型（看文件头）；临时文件用后即清（成功 / 失败都清）。
3. 预览不写 md；多图「后图覆盖」冲突出现在预览里；确认只写 md 数据块（带待人审标记），不写库。
4. 收件箱只收文件名（拒绝穿越）；归档 = 移到 已处理/日/。
5. clickup-pull：预览不写库；确认前整库备份、按整天替换、写后回读。
"""
import base64
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from review_tool.api import write_ops as wo
from review_tool.api.queries import QueryError
from review_tool.core import ai_draft as ad
from tests.api.test_life_api import BASE, HAVE_WEB, _sha
from tests.api.test_write_api import ENV, _ms, _WriteFixture
from tests.pipeline.test_vision_intake import (
    _MIN_PNG,
    SAMPLE_MD,
    _vision_client,
    _vision_client_sequence,
)

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from review_tool.api.app import create_app
    from review_tool.api.routes_write import build_router

VDAY = "2099-01-06"
B64 = base64.b64encode(_MIN_PNG).decode()


def _payload(**kw):
    return json.dumps(kw, ensure_ascii=False)


class _W11Fixture(_WriteFixture):
    def setUp(self):
        super().setUp()
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(SAMPLE_MD)
        self.inbox = os.path.join(self.dir, "收件箱")
        os.makedirs(self.inbox)
        p = mock.patch("review_tool.config.INBOX_DIR", self.inbox)
        p.start()
        self.addCleanup(p.stop)

    def _tmp_dirs(self):
        root = tempfile.gettempdir()
        return {n for n in os.listdir(root) if n.startswith("dl-vision-")}


class TestVision(_W11Fixture):
    def test_gate_before_any_io(self):
        before = self._tmp_dirs()
        with self.assertRaises(QueryError) as cm:
            wo.plan_vision(self.tokens, VDAY, uploads=[{"data": B64}],
                           client=_vision_client("{}"), mode="workbuddy")
        self.assertEqual((cm.exception.status, cm.exception.code), (409, "mode_gated"))
        self.assertEqual(self._tmp_dirs(), before)

    def test_upload_validation(self):
        cases = (
            ([], 422),
            ([{"data": B64}] * (wo.MAX_IMAGES + 1), 422),
            ([{"data": "不是 base64!!"}], 422),
            ([{"data": base64.b64encode(b"GIF89a....").decode()}], 415),
            ([{"data": "A" * (wo.MAX_IMAGE_BYTES * 2)}], 413),
        )
        for uploads, status in cases:
            with self.assertRaises(QueryError) as cm:
                wo.plan_vision(self.tokens, VDAY, uploads=uploads,
                               client=_vision_client("{}"), mode="deepseek")
            self.assertEqual(cm.exception.status, status, uploads[:1])

    def test_preview_conflict_no_write_then_confirm(self):
        md0, db0 = _sha(self.md), _sha(self.db)
        before = self._tmp_dirs()
        client = _vision_client_sequence([_payload(饮食热量_kcal=1000),
                                          _payload(饮食热量_kcal=2000, 睡眠时长_h=7.5)])
        plan = wo.plan_vision(self.tokens, VDAY, uploads=[{"name": "a.png", "data": B64},
                                                          {"name": "b.png", "data": "data:image/png;base64," + B64}],
                              client=client, mode="deepseek")
        pv = plan["preview"]
        self.assertEqual(pv["merge_strategy"], "later_wins")
        self.assertEqual(pv["conflicts"][0]["key"], "饮食热量_kcal")
        self.assertEqual(pv["fields"]["饮食热量_kcal"], 2000)
        self.assertEqual(pv["ok_images"], ["a.png", "b.png"])
        self.assertIn("--write", plan["cli"])
        self.assertEqual((_sha(self.md), _sha(self.db)), (md0, db0))  # 预览不落盘
        self.assertEqual(self._tmp_dirs(), before)  # 临时文件已清

        out = wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertTrue(out["result"]["written"])
        with open(self.md, encoding="utf-8") as f:
            back = f.read()
        self.assertIn("饮食热量_kcal: 2000", back)
        self.assertTrue(ad.is_ai_draft_pending(back))  # 待人审，ingest 默认跳过
        self.assertEqual(_sha(self.db), db0)  # 只写 md，不写库
        self.assertIn("ingest", out["result"]["next"])

    def test_tmp_cleaned_on_upstream_failure(self):
        before = self._tmp_dirs()
        with self.assertRaises(QueryError) as cm:
            wo.plan_vision(self.tokens, VDAY, uploads=[{"data": B64}],
                           client=_vision_client_sequence([]), mode="deepseek")
        self.assertEqual(cm.exception.code, "ai_upstream")
        self.assertEqual(self._tmp_dirs(), before)

    def test_stale_md(self):
        plan = wo.plan_vision(self.tokens, VDAY, uploads=[{"data": B64}],
                              client=_vision_client(_payload(饮食热量_kcal=1500)), mode="deepseek")
        with open(self.md, "a", encoding="utf-8") as f:
            f.write("\n手改\n")
        with self.assertRaises(QueryError) as cm:
            wo.confirm(self.tokens, plan["token"])
        self.assertEqual(cm.exception.code, "stale_plan")


class TestInbox(_W11Fixture):
    def _put(self, name, raw=_MIN_PNG):
        with open(os.path.join(self.inbox, name), "wb") as f:
            f.write(raw)

    def test_list_and_vision_from_inbox(self):
        self._put("薄荷.png")
        self._put("说明.txt", b"x")
        self.assertEqual([x["name"] for x in wo.list_inbox()["items"]], ["薄荷.png"])
        plan = wo.plan_vision(self.tokens, VDAY, inbox=["薄荷.png"],
                              client=_vision_client(_payload(饮食热量_kcal=1500)), mode="deepseek")
        self.assertEqual(plan["preview"]["inbox"], ["薄荷.png"])
        self.assertTrue(os.path.isfile(os.path.join(self.inbox, "薄荷.png")))  # 预览不动收件箱

    def test_path_guard(self):
        outside = os.path.join(self.dir, "x.png")
        with open(outside, "wb") as f:
            f.write(_MIN_PNG)
        for bad in ("../x.png", outside, "已处理/x.png", ".."):
            with self.assertRaises(QueryError) as cm:
                wo.plan_inbox_archive(self.tokens, VDAY, [bad])
            self.assertEqual(cm.exception.code, "path_forbidden", bad)
        self._put("fake.png", b"not an image at all")
        with self.assertRaises(QueryError) as cm:
            wo.plan_inbox_archive(self.tokens, VDAY, ["fake.png"])
        self.assertEqual(cm.exception.status, 415)

    def test_archive_plan_then_confirm(self):
        self._put("a.png")
        plan = wo.plan_inbox_archive(self.tokens, VDAY, ["a.png"])
        self.assertTrue(os.path.isfile(os.path.join(self.inbox, "a.png")))
        self.assertEqual(plan["preview"]["planned"][0]["src"], "a.png")
        out = wo.confirm(self.tokens, plan["token"])
        self.assertEqual(out["result"]["written"], 1)
        self.assertFalse(os.path.exists(os.path.join(self.inbox, "a.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.inbox, "已处理", VDAY, "a.png")))


def _pull_fetch(calls, day):
    tasks = [{"id": "c1", "name": "买菜", "date_closed": _ms(day, 20),
              "status": {"status": "complete", "type": "closed"}},
             {"id": "c2", "name": "未完成", "status": {"status": "to do"}}]

    def fetch(list_id, key):
        calls.append(list_id)
        return tasks if len(calls) == 1 else []  # 只让第一张 list 有数据

    return fetch


class TestClickupPull(_W11Fixture):
    def _count(self):
        c = sqlite3.connect(self.db)
        try:
            return c.execute("SELECT COUNT(*) FROM clickup_done").fetchone()[0]
        finally:
            c.close()

    def test_plan_no_write_then_confirm_with_backup(self):
        import datetime

        day = datetime.date.today().isoformat()
        calls = []
        db0 = _sha(self.db)
        plan = wo.plan_clickup_pull(self.tokens, days=7, env=ENV, fetch=_pull_fetch(calls, day))
        self.assertEqual(plan["preview"]["closed"], 1)
        self.assertEqual(plan["preview"]["per_day"], [{"date": day, "count": 1}])
        self.assertEqual(_sha(self.db), db0)  # 预览不写库
        n = len(calls)
        out = wo.confirm(self.tokens, plan["token"], db_path=self.db, backup_dir=self.bak)
        self.assertEqual(len(calls), n)  # 确认不二次拉取
        self.assertEqual(out["result"]["written"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.bak, out["result"]["backup"])))
        self.assertEqual(self._count(), 1)

    def test_days_range(self):
        for bad in (0, 400):
            with self.assertRaises(QueryError):
                wo.plan_clickup_pull(self.tokens, days=bad, env=ENV, fetch=_pull_fetch([], VDAY))


@unittest.skipUnless(HAVE_WEB, "需要 fastapi")
class TestW11Routes(_W11Fixture):
    def test_routes(self):
        r = build_router(db_path=self.db, env=ENV, backup_dir=self.bak,
                         client=_vision_client(_payload(饮食热量_kcal=1500)), mode="deepseek",
                         pull_fetch=_pull_fetch([], VDAY))
        tc = TestClient(create_app(dist_dir=self.dir, write_enabled=True, extra_routers=[r]),
                        base_url=BASE)
        self.assertEqual(tc.get("/api/write/inbox").status_code, 200)
        p = tc.post("/api/write/vision/plan",
                    json={"date": VDAY, "uploads": [{"name": "a.png", "data": B64}]})
        self.assertEqual(p.status_code, 200, p.text)
        bad = tc.post("/api/write/vision/plan", json={"date": VDAY, "uploads": [{"data": B64}]},
                      headers={"Origin": "http://evil.example"})
        self.assertEqual(bad.status_code, 403)
        g = tc.post("/api/write/inbox-archive/plan", json={"date": VDAY, "files": ["../x.png"]})
        self.assertEqual(g.status_code, 422)
        self.assertEqual(tc.post("/api/write/clickup-pull/plan", json={"days": 7}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
