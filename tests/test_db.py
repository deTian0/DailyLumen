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

    def test_exercise_src_roundtrip(self):
        upsert(self.conn, {"date": "2026-09-21", "exercise_min": 10,
                           "exercise_src": "derived"})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["exercise_min"], 10)
        self.assertEqual(row["exercise_src"], "derived")

    def test_exercise_src_check_rejects_unknown(self):
        with self.assertRaises(sqlite3.IntegrityError):
            upsert(self.conn, {"date": "2026-09-21", "exercise_src": "拍脑袋"})
            self.conn.commit()

    def test_exercise_src_always_refreshed(self):
        """来源标记跟着新值走：改成手填后不能还留着 derived。"""
        upsert(self.conn, {"date": "2026-09-21", "exercise_min": 10,
                           "exercise_src": "derived"})
        upsert(self.conn, {"date": "2026-09-21", "exercise_min": 10,
                           "exercise_src": "record"})
        self.conn.commit()
        row = fetch_all(self.conn)[0]
        self.assertEqual(row["exercise_src"], "record")


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

    def test_interrupted_rebuild_recovers_from_v3_old(self):
        """重建中断的现场（空新表 + daily_reviews_v3_old）必须能自愈。

        这是真实发生过的事故形态：旧表已改名、新表已建但未搬运数据。
        """
        d = tempfile.mkdtemp()
        path = os.path.join(d, "interrupted.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE daily_reviews_v3_old (
                date TEXT PRIMARY KEY,
                training_day INTEGER,
                exercise_min INTEGER,
                phone_h REAL
            );
            INSERT INTO daily_reviews_v3_old VALUES ('2026-09-13', 1, NULL, 8.0);
            CREATE TABLE daily_reviews (date TEXT PRIMARY KEY);
        """)
        conn.commit()
        conn.close()

        conn = init_db(db_path=path)
        rows = [tuple(r) for r in conn.execute(
            "SELECT date, training_day, exercise_min, phone_h FROM daily_reviews"
        )]
        self.assertEqual(rows, [("2026-09-13", 1, None, 8.0)])
        # 恢复后旧表不应残留，且能正常写 zero
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertNotIn("daily_reviews_v3_old", tables)
        conn.execute("UPDATE daily_reviews SET exercise_min=0, exercise_src='zero' "
                     "WHERE date='2026-09-13'")
        conn.commit()
        conn.close()
        os.remove(path)
        os.rmdir(d)

    def test_v3_check_rebuild_allows_zero_and_preserves_data(self):
        """v3 老库（exercise_src CHECK 不含 'zero'）-> v4 重建表。

        重建必须：数据逐行无损、'zero' 可写入、索引仍在、user_version=4。
        """
        d = tempfile.mkdtemp()
        path = os.path.join(d, "v3.db")
        conn = sqlite3.connect(path)
        # 仿 v3 真实 schema：exercise_src CHECK 只放行 record/derived
        conn.executescript("""
            CREATE TABLE daily_reviews (
                date TEXT PRIMARY KEY,
                training_day INTEGER,
                exercise_min INTEGER CHECK (exercise_min IS NULL OR exercise_min >= 0),
                exercise_src TEXT CHECK (exercise_src IS NULL
                                         OR exercise_src IN ('record', 'derived')),
                phone_h REAL
            );
            INSERT INTO daily_reviews VALUES ('2026-09-13', 1, 10, 'derived', 8.0);
            INSERT INTO daily_reviews VALUES ('2026-09-14', 1, NULL, NULL, 8.1);
            CREATE INDEX idx_exercise_src ON daily_reviews(exercise_src);
        """)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        conn = init_db(db_path=path)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        # 数据无损
        rows = [tuple(r) for r in conn.execute(
            "SELECT date, exercise_min, exercise_src, phone_h "
            "FROM daily_reviews ORDER BY date"
        )]
        self.assertEqual(rows, [
            ("2026-09-13", 10, "derived", 8.0),
            ("2026-09-14", None, None, 8.1),
        ])
        # 新约束放行 zero，仍拦截脏值
        conn.execute("UPDATE daily_reviews SET exercise_src='zero' "
                     "WHERE date='2026-09-14'")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE daily_reviews SET exercise_src='bogus' "
                         "WHERE date='2026-09-14'")
        conn.commit()
        # 索引随重建恢复
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='daily_reviews'"
        )}
        self.assertIn("idx_exercise_src", idx)
        conn.close()
        os.remove(path)
        os.rmdir(d)

    def test_backfills_exercise_src_for_recorded_values(self):
        """新增 exercise_src 后：老库里已有数值的标记 record，空值保持 NULL。"""
        d = tempfile.mkdtemp()
        path = os.path.join(d, "old_exercise.db")
        conn = sqlite3.connect(path)
        # 仿「加 exercise_src 之前」的表：只有 date + exercise_min
        conn.executescript("""
            CREATE TABLE daily_reviews (
                date         TEXT PRIMARY KEY,
                exercise_min INTEGER
            );
            INSERT INTO daily_reviews VALUES ('2026-08-05', 30);
            INSERT INTO daily_reviews VALUES ('2026-08-06', NULL);
            INSERT INTO daily_reviews VALUES ('2026-08-07', 0);
        """)
        conn.commit()
        conn.close()

        conn = init_db(db_path=path)  # 触发增量迁移
        cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_reviews)")}
        self.assertIn("exercise_src", cols)
        got = dict(conn.execute(
            "SELECT date, exercise_src FROM daily_reviews ORDER BY date"
        ).fetchall())
        self.assertEqual(got["2026-08-05"], "record")
        self.assertIsNone(got["2026-08-06"])          # 空值不标记
        self.assertEqual(got["2026-08-07"], "record")  # 0 也是填报值
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


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
