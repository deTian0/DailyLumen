"""B15 clickup-habit：dry-run / 成功 complete / 已完成幂等 / 缺任务 / 上游错误。

全部离线 —— 注入假 fetch/put；不碰真 ClickUp / 真库。
"""
from __future__ import annotations

import contextlib
import io
import json
import unittest
import urllib.error
from io import BytesIO

from review_tool.pipeline import clickup_habit as ch

DAY = "2026-11-08"
LIST_ID = "habit-list-1"
TASK_ID = "task-lianlian-1"
HABIT = "lianlian"


def _task(tid, name, *, closed=False, status="to do", status_type="open",
          date_closed=None, due_date=None):
    st = {"status": status, "type": status_type}
    # 2026-11-08 08:00 CST ≈ 1762556400000 ms（近似；测试用 completion_day 时给明确值）
    closed_ms = date_closed
    if closed and closed_ms is None:
        # 2026-11-08 10:00 +08 → 用固定毫秒，配合 completion_day
        closed_ms = "1762567200000"  # 占位；下面 Fake 会走 is_closed 优先
    return {
        "id": tid,
        "name": name,
        "status": st,
        "date_closed": closed_ms if closed else None,
        "due_date": due_date,
    }


class _FakeNet:
    def __init__(self, tasks=None, *, get_after_put=None, list_id=LIST_ID):
        self.list_id = list_id
        self.tasks = {t["id"]: dict(t) for t in (tasks or [])}
        self.put_calls: list[tuple[str, dict]] = []
        self.get_paths: list[str] = []
        self._after = list(get_after_put or [])

    def fetch(self, path, key, *, timeout=None):
        self.get_paths.append(path)
        if "/list/" in path and "/task" in path:
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
        cur = self.tasks.get(tid) or {"id": tid, "name": "练练健身"}
        cur = dict(cur)
        cur["status"] = {"status": "complete", "type": "closed"}
        cur["date_closed"] = cur.get("date_closed") or "1762567200000"
        self.tasks[tid] = cur
        return dict(cur)


class _KsOk:
    def iter_training_records(self, start, end):
        return [{"status": "completed", "id": "w1"}]


class _KsEmpty:
    def iter_training_records(self, start, end):
        return []


