"""db 模块测试：建表、upsert 幂等、CHECK 约束、派生字段自动计算、增量迁移。"""
import os
import shutil
import sqlite3
import tempfile
import unittest

from review_tool.db import (
    COLUMNS,
    SCHEMA_VERSION,
    count,
    fetch_all,
    init_db,
    upsert,
    upsert_personal_track,
)


def _tmp_db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.db")
    return init_db(db_path=path), path


class TestUpsert(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_insert_and_fetch(self):
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 7.0})
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)
        rows = fetch_all(self.conn)
        self.assertEqual(rows[0]["date"], "2026-08-05")
        self.assertEqual(rows[0]["sleep_h"], 7.0)

    def test_upsert_idempotent(self):
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 7.0})
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 8.0})
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)  # 同日期不重复
        self.assertEqual(fetch_all(self.conn)[0]["sleep_h"], 8.0)

    def test_auto_iso_week_and_month(self):
        upsert(self.conn, {"date": "2026-08-05"})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertIsInstance(row["iso_week"], int)
        self.assertEqual(row["month"], 202608)

    def test_check_rejects_bad_score(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-06", "health_score": 99})
            self.conn.commit()

    def test_check_rejects_bad_bool(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-07", "training_day": 2})
            self.conn.commit()

    def test_all_columns_present(self):
        # 写入全 None 的行不应报错（CHECK 允许 NULL）
        row = {c: None for c in COLUMNS}
        row["date"] = "2026-08-08"
        upsert(self.conn, row)
        self.conn.commit()
        self.assertEqual(count(self.conn), 1)

    def test_macro_columns_roundtrip(self):
        upsert(self.conn, {"date": "2026-08-05", "carbs_g": 150, "fat_g": 40, "protein_g": 55})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["carbs_g"], 150)
        self.assertEqual(row["fat_g"], 40)
        self.assertEqual(row["protein_g"], 55)

    def test_macro_check_rejects_negative(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-08-06", "carbs_g": -10})
            self.conn.commit()


class TestMigration(unittest.TestCase):
    """老库（schema 更新前建表）init_db 应无损补齐缺失宏量列。"""

    def test_adds_missing_macro_columns(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "old.db")
        conn = sqlite3.connect(path)
        # 仿「加宏量列之前」的真实历史 schema（含 iso_week/month，无 macros 列）
        conn.executescript("""
            CREATE TABLE daily_reviews (
                date     TEXT PRIMARY KEY,
                weekday  TEXT,
                iso_week INTEGER,
                month    INTEGER,
                training_day INTEGER,
                sleep_h  REAL,
                sleep_quality INTEGER,
                bedtime  INTEGER,
                exercise_min INTEGER,
                commute_done INTEGER,
                diet_kcal INTEGER,
                meals_count INTEGER,
                breakfast_on_time INTEGER,
                phone_h  REAL,
                deepwork_h REAL,
                learn_h  REAL,
                life_h   REAL,
                energy   TEXT,
                mood     TEXT,
                health_score INTEGER,
                work_score INTEGER,
                learn_score INTEGER,
                life_score INTEGER,
                system_score REAL,
                summary  TEXT,
                raw_path TEXT,
                ingested_at TEXT
            );
            INSERT INTO daily_reviews (date, diet_kcal) VALUES ('2026-08-05', 1500);
        """)
        conn.commit()
        conn.close()

        conn = init_db(db_path=path)  # 触发增量迁移
        cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")}
        for c in ("carbs_g", "fat_g", "protein_g"):
            self.assertIn(c, cols)
        # 老数据保留无损
        v = conn.execute(
            "SELECT diet_kcal FROM daily_reviews WHERE date='2026-08-05'"
        ).fetchone()[0]
        self.assertEqual(v, 1500)
        conn.close()
        os.remove(path)
        os.rmdir(d)


class TestPersonalTracks(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_upsert_and_fetch(self):
        upsert_personal_track(self.conn, "2026-08-05", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 1)
        upsert_personal_track(self.conn, "2026-08-05", "skincare",
                              "护肤", "skincare", "护肤", 0)
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT category, item_key, item, done FROM personal_tracks ORDER BY item_key"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(tuple(rows[0]), ("服药", "coq10", "CoQ10 ×1", 1))
        self.assertEqual(tuple(rows[1]), ("护肤", "skincare", "护肤", 0))

    def test_upsert_idempotent(self):
        upsert_personal_track(self.conn, "2026-08-05", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 1)
        upsert_personal_track(self.conn, "2026-08-05", "coq10@morning",
                              "服药", "coq10", "CoQ10 ×1", 0)
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT done FROM personal_tracks WHERE date='2026-08-05'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["done"], 0)

    def test_same_item_different_slots_coexist(self):
        """同一规范项在不同时段是两条记录——这正是归一化后主键设计要支持的。"""
        for slot in ("noon", "evening"):
            upsert_personal_track(self.conn, "2026-08-05", f"movefree@{slot}",
                                  "服药", "movefree", "Move Free 红色 ×1", 1)
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT track_key FROM personal_tracks WHERE date='2026-08-05' "
            "ORDER BY track_key"
        ).fetchall()
        self.assertEqual([r[0] for r in rows], ["movefree@evening", "movefree@noon"])
        # 但按 item_key 聚合时是同一项
        n = self.conn.execute(
            "SELECT COUNT(DISTINCT item_key) FROM personal_tracks"
        ).fetchone()[0]
        self.assertEqual(n, 1)


class TestUpsertProtection(unittest.TestCase):
    """默认保护模式：新值为 None 时不得把库里已有值刷掉。"""

    def setUp(self):
        self.conn, self.path = _tmp_db()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_none_does_not_erase_existing(self):
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 7.0, "summary": "写过了"})
        upsert(self.conn, {"date": "2026-08-05", "sleep_h": 8.0})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["sleep_h"], 8.0)      # 新值生效
        self.assertEqual(row["summary"], "写过了")  # 空值不擦旧值

    def test_overwrite_mode_does_erase(self):
        upsert(self.conn, {"date": "2026-08-05", "summary": "写过了"})
        upsert(self.conn, {"date": "2026-08-05", "summary": None}, overwrite=True)
        self.conn.commit()
        self.assertIsNone(fetch_all(self.conn)[0]["summary"])

    def test_metadata_always_refreshed(self):
        upsert(self.conn, {"date": "2026-08-05", "raw_path": "old.md"})
        upsert(self.conn, {"date": "2026-08-05", "raw_path": "new.md"})
        self.conn.commit()
        self.assertEqual(fetch_all(self.conn)[0]["raw_path"], "new.md")


