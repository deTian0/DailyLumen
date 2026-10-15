"""habit_sync 幂等：重复同步不重复行、不改写已有 done。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.core.habits import HABIT_CATEGORY
from review_tool.pipeline.habit_sync import rows_for_day, sync_habits
from review_tool.storage.db import init_db, load_habit_logs, upsert_habit_log


def _ms(day: str, hour: int = 10) -> str:
    """粗造东八区毫秒时间戳（仅测试用，足以让 completion_day 归到 day）。"""
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=8))
    dt = datetime.fromisoformat(day).replace(tzinfo=tz, hour=hour)
    return str(int(dt.timestamp() * 1000))


def _habit_tasks(day: str) -> list[dict]:
    return [
        {
            "id": "1", "name": "每日阅读 30 分钟",
            "status": {"status": "complete", "type": "closed"},
            "date_closed": _ms(day),
        },
        {
            "id": "2", "name": "练练健身",
            "status": {"status": "to do", "type": "open"},
        },
        {
            "id": "3", "name": "墨墨背单词app",
            "status": {"status": "complete", "type": "closed"},
            "date_closed": _ms(day, 11),
        },
    ]


class TestHabitSync(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(self.db)
        self.day = "2026-10-15"

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_rows_for_day_includes_incomplete(self):
        rows = rows_for_day(_habit_tasks(self.day), self.day)
        by = {r["habit_key"]: r for r in rows}
        self.assertEqual(by["reading_30"]["done"], 1)
        self.assertEqual(by["lianlian"]["done"], 0)
        self.assertEqual(by["maimemo"]["done"], 1)
        self.assertTrue(all(r["category"] == HABIT_CATEGORY for r in rows))
        self.assertTrue(all(r["src"] == "clickup" for r in rows))

    def test_idempotent_no_dup_no_overwrite_done(self):
        tasks = _habit_tasks(self.day)
        s1 = sync_habits(self.conn, self.day, tasks=tasks)
        self.assertEqual(s1["written"], s1["matched"])
        n1 = len(load_habit_logs(self.conn, date=self.day))
        self.assertEqual(n1, s1["matched"])

        # 把 reading_30 的 done 改成 0，再同步（源仍为 done=1）—— 不应被改回
        upsert_habit_log(self.conn, {
            "date": self.day, "habit_key": "reading_30",
            "category": HABIT_CATEGORY, "item": "每日阅读 30 分钟",
            "done": 0, "src": "clickup",
        }, overwrite=True)
        self.conn.commit()

        sync_habits(self.conn, self.day, tasks=tasks)
        n2 = len(load_habit_logs(self.conn, date=self.day))
        self.assertEqual(n2, n1)
        row = load_habit_logs(
            self.conn, date=self.day, habit_key="reading_30"
        )[0]
        self.assertEqual(row["done"], 0)  # 不改写已有 done

    def test_dry_run_writes_nothing(self):
        s = sync_habits(
            self.conn, self.day, tasks=_habit_tasks(self.day), dry_run=True,
        )
        self.assertEqual(s["written"], 0)
        self.assertEqual(len(load_habit_logs(self.conn)), 0)
        self.assertGreater(s["matched"], 0)

    def test_rebuild_from_clickup_snapshot(self):
        """重建回归（快照性质）：同一 ClickUp 任务快照 → 逐字段一致。

        habit_logs **不是**从 md 重建，而是从 ClickUp 当日快照重建；
        删表后用同一任务列表再 sync，应与首次写入逐字段 0 差异。
        """
        tasks = _habit_tasks(self.day)
        sync_habits(self.conn, self.day, tasks=tasks)
        snap = [
            (r["date"], r["habit_key"], r["category"], r["item"],
             r["done"], r["src"])
            for r in load_habit_logs(self.conn, date=self.day)
        ]
        self.conn.execute("DELETE FROM habit_logs")
        self.conn.commit()
        self.assertEqual(len(load_habit_logs(self.conn)), 0)
        sync_habits(self.conn, self.day, tasks=tasks)
        again = [
            (r["date"], r["habit_key"], r["category"], r["item"],
             r["done"], r["src"])
            for r in load_habit_logs(self.conn, date=self.day)
        ]
        self.assertEqual(snap, again)


if __name__ == "__main__":
    unittest.main()
