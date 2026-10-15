"""教练建议：可解释、可复算、同输入逐字节一致。"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from review_tool.reports.coach import collect, render
from review_tool.storage.db import init_db, upsert_training


def _seed(conn) -> None:
    """写入三天稳定俯卧撑 + 一天跑步，便于触发渐进/恢复规则。"""
    days = [
        ("2026-10-12", "俯卧撑", 4, 20),
        ("2026-10-13", "俯卧撑", 4, 20),
        ("2026-10-14", "俯卧撑", 4, 20),
    ]
    for d, key, sets, reps in days:
        upsert_training(
            conn,
            {
                "date": d,
                "session_key": "main",
                "plan_name": "A-胸背",
                "src": "self",
                "total_min": 15,
            },
            [{
                "item_key": key,
                "item": key,
                "sets": sets,
                "reps": reps,
                "minutes": 12.0,
                "load_kg": None,
            }],
        )
    conn.commit()


class TestCoach(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "c.db")
        self.conn = init_db(db_path=self.db)
        _seed(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_suggestions_have_evidence(self):
        data = collect(self.conn, as_of="2026-10-14")
        self.assertTrue(data["suggestions"])
        for s in data["suggestions"]:
            self.assertIn("evidence", s)
            self.assertTrue(str(s["evidence"]).strip(), s["title"])

    def test_deterministic_render(self):
        """同输入两次输出逐字节一致。"""
        d1 = collect(self.conn, as_of="2026-10-14")
        d2 = collect(self.conn, as_of="2026-10-14")
        self.assertEqual(render(d1), render(d2))
        t1 = render(d1)
        t2 = render(collect(self.conn, as_of="2026-10-14"))
        self.assertEqual(t1, t2)

    def test_recovery_flag_after_three_days(self):
        data = collect(self.conn, as_of="2026-10-14")
        kinds = {s["kind"]: s for s in data["suggestions"]}
        self.assertIn("recovery", kinds)
        self.assertTrue(data["recovery"]["needed"])
        self.assertIn("连续训练", kinds["recovery"]["evidence"])

    def test_empty_db_still_renders(self):
        path = os.path.join(self.root, "empty.db")
        conn = init_db(db_path=path)
        try:
            data = collect(conn, as_of="2026-10-01")
            text = render(data)
            self.assertIn("训练教练建议", text)
            self.assertTrue(data["suggestions"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
