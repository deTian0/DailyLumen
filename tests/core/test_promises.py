"""M29 承诺解析与对账：core.promises 纯规则 + reports.promises 判定。"""
from __future__ import annotations

import unittest

from review_tool.config import PROMISE_DECLINED_BUCKET
from review_tool.core.promises import (
    bucket_label,
    classify,
    clean_item,
    extract_constraints,
    has_section,
    is_declined,
    is_empty_marker,
    is_prompt_line,
    normalize,
    parse_items,
    parse_section,
    section_body,
)
from review_tool.reports.promises import (
    _bedtime_in_frame,
    judge,
    render,
)

DOC = """
## 二、今日三件事

- 这条不属于承诺区

## 三、一个改进点

> 如果今天只改一件事让明天更好，改什么？写不出就空着。

- 23:00 手机放客厅，23:30 关灯，避免番茄小说占用睡眠

## 四、明日 Top 3

> 明天最想推进的三件事，写就行，不强求完成。

1. 积极心理学 第03讲（固定时段看完，60min）
2. 《穷爸爸富爸爸》第6章（微信读书 30min+）
3. 午餐不点肥肠类主菜，脂肪目标 ≤70g；补剂从早上的 CoQ10 开始恢复勾
   - 这是子项，不算独立承诺

---

## 五、时间投入
"""


class TestParseSection(unittest.TestCase):
    def test_two_kinds(self):
        got = parse_section(DOC)
        self.assertEqual(set(got), {"improvement", "plan"})
        self.assertEqual(len(got["improvement"]), 1)
        self.assertEqual(len(got["plan"]), 3)

    def test_blockquote_prose_skipped(self):
        """引用块里的填写指引不是数据（模板每行指引都写在 `>` 里）。"""
        got = parse_section(DOC)
        for items in got.values():
            for it in items:
                self.assertNotIn("写不出就空着", it)
                self.assertNotIn("不强求完成", it)

    def test_indented_subitem_skipped(self):
        got = parse_section(DOC)
        self.assertFalse(any("这是子项" in it for it in got["plan"]))

    def test_missing_section_returns_none(self):
        self.assertIsNone(parse_section("## 一、日常打卡\n\n- 补剂\n"))

    def test_empty_section_is_empty_list(self):
        """章节在、内容空 → []；整段缺 → 该 kind 不出现。两种「空」语义不同。"""
        text = "## 三、一个改进点\n\n> 提示\n\n## 四、明日 Top 3\n\n1. 读书\n"
        got = parse_section(text)
        self.assertEqual(got["improvement"], [])
        self.assertEqual(len(got["plan"]), 1)

    def test_has_section(self):
        self.assertTrue(has_section(DOC, "improvement"))
        self.assertTrue(has_section(DOC, "plan"))
        self.assertFalse(has_section("## 三、一个改进点\n", "plan"))

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            section_body(DOC, "nope")

    def test_section_body_stops_at_next_heading(self):
        body = section_body(DOC, "plan")
        self.assertIn("积极心理学", body)
        self.assertNotIn("时间投入", body)


class TestPromptAndEmptyMarkers(unittest.TestCase):
    def test_prompt_lines(self):
        self.assertTrue(is_prompt_line("只写一个，越具体越好（动作 + 时间）。"))
        self.assertTrue(
            is_prompt_line("  只写一个，越具体越好（动作+时间）。 ")
        )
        self.assertFalse(is_prompt_line("只写一个改进点：早睡"))

    def test_empty_markers(self):
        for raw in ("空", "（空）", "无", "忘记了", "想不到", "（未填写）"):
            self.assertTrue(is_empty_marker(raw), raw)
        # 全等匹配，不做子串
        self.assertFalse(is_empty_marker("无糖酸奶"))
        self.assertFalse(is_empty_marker("空心病"))

    def test_clean_item_rejects_prompt_and_marker(self):
        self.assertIsNone(clean_item("- 空"))
        self.assertIsNone(clean_item("- 只写一个，越具体越好（动作 + 时间）。"))
        self.assertEqual(clean_item("- 早点睡"), "早点睡")

    def test_clean_item_rejects_table_and_rule(self):
        self.assertIsNone(clean_item("| 列 | 列 |"))
        self.assertIsNone(clean_item("---"))
        self.assertIsNone(clean_item("  "))

    def test_parse_items_dedup_keeps_order(self):
        items = parse_items("- 早点睡\n- 读书\n- 早点睡\n")
        self.assertEqual(items, ["早点睡", "读书"])


