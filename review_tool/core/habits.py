"""行为习惯纯规则：归一化 / 依从率 / streak / 断更（零 I/O）。

与 ``personal_tracks``（补剂 / 护肤）物理隔离 —— 本模块只认 ``config.HABITS``。
habit_logs 不参与四维评分（G5）；依从率只在独立指标区出现。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import HABITS
from .tracks import normalize_item

# 落库固定类别，便于与 personal_tracks.category 一眼区分（R3）
HABIT_CATEGORY = "行为习惯"


def resolve_habit(text: str, *, items: list[dict] | None = None) -> dict | None:
    """把任务名 / 展示名归一到 ``HABITS`` 目录项；未命中返回 None。"""
    return normalize_item(text, items if items is not None else HABITS)


def habit_by_key(key: str, *, items: list[dict] | None = None) -> dict | None:
    """按 key 取目录项。"""
    for item in (items if items is not None else HABITS):
        if item.get("key") == key:
            return item
    return None


def adherence_rate(done: int, recorded: int) -> float | None:
    """完成率 = done / recorded；无记录返回 None。"""
    if not recorded:
        return None
    return round(done / recorded, 4)


def adherence_from_rows(rows: list[dict]) -> dict:
    """按 ``habit_key`` 聚合依从率。

    每行需含 ``habit_key`` / ``done``（0/1）；可选 ``item``。
    返回 ``{"items": [...], "total": {...}}``。
    """
    acc: dict[str, dict] = {}
    for r in rows:
        key = r["habit_key"]
        bucket = acc.setdefault(key, {
            "habit_key": key,
            "item": r.get("item") or key,
            "recorded": 0,
            "done": 0,
        })
        bucket["recorded"] += 1
        if int(r.get("done") or 0) == 1:
            bucket["done"] += 1
        if r.get("item"):
            bucket["item"] = r["item"]

    items = []
    total_rec = total_done = 0
    for key in sorted(acc):
        b = acc[key]
        rate = adherence_rate(b["done"], b["recorded"])
        items.append({**b, "adherence": rate})
        total_rec += b["recorded"]
        total_done += b["done"]
    return {
        "items": items,
        "total": {
            "recorded": total_rec,
            "done": total_done,
            "adherence": adherence_rate(total_done, total_rec),
        },
    }


def streak_from_dates(ok_dates: set[str] | list[str], *, as_of: str | None = None) -> int:
    """从 ``as_of``（默认集合最大日）往回数连续命中天数；中断即停。"""
    if not ok_dates:
        return 0
    ok = set(ok_dates)
    end = as_of or max(ok)
    cur = datetime.strptime(end, "%Y-%m-%d")
    n = 0
    while cur.strftime("%Y-%m-%d") in ok:
        n += 1
        cur -= timedelta(days=1)
    return n


def habit_streak(rows: list[dict], habit_key: str, *, as_of: str | None = None) -> dict:
    """某习惯连续完成天数（当日 ``done=1``）。

    ``rows`` 为该习惯（或全表）的日志行，含 ``date`` / ``habit_key`` / ``done``。
    """
    mine = [r for r in rows if r["habit_key"] == habit_key]
    ok = {r["date"] for r in mine if int(r.get("done") or 0) == 1}
    end = as_of
    if end is None and mine:
        end = max(r["date"] for r in mine)
    current = streak_from_dates(ok, as_of=end) if end and end in ok else 0
    return {
        "habit_key": habit_key,
        "as_of": end,
        "current": current,
        "total_days": len(ok),
    }


def habit_gap(rows: list[dict], habit_key: str, *, as_of: str,
              alert_days: int | None = None,
              items: list[dict] | None = None) -> dict | None:
    """断更检测：从 ``as_of`` 往回，连续未完成（无行或 done=0）天数 ≥ alert_days。

    返回 ``{"habit_key", "gap_days", "alert_days", "as_of", "triggered"}``；
    目录里找不到该项时返回 None。
    """
    catalog = items if items is not None else HABITS
    spec = habit_by_key(habit_key, items=catalog)
    if spec is None:
        return None
    threshold = alert_days if alert_days is not None else int(spec.get("alert_days") or 0)
    if threshold <= 0:
        return {
            "habit_key": habit_key,
            "gap_days": 0,
            "alert_days": threshold,
            "as_of": as_of,
            "triggered": False,
        }

    by_date = {
        r["date"]: int(r.get("done") or 0)
        for r in rows if r["habit_key"] == habit_key
    }
    cur = datetime.strptime(as_of, "%Y-%m-%d")
    gap = 0
    # 最多回溯 alert_days + 缓冲，避免无限循环
    for _ in range(threshold + 366):
        d = cur.strftime("%Y-%m-%d")
        done = by_date.get(d)
        if done == 1:
            break
        gap += 1
        cur -= timedelta(days=1)
        if gap >= threshold:
            break
    return {
        "habit_key": habit_key,
        "gap_days": gap,
        "alert_days": threshold,
        "as_of": as_of,
        "triggered": gap >= threshold,
        "label": spec.get("label") or habit_key,
    }


def detect_gaps(rows: list[dict], *, as_of: str,
                items: list[dict] | None = None) -> list[dict]:
    """对目录内全部习惯做断更检测；只返回 ``triggered=True`` 的项。"""
    catalog = items if items is not None else HABITS
    out = []
    for spec in catalog:
        g = habit_gap(rows, spec["key"], as_of=as_of, items=catalog)
        if g and g["triggered"]:
            out.append(g)
    return out


def key_overlap(habit_keys: set[str] | list[str],
                track_keys: set[str] | list[str]) -> list[str]:
    """R3：habit_key ∩ item_key 交集（有序列表）；空 = 隔离完好。"""
    return sorted(set(habit_keys) & set(track_keys))
