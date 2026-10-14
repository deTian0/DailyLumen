"""正向连续天数（streak）：复盘 / 训练达标 / 打卡完成。

与 ``fuse`` 里的**负面**连续（低分 / 晚睡）相对 —— 这里统计「我连续 N 天做到了」。
口径以库为准；训练用 ``training_day=1`` 且 ``exercise_min > 0``；
打卡用 ``personal_tracks.done=1``（按 ``item_key``）。
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _parse(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def streak_from_dates(ok_dates: set[str] | list[str], *, as_of: str | None = None) -> int:
    """从 ``as_of``（默认 = 集合最大日）往回数连续命中天数；中断即停。"""
    if not ok_dates:
        return 0
    ok = set(ok_dates)
    end = as_of or max(ok)
    cur = _parse(end)
    n = 0
    while cur.strftime("%Y-%m-%d") in ok:
        n += 1
        cur -= timedelta(days=1)
    return n


def review_streak(conn, *, as_of: str | None = None) -> dict:
    """复盘连续入库天数（有 ``daily_reviews`` 行即算）。"""
    dates = [r[0] for r in conn.execute("SELECT date FROM daily_reviews ORDER BY date")]
    latest = dates[-1] if dates else None
    end = as_of or latest
    return {
        "kind": "review",
        "label": "复盘入库",
        "as_of": end,
        "current": streak_from_dates(dates, as_of=end) if end else 0,
        "total_days": len(dates),
    }


def training_streak(conn, *, as_of: str | None = None) -> dict:
    """训练达标连续：按日历日往回走，遇到「训练日且未达标」中断；
    非训练日**跳过不打断**（不算入 streak，也不重置）。
    """
    rows = list(conn.execute(
        "SELECT date, training_day, exercise_min FROM daily_reviews ORDER BY date"
    ))
    if not rows:
        return {"kind": "training", "label": "训练达标", "as_of": as_of,
                "current": 0, "total_days": 0}
    by_date = {r["date"]: r for r in rows}
    end = as_of or rows[-1]["date"]
    cur = _parse(end)
    n = 0
    # 最多回溯库跨度 + 缓冲
    for _ in range(len(rows) + 7):
        d = cur.strftime("%Y-%m-%d")
        row = by_date.get(d)
        if row is None:
            break
        if int(row["training_day"] or 0) != 1:
            cur -= timedelta(days=1)
            continue
        if row["exercise_min"] is not None and float(row["exercise_min"]) > 0:
            n += 1
            cur -= timedelta(days=1)
            continue
        break
    return {
        "kind": "training",
        "label": "训练达标",
        "as_of": end,
        "current": n,
        "total_days": sum(1 for r in rows if int(r["training_day"] or 0) == 1),
    }


def track_streak(conn, item_key: str, *, as_of: str | None = None) -> dict:
    """某 ``item_key`` 连续完成天数（当日至少一条 ``done=1``）。"""
    rows = conn.execute(
        "SELECT date, MAX(done) AS done FROM personal_tracks "
        "WHERE item_key=? GROUP BY date ORDER BY date",
        (item_key,),
    ).fetchall()
    ok = {r["date"] for r in rows if int(r["done"] or 0) == 1}
    # as_of 默认取该 item 最近有记录的日子；若指定 as_of 则按日历连续
    end = as_of
    if end is None and rows:
        end = rows[-1]["date"]
    # 日历连续：as_of 当天必须 done，否则 0
    current = 0
    if end and end in ok:
        current = streak_from_dates(ok, as_of=end)
    return {
        "kind": "track",
        "label": f"打卡:{item_key}",
        "item_key": item_key,
        "as_of": end,
        "current": current,
        "total_days": len(ok),
    }


def summarize_streaks(conn, *, as_of: str | None = None,
                      track_keys: list[str] | None = None) -> dict:
    """汇总一轮正向 streak（供 week/month / 独立展示）。"""
    rev = review_streak(conn, as_of=as_of)
    train = training_streak(conn, as_of=as_of)
    keys = track_keys
    if keys is None:
        keys = [r[0] for r in conn.execute(
            "SELECT item_key FROM personal_tracks GROUP BY item_key ORDER BY item_key"
        )]
    tracks = [track_streak(conn, k, as_of=as_of) for k in keys]
    return {"review": rev, "training": train, "tracks": tracks}


def render_streaks(summary: dict) -> str:
    """渲染简短段落。"""
    L = ["", "  ---- 正向连续（streak）----"]
    rev = summary["review"]
    L.append(f"  复盘入库      : 连续 {rev['current']} 天"
             + (f"（截至 {rev['as_of']}）" if rev.get("as_of") else ""))
    tr = summary["training"]
    L.append(f"  训练达标      : 连续 {tr['current']} 个训练日"
             + (f"（截至 {tr['as_of']}）" if tr.get("as_of") else ""))
    tops = sorted(summary.get("tracks") or [], key=lambda x: -x["current"])[:6]
    if tops and any(t["current"] for t in tops):
        bits = "、".join(f"{t['item_key']}×{t['current']}" for t in tops if t["current"])
        L.append(f"  打卡连续      : {bits}" if bits else "  打卡连续      : 无")
    else:
        L.append("  打卡连续      : 无")
    return "\n".join(L)
