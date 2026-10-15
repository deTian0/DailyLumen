"""训练教练建议：达标 / 渐进 / 恢复 / 部位轮换（可解释、可复算）。

用法:
    python -m review_tool coach
    python -m review_tool coach --json
    python -m review_tool coach 2026-10-15

每条建议必须打印依据数字；同输入两次输出逐字节一致（无随机）。
训练明细不直接改四维分 —— 只经既有 ``exercise_min`` 路径（G5 / R2）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from ..config import COACH_RULES, PROFILE, TRAINING_MOVES, TRAINING_PLAN
from ..core.training import (
    hours_between,
    needs_recovery,
    suggest_progression,
    volume,
    week_completion_ok,
)
from ..storage.db import init_db, load_training


def _planned_sessions() -> int:
    """本周计划课次：有 TRAINING_PLAN 用其长度，否则用 training_weekdays。"""
    if TRAINING_PLAN:
        return len(TRAINING_PLAN)
    return len(PROFILE.get("training_weekdays") or [])


def _iso_week_bounds(as_of: str) -> tuple[str, str]:
    d = date.fromisoformat(as_of)
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _item_volumes(items: list, item_key: str, *, limit: int) -> list[int]:
    """按日期升序取某动作近 ``limit`` 次的组×次体积。"""
    rows = [
        r for r in items
        if r["item_key"] == item_key and r["sets"] is not None and r["reps"] is not None
    ]
    rows.sort(key=lambda r: (r["date"], r["session_key"]))
    vols = []
    for r in rows[-limit:]:
        v = volume(r["sets"], r["reps"])
        if v is not None:
            vols.append(v)
    return vols


def _main_body_part(items_for_day: list) -> str | None:
    """当日主项部位：取第一条有 body_part 的动作（目录优先）。"""
    for r in items_for_day:
        spec = TRAINING_MOVES.get(r["item_key"]) or {}
        part = spec.get("body_part")
        if part:
            return part
    return None


def collect(conn, *, as_of: str | None = None) -> dict:
    """汇总统教练建议所需数据与建议列表（结构化，文本/JSON 共用）。"""
    if as_of is None:
        row = conn.execute("SELECT MAX(date) FROM training_sessions").fetchone()
        as_of = row[0] if row and row[0] else date.today().isoformat()

    lookback_days = 28
    start = (date.fromisoformat(as_of) - timedelta(days=lookback_days)).isoformat()
    data = load_training(conn, start=start, end=as_of)
    sessions = [dict(r) for r in data["sessions"]]
    items = [dict(r) for r in data["items"]]

    week_start, week_end = _iso_week_bounds(as_of)
    week_dates = sorted({
        s["date"] for s in sessions
        if week_start <= s["date"] <= week_end
    })
    completed = len(week_dates)
    planned = _planned_sessions()
    completion = week_completion_ok(
        completed, planned, min_ratio=float(COACH_RULES["min_ratio"])
    )

    all_dates = sorted({s["date"] for s in sessions if s["date"] <= as_of})
    recovery = needs_recovery(
        all_dates, max_consecutive=int(COACH_RULES["max_consecutive_days"])
    )

    suggestions: list[dict] = []

    # 1) 达标线
    if completion["ok"]:
        suggestions.append({
            "kind": "volume",
            "title": "课次达标，可考虑加量",
            "evidence": completion["evidence"],
        })
    else:
        suggestions.append({
            "kind": "volume",
            "title": "先补课次，暂不加量",
            "evidence": completion["evidence"],
        })

    # 2) 渐进（每个在 lookback 内出现过的动作）
    lookback = int(COACH_RULES["progression_lookback"])
    keys = sorted({i["item_key"] for i in items})
    for key in keys:
        vols = _item_volumes(items, key, limit=lookback)
        if len(vols) < 2:
            continue
        prog = suggest_progression(
            vols,
            max_cv=float(COACH_RULES["progression_cv"]),
            add_sets=int(COACH_RULES["add_sets"]),
            add_reps=int(COACH_RULES["add_reps"]),
        )
        if not completion["ok"]:
            # 课次不达标时渐进也只维持（规则 1 优先）
            suggestions.append({
                "kind": "progression",
                "item_key": key,
                "title": f"{key}：维持（课次未达加量门槛）",
                "evidence": prog["evidence"] + "；" + completion["evidence"],
            })
        elif prog["action"] == "increase":
            suggestions.append({
                "kind": "progression",
                "item_key": key,
                "title": (
                    f"{key}：建议 +{prog['add_sets']} 组或 +{prog['add_reps']} 次"
                ),
                "evidence": prog["evidence"],
            })
        else:
            suggestions.append({
                "kind": "progression",
                "item_key": key,
                "title": f"{key}：维持当前负荷",
                "evidence": prog["evidence"],
            })

    # 3) 恢复
    if recovery["needed"]:
        suggestions.append({
            "kind": "recovery",
            "title": "强制建议：插入 1 天恢复",
            "evidence": recovery["evidence"] + (
                f"；训练日约定={PROFILE.get('training_weekdays')}"
            ),
        })
    else:
        suggestions.append({
            "kind": "recovery",
            "title": "恢复窗口正常",
            "evidence": recovery["evidence"],
        })

    # 4) 部位轮换：相对 as_of，检查最近主项
    gap_h = int(COACH_RULES["body_part_gap_hours"])
    by_date: dict[str, list] = {}
    for it in items:
        by_date.setdefault(it["date"], []).append(it)
    recent_parts: list[tuple[str, str]] = []
    for d in sorted(by_date):
        part = _main_body_part(by_date[d])
        if part:
            recent_parts.append((d, part))
    if recent_parts:
        last_date, last_part = recent_parts[-1]
        gap = hours_between(last_date, as_of)
        # 若 as_of 当天就是最后训练日，gap=0 → 冲突（下次别再练同部位）
        conflict = gap < gap_h
        suggestions.append({
            "kind": "rotation",
            "title": (
                f"部位轮换：{last_part} 距今 {gap:.0f}h"
                + ("，下次勿作主项" if conflict else "，可安排")
            ),
            "evidence": (
                f"最近主项部位={last_part}（{last_date}），"
                f"相对 {as_of} 间隔 {gap:.0f}h，窗口 {gap_h}h → "
                f"{'冲突' if conflict else '安全'}"
            ),
        })
    else:
        suggestions.append({
            "kind": "rotation",
            "title": "部位轮换：暂无明细",
            "evidence": "近窗无 training_items，跳过轮换",
        })

    return {
        "as_of": as_of,
        "week": {"start": week_start, "end": week_end},
        "completion": completion,
        "recovery": recovery,
        "sessions_in_window": len(sessions),
        "items_in_window": len(items),
        "suggestions": suggestions,
    }


def render(data: dict) -> str:
    """人类可读文本；确定性拼装，无时间戳 / 无随机。"""
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 训练教练建议")
    L.append("=" * 52)
    L.append("")
    L.append(f"[基准日] {data['as_of']}")
    L.append(
        f"[本周] {data['week']['start']} ~ {data['week']['end']} ｜ "
        f"完成 {data['completion']['completed']}/"
        f"{data['completion']['planned']} 课"
        f"（比率 {data['completion']['ratio']}）"
    )
    L.append(
        f"[窗口] sessions={data['sessions_in_window']} ｜ "
        f"items={data['items_in_window']}"
    )
    L.append("")
    L.append("[建议]")
    for i, s in enumerate(data["suggestions"], 1):
        L.append(f"  {i}. {s['title']}")
        L.append(f"     依据: {s['evidence']}")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    as_of = None
    db_path = None
    for a in args:
        if len(a) == 10 and a[4] == "-" and a[7] == "-":
            as_of = a
        else:
            db_path = a

    conn = init_db(db_path)
    try:
        data = collect(conn, as_of=as_of)
    finally:
        conn.close()

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
