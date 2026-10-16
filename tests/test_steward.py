"""M14 总管家编排：三段 slot + 溯源 + 无独立计算。"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest import mock

from review_tool.config import PROFILE
from review_tool.reports import steward
from review_tool.reports.steward import (
    collect,
    collect_evening,
    collect_morning,
    collect_week,
    render,
)
from review_tool.storage.db import init_db, upsert, upsert_body_metrics


def _seed_day(conn, d: str, **extra):
    row = {
        "date": d,
        "weekday": date.fromisoformat(d).weekday(),
        "health_score": 7,
        "work_score": 5,
        "learn_score": 3,
        "life_score": 5,
        "system_score": 5.0,
        "diet_kcal": 1500,
        "carbs_g": 180,
        "fat_g": 40,
        "protein_g": 70,
        "training_day": 1,
        "exercise_min": 30,
    }
    row.update(extra)
    upsert(conn, row, overwrite=True)


class TestStewardMorning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = init_db(db_path=self.db)
        # 今日=周四 2026-10-15；昨日有分
        self.today = "2026-10-15"
        self.yday = "2026-10-14"
        _seed_day(self.conn, self.yday)
        # 连续 3 天学习低分 → 熔断
        for i, sc in enumerate((3, 3, 3)):
            d = (date.fromisoformat(self.yday) - timedelta(days=2 - i)).isoformat()
            _seed_day(self.conn, d, learn_score=sc, system_score=5.0)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_morning_sections_and_sources(self):
        data = collect_morning(
            self.conn, as_of=self.today, todos=["A", "B", "C", "D"]
        )
        self.assertEqual(data["slot"], "morning")
        self.assertEqual(data["yesterday"], self.yday)
        self.assertIsNotNone(data["scores"])
        self.assertEqual(data["scores"]["learn_score"], 3)
        self.assertIn("source", data["scores"])
        self.assertGreaterEqual(data["fuse"]["absolute_count"], 1)
        self.assertIn("fuse.find_fuses", data["fuse"]["source"])
        self.assertEqual(len(data["todos"]["items"]), 3)  # Top 3 截断
        self.assertIn("macro_targets", data["diet_targets"]["source"])
        text = render(data)
        self.assertIn("晨间 brief", text)
        self.assertIn("昨日四维", text)
        self.assertIn("今日训练课", text)
        self.assertIn("饮食目标", text)
        self.assertIn("待办 Top 3", text)
        self.assertIn("source=", text)
        self.assertIn("1. A", text)
        self.assertIn("3. C", text)
        self.assertNotIn("4. D", text)
        self.assertNotIn("休息日", text)
        self.assertIn("不判断", text)
        self.assertIn("keepstrong --type plan", text)

    def test_morning_prints_passed_plan_name(self):
        data = collect_morning(
            self.conn, as_of=self.today, today_plan="全身A",
        )
        text = render(data)
        self.assertIn("全身A", text)
        self.assertNotIn("不判断", text)
        self.assertNotIn("休息日", text)

    def test_morning_todo_hint_when_empty(self):
        data = collect_morning(self.conn, as_of=self.today)
        self.assertEqual(data["todos"]["items"], [])
        self.assertIn("clickup", data["todos"]["hint"])
        text = render(data)
        self.assertIn("clickup --stdout", text)

    def test_morning_diet_targets_from_profile(self):
        data = collect_morning(self.conn, as_of=self.today)
        targets = PROFILE["macro_targets"]
        self.assertEqual(data["diet_targets"]["protein_g"], targets["protein_g"])
        self.assertEqual(data["diet_targets"]["carbs_g"], targets["carbs_g"])


class TestStewardEvening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = init_db(db_path=self.db)
        _seed_day(self.conn, "2026-10-15")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_evening_checklist_and_intake(self):
        data = collect_evening(self.conn, as_of="2026-10-15")
        self.assertEqual(data["slot"], "evening")
        self.assertTrue(data["day_in_db"])
        ids = [s["id"] for s in data["steps"]]
        self.assertEqual(ids[0], "intake")
        self.assertIn("body", ids)
        self.assertIn("training", ids)
        self.assertIn("nutrition", ids)
        self.assertIn("doctor", ids)
        text = render(data)
        self.assertIn("daily-review-intake", text)
        self.assertIn("夜间复盘", text)
        self.assertIn("python -m review_tool body", text)
        train = next(s for s in data["steps"] if s["id"] == "training")
        self.assertEqual(
            train["cmd"],
            "python -m review_tool keepstrong --date 2026-10-15 --write --ingest",
        )
        self.assertIn(train["cmd"], text)
        self.assertIn("source=", text)


class TestStewardWeek(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = init_db(db_path=self.db)
        # ISO 周 42：2026-10-12（一）~ 2026-10-18（日）
        for offset in range(5):
            d = (date(2026, 10, 12) + timedelta(days=offset)).isoformat()
            _seed_day(self.conn, d, health_score=7, work_score=6,
                      learn_score=4, life_score=5, system_score=5.5)
        upsert_body_metrics(self.conn, {
            "date": "2026-10-15",
            "weight_kg": 70.0,
            "body_fat_pct": 20.0,
            "waist_cm": 80.0,
            "src": "manual",
        })
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_week_six_sections(self):
        data = collect_week(self.conn, iso_week=42)
        self.assertEqual(data["slot"], "week")
        self.assertEqual(data["iso_week"], 42)
        self.assertIsNotNone(data["four_dims"]["data"])
        self.assertEqual(data["four_dims"]["data"]["days"], 5)
        self.assertIn("analyze.collect", data["four_dims"]["source"])
        self.assertIsNotNone(data["body"]["latest"])
        self.assertEqual(data["body"]["latest"]["weight_kg"], 70.0)
        self.assertIn("body.collect", data["body"]["source"])
        self.assertIn("coach.collect", data["training"]["source"])
        self.assertIn("nutrition.collect", data["nutrition"]["source"])
        self.assertIn("habits.collect", data["habits"]["source"])
        self.assertIn("tutor.collect", data["learning"]["source"])
        text = render(data)
        for title in ("四维", "体征", "训练", "饮食", "习惯", "学习"):
            self.assertIn(title, text)
        self.assertIn("source=", text)
        self.assertIn("无独立计算", text)


class TestStewardNoIndependentCalc(unittest.TestCase):
    """编排层数字必须能对上既有模块（抽样：昨日学习分 + 饮食目标）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = init_db(db_path=self.db)
        _seed_day(self.conn, "2026-10-14", learn_score=2, system_score=4.75)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_scores_match_fetch_day(self):
        from review_tool.reports.ai_review import fetch_day
        from review_tool.reports.fuse import find_fuses
        from review_tool.reports.nutrition import collect as nutri_collect

        data = collect_morning(self.conn, as_of="2026-10-15")
        day = fetch_day(self.conn, "2026-10-14")
        self.assertEqual(data["scores"]["learn_score"], day["learn_score"])
        self.assertEqual(data["scores"]["system_score"], day["system_score"])
        fuse_raw = find_fuses(self.conn)
        self.assertEqual(
            data["fuse"]["absolute_count"], len(fuse_raw["absolute"])
        )
        nutri = nutri_collect(self.conn, as_of="2026-10-15")
        self.assertEqual(
            data["diet_targets"]["protein_g"], nutri["targets"]["protein_g"]
        )


class TestStewardCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = init_db(db_path=self.db)
        _seed_day(self.conn, "2026-10-14")
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_morning_json(self):
        with mock.patch("review_tool.reports.steward.init_db") as m:
            m.return_value = init_db(db_path=self.db)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = steward.main([
                    "--slot", "morning", "2026-10-15",
                    "--json", "--todo", "写周报",
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["slot"], "morning")
            self.assertEqual(payload["todos"]["items"], ["写周报"])

    def test_cli_requires_slot(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = steward.main([])
        self.assertEqual(rc, 2)

    def test_collect_dispatch(self):
        conn = init_db(db_path=self.db)
        try:
            m = collect(conn, slot="morning", as_of="2026-10-15")
            e = collect(conn, slot="evening", as_of="2026-10-15")
            w = collect(conn, slot="week", iso_week=42)
            self.assertEqual(m["slot"], "morning")
            self.assertEqual(e["slot"], "evening")
            self.assertEqual(w["slot"], "week")
        finally:
            conn.close()

    def test_route_registered(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("steward", ROUTES)


class TestSkillLayout(unittest.TestCase):
    def test_life_steward_skill_present(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(
            root, ".workbuddy", "skills", "life-steward-daily", "SKILL.md"
        )
        self.assertTrue(os.path.isfile(path), "缺 life-steward-daily skill")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("name: life-steward-daily", text)
        self.assertIn("晨间", text)
        self.assertIn("夜间", text)
        self.assertIn("周度", text)
        self.assertIn("daily-review-intake", text)


if __name__ == "__main__":
    unittest.main()
