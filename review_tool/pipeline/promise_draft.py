"""promise-draft：明日 Top 3 候选草稿（M34 / v1.40.0）—— 承诺写侧降摩擦。

背景
----
承诺对账（M29/M30）两头都空：近 30 天 29 篇复盘只有 **5 天**写了承诺
（24 天空白），已写的 129 条里 **71% unmapped**。先解决「写」，再谈「判」——
写承诺的最大摩擦是「要想明天干什么」，而 ClickUp 的到期未完成 / 逾期 /
进行中任务天然就是候选池。

边界（红线，改代码前重读）
------------------------
- **机器只搬运，不编造**：候选 = ClickUp 任务名原样，不做任何语义改写；
- **人勾选后才回填**：草稿落 ``收件箱/``（不参与 ingest），不自动写复盘、
  不自动入库 —— 没勾的不会进任何库表；
- **不做「承诺文本 ↔ 任务名」语义匹配**（M30 三条硬约束不变）；
- 候选条目附**约束提示**：从任务名抽出数字（时长 / 上限），没有数字的
  显式提醒「回填时补一个」—— 可判定的承诺越多，次日对账的 unmapped 越少。
"""
from __future__ import annotations

import datetime
import os
import re
import sys

from ..config import INBOX_DIR
from .clickup import CredError, _name, collect, load_creds

USAGE = "promise-draft [--date YYYY-MM-DD] [--stdout] [--out DIR]"

INBOX_PREFIX = "明日候选"

# 任务名里的时长估算：「60min」「1.5h」「90 分钟」「2 小时」
_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(min|分钟|h|hr|小时)", re.I)
# 上限 / 下限约束：「≤70g」「≤1h」「至少 30min」
_LIMIT_RE = re.compile(r"[≤<=]\s*\d+(?:\.\d+)?\s*[a-zA-Z\u4e00-\u9fa5]*")


def extract_constraint(name: str) -> str | None:
    """从任务名抽约束提示（返回 None = 无数字约束）。

    只抽**数字**，不做语义推断 —— 「彻底修复」这种词不构成可判定约束。
    """
    m = _TIME_RE.search(name)
    if m:
        v, unit = m.group(1), m.group(2).lower()
        if unit in ("min", "分钟"):
            return f"约 {v}min"
        return f"约 {v}h"
    m = _LIMIT_RE.search(name)
    if m:
        return m.group(0).replace(" ", "")
    return None


def _dedup(tasks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for t in tasks:
        tid = str(t.get("id") or "")
        if tid and tid in seen:
            continue
        seen.add(tid)
        out.append(t)
    return out


def candidate_pool(day: str, groups: list[dict]) -> list[dict]:
    """候选池 = 明天到期未完成 + 逾期（含今天到期没做的）+ 进行中，按 list 去重。"""
    pool: list[dict] = []
    for g in groups:
        merged = _dedup([*g["open"], *g["overdue"], *g["in_progress"]])
        for t in merged:
            pool.append({"list": g["name"], "task": t})
    return pool


def build_draft(day: str, pool: list[dict], *, generated_at: str) -> str:
    """渲染候选草稿 md。``day`` = 承诺执行日（= 生成日的明天）。"""
    L: list[str] = []
    L.append(f"# 明日 Top 3 候选（{day}）")
    L.append("")
    L.append(f"> 生成时间 {generated_at}｜来源：ClickUp 当日到期未完成 / 逾期 / 进行中。")
    L.append("> **机器只搬运，不编造**；本文件是草稿，**不入库** ——")
    L.append("> 睡前勾 ≤3 条回填到复盘 md「四、明日 Top 3」，没勾的不会进任何库表。")
    L.append("> 回填时给条目补数字约束（时长 / 上限 / 锚点），可判定的承诺越多，次日对账越准。")
    L.append("")
    if not pool:
        L.append("（候选池为空：ClickUp 里没有到期未完成 / 逾期 / 进行中的任务。")
        L.append("明天想设承诺就从零写 ——「今天不设」也是一个决定。）")
        return "\n".join(L) + "\n"
    L.append(f"## 候选池（{len(pool)} 条）")
    L.append("")
    cur_list: str | None = None
    for it in pool:
        if it["list"] != cur_list:
            cur_list = it["list"]
            L.append(f"### {cur_list}")
            L.append("")
        name = _name(it["task"])
        c = extract_constraint(name)
        if c:
            L.append(f"- [ ] {name}（{c}）")
        else:
            L.append(f"- [ ] {name} ⚠️ 无数字约束 —— 回填时补一个（如「30min」「≤1h」「22:30 前」）")
    L.append("")
    L.append("## 回填提醒")
    L.append("")
    L.append("1. 勾 ≤3 条（Top 3 就是最多 3 条，别把候选池整个搬过去）；")
    L.append("2. 每条尽量带数字（次日 `promises` 对账只认结构化字段）；")
    L.append("3. 不想设就写「今天不设」—— 它是决定，不进兑现率分母。")
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
        day = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
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
        print("明日 Top 3 候选草稿：ClickUp 到期未完成 / 逾期 / 进行中 → 收件箱 md。")
        print("草稿不入库；人勾选后回填复盘 md「四、明日 Top 3」。")
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
    except Exception as e:  # 与 clickup.main 同款兜底文案
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
    print(f"已生成: {out}（候选 {len(pool)} 条）")
    print("这是**草稿**：勾 ≤3 条回填复盘 md「四、明日 Top 3」；不勾不会进库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
