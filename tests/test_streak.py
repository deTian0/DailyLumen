"""正向 streak 测试（v1.9.1）。"""
import os
import shutil
import tempfile
import unittest

from review_tool.reports import streak
from review_tool.storage.db import init_db, upsert, upsert_personal_track


class TestStreakHelpers(unittest.TestCase):
    def test_contiguous(self):
        self.assertEqual(
            streak.streak_from_dates(["2026-09-01", "2026-09-02", "2026-09-03"]),
            3,
        )

    def test_break_resets(self):
        self.assertEqual(
            streak.streak_from_dates(
                ["2026-09-01", "2026-09-02", "2026-09-04"], as_of="2026-09-04"
            ),
            1,
        )

    def test_empty(self):
        self.assertEqual(streak.streak_from_dates([]), 0)


class TestStreakDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.conn = init_db(db_path=os.path.join(self.dir, "t.db"))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_review_and_training(self):
        # Mon/Tue/Wed training weekdays in PROFILE typically 0,1,2,...
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1, "exercise_min": 20})
        upsert(self.conn, {"date": "2026-09-08", "training_day": 1, "exercise_min": 15})
        upsert(self.conn, {"date": "2026-09-09", "training_day": 1, "exercise_min": 0})
        self.conn.commit()
        rev = streak.review_streak(self.conn)
        self.assertEqual(rev["current"], 3)
        # as_of 09-08：两个训练日达标；09-09 未达标则从 09-09 起为 0
        self.assertEqual(streak.training_streak(self.conn, as_of="2026-09-08")["current"], 2)
        self.assertEqual(streak.training_streak(self.conn, as_of="2026-09-09")["current"], 0)

    def test_track_streak(self):
        for d, done in (("2026-09-07", 1), ("2026-09-08", 1), ("2026-09-09", 0)):
            upsert(self.conn, {"date": d})
            upsert_personal_track(
                self.conn, d, "coq10@morning", "服药", "coq10", "CoQ10", done)
        self.conn.commit()
        self.assertEqual(streak.track_streak(self.conn, "coq10", as_of="2026-09-08")["current"], 2)
        self.assertEqual(streak.track_streak(self.conn, "coq10", as_of="2026-09-09")["current"], 0)

    def test_render_contains_section(self):
        upsert(self.conn, {"date": "2026-09-07", "training_day": 1, "exercise_min": 10})
        self.conn.commit()
        text = streak.render_streaks(streak.summarize_streaks(self.conn))
        self.assertIn("正向连续", text)
        self.assertIn("复盘入库", text)


if __name__ == "__main__":
    unittest.main()
