"""doctor 模块测试：对账、新鲜度、归一化、训练日口径。"""
import os
import shutil
import tempfile
import unittest

from review_tool.reports import doctor
from review_tool.storage.db import SCHEMA_VERSION, init_db, upsert, upsert_personal_track


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "t.db")
        self.md_dir = os.path.join(self.root, "每日复盘")
        os.makedirs(os.path.join(self.md_dir, "复盘", "2026-09"), exist_ok=True)
        os.makedirs(os.path.join(self.md_dir, "收件箱"), exist_ok=True)
        os.makedirs(os.path.join(self.md_dir, "历史源复盘"), exist_ok=True)
        self.conn = init_db(db_path=self.db)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _md(self, rel):
        p = os.path.join(self.md_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        return p

    def _run(self, **kw):
        return doctor.diagnose(db_path=self.db, input_dir=self.md_dir, **kw)


class TestDiagnoseBasics(_Fixture):
    def test_reports_schema_and_integrity(self):
        r = self._run(today="2026-09-22")
        self.assertEqual(r["schema_version"], SCHEMA_VERSION)
        self.assertEqual(r["schema_expected"], SCHEMA_VERSION)
        self.assertEqual(r["integrity"], "ok")

    def test_empty_db_has_no_latest(self):
        r = self._run(today="2026-09-22")
        self.assertEqual(r["rows"], 0)
        self.assertIsNone(r["latest_date"])
        self.assertIsNone(r["stale_days"])

    def test_freshness(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["stale_days"], 1)


class TestReconciliation(_Fixture):
    def test_detects_not_ingested(self):
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-22")
        self.assertIn("2026-09-21", r["not_ingested"])

    def test_detects_orphan_in_db(self):
        upsert(self.conn, {"date": "2026-09-01"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertIn("2026-09-01", r["orphan_in_db"])

    def test_inbox_and_archive_not_treated_as_standard_source(self):
        """收件箱/历史源复盘里的文件不算「标准源」，不得出现在 not_ingested。"""
        self._md("收件箱/2026-09-05.md")
        self._md("历史源复盘/2026-07-16.md")
        r = self._run(today="2026-09-22")
        self.assertNotIn("2026-09-05", r["not_ingested"])
        self.assertNotIn("2026-07-16", r["not_ingested"])

    def test_inbox_readme_not_counted_as_material(self):
        """收件箱里的说明文档（README / 下划线前缀 / 隐藏文件）不算待处理素材。"""
        inbox = os.path.join(self.md_dir, "收件箱")
        with open(os.path.join(inbox, "README.md"), "w", encoding="utf-8") as f:
            f.write("# 收件箱说明")
        with open(os.path.join(inbox, "_note.md"), "w", encoding="utf-8") as f:
            f.write("辅助说明")
        with open(os.path.join(inbox, ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("")
        self.assertEqual(self._run(today="2026-09-22")["inbox_files"], 0)
        with open(os.path.join(inbox, "截图转写.md"), "w", encoding="utf-8") as f:
            f.write("今日素材")
        self.assertEqual(self._run(today="2026-09-22")["inbox_files"], 1)

    def test_archive_only_reported(self):
        self._md("历史源复盘/2026-07-16.md")
        upsert(self.conn, {"date": "2026-07-16"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertIn("2026-07-16", r["archive_only"])
        self.assertNotIn("2026-07-16", r["orphan_in_db"])


class TestFilenameDateParsing(unittest.TestCase):
    """只认「主干恰为日期」的日复盘，周/月汇总不得冒充某一天（v1.4.1 修复）。"""

    def test_plain_date_ok(self):
        self.assertEqual(doctor._date_from_filename("2026-09-21.md"), "2026-09-21")

    def test_weekly_summary_rejected(self):
        self.assertIsNone(doctor._date_from_filename("周总结-W36-2026-09-21_09-27.md"))
        self.assertIsNone(doctor._date_from_filename("周总结-W36-2026-08-31_09-06.md"))

    def test_extra_suffix_rejected(self):
        self.assertIsNone(doctor._date_from_filename("2026-09-21-补充.md"))
        self.assertIsNone(doctor._date_from_filename("备份-2026-09-21.md"))

    def test_dates_from_dir_ignores_summary(self):
        root = tempfile.mkdtemp()
        try:
            with open(os.path.join(root, "2026-09-21.md"), "w", encoding="utf-8") as f:
                f.write("x")
            with open(os.path.join(root, "周总结-W39-2026-09-21_09-27.md"),
                      "w", encoding="utf-8") as f:
                f.write("x")
            self.assertEqual(doctor._dates_from_dir(root), {"2026-09-21"})
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestWeeklySummaryNotADailySource(_Fixture):
    """假阴性回归：周总结曾让缺失的日文档「看起来有人管」（v1.4.1 修复）。"""

    def test_weekly_summary_does_not_mask_missing_daily(self):
        # 只有周总结、没有 09-21 的日文档；库里有 09-21 的记录
        self._md("复盘/2026-09/周总结-W39-2026-09-21_09-27.md")
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        # 修复前：周总结被当成 09-21 的日文档 → 既不报 orphan 也不报 missing（假阴性）
        # 修复后：09-21 找不到真正的日文档 → 计入 orphan_in_db
        self.assertIn("2026-09-21", r["orphan_in_db"])
        self.assertNotIn("2026-09-21", r["not_ingested"])


class TestScoreConsistency(_Fixture):
    """库中四维 / 系统分必须与「按字段重算」一致（v1.4.1 新增检测）。"""

    _ROW = {
        "date": "2026-09-21", "training_day": 1,
        "sleep_h": 7.0, "sleep_quality": 85, "bedtime": 1400,
        "exercise_min": 30, "diet_kcal": 1800, "phone_h": 8.0,
        "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 1.0,
    }

    def _row_with_rule_scores(self, **over):
        from review_tool.core.score import (
            compute_health_score,
            compute_learn_score,
            compute_life_score,
            compute_work_score,
            system_score_from,
        )
        row = dict(self._ROW)
        row.update(over)
        base = row
        scores = {
            "health_score": compute_health_score(base),
            "work_score": compute_work_score(base),
            "learn_score": compute_learn_score(base),
            "life_score": compute_life_score(base),
        }
        scores["system_score"] = system_score_from(scores)
        row.update(scores)
        return row

    def test_clean_when_values_match_rules(self):
        upsert(self.conn, self._row_with_rule_scores())
        self.conn.commit()
        self.assertEqual(self._run(today="2026-09-22")["score_drift"], [])

    def test_detects_hand_edited_score(self):
        row = self._row_with_rule_scores(learn_h=0.5)  # 规则算 3 分
        row["learn_score"] = 9                         # 手改成 9
        upsert(self.conn, row)
        self.conn.commit()
        drift = self._run(today="2026-09-22")["score_drift"]
        self.assertTrue(any(d["col"] == "learn_score" for d in drift))

    def test_detects_stale_after_field_change(self):
        """字段改了但分数没跟着重算 → 必须报出来。"""
        row = self._row_with_rule_scores(deepwork_h=4.0)
        # 把字段改成 0 小时，但保留旧的 work_score
        row["deepwork_h"] = 0.0
        upsert(self.conn, row)
        self.conn.commit()
        drift = self._run(today="2026-09-22")["score_drift"]
        self.assertTrue(any(d["col"] == "work_score" for d in drift))

    def test_drift_does_not_break_health(self):
        row = self._row_with_rule_scores()
        row["learn_score"] = 9
        upsert(self.conn, row)
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-22")
        self.assertTrue(r["score_drift"])          # 有漂移
        self.assertTrue(doctor.is_healthy(r))      # 但手填覆盖属合法，不影响数据健康

    def test_render_lists_consistency_section(self):
        upsert(self.conn, self._row_with_rule_scores())
        self.conn.commit()
        text = doctor.render(self._run(today="2026-09-22"))
        self.assertIn("[分数一致性]", text)
        self.assertIn("与字段重算完全一致", text)


class TestTrackNormalization(_Fixture):
    def test_unnormalized_flagged(self):
        upsert_personal_track(self.conn, "2026-09-21", "other:某新补剂", "服药",
                              "other:某新补剂", "某新补剂", 1)
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(r["unnormalized_tracks"])

    def test_normalized_not_flagged(self):
        upsert_personal_track(self.conn, "2026-09-21", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 1)
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["unnormalized_tracks"], [])


class TestTrainingDayDrift(_Fixture):
    def test_detects_drift(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 0})  # 周一应为训练日
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(any(d == "2026-09-21" for d, _ in r["training_day_drift"]))

    def test_detects_missing(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(any(d == "2026-09-21" for d, _ in r["training_day_drift"]))

    def test_consistent_no_drift(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 1})  # 周一=训练日
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["training_day_drift"], [])


class TestExerciseSources(_Fixture):
    """运动时长来源分布：填报 / 描述折算 / 按 0 计 / 未记录 必须分得开。"""

    def test_counts_by_source(self):
        upsert(self.conn, {"date": "2026-09-07", "exercise_min": 30,
                           "exercise_src": "record"})
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        upsert(self.conn, {"date": "2026-09-09", "exercise_min": 0,
                           "exercise_src": "zero"})
        upsert(self.conn, {"date": "2026-09-10", "exercise_min": None})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["exercise_sources"],
                         {"recorded": 1, "derived": 1, "zero": 1, "missing": 1})

    def test_derivation_does_not_break_health(self):
        """折算只是来源差异，不应把体检判成不健康。"""
        self._md("复盘/2026-09/2026-09-08.md")
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertTrue(doctor.is_healthy(r))

    def test_render_lists_sources(self):
        upsert(self.conn, {"date": "2026-09-08", "exercise_min": 10,
                           "exercise_src": "derived"})
        self.conn.commit()
        text = doctor.render(self._run(today="2026-09-22"))
        self.assertIn("[运动时长来源]", text)
        self.assertIn("描述折算 1 天", text)


class TestTrackReconciliation(_Fixture):
    """[打卡对账]：库里打卡行必须在源 md 找到对应勾选（v1.4.2）。"""

    def _write_md(self, rel, content):
        p = os.path.join(self.md_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def _md_with_tracks(self, date="2026-09-21"):
        from tests.sample_data import SAMPLE_MD
        rel = f"复盘/2026-09/{date}.md"
        return self._write_md(rel, SAMPLE_MD.replace("2026-08-05", date))

    def test_detects_stale_row(self):
        path = self._md_with_tracks()
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        # 源 md 里的三项
        upsert_personal_track(self.conn, "2026-09-21", "coq10@morning", "服药",
                              "coq10", "CoQ10 ×1", 1)
        # 规范 ID 变化后残留的旧键
        upsert_personal_track(self.conn, "2026-09-21", "movefree", "服药",
                              "movefree", "Move Free 红色 ×1", 1)
        self.conn.commit()
        stale = doctor.stale_track_rows(self.conn)
        self.assertEqual([s["track_key"] for s in stale], ["movefree"])

    def test_clean_when_all_reproducible(self):
        path = self._md_with_tracks()
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        for key, ik in (("coq10@morning", "coq10"),
                        ("exia_am@morning", "exia_am"),
                        ("skincare", "skincare")):
            upsert_personal_track(self.conn, "2026-09-21", key, "服药", ik, ik, 1)
        self.conn.commit()
        self.assertEqual(doctor.stale_track_rows(self.conn), [])

    def test_skips_when_section_missing(self):
        """源 md 没有打卡章节 → 不敢断言（可能只是解析不到）。"""
        path = self._write_md("复盘/2026-09/2026-09-21.md",
                              "## 二、今日三件事\n\n```data\n日期: 2026-09-21\n```\n")
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        upsert_personal_track(self.conn, "2026-09-21", "movefree", "服药",
                              "movefree", "Move Free 红色 ×1", 1)
        self.conn.commit()
        self.assertEqual(doctor.stale_track_rows(self.conn), [])

    def test_render_reports_stale(self):
        path = self._md_with_tracks()
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        upsert_personal_track(self.conn, "2026-09-21", "movefree", "服药",
                              "movefree", "Move Free 红色 ×1", 1)
        self.conn.commit()
        text = doctor.render(self._run(today="2026-09-22"))
        self.assertIn("[打卡对账]", text)
        self.assertIn("--prune-tracks", text)

    def test_render_clean(self):
        path = self._md_with_tracks()
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        upsert_personal_track(self.conn, "2026-09-21", "skincare", "护肤",
                              "skincare", "护肤", 1)
        self.conn.commit()
        text = doctor.render(self._run(today="2026-09-22"))
        self.assertIn("每条打卡都能在源 md 找到对应勾选", text)

    def test_does_not_break_health(self):
        path = self._md_with_tracks()
        upsert(self.conn, {"date": "2026-09-21", "raw_path": path})
        upsert_personal_track(self.conn, "2026-09-21", "movefree", "服药",
                              "movefree", "Move Free 红色 ×1", 1)
        self.conn.commit()
        self.assertTrue(doctor.is_healthy(self._run(today="2026-09-22")))


class TestHealthConsistency(_Fixture):
    """结论与退出码同源：render 里的「数据健康」必须等于 is_healthy。"""

    def test_stale_is_advisory(self):
        """新鲜度只是建议：CI 里历史库必然「过期」，不该算数据故障。"""
        upsert(self.conn, {"date": "2020-01-01"})
        self.conn.commit()
        self._md("复盘/2020-01/2020-01-01.md")
        r = self._run(today="2026-09-22")
        self.assertGreater(r["stale_days"], 1)
        self.assertTrue(doctor.is_healthy(r))
        self.assertIn("数据健康", doctor.render(r))

    def test_empty_db_unhealthy(self):
        r = self._run(today="2026-09-22")
        self.assertFalse(doctor.is_healthy(r))
        self.assertIn("存在待处理项", doctor.render(r))

    def test_conclusion_matches_exit_code(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-22")
        text = doctor.render(r, encoding="utf-8")
        self.assertTrue(doctor.is_healthy(r))
        self.assertIn("结论: ✓ 数据健康", text)


class TestHistoryGaps(_Fixture):
    """历史断更：相邻入库日间隔 > 1 天（v1.7.1）。"""

    def test_detects_gaps_matching_sql(self):
        # 四处空洞：缺 1 + 1 + 6 + 11 = 19（对齐路线图证据形状）
        dates = [
            "2026-07-16",
            "2026-07-18",  # 缺 07-17 → 1
            "2026-07-19", "2026-07-20", "2026-07-21",
            "2026-07-22", "2026-07-23",
            "2026-07-25",  # 缺 07-24 → 1
            "2026-07-26", "2026-07-27", "2026-07-28",
            "2026-08-04",  # 缺 07-29..08-03 → 6
            "2026-08-05",
            "2026-08-17",  # 缺 08-06..08-16 → 11
        ]
        for d in dates:
            upsert(self.conn, {"date": d})
            ym = d[:7]
            self._md(f"复盘/{ym}/{d}.md")
        self.conn.commit()
        r = self._run(today="2026-09-22")
        gaps = r["history_gaps"]
        self.assertEqual(len(gaps), 4)
        self.assertEqual([g["missing"] for g in gaps], [1, 1, 6, 11])
        self.assertEqual(sum(g["missing"] for g in gaps), 19)
        self.assertEqual(
            gaps[0],
            {"prev": "2026-07-16", "next": "2026-07-18", "missing": 1},
        )
        self.assertTrue(doctor.is_healthy(r))
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("[历史断更]", text)
        self.assertIn("共 4 处断更 / 共缺 19 天", text)

    def test_no_gaps_when_contiguous(self):
        for d in ("2026-09-20", "2026-09-21", "2026-09-22"):
            upsert(self.conn, {"date": d})
            self._md(f"复盘/2026-09/{d}.md")
        self.conn.commit()
        r = self._run(today="2026-09-22")
        self.assertEqual(r["history_gaps"], [])
        self.assertIn("无历史空洞", doctor.render(r, encoding="utf-8"))

    def test_history_gaps_pure_helper(self):
        gaps = doctor.history_gaps(["2026-08-05", "2026-08-17", "2026-08-04"])
        # 排序后 08-04→08-05 连续，只剩 08-05→08-17
        self.assertEqual(gaps, [
            {"prev": "2026-08-05", "next": "2026-08-17", "missing": 11},
        ])
        gaps2 = doctor.history_gaps(["2026-08-04", "2026-08-05", "2026-08-17"])
        self.assertEqual(len(gaps2), 1)
        self.assertEqual(gaps2[0]["missing"], 11)


class TestTrackAdherenceCliff(_Fixture):
    """近周打卡完成率相对基线骤降（建议性，不影响 is_healthy）。"""

    def _seed_tracks(self, date: str, *, done: int, total: int = 7):
        """写入 total 条打卡，前 done 条完成。"""
        upsert(self.conn, {"date": date})
        ym = date[:7]
        self._md(f"复盘/{ym}/{date}.md")
        for i in range(total):
            upsert_personal_track(
                self.conn,
                date,
                track_key=f"t{i}",
                item_key=f"item{i}",
                item=f"项{i}",
                category="服药",
                done=1 if i < done else 0,
            )

    def test_triggered_when_recent_collapses(self):
        from datetime import date, timedelta
        # as_of=库最新 10-12 → recent 10-06..10-12；baseline 09-08..10-05
        for i in range(28):
            d = (date(2026, 9, 8) + timedelta(days=i)).isoformat()
            self._seed_tracks(d, done=6, total=7)  # ~85.7%
        for i in range(7):
            d = (date(2026, 10, 6) + timedelta(days=i)).isoformat()
            self._seed_tracks(d, done=0, total=7)  # 0%
        self.conn.commit()
        r = self._run(today="2026-10-14")
        cliff = r["track_adherence_cliff"]
        self.assertIsNotNone(cliff)
        self.assertTrue(cliff["triggered"])
        self.assertEqual(cliff["as_of"], "2026-10-12")  # 库最新日
        self.assertAlmostEqual(cliff["recent_rate"], 0.0, places=3)
        self.assertGreaterEqual(cliff["delta"], 0.3)
        self.assertTrue(doctor.is_healthy(r))
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("[打卡依从率]", text)
        self.assertIn("骤降", text)

    def test_not_triggered_when_stable(self):
        from datetime import date, timedelta
        for i in range(35):
            d = (date(2026, 9, 8) + timedelta(days=i)).isoformat()
            self._seed_tracks(d, done=5, total=7)
        self.conn.commit()
        r = self._run(today="2026-10-14")
        cliff = r["track_adherence_cliff"]
        self.assertIsNotNone(cliff)
        self.assertFalse(cliff["triggered"])
        self.assertTrue(doctor.is_healthy(r))
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("未达阈值", text)

    def test_none_when_no_tracks(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-22")
        self.assertIsNone(r["track_adherence_cliff"])
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("跳过骤降检测", text)

    def test_helper_window_math(self):
        from datetime import date, timedelta
        for i in range(5):
            d = (date(2026, 9, 1) + timedelta(days=i)).isoformat()
            self._seed_tracks(d, done=7, total=7)
        for i in range(3):
            d = (date(2026, 9, 6) + timedelta(days=i)).isoformat()
            self._seed_tracks(d, done=0, total=7)
        self.conn.commit()
        cliff = doctor.track_adherence_cliff(
            self.conn, as_of="2026-09-08",
            recent_days=3, baseline_days=5, drop=0.3,
        )
        self.assertEqual(cliff["recent_start"], "2026-09-06")
        self.assertEqual(cliff["baseline_start"], "2026-09-01")
        self.assertEqual(cliff["baseline_end"], "2026-09-05")
        self.assertTrue(cliff["triggered"])
        self.assertEqual(cliff["recent_rate"], 0.0)
        self.assertEqual(cliff["baseline_rate"], 1.0)


class TestConsoleEncoding(_Fixture):
    """非 UTF-8 stdout 不得因 ✓/⚠️ 崩溃（v1.7.1）。"""

    def _sample_result(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 1})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        return self._run(today="2026-09-22")

    def test_gbk_render_encodes(self):
        text = doctor.render(self._sample_result(), encoding="gbk")
        self.assertIn("[历史断更]", text)
        self.assertIn("[OK]", text)
        # 必需标记不得残留 Unicode 专用符
        for ch in ("✓", "⚠", "🔴", "▲", "▼"):
            self.assertNotIn(ch, text)
        text.encode("gbk")  # 整段必须可 encode

    def test_ascii_marks_safe(self):
        """ascii 控台：标记降级为 ASCII；正文中文仍按原样（GBK 场景才要求整段可 encode）。"""
        text = doctor.render(self._sample_result(), encoding="ascii")
        self.assertIn("[OK]", text)
        for ch in ("✓", "⚠", "🔴", "▲", "▼"):
            self.assertNotIn(ch, text)
        for v in doctor.marks_for_encoding("ascii").values():
            v.encode("ascii")

    def test_utf8_keeps_unicode_marks(self):
        text = doctor.render(self._sample_result(), encoding="utf-8")
        self.assertIn("✓", text)
        self.assertNotIn("[OK]", text)

    def test_marks_for_encoding_helper(self):
        self.assertEqual(doctor.marks_for_encoding("utf-8")["ok"], "✓")
        self.assertEqual(doctor.marks_for_encoding("gbk")["ok"], "[OK]")
        self.assertEqual(doctor.marks_for_encoding("ascii")["warn"], "[!]")


class TestRender(_Fixture):
    def test_render_runs_and_reports_health(self):
        upsert(self.conn, {"date": "2026-09-21", "training_day": 1,
                           "sleep_h": 7.0, "sleep_quality": 85, "bedtime": 1400,
                           "exercise_min": 30, "diet_kcal": 1800, "phone_h": 8.0,
                           "deepwork_h": 4.0, "learn_h": 1.0, "life_h": 1.0})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        text = doctor.render(self._run(today="2026-09-22"), encoding="utf-8")
        for token in ("DailyLumen 体检报告", "[数据库]", "[新鲜度]", "[历史断更]",
                      "[文件 <-> 数据库对账]", "[数据完整度]", "[打卡归一化]",
                      "[运动时长来源]", "[训练日口径]", "[打卡依从率]", "[体征]",
                      "结论:"):
            self.assertIn(token, text)


class TestBodyAdvisory(_Fixture):
    """体征段建议性：有/无记录都不影响 is_healthy。"""

    def test_body_section_empty_still_healthy_when_rest_ok(self):
        upsert(self.conn, {"date": "2026-09-21"})
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-21")
        self.assertEqual(r["body"]["count"], 0)
        self.assertTrue(doctor.is_healthy(r))
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("[体征]", text)
        self.assertIn("尚无体征记录", text)

    def test_body_spike_advisory_not_unhealthy(self):
        from review_tool.storage.db import upsert_body_metrics
        upsert(self.conn, {"date": "2026-09-21"})
        upsert_body_metrics(self.conn, {
            "date": "2026-09-14", "weight_kg": 70.0, "src": "manual",
        })
        upsert_body_metrics(self.conn, {
            "date": "2026-09-21", "weight_kg": 72.0, "src": "manual",
        })
        self.conn.commit()
        self._md("复盘/2026-09/2026-09-21.md")
        r = self._run(today="2026-09-21")
        self.assertTrue(r["body"]["spikes"])
        self.assertTrue(doctor.is_healthy(r))
        text = doctor.render(r, encoding="utf-8")
        self.assertIn("单周突变", text)


if __name__ == "__main__":
    unittest.main()