class TestFetchAllOrder(unittest.TestCase):
    def setUp(self):
        self.conn, self.path = _tmp_db()
        upsert(self.conn, {"date": "2026-08-05"})
        upsert(self.conn, {"date": "2026-08-07"})
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def test_order_desc(self):
        rows = fetch_all(self.conn, "date DESC")
        self.assertEqual(rows[0]["date"], "2026-08-07")

    def test_rejects_illegal_order(self):
        with self.assertRaises(ValueError):
            fetch_all(self.conn, "date; DROP TABLE daily_reviews")
        with self.assertRaises(ValueError):
            fetch_all(self.conn, "not_a_column ASC")


class TestMigrationPersonalTracks(unittest.TestCase):
    """老库（自由文本主键）升级到规范 track_key 的迁移。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "old.db")
        conn = sqlite3.connect(self.path)
        conn.executescript("""
            CREATE TABLE daily_reviews (
                date TEXT PRIMARY KEY,
                iso_week INTEGER,
                month INTEGER,
                carbs_g INTEGER,
                fat_g INTEGER,
                protein_g INTEGER
            );
            CREATE TABLE personal_tracks (
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                item TEXT NOT NULL,
                done INTEGER CHECK (done IN (0, 1)),
                note TEXT,
                PRIMARY KEY (date, category, item)
            );
            INSERT INTO personal_tracks VALUES
                ('2026-07-16', '服药', '晨间-CoQ10 ×1 ＋ Exia 早3', 1, NULL),
                ('2026-07-16', '服药', '晚间-Exia 晚3 ＋ Move Free 红色 ×1', 1, NULL),
                ('2026-07-17', '服药', 'CoQ10 ×1 ＋ Exia 早3', 0, NULL),
                ('2026-07-17', '护肤', '护肤', 1, NULL);
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_migrates_to_normalized_keys(self):
        conn = init_db(db_path=self.path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(personal_tracks)")}
        self.assertIn("track_key", cols)
        self.assertIn("item_key", cols)

        rows = conn.execute(
            "SELECT date, track_key, item_key, done FROM personal_tracks "
            "ORDER BY date, track_key"
        ).fetchall()
        got = [(r[0], r[1], r[3]) for r in rows]
        self.assertIn(("2026-07-16", "coq10@morning", 1), got)
        self.assertIn(("2026-07-16", "exia_am@morning", 1), got)
        self.assertIn(("2026-07-16", "exia_pm@evening", 1), got)
        self.assertIn(("2026-07-16", "movefree@evening", 1), got)
        # 老写法在两种日期下的同一项必须收敛到同一个 key
        keys_0717 = {r[1] for r in rows if r[0] == "2026-07-17"}
        self.assertIn("coq10@morning", keys_0717)
        self.assertIn("exia_am@morning", keys_0717)
        conn.close()

    def test_migration_is_idempotent(self):
        conn = init_db(db_path=self.path)
        n1 = conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]
        conn.close()
        conn = init_db(db_path=self.path)  # 再跑一次不得重复迁移
        n2 = conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]
        self.assertEqual(n1, n2)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        conn.close()

    def test_schema_version_recorded(self):
        conn = init_db(db_path=self.path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        conn.close()


if __name__ == "__main__":
    unittest.main()
