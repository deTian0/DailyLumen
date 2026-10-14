"""ClickUp 回写通道测试（v1.7.0）：dry-run / 幂等 / 入库门槛 / 回读校验。

**全部离线** —— 网络层用注入的假 fetch / put 顶替，不碰 api.clickup.com；
库用临时 SQLite，不碰真 ``reviews.db``。

锁死冲突规则：
1. 默认 dry-run，不调用 put；
2. 已 closed 幂等跳过；
3. 目标日未入库 → 不写、rc=2；
4. 回读不符则重试一次，仍失败则 rc=1；
5. 缺凭据 → rc=2。
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from review_tool.config import CLICKUP_REVIEW_TASK
from review_tool.pipeline import clickup_sync as cs
from review_tool.storage.db import init_db, upsert

DAY = "2026-10-12"
LIST_ID = CLICKUP_REVIEW_TASK["list_id"]
TASK_NAME = CLICKUP_REVIEW_TASK["name"]
TASK_ID = "task-review-1"


def _task(tid, name, *, closed=False, status="to do", status_type="open"):
    st = {"status": status, "type": status_type}
    return {
        "id": tid,
        "name": name,
        "status": st,
        "date_closed": "1690000000000" if closed else None,
    }


class _FakeNet:
    """假 ClickUp：list 拉取 + 单任务 GET/PUT。记录 put 次数供断言。"""

    def __init__(self, tasks=None, *, get_after_put=None):
        """``get_after_put``：每次 PUT 后下一次 GET ``/task/{id}`` 返回的任务序列。

        用完后回落到内存里的当前任务态（PUT 会就地改 status）。
        """
        self.tasks = {t["id"]: dict(t) for t in (tasks or [])}
        self.put_calls: list[tuple[str, dict]] = []
        self.get_paths: list[str] = []
        self._after = list(get_after_put or [])

    def fetch(self, path, key, *, timeout=None):
        self.get_paths.append(path)
        if path.startswith(f"/list/{LIST_ID}/task") or (
                "/list/" in path and "/task" in path and "page=" in path):
            return {"tasks": list(self.tasks.values())}
        if path.startswith("/task/"):
            tid = path.split("/task/", 1)[1].split("?", 1)[0]
            if self._after:
                return self._after.pop(0)
            return dict(self.tasks.get(tid) or {})
        return {}

    def put(self, path, key, body, *, timeout=None):
        self.put_calls.append((path, dict(body)))
        tid = path.split("/task/", 1)[1]
        cur = self.tasks.get(tid) or {"id": tid, "name": TASK_NAME}
        cur = dict(cur)
        cur["status"] = {"status": "complete", "type": "closed"}
        cur["date_closed"] = cur.get("date_closed") or "1690000000001"
        self.tasks[tid] = cur
        return dict(cur)


def _capture(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _ingest(self, day=DAY):
        upsert(self.conn, {"date": day, "summary": "ok"})
        self.conn.commit()


# ------------------------------------------------------------------ 纯函数
class TestIsClosed(unittest.TestCase):
    def test_type_closed(self):
        self.assertTrue(cs.is_closed(_task("a", "x", status_type="closed")))

    def test_status_complete(self):
        self.assertTrue(cs.is_closed(
            _task("a", "x", status="complete", status_type="done")))

    def test_date_closed(self):
        self.assertTrue(cs.is_closed(_task("a", "x", closed=True)))

    def test_open(self):
        self.assertFalse(cs.is_closed(_task("a", "x")))


class TestFindReviewTask(unittest.TestCase):
    def test_by_name_unique(self):
        tasks = [
            _task("1", "每日阅读 30 分钟"),
            _task(TASK_ID, TASK_NAME),
        ]
        t = cs.find_review_task(tasks, name=TASK_NAME)
        self.assertEqual(t["id"], TASK_ID)

    def test_by_task_id(self):
        tasks = [_task(TASK_ID, "别的名字")]
        t = cs.find_review_task(tasks, name=TASK_NAME, task_id=TASK_ID)
        self.assertEqual(t["id"], TASK_ID)

    def test_missing_name(self):
        with self.assertRaises(ValueError):
            cs.find_review_task([_task("1", "其它")], name=TASK_NAME)

    def test_ambiguous_name(self):
        tasks = [_task("1", TASK_NAME), _task("2", TASK_NAME)]
        with self.assertRaises(ValueError) as cm:
            cs.find_review_task(tasks, name=TASK_NAME)
        self.assertIn("不唯一", str(cm.exception))


# ------------------------------------------------------------------ 主流程
class TestRunPush(_DbCase):
    def test_dry_run_does_not_put(self):
        self._ingest()
        net = _FakeNet([_task(TASK_ID, TASK_NAME)])
        rc, msg = cs.run_push(
            DAY, apply=False, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 0)
        self.assertEqual(net.put_calls, [])
        self.assertIn("dry-run", msg)
        self.assertIn(TASK_ID, msg)

    def test_skip_when_already_closed(self):
        self._ingest()
        net = _FakeNet([_task(TASK_ID, TASK_NAME, closed=True,
                              status="complete", status_type="closed")])
        rc, msg = cs.run_push(
            DAY, apply=True, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 0)
        self.assertEqual(net.put_calls, [])
        self.assertIn("幂等跳过", msg)

    def test_missing_review_day_blocks_write(self):
        net = _FakeNet([_task(TASK_ID, TASK_NAME)])
        rc, msg = cs.run_push(
            DAY, apply=True, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 2)
        self.assertEqual(net.put_calls, [])
        self.assertIn("尚未入库", msg)

    def test_apply_puts_and_verifies(self):
        self._ingest()
        net = _FakeNet([_task(TASK_ID, TASK_NAME)])
        rc, msg = cs.run_push(
            DAY, apply=True, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 0)
        self.assertEqual(len(net.put_calls), 1)
        self.assertEqual(net.put_calls[0][0], f"/task/{TASK_ID}")
        self.assertEqual(net.put_calls[0][1], {"status": "complete"})
        self.assertIn("回读校验通过", msg)

    def test_verify_fail_retries_then_errors(self):
        """回读两次都仍 open → RuntimeError → rc=1；put 恰 2 次。"""
        self._ingest()
        open_task = _task(TASK_ID, TASK_NAME)
        # PUT 后故意返回仍 open 的任务（不更新内存态）
        stuck = _task(TASK_ID, TASK_NAME)  # still open

        class _Stuck(_FakeNet):
            def put(self, path, key, body, *, timeout=None):
                self.put_calls.append((path, dict(body)))
                return dict(open_task)

            def fetch(self, path, key, *, timeout=None):
                self.get_paths.append(path)
                if "page=" in path:
                    return {"tasks": [open_task]}
                return dict(stuck)

        net = _Stuck([open_task])
        rc, msg = cs.run_push(
            DAY, apply=True, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 1)
        self.assertEqual(len(net.put_calls), cs.MAX_PUT_ATTEMPTS)
        self.assertIn("回写失败", msg)

    def test_missing_creds(self):
        self._ingest()
        missing = os.path.join(self.root, "no-such-mcp.json")
        rc, msg = cs.run_push(
            DAY, apply=False, db_path=self.db, env={},
            creds_path=missing,
            fetch=lambda *a, **k: {"tasks": []}, put=lambda *a, **k: {})
        self.assertEqual(rc, 2)
        self.assertIn("凭据", msg)

    def test_task_not_found(self):
        self._ingest()
        net = _FakeNet([_task("other", "其它习惯")])
        rc, msg = cs.run_push(
            DAY, apply=True, db_path=self.db, key="k",
            fetch=net.fetch, put=net.put)
        self.assertEqual(rc, 2)
        self.assertEqual(net.put_calls, [])
        self.assertIn("定位失败", msg)


class TestCLI(_DbCase):
    def test_help(self):
        rc, out, _err = _capture(cs.main, ["-h"])
        self.assertEqual(rc, 0)
        self.assertIn("clickup-push", out)

    def test_bad_date(self):
        rc, _out, err = _capture(cs.main, ["not-a-date"])
        self.assertEqual(rc, 2)
        self.assertIn("参数错误", err)

    def test_main_dry_run_wired(self):
        self._ingest()
        net = _FakeNet([_task(TASK_ID, TASK_NAME)])
        rc, out, err = _capture(
            cs.main, [DAY, "--db", self.db],
            fetch=net.fetch, put=net.put, env={"CLICKUP_API_KEY": "pk_test"})
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertIn("dry-run", out)
        self.assertEqual(net.put_calls, [])

    def test_apply_flag_overrides_dry_run_default(self):
        self._ingest()
        net = _FakeNet([_task(TASK_ID, TASK_NAME)])
        rc, out, _err = _capture(
            cs.main, [DAY, "--apply", "--db", self.db],
            fetch=net.fetch, put=net.put, env={"CLICKUP_API_KEY": "pk_test"})
        self.assertEqual(rc, 0)
        self.assertEqual(len(net.put_calls), 1)
        self.assertIn("[apply]", out)


if __name__ == "__main__":
    unittest.main()
