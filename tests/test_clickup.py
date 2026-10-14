"""ClickUp 素材管道测试：归日口径、翻页去重、凭据优先级、渲染契约、CLI。

**全部离线** —— 网络层用注入的假 fetch 顶替，测试不碰 api.clickup.com。

锁死三条口径：
1. 按 ``date_closed`` 归日，**不是** ``due_date``（否则「今天做完的昨天到期任务」算到昨天）；
2. 素材里**不得出现** ``- [x]`` / ``- [ ]`` 勾选语法 —— ClickUp 习惯与复盘 md
   「一、日常打卡」的补剂 / 护肤是两套体系，格式上必须一眼可分；
3. 缺凭据 / 取数失败要给可读报错 + 明确退出码，不抛裸异常、不写坏文件。
"""
import contextlib
import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from review_tool.pipeline import clickup as cu

TZ = datetime.timezone(datetime.timedelta(hours=8))
DAY = "2026-10-14"


def _ms(iso: str) -> str:
    """东八区 ISO 时刻 -> ClickUp 用的 UTC 毫秒字符串。"""
    dt = datetime.datetime.fromisoformat(iso).replace(tzinfo=TZ)
    return str(int(dt.timestamp() * 1000))


def _task(tid, name, *, closed=None, due=None, status="complete",
          status_type=None, created=None):
    st = {"status": status}
    if status_type is not None:
        st["type"] = status_type
    return {
        "id": tid,
        "name": name,
        "date_closed": _ms(closed) if closed else None,
        "due_date": _ms(due) if due else None,
        "date_created": _ms(created) if created else None,
        "status": st,
    }


class _FakeAPI:
    """按 list id 返回固定任务；记录请求过的 path 供断言。"""

    def __init__(self, by_list=None, pages=None):
        self.by_list = by_list or {}
        self.pages = pages
        self.paths: list[str] = []

    def __call__(self, path, key, *, timeout=None):
        self.paths.append(path)
        if self.pages is not None:
            page = int(path.rsplit("page=", 1)[1])
            return {"tasks": self.pages[page] if page < len(self.pages) else []}
        for lid, tasks in self.by_list.items():
            if f"/list/{lid}/task" in path:
                return {"tasks": tasks}
        return {"tasks": []}