class TestDeclined(unittest.TestCase):
    """v1.37.0 / D1：`今天不设` 是**决定**，不是空转，也不是承诺。"""

    def test_is_declined(self):
        for raw in ("今天不设", " 今日不设 ", "不设", "今天跳过", "无改进点"):
            self.assertTrue(is_declined(raw), raw)

    def test_declined_is_not_empty_marker(self):
        # 两者方向相反：一个是没做决定，一个是做了决定
        self.assertFalse(is_empty_marker("今天不设"))
        self.assertFalse(is_declined("空"))
        self.assertFalse(is_declined("忘记了"))

    def test_declined_survives_clean_item(self):
        """关键：放弃标记不能被 `clean_item` 当空行丢掉，否则等于没写。"""
        self.assertEqual(clean_item("- 今天不设"), "今天不设")

    def test_full_equality_only(self):
        # 「不设上限地推进」是真实承诺，不能被误判成放弃
        self.assertFalse(is_declined("不设上限地推进 migration"))
        self.assertIsNone(classify("不设上限地推进 migration"))

    def test_classify_returns_declined_bucket(self):
        self.assertEqual(classify("今天不设"), PROMISE_DECLINED_BUCKET)
        self.assertEqual(bucket_label(PROMISE_DECLINED_BUCKET), "明写不设")

    def test_parse_section_keeps_declined(self):
        text = "## 三、一个改进点\n\n- 今天不设\n\n## 四、明日 Top 3\n\n1. 读书 30min\n"
        r = parse_section(text)
        self.assertEqual(r["improvement"], ["今天不设"])
        self.assertEqual(r["plan"], ["读书 30min"])

    def test_judge_declined_is_not_no_data(self):
        """次日没写复盘时，`今天不设` 仍应判 declined —— 它是当天的决定。"""
        status, _ = judge(
            {"bucket": PROMISE_DECLINED_BUCKET, "text": "今天不设"}, None, [], []
        )
        self.assertEqual(status, "declined")