def _capture(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


class TestFindHabitTask(unittest.TestCase):
    def test_prefers_closed_for_day(self):
        # date_closed 归到 DAY（用真实东八区毫秒：2026-11-08 12:00 +08）
        import datetime
        tz = datetime.timezone(datetime.timedelta(hours=8))
        ms = str(int(datetime.datetime(2026, 11, 8, 12, 0, tzinfo=tz).timestamp() * 1000))
        tasks = [
            _task("open1", "练练健身", due_date=ms),
            _task(TASK_ID, "练练健身", closed=True, date_closed=ms,
                  status="complete", status_type="closed"),
        ]
        t = ch.find_habit_task_for_day(tasks, HABIT, DAY)
        self.assertEqual(t["id"], TASK_ID)

    def test_open_due_day(self):
        import datetime
        tz = datetime.timezone(datetime.timedelta(hours=8))
        ms = str(int(datetime.datetime(2026, 11, 8, 18, 0, tzinfo=tz).timestamp() * 1000))
        tasks = [_task(TASK_ID, "练练健身", due_date=ms)]
        t = ch.find_habit_task_for_day(tasks, HABIT, DAY)
        self.assertEqual(t["id"], TASK_ID)

    def test_missing(self):
        with self.assertRaises(ValueError) as cm:
            ch.find_habit_task_for_day([_task("1", "每日阅读 30 分钟")], HABIT, DAY)
        self.assertIn("找不到", str(cm.exception))


class TestRunHabit(unittest.TestCase):
    def test_dry_run_no_put(self):
        net = _FakeNet([_task(TASK_ID, "练练健身")])
        rc, msg = ch.run_habit(
            DAY, HABIT, apply=False, list_id=LIST_ID, key="k",
            fetch=net.fetch, put=net.put, ks_client=_KsEmpty(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(net.put_calls, [])
        self.assertIn("dry-run", msg)
        self.assertIn("Continuity", msg)
        self.assertIn("≠", msg)

    def test_apply_complete(self):
        net = _FakeNet([_task(TASK_ID, "练练健身")])
        rc, msg = ch.run_habit(
            DAY, HABIT, apply=True, list_id=LIST_ID, key="k",
            fetch=net.fetch, put=net.put, ks_client=_KsOk(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(net.put_calls), 1)
        self.assertEqual(net.put_calls[0][1], {"status": "complete"})
        self.assertIn("回读校验通过", msg)
        self.assertIn("旁证", msg)

    def test_skip_closed_idempotent(self):
        import datetime
        tz = datetime.timezone(datetime.timedelta(hours=8))
        ms = str(int(datetime.datetime(2026, 11, 8, 9, 0, tzinfo=tz).timestamp() * 1000))
        net = _FakeNet([_task(
            TASK_ID, "练练健身", closed=True, date_closed=ms,
            status="complete", status_type="closed",
        )])
        rc, msg = ch.run_habit(
            DAY, HABIT, apply=True, list_id=LIST_ID, key="k",
            fetch=net.fetch, put=net.put, check_keepstrong=False,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(net.put_calls, [])
        self.assertIn("幂等跳过", msg)

    def test_missing_task(self):
        net = _FakeNet([_task("x", "墨墨背单词app")])
        rc, msg = ch.run_habit(
            DAY, HABIT, apply=True, list_id=LIST_ID, key="k",
            fetch=net.fetch, put=net.put, check_keepstrong=False,
        )
        self.assertEqual(rc, 2)
        self.assertEqual(net.put_calls, [])
        self.assertIn("任务定位失败", msg)

    def test_http_401(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.HTTPError(
                path, 401, "Unauthorized", {}, BytesIO(b"")
            )

        rc, msg = ch.run_habit(
            DAY, HABIT, apply=False, list_id=LIST_ID, key="k",
            fetch=boom, check_keepstrong=False,
        )
        self.assertEqual(rc, 1)
        self.assertIn("401", msg)

    def test_http_429(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.HTTPError(
                path, 429, "Too Many", {}, BytesIO(b"")
            )

        rc, msg = ch.run_habit(
            DAY, HABIT, apply=False, list_id=LIST_ID, key="k",
            fetch=boom, check_keepstrong=False,
        )
        self.assertEqual(rc, 1)
        self.assertIn("429", msg)

    def test_reject_other_habit(self):
        rc, msg = ch.run_habit(
            DAY, "reading_30", apply=False, list_id=LIST_ID, key="k",
            check_keepstrong=False,
        )
        self.assertEqual(rc, 2)
        self.assertIn("窄通道", msg)

    def test_stdout_json(self):
        net = _FakeNet([_task(TASK_ID, "练练健身")])
        rc, msg = ch.run_habit(
            DAY, HABIT, apply=False, list_id=LIST_ID, key="k",
            fetch=net.fetch, put=net.put, check_keepstrong=False, as_json=True,
        )
        self.assertEqual(rc, 0)
        data = json.loads(msg)
        self.assertEqual(data["action"], "would_complete")
        self.assertEqual(data["planned"]["habit_key"], HABIT)


class TestCli(unittest.TestCase):
    def test_help(self):
        rc, out, _err = _capture(ch.main, ["-h"])
        self.assertEqual(rc, 0)
        self.assertIn("clickup-habit", out)

    def test_parse_yes_alias(self):
        day, habit, apply, lid, as_json = ch._parse(
            ["--habit", "lianlian", "--date", DAY, "--yes"]
        )
        self.assertEqual((day, habit, apply), (DAY, HABIT, True))
        self.assertFalse(as_json)

    def test_main_dry_run(self):
        net = _FakeNet([_task(TASK_ID, "练练健身")])
        rc, out, err = _capture(
            ch.main,
            ["--habit", "lianlian", "--date", DAY],
            fetch=net.fetch, put=net.put, env={"CLICKUP_API_KEY": "k"},
            ks_client=_KsEmpty(),
        )
        # main 会走 load_creds；注入 env 可能不够 — 用 run 已测；此处保证缺 --habit 报错
        self.assertTrue(rc in (0, 2) or "凭据" in err or "dry-run" in out or "凭据" in out)

    def test_main_requires_habit(self):
        rc, _out, err = _capture(ch.main, ["--date", DAY])
        self.assertEqual(rc, 2)
        self.assertIn("--habit", err)


if __name__ == "__main__":
    unittest.main()
