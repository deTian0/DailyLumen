"""core/habits + select_habits + doctor R3 / 断更 + week 分栏。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.config import HABITS, PERSONAL_ITEMS
from review_tool.core.habits import (
    HABIT_CATEGORY,
    adherence_from_rows,
    detect_gaps,
    habit_gap,
    habit_streak,
    key_overlap,
    resolve_habit,
)
from review_tool.core.tracks import normalize_item, resolve_item
from review_tool.pipeline.clickup import select_habits
from review_tool.reports.analyze import collect, render_summary, render_week_md
from review_tool.reports.doctor import diagnose, is_healthy
from review_tool.reports.doctor import render as render_doctor
from review_tool.storage.db import (
    init_db,
    upsert,
    upsert_habit_log,
    upsert_personal_track,
)


def _task(name: str, *, closed: bool = False, tid: str = "t1") -> dict:
    st = {"status": "complete", "type": "closed"} if closed else {
        "status": "to do", "type": "open",
    }
    t: dict = {"id": tid, "name": name, "status": st}
    if closed:
        # 2026-10-15 10:00 CST
        t["date_closed"] = str(1760493600000)
    return t


class TestNormalizeShared(unittest.TestCase):
    def test_normalize_item_matches_resolve_item(self):
        for item in PERSONAL_ITEMS:
            for alias in item["aliases"]:
                self.assertEqual(
                    normalize_item(alias, PERSONAL_ITEMS),
                    resolve_item(alias),
                )

    def test_resolve_habit_catalog(self):
        self.assertEqual(resolve_habit("每日阅读 30 分钟")["key"], "reading_30")
        self.assertEqual(resolve_habit("练练健身")["key"], "lianlian")
        self.assertEqual(resolve_habit("墨墨背单词app")["key"], "maimemo")
        self.assertIsNone(resolve_habit("完全无关的任务"))


class TestSelectHabits(unittest.TestCase):
    def test_includes_open_and_closed(self):
        tasks = [
            _task("每日阅读 30 分钟", closed=True, tid="a"),
            _task("练练健身", closed=False, tid="b"),
            _task("无关任务", closed=False, tid="c"),
        ]
        got = select_habits(tasks)
        keys = {h["habit_key"] for h in got}
        self.assertEqual(keys, {"reading_30", "lianlian"})
        by = {h["habit_key"]: h for h in got}
        self.assertTrue(by["reading_30"]["done"])
        self.assertFalse(by["lianlian"]["done"])


class TestAdherenceStreakGap(unittest.TestCase):
    def test_adherence_and_streak(self):
        rows = [
            {"date": "2026-10-13", "habit_key": "reading_30", "item": "读", "done": 1},
            {"date": "2026-10-14", "habit_key": "reading_30", "item": "读", "done": 1},
            {"date": "2026-10-15", "habit_key": "reading_30", "item": "读", "done": 0},
        ]
        adh = adherence_from_rows(rows)
        self.assertEqual(adh["items"][0]["done"], 2)
        self.assertEqual(adh["items"][0]["recorded"], 3)
        st = habit_streak(rows, "reading_30", as_of="2026-10-14")
        self.assertEqual(st["current"], 2)
        st0 = habit_streak(rows, "reading_30", as_of="2026-10-15")
        self.assertEqual(st0["current"], 0)

    def test_gap_triggered(self):
        rows = [
            {"date": "2026-10-10", "habit_key": "daily_review", "done": 1},
            {"date": "2026-10-11", "habit_key": "daily_review", "done": 0},
            {"date": "2026-10-12", "habit_key": "daily_review", "done": 0},
        ]
        # alert_days for daily_review = 2
        g = habit_gap(rows, "daily_review", as_of="2026-10-12")
        self.assertTrue(g["triggered"])
        gaps = detect_gaps(rows, as_of="2026-10-12")
        self.assertTrue(any(x["habit_key"] == "daily_review" for x in gaps))


class TestDoctorR3(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.input_dir = os.path.join(self.root, "每日复盘", "复盘", "2026-10")
        os.makedirs(self.input_dir)
        # 对账需要同名 md
        with open(os.path.join(self.input_dir, "2026-10-15.md"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write("# 2026-10-15\n")
        self.conn = init_db(self.db)
        upsert(self.conn, {
            "date": "2026-10-15",
            "health_score": 7, "work_score": 7,
            "learn_score": 7, "life_score": 7, "system_score": 7.0,
            "raw_path": os.path.join(self.input_dir, "2026-10-15.md"),
        })
        upsert_personal_track(
            self.conn, "2026-10-15", "skincare", "护肤",
            "skincare", "护肤", 1,
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_isolation_ok(self):
        upsert_habit_log(self.conn, {
            "date": "2026-10-15", "habit_key": "reading_30",
            "category": HABIT_CATEGORY, "item": "每日阅读 30 分钟",
            "done": 1, "src": "clickup",
        })
        self.conn.commit()
        r = diagnose(db_path=self.db, input_dir=os.path.join(self.root, "每日复盘"),
                     today="2026-10-15")
        self.assertEqual(r["habit_track_overlap"], [])
        self.assertTrue(is_healthy(r))
        text = render_doctor(r)
        self.assertIn("无交集", text)

    def test_empty_habit_logs_is_not_all_gaps(self):
        """空 habit_logs ≠ 全部断更（回归 v1.19.0 的假告警）。

        setUp 里只有 personal_tracks、没有 habit_logs —— 正是「日志尚未同步」的真实场景。
        修复前 ``detect_gaps([], as_of=today)`` 会把目录内**全部**习惯判为连续未完成。
        """
        r = diagnose(db_path=self.db, input_dir=os.path.join(self.root, "每日复盘"),
                     today="2026-10-15")
        self.assertTrue(r["habit_gaps"]["empty"])
        self.assertEqual(r["habit_gaps"]["gaps"], [])
        self.assertEqual(r["habit_gaps"]["count"], 0)
        self.assertTrue(is_healthy(r))
        text = render_doctor(r)
        self.assertIn("尚无习惯日志", text)
        self.assertNotIn("项习惯断更", text)

    # 目录内每个习惯都真的断更时，告警仍要照报（避免上面那条把告警一并关掉）
    def test_all_gaps_still_reported_when_logs_exist(self):
        """有日志且各项都断更 → 仍然报警（守住「不是把告警关掉」）。"""
        upsert_habit_log(self.conn, {
            "date": "2026-10-01", "habit_key": "reading_30",
            "category": HABIT_CATEGORY, "item": "每日阅读 30 分钟",
            "done": 0, "src": "clickup",
        })
        self.conn.commit()
        r = diagnose(db_path=self.db, input_dir=os.path.join(self.root, "每日复盘"),
                     today="2026-10-15")
        self.assertFalse(r["habit_gaps"]["empty"])
        self.assertTrue(any(g["habit_key"] == "reading_30"
                            for g in r["habit_gaps"]["gaps"]))

    def test_isolation_violation(self):
        # 故意塞交集 key
        upsert_habit_log(self.conn, {
            "date": "2026-10-15", "habit_key": "skincare",
            "category": HABIT_CATEGORY, "item": "误入",
            "done": 1, "src": "clickup",
        })
        self.conn.commit()
        r = diagnose(db_path=self.db, input_dir=os.path.join(self.root, "每日复盘"),
                     today="2026-10-15")
        self.assertIn("skincare", r["habit_track_overlap"])
        self.assertFalse(is_healthy(r))
        text = render_doctor(r)
        self.assertIn("交集", text)

    def test_gap_advisory_not_unhealthy(self):
        # 连续未完成触发 daily_review alert_days=2，但不影响 is_healthy
        for d, done in (("2026-10-13", 1), ("2026-10-14", 0), ("2026-10-15", 0)):
            upsert(self.conn, {
                "date": d,
                "health_score": 7, "work_score": 7,
                "learn_score": 7, "life_score": 7, "system_score": 7.0,
                "raw_path": os.path.join(self.input_dir, "2026-10-15.md"),
            })
            upsert_habit_log(self.conn, {
                "date": d, "habit_key": "daily_review",
                "category": HABIT_CATEGORY, "item": "每日复盘总结",
                "done": done, "src": "clickup",
            })
            with open(os.path.join(self.input_dir, f"{d}.md"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(f"# {d}\n")
        self.conn.commit()
        r = diagnose(db_path=self.db, input_dir=os.path.join(self.root, "每日复盘"),
                     today="2026-10-15")
        self.assertTrue(any(g["habit_key"] == "daily_review"
                            for g in r["habit_gaps"]["gaps"]))
        self.assertTrue(is_healthy(r))


class TestWeekHabitSection(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.conn = init_db(self.db)
        # ISO week for 2026-10-13 is 42
        for d in ("2026-10-13", "2026-10-14", "2026-10-15"):
            upsert(self.conn, {
                "date": d, "iso_week": 42, "month": 202610,
                "health_score": 7, "work_score": 7,
                "learn_score": 7, "life_score": 7, "system_score": 7.0,
            })
            upsert_personal_track(
                self.conn, d, "skincare", "护肤", "skincare", "护肤", 1,
            )
            upsert_habit_log(self.conn, {
                "date": d, "habit_key": "reading_30",
                "category": HABIT_CATEGORY, "item": "每日阅读 30 分钟",
                "done": 1, "src": "clickup",
            })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_sections_separate(self):
        s = collect(self.conn, "iso_week=?", (42,), "W42")
        text = render_summary(s)
        self.assertIn("个人打卡依从率", text)
        self.assertIn("行为习惯依从率", text)
        self.assertIn("reading_30", text)
        self.assertIn("skincare", text)
        # 分栏：补剂段不含 habit_key 表头语义混用
        md = render_week_md(self.conn, 42)
        self.assertIn("## 三、个人打卡依从率", md)
        self.assertIn("## 四、行为习惯依从率", md)
        self.assertIn("skincare", md)
        self.assertIn("reading_30", md)
        # 两段分栏：补剂表用 item_key，习惯表用 habit_key
        self.assertIn("| 类别 | item_key |", md)
        self.assertIn("| habit_key |", md)

    def test_key_overlap_helper(self):
        self.assertEqual(key_overlap(["a", "b"], ["b", "c"]), ["b"])
        self.assertEqual(key_overlap([HABITS[0]["key"]], []), [])


if __name__ == "__main__":
    unittest.main()
