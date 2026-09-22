"""export 模块测试：CSV / JSON 导出与依从率聚合。"""
import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest

from review_tool.db import init_db, upsert, upsert_personal_track
from review_tool.export import export


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t.db")
        self.out = os.path.join(self.dir, "out")
        self.conn = init_db(db_path=self.db)
        upsert(self.conn, {"date": "2026-09-21", "sleep_h": 7.0, "health_score": 6})
        upsert(self.conn, {"date": "2026-09-22", "sleep_h": 8.0, "health_score": 7})
        upsert_personal_track(self.conn, "2026-09-21", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 1)
        upsert_personal_track(self.conn, "2026-09-22", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 0)
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _read_csv(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))


class TestCsvExport(_Fixture):
    def test_writes_three_files(self):
        written = export(db_path=self.db, fmt="csv", out_dir=self.out)
        names = sorted(os.path.basename(p) for p in written)
        self.assertEqual(names, ["adherence.csv", "daily_reviews.csv",
                                 "personal_tracks.csv"])

    def test_daily_rows(self):
        export(db_path=self.db, out_dir=self.out)
        rows = self._read_csv("daily_reviews.csv")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-09-21")
        self.assertEqual(rows[0]["sleep_h"], "7.0")

    def test_tracks_rows(self):
        export(db_path=self.db, out_dir=self.out)
        rows = self._read_csv("personal_tracks.csv")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["track_key"], "coq10@morning")

    def test_adherence_computed(self):
        export(db_path=self.db, out_dir=self.out)
        rows = self._read_csv("adherence.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recorded"], "2")
        self.assertEqual(rows[0]["done"], "1")
        self.assertEqual(rows[0]["adherence"], "0.5")

    def test_csv_is_excel_friendly(self):
        """必须带 BOM，否则 Excel 打开中文乱码。"""
        export(db_path=self.db, out_dir=self.out)
        with open(os.path.join(self.out, "daily_reviews.csv"), "rb") as f:
            self.assertTrue(f.read(3).startswith(b"\xef\xbb\xbf"))


class TestJsonExport(_Fixture):
    def test_single_json_file(self):
        written = export(db_path=self.db, fmt="json", out_dir=self.out)
        self.assertEqual(len(written), 1)
        with open(written[0], encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["daily_reviews"]), 2)
        self.assertEqual(len(data["personal_tracks"]), 2)
        self.assertEqual(data["adherence"][0]["adherence"], 0.5)

    def test_stdout_mode(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            written = export(db_path=self.db, fmt="json", to_stdout=True)
        self.assertEqual(written, [])
        data = json.loads(buf.getvalue())
        self.assertIn("daily_reviews", data)

    def test_bad_format_raises(self):
        with self.assertRaises(ValueError):
            export(db_path=self.db, fmt="xml", out_dir=self.out)


if __name__ == "__main__":
    unittest.main()
