"""daily-pull：夜间采集拉齐 —— 练练落 md + 习惯快照 + 入库，一条命令。

M33（v1.39.0）。夜间 SOP 原本要依次跑三条命令（``keepstrong --write --ingest``
/ ``habits --sync`` / ``ingest``），任何一步忘跑就静默缺数 ——
``body_metrics`` 78 天 0 行、``habit_logs`` 只覆盖 1 天的根因不是「没数据」，
是「链路没触发」。

边界（立项时定死，别放宽）：

- **只允许夜间使用**（打网：练练 + ClickUp）；晨间不打网纪律不变。
- 默认 dry-run：只打印将执行的动作，不发任何网络请求、不写库；
  ``--apply`` 才真跑（沿袭 ``clickup-push`` 的 dry-run 默认惯例）。
- 各步骤失败显式报错并**继续跑其余步骤**（练练 401 不该挡住习惯快照）；
  退出码 = 任一步失败则 1。
- 编排层不重算：全部沿用 keepstrong / habit_sync / ingest 既有实现，
  数据通道守 G1（先落 md 再入库，``--ingest`` 内建校验）。
"""
from __future__ import annotations

import datetime
import sys

from .habit_sync import sync_main
from .ingest import main as ingest_main
from .keepstrong import main as keepstrong_main

USAGE = "daily-pull [--date YYYY-MM-DD] [--apply]"


def _default_day() -> str:
    return datetime.date.today().isoformat()


def _parse(argv: list[str]) -> tuple[str | None, bool]:
    """返回 ``(date_str, apply)``。"""
    day: str | None = None
    apply = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--apply":
            apply = True
        elif a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期（YYYY-MM-DD）")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            raise ValueError(f"多余的位置参数: {a}（日期用 --date 传）")
        i += 1
    if day is not None:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    return day, apply


def _steps(day: str) -> list[tuple[str, object, str]]:
    """返回 [(步骤名, 执行函数, 等价 CLI), ...]。顺序 = 数据流向。"""
    return [
        ("练练素材 → 复盘 md + 入库",
         lambda: keepstrong_main(["--date", day, "--write", "--ingest"]),
         f"keepstrong --date {day} --write --ingest"),
        ("习惯快照（ClickUp → habit_logs）",
         lambda: sync_main([day]),
         f"habits --sync {day}"),
        ("全量入库（保护模式，补当日手填字段）",
         lambda: ingest_main([]),
         "ingest"),
    ]


def _report(day: str) -> None:
    """收尾一行汇报：当天各关键位置的就位情况（只读）。"""
    from ..storage.db import DB_PATH, init_db

    conn = init_db()
    try:
        rv = conn.execute(
            "SELECT system_score FROM daily_reviews WHERE date=?", (day,)
        ).fetchone()
        habits = conn.execute(
            "SELECT count(*) FROM habit_logs WHERE date=?", (day,)
        ).fetchone()[0]
        body = conn.execute(
            "SELECT count(*) FROM body_metrics WHERE date=?", (day,)
        ).fetchone()[0]
        train = conn.execute(
            "SELECT training_day FROM daily_reviews WHERE date=?", (day,)
        ).fetchone()
    finally:
        conn.close()
    L = [f"[汇报] {day}（db: {DB_PATH}）"]
    L.append(f"  复盘入库: {'✓ 系统分 ' + str(rv[0]) if rv and rv[0] is not None else ('✓（未评分）' if rv else '✗ 尚无当日 md 或未 ingest')}")
    L.append(f"  习惯快照: {habits} 行")
    L.append(f"  体征记录: {body} 行")
    if train is not None:
        L.append(f"  训练日: {'是' if train[0] else '否'}")
    print("\n".join(L))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("夜间采集拉齐：练练落 md + 习惯快照 + 入库。默认 dry-run，"
              "--apply 真跑（会打网，仅夜间使用）。")
        return 0
    try:
        day, apply = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2
    day = day or _default_day()

    steps = _steps(day)
    if not apply:
        print(f"dry-run：将对 {day} 执行以下动作（加 --apply 真跑；"
              "会打网，仅夜间使用）：")
        for name, _fn, cmd in steps:
            print(f"  · {name}\n      $ python -m review_tool {cmd}")
        return 0

    failures: list[tuple[str, int]] = []
    for name, fn, cmd in steps:
        print(f"\n[{name}]")
        print(f"  $ python -m review_tool {cmd}")
        rc = fn()  # type: ignore[operator]
        if rc != 0:
            failures.append((name, rc))
            print(f"  ⚠️ 该步返回码 {rc}，继续执行其余步骤", file=sys.stderr)

    if failures:
        print(f"\ndaily-pull ✗ {len(failures)} 步失败：")
        for name, rc in failures:
            print(f"  ✗ {name}（rc={rc}）")
        print("练练「认证失败」→ Key 过期，换 Key：练练 App → 我的 → 连接 AI → "
              "生成新 API Key → 写 .env（详见 conventions §6，过期表现是静默无数据）")
        _report(day)
        return 1

    print("\ndaily-pull ✓ 全部步骤完成")
    _report(day)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
