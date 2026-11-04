"""M37 improve-draft：骨架字段 / stdout 零写盘 / --out 草稿 / 不进 ingest。"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from review_tool.reports import improve_draft
from review_tool.storage.db import init_db, upsert


def _seed(db: str, day: str = "2026-11-03") -> None:
    conn = init_db(db)
    upsert(conn, {
        "date": day, "weekday": "星期二",
        "sleep_h": 6.0, "sleep_quality": 70, "bedtime": 30,
        "phone_h": 8.0, "exercise_min": 0, "training_day": 1,
        "diet_kcal": 1400, "deepwork_h": 1.0, "learn_h": 0.5, "life_h": 1.0,
        "health_score": 3, "work_score": 4, "learn_score": 4, "life_score": 5,
        "system_score": 4.0,
    })
    conn.commit()
    conn.close()


class TestBuildSkeleton(unittest.TestCase):
    def test_required_fields_in_empty_slots(self):
        text = improve_draft.build_skeleton(
            "2026-11-03", generated_at="x", context_md="# ctx\nflag")
        self.assertIn("改进点候选（2026-11-03）", text)
        self.assertIn("不入库", text)
        self.assertIn("life-decision-guide", text)
        for key in improve_draft.CANDIDATE_FIELDS:
            self.assertIn(key, text)
        self.assertIn("证据等级", text)
        self.assertIn("书条目", text)

    def test_filled_candidates(self):
        cands = [{
            "事项": "抖音限时",
            "钱": "少", "时间": "少", "毅力": "些",
            "收益": "中", "证据等级": "B",
            "书条目": "第2节第3条",
        }]
        text = improve_draft.build_skeleton(
            "2026-11-03", generated_at="x", context_md="ctx",
            candidates=cands)
        self.assertIn("抖音限时", text)
        self.assertIn("第2节第3条", text)
        self.assertIn("证据等级：B", text)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        _seed(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stdout_no_write(self):
        before = set(os.listdir(self.tmp))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = improve_draft.main(
                ["--date", "2026-11-03", "--stdout", "--db", self.db])
        self.assertEqual(rc, 0)
        self.assertIn("改进点候选", buf.getvalue())
        self.assertEqual(set(os.listdir(self.tmp)), before)

    def test_out_writes_skeleton(self):
        out_dir = os.path.join(self.tmp, "inbox")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = improve_draft.main(
                ["--date", "2026-11-03", "--out", out_dir, "--db", self.db])
        self.assertEqual(rc, 0)
        path = os.path.join(out_dir, "改进点候选-2026-11-03.md")
        self.assertTrue(os.path.isfile(path))
        body = open(path, encoding="utf-8").read()
        self.assertIn("不入库", body)
        self.assertIn("书条目", body)
        self.assertIn("三、一个改进点", body)

    def test_bad_args_rc_2(self):
        rc = improve_draft.main(["--date", "bad"])
        self.assertEqual(rc, 2)

    def test_route_registered(self):
        from review_tool.__main__ import ROUTES
        self.assertIn("improve-draft", ROUTES)

    def test_prefix_not_ingested(self):
        from review_tool.pipeline.ingest import iter_markdown
        inbox = os.path.join(self.tmp, "收件箱")
        review = os.path.join(self.tmp, "复盘", "2026-11")
        os.makedirs(inbox)
        os.makedirs(review)
        draft = os.path.join(inbox, "改进点候选-2026-11-03.md")
        real = os.path.join(review, "2026-11-03.md")
        with open(draft, "w", encoding="utf-8", newline="\n") as f:
            f.write("# draft\n")
        with open(real, "w", encoding="utf-8", newline="\n") as f:
            f.write("# real\n")
        names = [os.path.basename(p) for p in iter_markdown(self.tmp)]
        self.assertIn("2026-11-03.md", names)
        self.assertNotIn("改进点候选-2026-11-03.md", names)


class TestPrefixesDistinct(unittest.TestCase):
    def test_not_collide_with_siblings(self):
        from review_tool.pipeline import promise_draft, three_things_draft
        prefs = {
            promise_draft.INBOX_PREFIX,
            three_things_draft.INBOX_PREFIX,
            improve_draft.INBOX_PREFIX,
        }
        self.assertEqual(len(prefs), 3)


if __name__ == "__main__":
    unittest.main()