def _capture(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


# ------------------------------------------------------------------ 时间 / 归日
class TestTimeBucket(unittest.TestCase):
    def test_day_of_is_utc8(self):
        self.assertEqual(cu.day_of(_ms("2026-10-14T23:30")), DAY)
        self.assertEqual(cu.day_of(_ms("2026-10-15T00:10")), "2026-10-15")

    def test_day_of_accepts_int_and_str(self):
        ms = _ms("2026-10-14T09:00")
        self.assertEqual(cu.day_of(int(ms)), DAY)
        self.assertEqual(cu.day_of(ms), DAY)

    def test_clock_of(self):
        self.assertEqual(cu.clock_of(_ms("2026-10-14T21:32")), "21:32")
        self.assertEqual(cu.clock_of(_ms("2026-10-14T07:05")), "07:05")


class TestSelect(unittest.TestCase):
    def setUp(self):
        self.tasks = [
            _task("a", "昨天到期今天做完", closed="2026-10-14T21:32", due="2026-10-13T09:00"),
            _task("b", "今天到期没做", due="2026-10-14T09:00", status="to do"),
            _task("c", "今天做完的第二个", closed="2026-10-14T08:10"),
            _task("d", "明天才做完", closed="2026-10-15T00:10"),
        ]

    def test_completed_uses_date_closed_not_due_date(self):
        """核心口径：完成日看 date_closed —— 「昨天到期今天做完」必须算今天。"""
        names = [t["name"] for t in cu.select_completed(self.tasks, DAY)]
        self.assertIn("昨天到期今天做完", names)
        self.assertNotIn("明天才做完", names)
        self.assertNotIn("今天到期没做", names)

    def test_completed_sorted_by_clock(self):
        got = [cu.clock_of(t["date_closed"]) for t in cu.select_completed(self.tasks, DAY)]
        self.assertEqual(got, ["08:10", "21:32"])

    def test_due_open_only_open_items_due_that_day(self):
        names = [t["name"] for t in cu.select_due_open(self.tasks, DAY)]
        self.assertEqual(names, ["今天到期没做"])

    def test_empty_inputs_are_safe(self):
        self.assertEqual(cu.select_completed([], DAY), [])
        self.assertEqual(cu.select_due_open([], DAY), [])


class TestSelectEnhanced(unittest.TestCase):
    """进行中 / 逾期 / 跨天未闭合（v1.8.1）。"""

    def setUp(self):
        self.tasks = [
            _task("ip", "写周报", status="进行中", status_type="custom"),
            _task("od", "上周就该交", due="2026-10-10T09:00", status="to do",
                  status_type="open"),
            _task("xd", "前天开的还挂着", created="2026-10-12T08:00",
                  status="to do", status_type="open"),
            _task("done", "已完成不该进", closed="2026-10-14T10:00"),
            _task("today_due", "今天到期未做", due="2026-10-14T09:00",
                  status="to do", status_type="open"),
        ]

    def test_in_progress(self):
        names = [t["name"] for t in cu.select_in_progress(self.tasks, DAY)]
        self.assertEqual(names, ["写周报"])

    def test_overdue(self):
        names = [t["name"] for t in cu.select_overdue(self.tasks, DAY)]
        self.assertEqual(names, ["上周就该交"])

    def test_cross_day_open(self):
        names = [t["name"] for t in cu.select_cross_day_open(self.tasks, DAY)]
        self.assertEqual(names, ["前天开的还挂着"])

    def test_render_includes_new_sections(self):
        groups = [{
            "id": "L", "name": "日常事务", "role": "",
            "done": [], "open": [],
            "in_progress": [self.tasks[0]],
            "overdue": [self.tasks[1]],
            "cross_day": [self.tasks[2]],
        }]
        text = cu.render(DAY, groups, generated_at="T")
        self.assertIn("进行中", text)
        self.assertIn("逾期", text)
        self.assertIn("跨天未闭合", text)
        self.assertIn("写周报", text)
        self.assertNotIn("- [x]", text)


# --------------------------------------------------------------- 取数 / 翻页去重
class TestFetch(unittest.TestCase):
    def test_includes_closed_and_subtasks_flags(self):
        """少 include_closed=true 会漏掉全部已完成任务 —— 把这条钉死。"""
        api = _FakeAPI({"L1": []})
        cu.fetch_tasks("L1", "k", fetch=api)
        self.assertIn("include_closed=true", api.paths[0])
        self.assertIn("subtasks=true", api.paths[0])

    def test_dedupes_repeated_ids(self):
        """subtasks=true 翻页会重复返回同一条 —— 按 id 去重。"""
        one = _task("same", "重复项", closed="2026-10-14T10:00")
        api = _FakeAPI({"L1": [one, dict(one)]})
        self.assertEqual(len(cu.fetch_tasks("L1", "k", fetch=api)), 1)

    def test_pages_until_short_page(self):
        """单页上限 100：只取第 0 页会静默漏数据（本仓库某 list 有 121 条）。"""
        page0 = [_task(f"p0-{i}", f"任务{i}") for i in range(cu.PAGE_SIZE)]
        page1 = [_task(f"p1-{i}", f"任务{i}") for i in range(5)]
        api = _FakeAPI(pages=[page0, page1])
        got = cu.fetch_tasks("L1", "k", fetch=api)
        self.assertEqual(len(got), cu.PAGE_SIZE + 5)
        self.assertEqual(len(api.paths), 2)


# ------------------------------------------------------------------------ 凭据
class TestCreds(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "mcp.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, payload):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_env_wins_over_file(self):
        self._write({"mcpServers": {"clickup": {"env": {"CLICKUP_API_KEY": "pk_file"}}}})
        key, team = cu.load_creds(env={"CLICKUP_API_KEY": "pk_env", "CLICKUP_TEAM_ID": "9"},
                                   path=self.path)
        self.assertEqual((key, team), ("pk_env", "9"))

    def test_reads_mcp_json(self):
        self._write({"mcpServers": {"clickup": {"env": {
            "CLICKUP_API_KEY": "pk_file", "CLICKUP_TEAM_ID": "123"}}}})
        self.assertEqual(cu.load_creds(env={}, path=self.path), ("pk_file", "123"))

    def test_team_optional(self):
        self._write({"mcpServers": {"clickup": {"env": {"CLICKUP_API_KEY": "pk_file"}}}})
        self.assertEqual(cu.load_creds(env={}, path=self.path), ("pk_file", None))

    def test_missing_file_raises_cred_error(self):
        with self.assertRaises(cu.CredError):
            cu.load_creds(env={}, path=os.path.join(self.dir, "nope.json"))

    def test_missing_key_raises_cred_error(self):
        self._write({"mcpServers": {"clickup": {"env": {}}}})
        with self.assertRaises(cu.CredError):
            cu.load_creds(env={}, path=self.path)

    def test_broken_json_raises_cred_error(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{不是 json")
        with self.assertRaises(cu.CredError):
            cu.load_creds(env={}, path=self.path)


# ------------------------------------------------------------------ 汇总与渲染
class TestCollectRender(unittest.TestCase):
    def setUp(self):
        self.api = _FakeAPI({
            "L1": [_task("a", "整理日报", closed="2026-10-14T21:32"),
                   _task("b", "明天再做", closed="2026-10-15T09:00")],
            "L2": [_task("c", "每日阅读", closed="2026-10-14T23:04", status="in progress")],
        })
        self.meta = {"L1": {"name": "日常事务", "role": "行为流水"},
                     "L2": {"name": "习惯与打卡", "role": "长期习惯"}}
        self.groups = cu.collect(DAY, ["L1", "L2"], key="k", fetch=self.api, meta=self.meta)
        self.text = cu.render(DAY, self.groups, generated_at="2026-10-14 23:30",
                              workspace="9014643172")

    def test_collect_groups_in_given_order(self):
        self.assertEqual([g["name"] for g in self.groups], ["日常事务", "习惯与打卡"])
        self.assertEqual(len(self.groups[0]["done"]), 1)
        self.assertEqual(self.groups[1]["done"][0]["name"], "每日阅读")

    def test_render_header_and_source(self):
        self.assertIn("# ClickUp 素材 · 2026-10-14（星期三）", self.text)
        self.assertIn("生成时间：2026-10-14 23:30", self.text)
        self.assertIn("9014643172", self.text)

    def test_render_declares_it_is_material_not_scored(self):
        """素材必须自带声明：不参与评分、不落库、习惯不许混进打卡节。"""
        self.assertIn("素材", self.text)
        self.assertIn("不参与四维评分", self.text)
        self.assertIn("不得", self.text)
        self.assertIn("date_closed", self.text)

    def test_render_has_no_checkbox_syntax(self):
        """⛔ 两套打卡体系不许混：素材里不能出现能被误读成打卡的勾选语法。"""
        self.assertNotIn("- [x]", self.text)
        self.assertNotIn("- [ ]", self.text)
        self.assertNotIn("- [X]", self.text)

    def test_render_lists_names_and_clock(self):
        self.assertIn("整理日报（完成 21:32）", self.text)
        self.assertIn("每日阅读（完成 23:04 · in progress）", self.text)

    def test_render_summary_table_counts(self):
        self.assertIn("| 分组 | 当日完成 | 到期未完成 | 进行中 | 逾期 | 跨天未闭合 |",
                      self.text)
        self.assertIn("| 日常事务 | 1 | 0 |", self.text)
        self.assertIn("**当日完成合计**：2 条", self.text)

    def test_render_zero_done_is_explicit(self):
        empty = cu.collect(DAY, ["L1"], key="k", fetch=_FakeAPI({}), meta=self.meta)
        text = cu.render(DAY, empty, generated_at="x")
        self.assertIn("当日完成 0 条", text)

    def test_render_carries_no_secret(self):
        self.assertNotIn("pk_", self.text)


class TestBulkHint(unittest.TestCase):
    """批量改状态会让某天凭空多出上百条同时刻完成 —— 素材必须带提示防误读。"""

    def _groups(self, n, clock="11:18"):
        tasks = [_task(f"x{i}", f"任务{i}", closed=f"2026-10-13T{clock}") for i in range(n)]
        return [{"id": "L1", "name": "日常事务", "role": "", "done": tasks, "open": []}]

    def test_hint_appears_when_many_share_one_minute(self):
        text = cu.render("2026-10-13", self._groups(12), generated_at="T")
        self.assertIn("批量改状态", text)
        self.assertIn("11:18", text)

    def test_no_hint_below_threshold(self):
        text = cu.render("2026-10-13", self._groups(cu.BULK_HINT_MIN - 1), generated_at="T")
        self.assertNotIn("批量改状态", text)

    def test_no_hint_on_empty(self):
        text = cu.render("2026-10-13", self._groups(0), generated_at="T")
        self.assertNotIn("批量改状态", text)

    def test_spread_out_clocks_do_not_trigger(self):
        tasks = [_task(f"y{i}", f"任务{i}", closed=f"2026-10-13T{8 + i % 12:02d}:{i % 60:02d}")
                 for i in range(20)]
        groups = [{"id": "L1", "name": "L", "role": "", "done": tasks, "open": []}]
        self.assertIsNone(cu.bulk_hint(groups))


# -------------------------------------------------------------------------- CLI
class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = {"CLICKUP_API_KEY": "pk_test", "CLICKUP_TEAM_ID": "9014643172"}
        self.api = _FakeAPI({
            "901422213138": [_task("a", "整理日报", closed="2026-10-14T21:32")],
            "901422213139": [],
        })
        self._patch = mock.patch.object(cu, "CLICKUP_MCP_PATH",
                                        os.path.join(self.dir, "absent.json"))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_help_does_not_fetch(self):
        api = _FakeAPI({})
        rc, out, _ = _capture(cu.main, ["-h"], fetch=api, env=self.env)
        self.assertEqual(rc, 0)
        self.assertIn("用法", out)
        self.assertEqual(api.paths, [])

    def test_stdout_does_not_write_file(self):
        rc, out, _ = _capture(cu.main, [DAY, "--stdout", "--out", self.dir],
                              fetch=self.api, env=self.env, now=lambda: "T")
        self.assertEqual(rc, 0)
        self.assertIn("# ClickUp 素材 · 2026-10-14", out)
        self.assertEqual([f for f in os.listdir(self.dir) if f.endswith(".md")], [])

    def test_writes_material_into_out_dir_with_lf(self):
        rc, out, _ = _capture(cu.main, [DAY, "--out", self.dir],
                              fetch=self.api, env=self.env, now=lambda: "T")
        self.assertEqual(rc, 0)
        path = os.path.join(self.dir, f"{cu.CLICKUP_INBOX_PREFIX}-{DAY}.md")
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r\n", raw, "素材文件必须是 LF（项目 .gitattributes 要求 eol=lf）")
        self.assertIn("整理日报".encode(), raw)

    def test_default_out_is_inbox(self):
        self.assertEqual(cu._parse([])[1], cu.INBOX_DIR)

    def test_list_filter(self):
        api = _FakeAPI({"901422213139": [_task("c", "每日阅读", closed="2026-10-14T23:04")]})
        rc, out, _ = _capture(cu.main, [DAY, "--stdout", "--list", "901422213139"],
                              fetch=api, env=self.env)
        self.assertEqual(rc, 0)
        self.assertIn("每日阅读", out)
        self.assertNotIn("901422213138", "".join(api.paths))

    def test_bad_date_is_usage_error(self):
        rc, _, err = _capture(cu.main, ["2026/10/14"], fetch=self.api, env=self.env)
        self.assertEqual(rc, 2)
        self.assertIn("参数错误", err)

    def test_extra_positional_rejected(self):
        rc, _, err = _capture(cu.main, [DAY, "2026-10-15"], fetch=self.api, env=self.env)
        self.assertEqual(rc, 2)
        self.assertIn("参数错误", err)

    def test_unknown_flag_rejected(self):
        rc, _, err = _capture(cu.main, ["--nope"], fetch=self.api, env=self.env)
        self.assertEqual(rc, 2)
        self.assertIn("未知参数", err)

    def test_missing_creds_is_usage_error(self):
        rc, _, err = _capture(cu.main, [DAY], fetch=self.api, env={})
        self.assertEqual(rc, 2)
        self.assertIn("凭据错误", err)

    def test_http_401_gives_actionable_hint(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.HTTPError("u", 401, "Unauthorized", None, None)

        rc, _, err = _capture(cu.main, [DAY, "--stdout"], fetch=boom, env=self.env)
        self.assertEqual(rc, 1)
        self.assertIn("401", err)
        self.assertIn("token", err)

    def test_network_error_is_runtime_error(self):
        def boom(path, key, *, timeout=None):
            raise urllib.error.URLError("no route")

        rc, _, err = _capture(cu.main, [DAY, "--stdout"], fetch=boom, env=self.env)
        self.assertEqual(rc, 1)
        self.assertIn("网络不可达", err)

    def test_env_key_is_never_printed(self):
        rc, out, err = _capture(cu.main, [DAY, "--stdout"], fetch=self.api, env=self.env)
        self.assertEqual(rc, 0)
        self.assertNotIn("pk_test", out + err)


if __name__ == "__main__":
    unittest.main()
