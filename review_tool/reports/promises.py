"""承诺对账报告：改进点 / 明日 Top 3 的兑现率（独立指标区，不参与四维）。

用法:
    python -m review_tool promises                 # 全部历史
    python -m review_tool promises 2026-10-14 2026-10-21
    python -m review_tool promises --json

设计红线（写在前面，改代码前先读）
--------------------------------
1. **只做证据型判定**：判据一律来自**次日**已入库的结构化字段
   （``learn_h`` / ``exercise_min`` / ``fat_g`` / ``bedtime`` / ``deepwork_h`` /
   ``phone_h`` / ``personal_tracks.done``），可复现、可单测，不做语义猜测。
2. **判不了就说判不了**：映射不到字段的承诺记 ``unmapped``，**不算未兑现**。
3. **次日没写复盘**记 ``no_data``，也不算未兑现 —— 否则「没写复盘」会被
   伪装成「承诺没做到」，冤枉一整类情况。
4. **兑现率只在「可判定」子集上算**，分子分母都在输出里露出来。
5. **不进四维评分、不加惩罚**：它是镜子，不是鞭子。

``date`` 是写下承诺那天，对账对象是**次日**。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

from ..config import PROMISE_BUCKETS, PROMISE_KINDS
from ..core.promises import bucket_label, extract_constraints
from ..core.util import minutes_to_clock
from ..storage.db import init_db, load_promises

STATUS_LABELS = {
    "fulfilled": "兑现",
    "missed": "未兑现",
    "unmapped": "无法判定",
    "no_data": "次日未记录",
}

# 判定顺序：越靠前越严格。用于汇总时取「最需要关注」的状态。
_STATUS_ORDER = ["missed", "fulfilled", "no_data", "unmapped"]

# 饮食类承诺的字段线索（单位是 g 时按这些词选列）
_DIET_FIELDS = [
    ("脂肪", "fat_g", "脂肪", "g"),
    ("碳水", "carbs_g", "碳水", "g"),
    ("蛋白质", "protein_g", "蛋白质", "g"),
    ("热量", "diet_kcal", "热量", "kcal"),
    ("kcal", "diet_kcal", "热量", "kcal"),
    ("大卡", "diet_kcal", "热量", "kcal"),
]

_SUPPLEMENT_KEYWORDS = next(
    (b["keywords"] for b in PROMISE_BUCKETS if b["key"] == "supplement"), []
)


def _next_day(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def _num(v) -> float | None:
    return float(v) if v is not None else None


def _bedtime_in_frame(bedtime, clock) -> int:
    """把入睡时刻换算到与目标时刻同一个坐标系。

    存储是「当日 00:00 起的分钟」：23:40=1420、01:29=89。
    目标是晚上（clock ≥ 12:00）→ 凌晨入睡值 +1440，迟到者自然比目标大；
    目标是凌晨（clock < 12:00）→ 晚上入睡值 -1440（变负数，表示更早），
    这样「目标 00:30、实际 23:20」会判成**达标**而不是「晚了 23 小时」。
    """
    b = int(bedtime)
    if clock < 720:
        return b - 1440 if b >= 720 else b
    return b + 1440 if b < 720 else b


def _judge_learn(cons, nxt, tracks, logs) -> tuple[str, str]:
    target = cons.get("minutes")
    hours = _num(nxt.get("learn_h"))
    actual = hours * 60 if hours is not None else None
    if target:
        if actual is None:
            return "unmapped", "次日无学习时长"
        ok = actual >= target
        return (
            ("fulfilled" if ok else "missed"),
            f"学习 {actual:.0f}min / 目标 {target:.0f}min",
        )
    if actual:
        return "fulfilled", f"学习 {actual:.0f}min"
    if logs:
        return "fulfilled", f"次日 {len(logs)} 条学习记录"
    if actual == 0:
        return "missed", "次日学习 0"
    return "unmapped", "次日无学习数据"


def _judge_exercise(cons, nxt, tracks, logs) -> tuple[str, str]:
    target = cons.get("minutes")
    actual = _num(nxt.get("exercise_min"))
    if target:
        if actual is None:
            return "unmapped", "次日无运动时长"
        ok = actual >= target
        return (
            ("fulfilled" if ok else "missed"),
            f"运动 {actual:.0f}min / 目标 {target:.0f}min",
        )
    if actual:
        return "fulfilled", f"运动 {actual:.0f}min"
    if actual == 0:
        return "missed", "次日运动 0"
    return "unmapped", "次日无运动数据"


def _judge_diet(cons, nxt, tracks, logs, text: str) -> tuple[str, str]:
    limit = cons.get("limit")
    if not limit:
        return "unmapped", "饮食承诺未写可验证阈值（≤N克 / ≤N大卡）"
    val = limit["value"]
    unit = limit.get("unit")

    if unit == "kcal":
        field, label, suffix = "diet_kcal", "热量", "kcal"
    else:
        field = label = suffix = None
        for word, col, cn, sfx in _DIET_FIELDS:
            if word in text:
                field, label, suffix = col, cn, sfx
                break
        if field is None:
            field, label, suffix = "fat_g", "脂肪", "g"

    actual = _num(nxt.get(field))
    if actual is None:
        return "unmapped", f"次日无{label}记录"
    ok = actual <= val
    return (
        ("fulfilled" if ok else "missed"),
        f"{label} {actual:g}{suffix} / 上限 {val:g}{suffix}",
    )


def _judge_sleep(cons, nxt, tracks, logs, text: str) -> tuple[str, str]:
    clock = cons.get("clock")
    if clock is None:
        return "unmapped", "睡眠承诺未写目标时刻（如 23:30）"
    bedtime = nxt.get("bedtime")
    if bedtime is None:
        return "unmapped", "次日无入睡时间"
    b = _bedtime_in_frame(bedtime, clock)
    ok = b <= clock
    shown = b % 1440
    return (
        ("fulfilled" if ok else "missed"),
        f"入睡 {minutes_to_clock(shown)} / 目标 ≤{minutes_to_clock(clock)}",
    )


def _judge_phone(cons, nxt, tracks, logs, text: str) -> tuple[str, str]:
    limit = cons.get("limit")
    if not limit:
        return "unmapped", "手机承诺未写上限（如 ≤1h）"
    val = limit["value"]
    actual = _num(nxt.get("phone_h"))
    if actual is None:
        return "unmapped", "次日无屏幕时长"
    if limit.get("unit") == "min":
        val = val / 60.0
    ok = actual <= val
    return (
        ("fulfilled" if ok else "missed"),
        f"屏幕 {actual:g}h / 上限 {val:g}h",
    )


def _judge_work(cons, nxt, tracks, logs) -> tuple[str, str]:
    """工作类承诺：**必须带具体时长才判**。

    「migration 文件夹彻底修复」这种承诺，用 ``deepwork_h > 0`` 去核对是荒谬的 ——
    那只证明「那天上过班」（库里 92% 的天都有深度工作记录），会让兑现率虚高到 100%。
    所以无时长约束时一律 ``unmapped``，把「判不了」老实说出来。
    """
    target = cons.get("minutes")
    if not target:
        return "unmapped", "工作类承诺需写具体时长（如 5h）才能核对"
    hours = _num(nxt.get("deepwork_h"))
    if hours is None:
        return "unmapped", "次日无深度工作时长"
    actual = hours * 60
    ok = actual >= target
    return (
        ("fulfilled" if ok else "missed"),
        f"深度工作 {actual:.0f}min / 目标 {target:.0f}min",
    )


def _judge_supplement(cons, nxt, tracks, logs, text: str) -> tuple[str, str]:
    low = (text or "").lower()
    hits = [kw for kw in _SUPPLEMENT_KEYWORDS if kw.lower() in low]
    if not hits:
        return "unmapped", "承诺里没点名具体补剂"
    matched = [
        t
        for t in tracks
        if any(
            kw.lower() in str(t.get("item") or "").lower()
            or kw.lower() in str(t.get("item_key") or "").lower()
            for kw in hits
        )
    ]
    if not matched:
        return "unmapped", "次日打卡里没有对应补剂项"
    done = [t for t in matched if t.get("done")]
    if done:
        names = "、".join(str(t.get("item") or t.get("item_key")) for t in done)
        return "fulfilled", f"已勾：{names}"
    names = "、".join(str(t.get("item") or t.get("item_key")) for t in matched)
    return "missed", f"未勾：{names}"


_HANDLERS = {
    "learn": _judge_learn,
    "exercise": _judge_exercise,
    "diet": _judge_diet,
    "sleep": _judge_sleep,
    "phone": _judge_phone,
    "work": _judge_work,
    "supplement": _judge_supplement,
}


def judge(item: dict, nxt: dict | None, tracks: list[dict], logs: list[dict]) -> tuple[str, str]:
    """单条承诺 → ``(status, evidence)``。"""
    if nxt is None:
        return "no_data", "次日无复盘记录"
    bucket = item.get("bucket")
    if not bucket:
        return "unmapped", "未归类到可验证指标"
    handler = _HANDLERS.get(bucket)
    if handler is None:
        return "unmapped", f"桶 {bucket} 暂无判定规则"
    cons = extract_constraints(item.get("text") or "")
    if bucket in ("diet", "sleep", "phone", "supplement"):
        return handler(cons, nxt, tracks, logs, item.get("text") or "")
    return handler(cons, nxt, tracks, logs)


def _prefetch(conn, dates: list[str]) -> tuple[dict, dict, dict]:
    """一次取齐所有次日的数据，避免逐条查库。"""
    if not dates:
        return {}, {}, {}
    marks = ",".join("?" * len(dates))
    days = {
        r["date"]: dict(r)
        for r in conn.execute(
            f"SELECT * FROM daily_reviews WHERE date IN ({marks})", dates
        )
    }
    tracks: dict[str, list[dict]] = {d: [] for d in dates}
    for r in conn.execute(
        f"SELECT * FROM personal_tracks WHERE date IN ({marks}) ORDER BY date, track_key",
        dates,
    ):
        tracks.setdefault(r["date"], []).append(dict(r))
    logs: dict[str, list[dict]] = {d: [] for d in dates}
    for r in conn.execute(
        f"SELECT * FROM learning_logs WHERE date IN ({marks})", dates
    ):
        logs.setdefault(r["date"], []).append(dict(r))
    return days, tracks, logs


def collect(
    conn,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """汇总结论（文本 / JSON 共用）。"""
    rows = [dict(r) for r in load_promises(conn, start=start, end=end)]
    for r in rows:
        r["due"] = _next_day(r["date"])

    dates = sorted({r["due"] for r in rows})
    days, tracks, logs = _prefetch(conn, dates)

    # 对账日 >= 今天就还没过完 —— 此刻判「未兑现」是冤枉。
    today = datetime.now().strftime("%Y-%m-%d")
    for r in rows:
        due = r["due"]
        if due >= today:
            status, evidence = "no_data", "对账日尚未结束"
        else:
            status, evidence = judge(
                r, days.get(due), tracks.get(due) or [], logs.get(due) or []
            )
        r["status"] = status
        r["evidence"] = evidence
        r["bucket_label"] = bucket_label(r.get("bucket"))

    counts = {k: 0 for k in STATUS_LABELS}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    judged = counts["fulfilled"] + counts["missed"]
    rate = (counts["fulfilled"] / judged) if judged else None

    # 按桶
    by_bucket: dict[str, dict] = {}
    for r in rows:
        key = r.get("bucket") or "_none"
        b = by_bucket.setdefault(
            key,
            {
                "bucket": r.get("bucket"),
                "label": r.get("bucket_label"),
                "total": 0,
                "fulfilled": 0,
                "missed": 0,
                "unmapped": 0,
                "no_data": 0,
            },
        )
        b["total"] += 1
        b[r["status"]] = b.get(r["status"], 0) + 1
    for b in by_bucket.values():
        j = b["fulfilled"] + b["missed"]
        b["judged"] = j
        b["rate"] = (b["fulfilled"] / j) if j else None

    # 按 kind
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = r["kind"]
        b = by_kind.setdefault(
            k,
            {
                "kind": k,
                "label": (PROMISE_KINDS.get(k) or {}).get("label", k),
                "total": 0,
                "fulfilled": 0,
                "missed": 0,
                "unmapped": 0,
                "no_data": 0,
            },
        )
        b["total"] += 1
        b[r["status"]] = b.get(r["status"], 0) + 1
    for b in by_kind.values():
        j = b["fulfilled"] + b["missed"]
        b["judged"] = j
        b["rate"] = (b["fulfilled"] / j) if j else None

    dates_all = sorted({r["date"] for r in rows})
    # 「无法判定」再拆两类：压根没归类 vs 有话题但承诺里没写可验证的数字
    unmapped_no_bucket = sum(
        1 for r in rows if r["status"] == "unmapped" and not r.get("bucket")
    )
    unmapped_no_constraint = sum(
        1 for r in rows if r["status"] == "unmapped" and r.get("bucket")
    )
    return {
        "start": start,
        "end": end,
        "date_from": dates_all[0] if dates_all else None,
        "date_to": dates_all[-1] if dates_all else None,
        "days": len(dates_all),
        "total": len(rows),
        "counts": counts,
        "judged": judged,
        "rate": rate,
        "unmapped_no_bucket": unmapped_no_bucket,
        "unmapped_no_constraint": unmapped_no_constraint,
        "by_bucket": sorted(
            by_bucket.values(), key=lambda x: (-x["total"], str(x["label"]))
        ),
        "by_kind": sorted(by_kind.values(), key=lambda x: x["kind"]),
        "items": rows,
    }


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def render(result: dict, *, show_items: int = 12) -> str:
    c = result["counts"]
    L: list[str] = []
    span = (
        f"{result['date_from']} ~ {result['date_to']}"
        if result["date_from"]
        else "（无数据）"
    )
    L.append(f"承诺对账 · {span}")
    L.append("-" * 62)
    if not result["total"]:
        L.append("没有承诺记录。先在复盘的「三、一个改进点」「四、明日 Top 3」里写点什么。")
        return "\n".join(L)

    L.append(
        f"总承诺 {result['total']} 条（{result['days']} 天）"
        f" · 可判定 {result['judged']} 条 · "
        f"**兑现率 {_pct(result['rate'])}**（只在可判定子集上算）"
    )
    L.append("")
    for key in ("fulfilled", "missed", "no_data", "unmapped"):
        n = c.get(key, 0)
        if not n:
            continue
        share = n / result["total"] * 100
        L.append(f"  {STATUS_LABELS[key]:6s} {n:4d} 条  {share:5.1f}%")

    if c.get("no_data"):
        L.append("")
        L.append(
            "  ↳ 「次日未记录」= 次日没写复盘，**不算没做到** —— 只是没法核对。"
        )
    if c.get("unmapped"):
        L.append(
            "  ↳ 「无法判定」= 承诺没写可验证的数字或没归到指标，"
            "**不算没做到**。写得越具体（`脂肪≤70g` / `23:30 前` / `60min`）越可判定。"
        )
        nb = result.get("unmapped_no_bucket") or 0
        nc = result.get("unmapped_no_constraint") or 0
        if nb or nc:
            parts = []
            if nc:
                parts.append(f"有话题但没写数字 {nc} 条（如「深度工作」缺 `5h`）")
            if nb:
                parts.append(f"没归到任何指标 {nb} 条（生活琐事 / 工作任务）")
            L.append("     · " + "；".join(parts))

    L.append("")
    L.append("按类型")
    for b in result["by_kind"]:
        L.append(
            f"  {b['label']:10s} {b['total']:3d} 条 · 可判定 {b['judged']:3d} · "
            f"兑现率 {_pct(b['rate'])}"
        )

    L.append("")
    L.append("按话题")
    for b in result["by_bucket"]:
        label = b["label"] or "未归类"
        L.append(
            f"  {label:6s} {b['total']:3d} 条 · 兑现 {b['fulfilled']:3d} · "
            f"未兑现 {b['missed']:3d} · 无法判定 {b['unmapped']:3d} · "
            f"兑现率 {_pct(b['rate'])}"
        )

    items = [r for r in result["items"] if r["status"] in ("fulfilled", "missed")]
    if items:
        items = items[-show_items:]
        L.append("")
        L.append(f"已判定明细（最近 {len(items)} 条）")
        for r in items:
            mark = "✓" if r["status"] == "fulfilled" else "✗"
            text = r["text"]
            if len(text) > 46:
                text = text[:46] + "…"
            L.append(
                f"  {mark} {r['date']} [{r['bucket_label']}] {text}"
                f"\n      → {r['evidence']}"
            )

    L.append("")
    L.append("-" * 62)
    L.append("口径：次日证据型判定，不改评分、不加惩罚。")
    L.append("来源：复盘 md「三、一个改进点」「四、明日 Top 3」→ ingest。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    start = args[0] if len(args) >= 1 else None
    end = args[1] if len(args) >= 2 else None
    if start and end is None:
        end = start

    conn = init_db()
    try:
        result = collect(conn, start=start, end=end)
    finally:
        conn.close()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
