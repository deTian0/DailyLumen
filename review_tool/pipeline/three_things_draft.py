"""three-things-draft：今日三件事候选草稿（M36 / v1.43.0）—— 对称 promise-draft。

背景
----
承诺写侧已有 M34 ``promise-draft``（明日 Top 3 候选），但复盘「二、今日三件事」
仍常空 —— 用户要回想「今天做成了什么」。ClickUp **当日已完成**任务天然是候选池：
一个面向「明日要做」，一个面向「今日做成」。

边界（红线，改代码前重读）
------------------------
- **机器只搬运，不编造**：候选 = ClickUp 任务名原样；
- **人勾选后才回填**：草稿落 ``收件箱/``（不参与 ingest），不自动写复盘、不入库；
- **与 promise-draft 物理分文件**：前缀 ``三件事候选-`` ≠ ``明日候选-``，同日可并存；
- 不改 ``promises`` / ``clickup_done`` schema；不改四维评分。
"""
from __future__ import annotations

import datetime
import os
import re
import sys

from ..config import INBOX_DIR
from .clickup import CredError, _name, collect, load_creds

USAGE = "three-things-draft [--date YYYY-MM-DD] [--stdout] [--out DIR]"

INBOX_PREFIX = "三件事候选"

# 标题含「交付物」类词 → 优先（有产出启发式）
_DELIVERABLE_RE = re.compile(
    r"(交付|报告|文档|周报|月报|方案|总结|导出|提交|发布|产出|PR|稿|\.pdf|\.md)",
    re.I,
)
# 时长数字：「60min」「1.5h」「90 分钟」「2 小时」
_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(min|分钟|h|hr|小时)", re.I)


def productivity_rank(name: str) -> int:
    """有产出启发式分：交付物词 +2、时长数字 +1；越高越靠前。"""
    score = 0
    if _DELIVERABLE_RE.search(name or ""):
        score += 2
    if _TIME_RE.search(name or ""):
        score += 1
    return score


def _dedup(tasks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for t in tasks:
        tid = str(t.get("id") or "")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        out.append(t)
    return out


def candidate_pool(day: str, groups: list[dict]) -> list[dict]:
    """候选池 = 当日已完成（各 list 的 done），全局去重后按有产出启发式 + 关闭时间降序。"""
    _ = day  # 归日已在 collect → select_completed 完成
    pool: list[dict] = []
    seen: set[str] = set()
    for g in groups:
        for t in _dedup(g.get("done") or []):
            tid = str(t.get("id") or "")
            if tid and tid in seen:
                continue
            if tid:
                seen.add(tid)
            pool.append({"list": g["name"], "task": t})
    pool.sort(
        key=lambda it: (
            -productivity_rank(_name(it["task"])),
            -int(it["task"].get("date_closed") or 0),
        )
    )
    return pool


def build_draft(day: str, pool: list[dict], *, generated_at: str) -> str:
    """渲染候选草稿 md。``day`` = 被复盘日（= 今日三件事归属日）。"""
    L: list[str] = []
    L.append(f"# 今日三件事候选（{day}）")
    L.append("")
    L.append(f"> 生成时间 {generated_at}｜来源：ClickUp 当日已完成（`date_closed` 归日，含次日补勾回拨）。")
    L.append("> **机器只搬运，不编造**；本文件是草稿，**不入库** ——")
    L.append("> 勾 ≤3 条回填到复盘 md「二、今日三件事」，没勾的不会进任何库表。")
    L.append("> 与「明日候选」分文件并存；排序：标题含交付物 / 时长数字优先，其余按关闭时间。")
    L.append("")
    if not pool:
        L.append("（候选池为空：ClickUp 里没有当日已完成的任务。")
        L.append("今天做成的事若只在口头 / 别处，就从零手写三件事。）")
        return "\n".join(L) + "\n"
    L.append(f"## 候选池（{len(pool)} 条）")
    L.append("")
    # 已按启发式全局排序；渲染时仍按 list 分组会打乱顺序 ——
    # 改成扁平列表 + 标所属 list，保留排序意图。
    for it in pool:
        name = _name(it["task"])
        rank = productivity_rank(name)
        tag = " · 有产出优先" if rank >= 2 else (" · 含时长" if rank == 1 else "")
        L.append(f"- [ ] {name}（{it['list']}{tag}）")
    L.append("")
    L.append("## 回填提醒")
    L.append("")
    L.append("1. 勾 ≤3 条回填「二、今日三件事」（成就，不是计划）；")
    L.append("2. 条目可原样搬，也可压缩成更短的成就句；")
    L.append("3. 没做成可写的事就留空或少写 —— ⛔ 不编造。")
    return "\n".join(L) + "\n"


def _parse(argv: list[str]) -> tuple[str, bool, str | None]:
    day: str | None = None
    to_stdout = False
    out_dir: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stdout":
            to_stdout = True
        elif a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期（YYYY-MM-DD）")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a == "--out":
            i += 1
            if i >= len(argv):
                raise ValueError("--out 需要跟目录")
            out_dir = argv[i]
        elif a.startswith("--out="):
            out_dir = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            raise ValueError(f"多余的位置参数: {a}")
        i += 1
    if day is None:
        day = datetime.date.today().isoformat()
    else:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    return day, to_stdout, out_dir


def main(argv: list[str] | None = None, *, fetch=None, env=None, now=None) -> int:
    """CLI 入口。``fetch`` / ``env`` / ``now`` 可注入（测试离线跑）。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("今日三件事候选草稿：ClickUp 当日已完成 → 收件箱 md。")
        print("草稿不入库；人勾选后回填复盘 md「二、今日三件事」。")
        return 0
    try:
        day, to_stdout, out_dir = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        key, _team = load_creds(env=env)
    except CredError as e:
        print(f"凭据错误: {e}", file=sys.stderr)
        return 2

    try:
        groups = collect(day, None, key=key, fetch=fetch)
    except Exception as e:
        code = getattr(e, "code", None)
        hint = "（401/403 = token 失效或权限不足）" if str(code) in ("401", "403") else ""
        print(f"取数失败: {hint}{e}", file=sys.stderr)
        return 1

    pool = candidate_pool(day, groups)
    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = build_draft(day, pool, generated_at=stamp)

    if to_stdout:
        print(text)
        return 0

    target = out_dir or INBOX_DIR
    os.makedirs(target, exist_ok=True)
    out = os.path.join(target, f"{INBOX_PREFIX}-{day}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    # 写盘回读校验（本机 Windows 可能报成功不落盘）
    with open(out, encoding="utf-8") as f:
        got = f.read()
    if got != text:
        print(f"写盘校验失败: {out}", file=sys.stderr)
        return 1
    print(f"已生成: {out}（候选 {len(pool)} 条）")
    print("这是**草稿**：勾 ≤3 条回填复盘 md「二、今日三件事」；不勾不会进库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
