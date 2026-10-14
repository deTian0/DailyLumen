"""ClickUp → 复盘素材简报（只读管道，v1.6.0）。

用法:
    python -m review_tool clickup                    # 取今天的，落 收件箱/
    python -m review_tool clickup 2026-10-14         # 取指定日期
    python -m review_tool clickup 2026-10-14 --stdout   # 只打印，不落文件
    python -m review_tool clickup --out DIR          # 换输出目录
    python -m review_tool clickup --list 901422213142   # 只取指定 list（可重复）

三条边界（改本模块前先看）
--------------------------
1. **只读**。只 GET ClickUp 任务：不回写 ClickUp、**不读进 reviews.db**、不参与四维评分。
   四维分只由 ``config.SCORE_THRESHOLDS`` + 复盘 md 的数据块决定。
2. **日期看 ``date_closed``**。「某天完成了什么」按**实际完成时刻**（东八区）归日，
   不看 ``due_date``（那是计划日）—— 否则「今天做完的昨天到期任务」会被算到昨天。
3. **两套打卡体系不许混**。ClickUp「习惯与打卡」的勾选是**行为习惯**，与复盘 md
   「一、日常打卡」的补剂 / 护肤（``config.PERSONAL_ITEMS``）不是一回事。
   本模块产出的素材**故意不使用 ``- [x]`` 勾选语法**，从格式上杜绝被误读成打卡。

产出的是一份**素材**（不是复盘成品），默认落 ``每日复盘/收件箱/``（该目录不参与
ingest 扫描，所以不会被当成待入库的复盘自动吃进去）。

退出码：0 = 成功；1 = 取数失败（网络 / 认证）；2 = 用法错误或凭据缺失。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

from ..config import (
    CLICKUP_DAILY_IDS,
    CLICKUP_INBOX_PREFIX,
    CLICKUP_LIST_META,
    CLICKUP_MCP_PATH,
    CLICKUP_TZ_HOURS,
    INBOX_DIR,
    WEEKDAY_CN,
)

API_BASE = "https://api.clickup.com/api/v2"

# ClickUp list 任务接口单页上限 100 —— 超过就必须翻页，否则静默少拿
# （本仓库「日常事务」有 121 条，不翻页会整批漏掉 21 条）
PAGE_SIZE = 100
MAX_PAGES = 20

# 同一分钟内这么多条「完成」= 多半是批量改状态（迁移 / 整批关闭），不是逐条做完
# （实例：2026-10-13 有 114 条集中在 11:17–11:18 关闭）。素材里要出提示，防误读。
BULK_HINT_MIN = 10


class CredError(RuntimeError):
    """凭据缺失 / 不可读 —— 给可读提示，而不是抛裸 KeyError。"""


# --------------------------------------------------------------------- 时间
def _tz(tz_hours: int | None = None) -> datetime.timezone:
    return datetime.timezone(
        datetime.timedelta(hours=CLICKUP_TZ_HOURS if tz_hours is None else tz_hours))


def day_of(ms, *, tz_hours: int | None = None) -> str:
    """ClickUp 的 UTC 毫秒时间戳 -> 东八区 ``YYYY-MM-DD``。"""
    return datetime.datetime.fromtimestamp(int(ms) / 1000, _tz(tz_hours)).strftime("%Y-%m-%d")


def clock_of(ms, *, tz_hours: int | None = None) -> str:
    """同 ``day_of``，但输出 ``HH:MM``（素材里标完成时刻用）。"""
    return datetime.datetime.fromtimestamp(int(ms) / 1000, _tz(tz_hours)).strftime("%H:%M")


# ----------------------------------------------------------------- 凭据 / 网络
def load_creds(env=None, path: str | None = None) -> tuple[str, str | None]:
    """解析 ClickUp 凭据：环境变量优先，其次 ``~/.workbuddy/mcp.json``。

    返回 ``(api_key, team_id)``；``team_id`` 允许为 None（仅用于展示）。
    两处都没有 -> :class:`CredError`。
    """
    env = os.environ if env is None else env
    key = (env.get("CLICKUP_API_KEY") or "").strip()
    team = (env.get("CLICKUP_TEAM_ID") or "").strip() or None
    if key:
        return key, team

    p = CLICKUP_MCP_PATH if path is None else path
    try:
        with open(p, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise CredError(
            f"找不到 ClickUp 凭据：{p} 不存在，也没设环境变量 CLICKUP_API_KEY。\n"
            "  → 设 CLICKUP_API_KEY（+ CLICKUP_TEAM_ID），或把 MCP 配置写到该路径的 "
            "mcpServers.clickup.env 下。") from None
    except (OSError, ValueError) as e:
        raise CredError(f"读不了 ClickUp 凭据文件 {p}：{type(e).__name__}: {e}") from e

    block = (cfg.get("mcpServers", {}) or {}).get("clickup", {}) or {}
    block = block.get("env", {}) or {}
    key = (block.get("CLICKUP_API_KEY") or "").strip()
    team = (block.get("CLICKUP_TEAM_ID") or "").strip() or None
    if not key:
        raise CredError(
            f"{p} 里没有 mcpServers.clickup.env.CLICKUP_API_KEY。\n"
            "  → 补上该配置，或改用环境变量 CLICKUP_API_KEY。")
    return key, team


def http_get(path: str, key: str, *, timeout: int = 60) -> dict:
    """GET 一个 ClickUp API 路径，返回解析后的 JSON。"""
    req = urllib.request.Request(API_BASE + path)
    req.add_header("Authorization", key)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_tasks(list_id: str, key: str, *, fetch=None, timeout: int = 60) -> list[dict]:
    """拉一个 list 的全部任务（含子任务与**已完成**），按 id 去重。

    ⚠️ 两个已知坑，别"简化"掉：
    - 必须带 ``include_closed=true``，否则已完成任务整批漏掉，看着像「今天什么都没干」；
    - ``subtasks=true`` 翻页会**重复返回**同一条，按 id 去重才干净。
    ``fetch`` 可注入（测试用假实现，离线跑）。
    """
    fetch = http_get if fetch is None else fetch
    seen: set[str] = set()
    out: list[dict] = []
    for page in range(MAX_PAGES):
        path = (f"/list/{list_id}/task?subtasks=true&include_closed=true&page={page}")
        batch = (fetch(path, key, timeout=timeout) or {}).get("tasks") or []
        for t in batch:
            tid = t.get("id")
            if tid in seen:
                continue
            seen.add(tid)
            out.append(t)
        if len(batch) < PAGE_SIZE:
            break
    return out


# --------------------------------------------------------------------- 选数
def _name(t: dict) -> str:
    return (t.get("name") or "(未命名)").strip()


def _status(t: dict) -> str:
    st = t.get("status")
    return (st or {}).get("status", "") if isinstance(st, dict) else str(st or "")


def _status_type(t: dict) -> str:
    st = t.get("status")
    if isinstance(st, dict):
        return str(st.get("type") or "").lower()
    return ""


def select_completed(tasks: list[dict], day: str, *, tz_hours: int | None = None) -> list[dict]:
    """当日完成：``date_closed`` 落在 ``day``（东八区），按完成时刻升序。"""
    hit = [t for t in tasks
           if t.get("date_closed") and day_of(t["date_closed"], tz_hours=tz_hours) == day]
    return sorted(hit, key=lambda t: int(t["date_closed"]))


def select_due_open(tasks: list[dict], day: str, *, tz_hours: int | None = None) -> list[dict]:
    """当日到期但**未完成**：``due_date`` 落在 ``day`` 且没有 ``date_closed``。

    只作参考（提醒「计划了没做」），**不是**完成证据，别拿它当「今天做了什么」。
    """
    hit = []
    for t in tasks:
        if t.get("date_closed"):
            continue
        due = t.get("due_date")
        if due and day_of(due, tz_hours=tz_hours) == day:
            hit.append(t)
    return sorted(hit, key=lambda t: int(t["due_date"]))


_IN_PROGRESS_NAMES = ("进行中", "in progress", "in_progress", "doing", "wip")


def select_in_progress(tasks: list[dict], day: str = "", *, tz_hours: int | None = None) -> list[dict]:
    """进行中：未关闭，且状态名为进行中类，或 ClickUp ``status.type == custom``。"""
    _ = (day, tz_hours)  # 签名与其它选取器对齐；进行中看状态不看归日
    hit = []
    for t in tasks:
        if t.get("date_closed"):
            continue
        name = _status(t).lower()
        if _status_type(t) == "custom" or any(k in name for k in _IN_PROGRESS_NAMES):
            hit.append(t)
    return sorted(hit, key=lambda t: (t.get("name") or ""))

def select_overdue(tasks: list[dict], day: str, *, tz_hours: int | None = None) -> list[dict]:
    """逾期：未关闭，且 ``due_date`` 归日 **早于** ``day``。"""
    hit = []
    for t in tasks:
        if t.get("date_closed"):
            continue
        due = t.get("due_date")
        if due and day_of(due, tz_hours=tz_hours) < day:
            hit.append(t)
    return sorted(hit, key=lambda t: int(t["due_date"]))


def select_cross_day_open(tasks: list[dict], day: str, *, tz_hours: int | None = None) -> list[dict]:
    """跨天未闭合：未关闭，且创建日早于 ``day``（拖了多天仍挂着）。"""
    hit = []
    for t in tasks:
        if t.get("date_closed"):
            continue
        created = t.get("date_created")
        if created and day_of(created, tz_hours=tz_hours) < day:
            hit.append(t)
    return sorted(hit, key=lambda t: int(t.get("date_created") or 0))


def collect(day: str, list_ids=None, *, key: str = "", fetch=None,
            meta: dict | None = None, timeout: int = 60) -> list[dict]:
    """按 list 汇总某天的素材。

    返回 ``[{id, name, role, done, open, in_progress, overdue, cross_day}]``。
    """
    ids = CLICKUP_DAILY_IDS if list_ids is None else tuple(list_ids)
    meta = CLICKUP_LIST_META if meta is None else meta
    groups = []
    for lid in ids:
        info = meta.get(lid) or {}
        tasks = fetch_tasks(lid, key, fetch=fetch, timeout=timeout)
        groups.append({
            "id": lid,
            "name": info.get("name") or lid,
            "role": info.get("role") or "",
            "done": select_completed(tasks, day),
            "open": select_due_open(tasks, day),
            "in_progress": select_in_progress(tasks, day),
            "overdue": select_overdue(tasks, day),
            "cross_day": select_cross_day_open(tasks, day),
        })
    return groups


# --------------------------------------------------------------------- 渲染
def bulk_hint(groups: list[dict], *, min_count: int = BULK_HINT_MIN) -> str | None:
    """同一分钟内大量「完成」→ 提示疑似批量改状态；无异常返回 None。

    为什么需要：迁移或整批关闭会让某天凭空多出上百条同时刻完成的记录
    （实例 2026-10-13：114 条挤在 11:17–11:18）。素材本身如实呈现，
    但**必须**附一句提示，否则会被读成「那天一口气干了 114 件事」。
    """
    buckets: dict[str, int] = {}
    for g in groups:
        for t in g["done"]:
            c = clock_of(t["date_closed"])
            buckets[c] = buckets.get(c, 0) + 1
    if not buckets:
        return None
    clock, n = max(buckets.items(), key=lambda kv: kv[1])
    if n < min_count:
        return None
    return (f"⚠️ 当日有 {n} 条任务在同一分钟（{clock}）被标记完成 —— 疑似**批量改状态**"
            "（迁移 / 整批关闭），不宜解读为「逐条完成」；请结合复盘 md 的实际记录判断。")


def render(day: str, groups: list[dict], *, generated_at: str | None = None,
           workspace: str | None = None) -> str:
    """把汇总结果渲染成素材简报 md。

    ⛔ 刻意不用 ``- [x]`` 勾选语法：ClickUp 习惯与复盘 md「一、日常打卡」的
    补剂 / 护肤是两套体系，格式上要一眼能分开。
    """
    try:
        wd = WEEKDAY_CN[datetime.date.fromisoformat(day).weekday()]
    except ValueError:
        wd = ""
    stamp = generated_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"# ClickUp 素材 · {day}（星期{wd}）" if wd else f"# ClickUp 素材 · {day}", ""]
    lines += [
        "> ⚠️ **这是素材，不是复盘成品** —— 由 `python -m review_tool clickup` 自动生成。",
        "> ClickUp 是行为跟踪的**执行层**，只提供「今天干了什么」的证据："
        "**不参与四维评分、不落库**。",
        "> ⛔ 「习惯与打卡」的勾选属**行为习惯**，**不得**写进复盘 md 的「一、日常打卡」"
        "（那一节只收补剂 / 护肤，混进去会污染 `personal_tracks` 依从率）。",
        "> 归日口径：按 `date_closed`（实际完成时刻，东八区），不是 `due_date`。",
        "",
        f"- 生成时间：{stamp}",
    ]
    src = "ClickUp" + (f" · 工作区 {workspace}" if workspace else "")
    lines += [f"- 数据来源：{src}", ""]

    lines += [
        "| 分组 | 当日完成 | 到期未完成 | 进行中 | 逾期 | 跨天未闭合 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for g in groups:
        lines.append(
            f"| {g['name']} | {len(g['done'])} | {len(g['open'])} | "
            f"{len(g.get('in_progress') or [])} | {len(g.get('overdue') or [])} | "
            f"{len(g.get('cross_day') or [])} |"
        )
    lines += [
        "",
        f"- **当日完成合计**：{sum(len(g['done']) for g in groups)} 条",
        "",
    ]

    hint = bulk_hint(groups)
    if hint:
        lines += [f"> {hint}", ""]

    def _section(title: str, items: list[dict], *, note: str = "") -> None:
        if not items:
            return
        lines.append(f"**{title} {len(items)} 条**" + (f"（{note}）" if note else ""))
        lines.append("")
        for t in items:
            due = t.get("due_date")
            due_s = f" · 到期 {day_of(due)}" if due else ""
            lines.append(f"- {_name(t)}（状态 {_status(t) or '未知'}{due_s}）")
        lines.append("")

    for g in groups:
        role = f" · {g['role']}" if g["role"] else ""
        lines += [f"## {g['name']}{role}", ""]
        if g["done"]:
            lines.append(f"**当日完成 {len(g['done'])} 条**")
            lines.append("")
            for t in g["done"]:
                when = clock_of(t["date_closed"])
                st = _status(t)
                tail = f"（完成 {when}" + (f" · {st}" if st and st.lower() != "complete" else "") + "）"
                lines.append(f"- {_name(t)}{tail}")
            lines.append("")
        else:
            lines += ["**当日完成 0 条**（ClickUp 侧无记录）", ""]

        if g["open"]:
            lines += [f"**当日到期未完成 {len(g['open'])} 条（仅供参考，不是完成证据）**", ""]
            for t in g["open"]:
                lines.append(f"- {_name(t)}（状态 {_status(t) or '未知'}）")
            lines += [""]

        _section("进行中", g.get("in_progress") or [], note="便于写明日 Top 3")
        _section("逾期", g.get("overdue") or [], note="due 早于当日且未关")
        _section("跨天未闭合", g.get("cross_day") or [], note="创建日早于当日仍未关")

    lines += [
        "---",
        "",
        "以上为 ClickUp 侧证据，撰写复盘时按需取用；**四维分与熔断仍由复盘流程决定**。",
        "复盘 md 只收补剂 / 护肤的打卡勾选，ClickUp 习惯**不进**「一、日常打卡」。",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------- CLI
USAGE = "clickup [YYYY-MM-DD] [--out DIR] [--stdout] [--list ID]..."


def _parse(argv: list[str]) -> tuple[str, str, bool, list[str]]:
    """返回 ``(day, out_dir, to_stdout, list_ids)``；非法参数抛 ValueError。"""
    day, out_dir, to_stdout = "", INBOX_DIR, False
    list_ids: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stdout":
            to_stdout = True
        elif a == "--out" or a.startswith("--out="):
            if a.startswith("--out="):
                out_dir = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--out 需要跟一个目录")
                out_dir = argv[i]
        elif a == "--list" or a.startswith("--list="):
            if a.startswith("--list="):
                raw = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--list 需要跟一个 list id")
                raw = argv[i]
            list_ids += [p.strip() for p in raw.split(",") if p.strip()]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day:
                raise ValueError(f"多余的参数: {a}（日期只接受一个）")
            day = a
        i += 1

    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    else:
        day = datetime.date.today().isoformat()
    return day, out_dir, to_stdout, list_ids


def main(argv: list[str] | None = None, *, fetch=None, env=None, now=None) -> int:
    """CLI 入口。``fetch`` / ``env`` / ``now`` 可注入（测试离线跑）。"""
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        return 0

    try:
        day, out_dir, to_stdout, list_ids = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        key, team = load_creds(env=env)
    except CredError as e:
        print(f"凭据错误: {e}", file=sys.stderr)
        return 2

    try:
        groups = collect(day, list_ids or None, key=key, fetch=fetch)
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        hint = "（401/403 = token 失效或权限不足）" if str(code) in ("401", "403") else ""
        print(f"取数失败: HTTP {code} {hint}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"取数失败: 网络不可达 —— {e.reason}", file=sys.stderr)
        return 1

    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = render(day, groups, generated_at=stamp, workspace=team)

    total = sum(len(g["done"]) for g in groups)
    if to_stdout:
        print(text)
        return 0

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{CLICKUP_INBOX_PREFIX}-{day}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"已生成: {out}")
    print(f"当日完成合计 {total} 条；这是**素材**，不是复盘成品 —— "
          "按 skill daily-review-intake 转成复盘。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