class TestConstraints(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(extract_constraints("看完 60min")["minutes"], 60.0)
        self.assertEqual(extract_constraints("练 90 分钟")["minutes"], 90.0)

    def test_hour_converted_to_minutes(self):
        self.assertEqual(extract_constraints("深度工作保持 5h")["minutes"], 300.0)

    def test_clock(self):
        self.assertEqual(extract_constraints("22:30 手机离手")["clock"], 1350)

    def test_clock_prefers_before_marker(self):
        """句首是「昨天几点睡的」描述，目标写在「22:30 前」——必须取后者。"""
        text = "00:43 才入睡（较昨天 22:28 晚）——今晚 22:30 前把手机放客厅"
        self.assertEqual(extract_constraints(text)["clock"], 1350)

    def test_limit_g(self):
        got = extract_constraints("脂肪目标 ≤70g")
        self.assertEqual(got["limit"], {"op": "lte", "value": 70.0, "unit": "g"})

    def test_limit_kcal(self):
        got = extract_constraints("热量不超过 1800 大卡")
        self.assertEqual(got["limit"]["unit"], "kcal")
        self.assertEqual(got["limit"]["value"], 1800.0)

    def test_limit_h_does_not_become_minutes(self):
        """「≤1h」是上限，不是目标时长 —— 两者不能串。"""
        got = extract_constraints("控制番茄小说 ≤1h")
        self.assertEqual(got["limit"], {"op": "lte", "value": 1.0, "unit": "h"})
        self.assertNotIn("minutes", got)

    def test_nothing_found(self):
        self.assertEqual(extract_constraints("刷鞋"), {})


class TestClassify(unittest.TestCase):
    def test_position_wins_over_bucket_order(self):
        """「午餐…；补剂 CoQ10」主体是吃饭 —— 位置在前的关键词胜出。"""
        text = "午餐不点肥肠类主菜，脂肪目标 ≤70g；补剂从早上的 CoQ10 开始恢复勾"
        self.assertEqual(classify(text), "diet")

    def test_longer_keyword_wins_on_tie(self):
        """「手机放客厅」和「手机」同位置，取更长的 → 睡眠桶。"""
        self.assertEqual(classify("23:00 手机放客厅，23:30 关灯"), "sleep")

    def test_buckets(self):
        cases = {
            "积极心理学 第03讲（60min）": "learn",
            "周三训练日 19:30 提醒 Keep": "exercise",
            "补剂从 CoQ10 恢复": "supplement",
            "深度工作保持 5h": "work",
            "控制番茄小说 ≤1h": "phone",
        }
        for text, want in cases.items():
            self.assertEqual(classify(text), want, text)

    def test_unclassified(self):
        self.assertIsNone(classify("刷鞋"))
        self.assertIsNone(classify(""))

    def test_normalize_is_stable(self):
        self.assertEqual(normalize("只写一个，越具体越好（动作 + 时间）。"),
                         normalize(" 只写一个越具体越好动作时间 "))


def _day(**kw):
    base = {
        "date": "2026-10-21",
        "learn_h": None,
        "exercise_min": None,
        "deepwork_h": None,
        "phone_h": None,
        "bedtime": None,
        "diet_kcal": None,
        "fat_g": None,
        "carbs_g": None,
        "protein_g": None,
    }
    base.update(kw)
    return base


def _item(text, bucket):
    return {"text": text, "bucket": bucket, "date": "2026-10-20", "kind": "plan"}


class TestJudge(unittest.TestCase):
    def test_no_next_day(self):
        status, _ = judge(_item("读书", "learn"), None, [], [])
        self.assertEqual(status, "no_data")

    def test_unclassified(self):
        status, _ = judge(_item("刷鞋", None), _day(), [], [])
        self.assertEqual(status, "unmapped")

    def test_learn_with_target(self):
        item = _item("积极心理学 60min", "learn")
        self.assertEqual(judge(item, _day(learn_h=1.0), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(learn_h=0.5), [], [])[0], "missed")

    def test_learn_without_target(self):
        item = _item("阅读", "learn")
        self.assertEqual(judge(item, _day(learn_h=0.5), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(learn_h=0), [], [])[0], "missed")

    def test_learn_uses_learning_logs(self):
        item = _item("阅读", "learn")
        logs = [{"topic": "阅读", "minutes": 30}]
        self.assertEqual(judge(item, _day(learn_h=0), [], logs)[0], "fulfilled")

    def test_exercise(self):
        item = _item("训练 20min", "exercise")
        self.assertEqual(judge(item, _day(exercise_min=30), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(exercise_min=0), [], [])[0], "missed")

    def test_diet_limit(self):
        item = _item("脂肪目标 ≤70g", "diet")
        self.assertEqual(judge(item, _day(fat_g=60), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(fat_g=113), [], [])[0], "missed")

    def test_diet_without_limit_unmapped(self):
        item = _item("少吃点油", "diet")
        self.assertEqual(judge(item, _day(fat_g=60), [], [])[0], "unmapped")

    def test_diet_missing_field_unmapped(self):
        item = _item("脂肪目标 ≤70g", "diet")
        self.assertEqual(judge(item, _day(), [], [])[0], "unmapped")

    def test_sleep_late_is_missed(self):
        item = _item("23:30 前关灯", "sleep")
        self.assertEqual(judge(item, _day(bedtime=1410), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(bedtime=1439), [], [])[0], "missed")

    def test_sleep_after_midnight_is_missed(self):
        item = _item("23:30 前关灯", "sleep")
        self.assertEqual(judge(item, _day(bedtime=89), [], [])[0], "missed")

    def test_sleep_target_after_midnight(self):
        """目标 00:30、实际 23:20 → 提前了，应判兑现（不能被 +1440 绕晕）。"""
        item = _item("00:30 前睡", "sleep")
        self.assertEqual(judge(item, _day(bedtime=1400), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(bedtime=89), [], [])[0], "missed")

    def test_phone_limit(self):
        item = _item("屏幕 ≤3h", "phone")
        self.assertEqual(judge(item, _day(phone_h=2.5), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(phone_h=4.0), [], [])[0], "missed")

    def test_phone_without_limit_unmapped(self):
        item = _item("少刷手机", "phone")
        self.assertEqual(judge(item, _day(phone_h=2.5), [], [])[0], "unmapped")

    def test_work_without_target_unmapped(self):
        """「修复 migration」不能用 deepwork_h>0 判 —— 那只证明那天上过班。"""
        item = _item("migration 文件夹彻底修复", "work")
        self.assertEqual(judge(item, _day(deepwork_h=6), [], [])[0], "unmapped")

    def test_work_with_target(self):
        item = _item("深度工作保持 5h", "work")
        self.assertEqual(judge(item, _day(deepwork_h=6), [], [])[0], "fulfilled")
        self.assertEqual(judge(item, _day(deepwork_h=3), [], [])[0], "missed")

    def test_supplement(self):
        item = _item("补剂从 CoQ10 恢复勾", "supplement")
        tracks = [{"item": "CoQ10 ×1", "item_key": "coq10", "done": 1}]
        self.assertEqual(judge(item, _day(), tracks, [])[0], "fulfilled")
        tracks[0]["done"] = 0
        self.assertEqual(judge(item, _day(), tracks, [])[0], "missed")

    def test_supplement_no_matching_track(self):
        item = _item("补剂记得吃", "supplement")
        self.assertEqual(judge(item, _day(), [], [])[0], "unmapped")


class TestBedtimeFrame(unittest.TestCase):
    def test_evening_target(self):
        self.assertEqual(_bedtime_in_frame(1420, 1380), 1420)
        self.assertEqual(_bedtime_in_frame(89, 1380), 1529)

    def test_after_midnight_target(self):
        self.assertEqual(_bedtime_in_frame(1400, 30), -40)
        self.assertEqual(_bedtime_in_frame(89, 30), 89)


class TestRender(unittest.TestCase):
    def test_empty(self):
        out = render({
            "start": None, "end": None, "date_from": None, "date_to": None,
            "days": 0, "total": 0, "counts": {}, "judged": 0, "rate": None,
            "by_bucket": [], "by_kind": [], "items": [],
        })
        self.assertIn("没有承诺记录", out)

    def test_lists_rate_and_caveats(self):
        out = render({
            "start": None, "end": None,
            "date_from": "2026-08-05", "date_to": "2026-10-20",
            "days": 41, "total": 10,
            "counts": {"fulfilled": 3, "missed": 2, "unmapped": 4, "no_data": 1},
            "judged": 5, "rate": 0.6,
            "by_bucket": [{"bucket": "learn", "label": "学习", "total": 10,
                           "fulfilled": 3, "missed": 2, "unmapped": 4,
                           "no_data": 1, "judged": 5, "rate": 0.6}],
            "by_kind": [{"kind": "plan", "label": "明日 Top 3", "total": 10,
                         "fulfilled": 3, "missed": 2, "unmapped": 4,
                         "no_data": 1, "judged": 5, "rate": 0.6}],
            "items": [],
        })
        self.assertIn("60%", out)
        self.assertIn("不算没做到", out)


if __name__ == "__main__":
    unittest.main()
