"""周分析 / 月分析：从 SQLite 用 SQL 聚合，打印可读报告。

用法:
    python -m review_tool week            # 所有周汇总
    python -m review_tool week 32         # 指定 ISO 周
    python -m review_tool week 41 --write # 落盘周总结 md（幂等，需 --force 覆盖）
    python -m review_tool month           # 当月 (最近一个月) 汇总
    python -m review_tool month 202608    # 指定月份 202608
    python -m review_tool month 202609 --write [--force] [--check]

口径说明（重要）
----------------
「训练日运动达标」按**二态**统计（v1.3.2 起）：训练日未记录按 0 计，
直接落入「未达标」，不再保留「未记录」豁免态 ——「没填」即「没练」，
达成分母恒等于训练日总数：

    达标 2 / 4 天 = 50%（其中 1 天为描述折算，2 天未记录按 0 计）

历史背景：更早版本曾把「字段空着」与「没运动」混为一谈（v1.3.0 修复），
v1.3.1 引入折算后仍留「未记录」豁免；v1.3.2 用户拍板收口为二态。

另外，「运动时长_min」为空但「二、今日三件事」里提到俯卧撑等动作时，
该值会由 bodyweight 模块**折算**补上（``exercise_src='derived'``）。
报告里会把折算天数单独标出来，避免把估算值当成计时记录。

v1.8.0 起 ``--write`` 把结构化骨架落盘到 ``每日复盘/复盘/YYYY-MM/``；
关键发现 / 行动清单等叙事段**不自动生成**（默认不回填既有手写件）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from ..config import DIMENSIONS, GENERATED_DIR
from ..core.learning import week_rollup
from ..core.util import minutes_to_clock
from ..storage.db import (
    COLUMNS,
    init_db,
    load_habit_logs,
    load_learning_logs,
    load_training,
)
from .streak import render_streaks, summarize_streaks
from .tutor import week_section_lines

DIM_LABEL = {
    "health_score": "健康", "work_score": "工作",
    "learn_score": "学习", "life_score": "生活",
}

# 数据完整度考察的核心字段（叙事型字段如 summary 不计入）
_CORE_FIELDS = [
    "training_day", "sleep_h", "sleep_quality", "bedtime", "exercise_min",
    "diet_kcal", "phone_h", "deepwork_h", "learn_h", "life_h",
]

_WEEK_FIELDS = [
    ("sleep_h", "睡眠"), ("phone_h", "屏幕"),
    ("deepwork_h", "深度工作"), ("diet_kcal", "饮食"),
]
_MONTH_FIELDS = [
    ("sleep_h", "睡眠"), ("sleep_quality", "睡眠质量"),
    ("phone_h", "屏幕"), ("deepwork_h", "深度工作"),
    ("diet_kcal", "饮食"),
]

# 标签对齐宽度（按显示列数，中日韩字符算 2 列）
_LABEL_WIDTH = 12


def _check_col(col: str) -> str:
    if col not in COLUMNS:
        raise ValueError(f"未知数据列: {col!r}")
    return col


def _avg(conn, col: str, where: str = "", params: tuple = ()) -> float | None:
    sql = f"SELECT AVG({_check_col(col)}) FROM daily_reviews"
    if where:
        sql += f" WHERE {where}"
    v = conn.execute(sql, params).fetchone()[0]
    return round(v, 2) if v is not None else None


def _bar(v: float | None, width: int = 10) -> str:
    if v is None:
        return ""
    filled = int(round(v / 10 * width))
    return "[" + "█" * filled + "·" * (width - filled) + "]"


def _pct(v: float | None) -> str:
    return f"{round(v * 100)}%" if v is not None else "-"


def _line(label: str, value, width: int = _LABEL_WIDTH) -> str:
    """中文标签行（按显示宽度对齐：中日韩字符按 2 列计）。"""
    dw = sum(2 if ord(ch) > 0x2E80 else 1 for ch in label)
    return f"  {label}{' ' * max(0, width - dw)}: {value}"


def _macro_stats(conn, where: str = "", params: tuple = ()) -> dict | None:
    """三大营养素结构化统计：日均碳水/脂肪/蛋白质 + 宏量热量与供能占比。

    carbs/fat/protein 按 4/9/4 kcal 每克折算。任一宏量都未记录时返回 None。
    """
    cond = f" WHERE {where}" if where else ""
    n, c, f, p = conn.execute(
        f"SELECT COUNT(carbs_g), AVG(carbs_g), AVG(fat_g), AVG(protein_g) "
        f"FROM daily_reviews{cond}",
        params,
    ).fetchone()
    if not n:
        return None
    c, f, p = round(c), round(f), round(p)
    kc, kf, kp = 4 * c, 9 * f, 4 * p
    total = kc + kf + kp
    if total <= 0:
        return None
    pc, pf = round(kc / total * 100), round(kf / total * 100)
    return {
        "days": n, "carbs_g": c, "fat_g": f, "protein_g": p, "kcal": total,
        "split_pct": {"carbs": pc, "fat": pf, "protein": 100 - pc - pf},
    }


def _macro_lines(macros: dict | None) -> str:
    """把宏量统计渲染成两行文本（无数据返回空串）。"""
    if not macros:
        return ""
    s = macros["split_pct"]
    return (
        _line("宏量日均", f"碳水 {macros['carbs_g']}g / 脂肪 {macros['fat_g']}g"
                          f" / 蛋白质 {macros['protein_g']}g (记录 {macros['days']} 天)") + "\n"
        + _line("估算宏量热量", f"{macros['kcal']} kcal ［碳水 {s['carbs']}%・"
                               f"脂肪 {s['fat']}%・蛋白质 {s['protein']}%］")
    )


def training_stats(conn, where: str, params: tuple) -> dict:
    """训练日运动二态统计（v1.3.2 口径）。

    total=训练日总数；done=达标(>0)；derived=描述折算；zero=未记录按 0 计；
    missing=仍无任何数据的天数（理论上仅存在于未重跑 ingest 的旧库）。
    """
    total, done, derived, zero, missing = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN training_day=1 THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_min > 0 THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_src='derived' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_src='zero' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_min IS NULL THEN 1 ELSE 0 END) "
        f"FROM daily_reviews WHERE {where}",
        params,
    ).fetchone()
    total = total or 0
    done = done or 0
    derived = derived or 0
    zero = zero or 0
    missing = missing or 0
    return {
        "total": total,
        "recorded": total - missing,
        "done": done,
        "derived": derived,
        "zero": zero,
        "missing": missing,
    }


def derived_count(conn, where: str, params: tuple) -> int:
    """该区间内运动时长来自「描述折算」的天数（含非训练日）。"""
    return conn.execute(
        f"SELECT COUNT(*) FROM daily_reviews WHERE {where} AND exercise_src='derived'",
        params,
    ).fetchone()[0]


def _training_line(st: dict) -> str:
    total, done, missing = st["total"], st["done"], st["missing"]
    derived, zero = st.get("derived", 0), st.get("zero", 0)
    if total == 0:
        return _line("训练日运动", "无训练日记录")
    if missing == total:
        return _line("训练日运动", f"训练日 {total} 天均无运动数据（旧库未重跑 ingest）")
    text = f"达标 {done}/{total} 天 = {_pct(done / total)}"
    notes = []
    if derived:
        notes.append(f"{derived} 天为描述折算")
    if zero:
        notes.append(f"{zero} 天未记录按 0 计")
    if notes:
        text += f"（其中 {'，'.join(notes)}）"
    if missing:
        text += f"  ⚠️ 另有 {missing} 天无数据（旧库未重跑 ingest）"
    return _line("训练日运动", text)


def completeness(conn, where: str, params: tuple) -> tuple[float, list[tuple[str, int]]]:
    """核心字段完整度 -> (完整率, [(字段, 缺失天数), ...] 按缺失降序)。"""
    n = conn.execute(
        f"SELECT COUNT(*) FROM daily_reviews WHERE {where}", params
    ).fetchone()[0]
    if not n:
        return 0.0, []
    missing: list[tuple[str, int]] = []
    for col in _CORE_FIELDS:
        m = conn.execute(
            f"SELECT COUNT(*) FROM daily_reviews WHERE {where} AND {col} IS NULL",
            params,
        ).fetchone()[0]
        if m:
            missing.append((col, m))
    missing.sort(key=lambda x: -x[1])
    filled = n * len(_CORE_FIELDS) - sum(m for _, m in missing)
    return filled / (n * len(_CORE_FIELDS)), missing


def track_adherence(conn, where: str, params: tuple) -> dict:
    """周期内个人打卡依从率（按 ``item_key`` 聚合，按 ``category`` 分组）。

    口径与 ``pipeline/export._adherence`` 一致：完成率 = done 次数 / 有记录次数。
    键来自入库时 ``core/tracks`` 归一化结果 —— **不重造 ID 规则**。
    打卡**不参与四维评分**；与 ClickUp「习惯与打卡」永久分离。

    返回 ``{"items": [...], "categories": [...], "by_week": [...]}``；
    无打卡行时三项皆空列表。
    """
    rows = conn.execute(
        "SELECT pt.category, pt.item_key, MAX(pt.item) AS item, "
        "       COUNT(*) AS recorded, "
        "       SUM(CASE WHEN pt.done=1 THEN 1 ELSE 0 END) AS done "
        "FROM personal_tracks pt "
        "JOIN daily_reviews dr ON dr.date = pt.date "
        f"WHERE {where} "
        "GROUP BY pt.category, pt.item_key "
        "ORDER BY pt.category, pt.item_key",
        params,
    ).fetchall()
    items: list[dict] = []
    cat_acc: dict[str, dict] = {}
    for r in rows:
        recorded = int(r["recorded"] or 0)
        done = int(r["done"] or 0)
        rate = round(done / recorded, 4) if recorded else None
        cat = r["category"]
        items.append({
            "category": cat,
            "item_key": r["item_key"],
            "item": r["item"],
            "recorded": recorded,
            "done": done,
            "adherence": rate,
        })
        bucket = cat_acc.setdefault(cat, {"recorded": 0, "done": 0})
        bucket["recorded"] += recorded
        bucket["done"] += done

    categories = []
    for cat in sorted(cat_acc):
        b = cat_acc[cat]
        categories.append({
            "category": cat,
            "recorded": b["recorded"],
            "done": b["done"],
            "adherence": round(b["done"] / b["recorded"], 4) if b["recorded"] else None,
        })

    # 周期内按 ISO 周的总体依从率（可选趋势；单周时通常只有一行）
    week_rows = conn.execute(
        "SELECT dr.iso_week AS iso_week, "
        "       COUNT(*) AS recorded, "
        "       SUM(CASE WHEN pt.done=1 THEN 1 ELSE 0 END) AS done "
        "FROM personal_tracks pt "
        "JOIN daily_reviews dr ON dr.date = pt.date "
        f"WHERE {where} "
        "GROUP BY dr.iso_week "
        "ORDER BY dr.iso_week",
        params,
    ).fetchall()
    by_week = []
    for r in week_rows:
        recorded = int(r["recorded"] or 0)
        done = int(r["done"] or 0)
        by_week.append({
            "iso_week": r["iso_week"],
            "recorded": recorded,
            "done": done,
            "adherence": round(done / recorded, 4) if recorded else None,
        })

    return {"items": items, "categories": categories, "by_week": by_week}


def habit_adherence(conn, where: str, params: tuple) -> dict:
    """周期内行为习惯依从率（按 ``habit_key`` 聚合）。

    与 ``track_adherence``（补剂/护肤）**分栏不混**（R3）。
    完成率 = done 次数 / 有记录次数；不参与四维（G5）。
    """
    dates = [
        r[0] for r in conn.execute(
            f"SELECT date FROM daily_reviews WHERE {where} ORDER BY date",
            params,
        )
    ]
    if not dates:
        return {"items": [], "by_week": []}
    rows = load_habit_logs(conn, start=dates[0], end=dates[-1])
    date_set = set(dates)
    # 仅计入本周期有复盘日的习惯行
    filtered = [r for r in rows if r["date"] in date_set]

    acc: dict[str, dict] = {}
    for r in filtered:
        key = r["habit_key"]
        b = acc.setdefault(key, {
            "habit_key": key, "item": r["item"], "recorded": 0, "done": 0,
        })
        b["recorded"] += 1
        if int(r["done"] or 0) == 1:
            b["done"] += 1
        if r["item"]:
            b["item"] = r["item"]

    items = []
    for key in sorted(acc):
        b = acc[key]
        rate = round(b["done"] / b["recorded"], 4) if b["recorded"] else None
        items.append({**b, "adherence": rate})

    # 按 ISO 周总体依从率
    week_of = {
        r[0]: r[1] for r in conn.execute(
            f"SELECT date, iso_week FROM daily_reviews WHERE {where}", params
        )
    }
    week_acc: dict[int, dict] = {}
    for r in filtered:
        wk = week_of.get(r["date"])
        if wk is None:
            continue
        b = week_acc.setdefault(wk, {"recorded": 0, "done": 0})
        b["recorded"] += 1
        if int(r["done"] or 0) == 1:
            b["done"] += 1
    by_week = []
    for wk in sorted(week_acc):
        b = week_acc[wk]
        by_week.append({
            "iso_week": wk,
            "recorded": b["recorded"],
            "done": b["done"],
            "adherence": round(b["done"] / b["recorded"], 4) if b["recorded"] else None,
        })
    return {"items": items, "by_week": by_week}


def _track_adherence_lines(adh: dict | None) -> list[str]:
    """渲染「个人打卡依从率」段落；无数据时给一行说明。"""
    L: list[str] = []
    L.append("")
    L.append("  ---- 个人打卡依从率（不计入四维评分）----")
    if not adh or not adh.get("items"):
        L.append(_line("打卡", "本周期无 personal_tracks 记录"))
        return L
    for it in adh["items"]:
        rate = _pct(it["adherence"])
        L.append(_line(
            f"{it['category']}/{it['item_key']}",
            f"{rate}（{it['done']}/{it['recorded']}）· {it['item']}",
        ))
    if adh.get("categories"):
        L.append(_line("类别小计", ""))
        for c in adh["categories"]:
            L.append(_line(
                f"  · {c['category']}",
                f"{_pct(c['adherence'])}（{c['done']}/{c['recorded']}）",
            ))
    weeks = adh.get("by_week") or []
    if len(weeks) >= 2:
        bits = [f"W{w['iso_week']} {_pct(w['adherence'])}" for w in weeks]
        L.append(_line("周趋势", " → ".join(bits)))
    return L


def _habit_adherence_lines(adh: dict | None) -> list[str]:
    """渲染「行为习惯依从率」段落（与补剂分栏）。"""
    L: list[str] = []
    L.append("")
    L.append("  ---- 行为习惯依从率（不计入四维评分 · 与补剂分栏）----")
    if not adh or not adh.get("items"):
        L.append(_line("习惯", "本周期无 habit_logs 记录"))
        return L
    for it in adh["items"]:
        L.append(_line(
            it["habit_key"],
            f"{_pct(it['adherence'])}（{it['done']}/{it['recorded']}）· {it['item']}",
        ))
    weeks = adh.get("by_week") or []
    if len(weeks) >= 2:
        bits = [f"W{w['iso_week']} {_pct(w['adherence'])}" for w in weeks]
        L.append(_line("周趋势", " → ".join(bits)))
    return L


def learning_week(conn, where: str, params: tuple) -> dict:
    """周期内学习记录汇总（独立指标区，不计入四维）。"""
    dates = [
        r[0] for r in conn.execute(
            f"SELECT date FROM daily_reviews WHERE {where} ORDER BY date",
            params,
        )
    ]
    if not dates:
        return week_rollup([])
    logs = [
        dict(r) for r in load_learning_logs(
            conn, start=dates[0], end=dates[-1]
        )
        if r["date"] in set(dates)
    ]
    return week_rollup(logs)


def _learning_week_lines(week: dict | None) -> list[str]:
    """渲染「学习记录」段落（独立指标区）。"""
    L: list[str] = []
    L.append("")
    L.append("  ---- 学习记录（不计入四维评分）----")
    L.extend(week_section_lines(week or {}))
    return L


def _training_structure_lines(ts: dict | None) -> list[str]:
    """渲染「训练结构」段落（独立指标区）。"""
    L: list[str] = []
    L.append("")
    L.append("  ---- 训练结构（不计入四维评分）----")
    if not ts or not ts.get("sessions"):
        L.append(_line("训练明细", "本周期无 training_sessions 记录"))
        return L
    L.append(_line(
        "课次/动作",
        f"{ts['sessions']} 课 / {ts['items']} 条明细",
    ))
    for day in ts.get("by_date") or []:
        moves = "、".join(day.get("moves") or []) or "—"
        plan = day.get("plan_name") or "—"
        mins = day.get("total_min")
        mins_s = f"{mins}min" if mins is not None else "—"
        L.append(_line(day["date"], f"{plan} · {mins_s} · {moves}"))
    for m in (ts.get("by_move") or [])[:8]:
        L.append(_line(
            f"  · {m['item_key']}",
            f"{m['sessions']} 次 · 体积合计 {m['volume']}",
        ))
    return L


def collect(conn, where: str, params: tuple, title: str) -> dict | None:
    """把周 / 月报告涉及的全部数字收集成结构化 dict（渲染与 JSON 共用同一份数据）。

    返回 None 表示该区间没有任何记录。要点：**先取数、再渲染**，
    这样 `--json` 与文本报告不可能出现口径分歧。
    """
    n = conn.execute(
        f"SELECT COUNT(*) FROM daily_reviews WHERE {where}", params
    ).fetchone()[0]
    if not n:
        return None

    dims = {DIM_LABEL[d]: _avg(conn, d, where, params) for d in DIMENSIONS}
    adh = conn.execute(
        f"SELECT AVG(commute_done), AVG(breakfast_on_time) "
        f"FROM daily_reviews WHERE {where}",
        params,
    ).fetchone()
    fields = _MONTH_FIELDS if "month" in where else _WEEK_FIELDS
    rate, missing = completeness(conn, where, params)
    worst = min(
        ((DIM_LABEL[d], dims[DIM_LABEL[d]]) for d in DIMENSIONS),
        key=lambda x: x[1] if x[1] is not None else 99,
    )
    return {
        "title": title,
        "days": n,
        "system_avg": _avg(conn, "system_score", where, params),
        "dims": dims,
        "breakfast_on_time_pct": adh[1],   # 0-1 浮点，渲染走 _pct
        "commute_pct": adh[0],
        "training": training_stats(conn, where, params),
        "derived_days": derived_count(conn, where, params),
        "field_avgs": {lbl: _avg(conn, col, where, params) for col, lbl in fields},
        "macros": _macro_stats(conn, where, params),
        "completeness": {
            "rate": round(rate, 4),
            "rate_pct": round(rate * 100),
            "missing": [{"field": c, "days": m} for c, m in missing],
        },
        "worst_dim": {"name": worst[0], "value": worst[1]},
        "track_adherence": track_adherence(conn, where, params),
        "habit_adherence": habit_adherence(conn, where, params),
        "streaks": _streaks_for_scope(conn, where, params),
        "training_structure": training_structure(conn, where, params),
        "learning_week": learning_week(conn, where, params),
    }


def training_structure(conn, where: str, params: tuple) -> dict:
    """周期内训练课 / 动作明细汇总（独立指标区，不计入四维）。

    返回 ``{"sessions": n, "items": n, "by_date": [...], "by_move": [...]}``。
    """
    # 用 daily_reviews 日期集合限定窗口（与 where 口径一致）
    dates = [
        r[0] for r in conn.execute(
            f"SELECT date FROM daily_reviews WHERE {where} ORDER BY date",
            params,
        )
    ]
    if not dates:
        return {"sessions": 0, "items": 0, "by_date": [], "by_move": []}
    data = load_training(conn, start=dates[0], end=dates[-1])
    date_set = set(dates)
    sessions = [dict(r) for r in data["sessions"] if r["date"] in date_set]
    items = [dict(r) for r in data["items"] if r["date"] in date_set]

    by_date_map: dict[str, dict] = {}
    for s in sessions:
        bucket = by_date_map.setdefault(s["date"], {
            "date": s["date"],
            "plan_name": None,
            "total_min": None,
            "moves": [],
        })
        if s["plan_name"] and not bucket["plan_name"]:
            bucket["plan_name"] = s["plan_name"]
        if s["total_min"] is not None:
            bucket["total_min"] = (bucket["total_min"] or 0) + int(s["total_min"])
    for it in items:
        bucket = by_date_map.setdefault(it["date"], {
            "date": it["date"], "plan_name": None, "total_min": None, "moves": [],
        })
        bit = it["item_key"]
        if it["sets"] is not None and it["reps"] is not None:
            bit += f" {it['sets']}×{it['reps']}"
        elif it["minutes"] is not None:
            bit += f" {it['minutes']}min"
        if it["load_kg"] is not None:
            bit += f" @{it['load_kg']}kg"
        bucket["moves"].append(bit)

    move_acc: dict[str, dict] = {}
    for it in items:
        key = it["item_key"]
        b = move_acc.setdefault(key, {"item_key": key, "sessions": 0, "volume": 0})
        b["sessions"] += 1
        if it["sets"] is not None and it["reps"] is not None:
            b["volume"] += int(it["sets"]) * int(it["reps"])

    return {
        "sessions": len(sessions),
        "items": len(items),
        "by_date": [by_date_map[d] for d in sorted(by_date_map)],
        "by_move": sorted(move_acc.values(), key=lambda x: (-x["sessions"], x["item_key"])),
    }


def _streaks_for_scope(conn, where: str, params: tuple) -> dict:
    """周期末日为 as_of；打卡键限于本周期出现过的 item_key。"""
    end = conn.execute(
        f"SELECT MAX(date) FROM daily_reviews WHERE {where}", params
    ).fetchone()[0]
    keys = [r[0] for r in conn.execute(
        "SELECT DISTINCT pt.item_key FROM personal_tracks pt "
        "JOIN daily_reviews dr ON dr.date = pt.date "
        f"WHERE {where} ORDER BY pt.item_key",
        params,
    )]
    return summarize_streaks(conn, as_of=end, track_keys=keys)


def render_summary(s: dict) -> str:
    """把 `collect()` 的结构化结果渲染成可读文本。"""
    L: list[str] = []
    L.append(f"\n{'=' * 52}")
    L.append(f"{s['title']}  (共 {s['days']} 天)")
    L.append(f"{'=' * 52}")
    L.append(_line("记录天数", s["days"]))
    L.append(_line("系统分均值", s["system_avg"]))
    for label, v in s["dims"].items():
        bar = _bar(v) if v else "  - "
        L.append(_line(f"{label}分均值", f"{v}  {bar}"))
    L.append(_line("早餐按时", _pct(s["breakfast_on_time_pct"])))
    L.append(_line("通勤完成", _pct(s["commute_pct"])))
    L.append(_training_line(s["training"]))
    if s["derived_days"]:
        L.append(_line("运动折算", f"{s['derived_days']} 天的运动时长由"
                                   "「三件事」描述折算（非计时记录）"))
    for lbl, v in s["field_avgs"].items():
        L.append(_line(f"{lbl}均值", v))
    ml = _macro_lines(s["macros"])
    if ml:
        L.append(ml)
    detail = "、".join(f"{m['field']}×{m['days']}"
                       for m in s["completeness"]["missing"][:6]) or "无"
    L.append(_line("数据完整度",
                   f"{s['completeness']['rate_pct']}%（核心字段缺失: {detail}）"))
    L.append(f"  >> 最差维度: {s['worst_dim']['name']} ({s['worst_dim']['value']})")
    L.extend(_track_adherence_lines(s.get("track_adherence")))
    L.extend(_habit_adherence_lines(s.get("habit_adherence")))
    L.extend(_training_structure_lines(s.get("training_structure")))
    L.extend(_learning_week_lines(s.get("learning_week")))
    if s.get("streaks"):
        L.append(render_streaks(s["streaks"]))
    return "\n".join(L)


def _report(conn, where: str, params: tuple, title: str) -> dict | None:
    """周 / 月共用的报告主体（文本渲染）。返回结构化结果供上层复用。"""
    s = collect(conn, where, params, title)
    if s is not None:
        print(render_summary(s))
    return s


def _dump(obj) -> None:
    """打印结构化 JSON（供 `--json` 使用）。"""
    import json
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def report_week(conn, iso_week: int | None = None, *, as_json: bool = False) -> list[dict]:
    """周汇总。`as_json=True` 时不打印文本，返回/打印结构化结果。"""
    cur = conn.execute("SELECT DISTINCT iso_week FROM daily_reviews ORDER BY iso_week")
    weeks = [r[0] for r in cur.fetchall()]
    if iso_week is not None:
        weeks = [w for w in weeks if w == iso_week]
    if not weeks:
        if not as_json:
            print("无可分析的周数据。")
        return []
    out: list[dict] = []
    for wk in weeks:
        s = collect(conn, "iso_week=?", (wk,), f"ISO 周 {wk}")
        if s is None:
            continue
        out.append(s)
        if not as_json:
            print(render_summary(s))
    if as_json:
        _dump(out)
    return out


def report_month(conn, month: int | None = None, *, as_json: bool = False) -> dict | None:
    """月汇总（含与上月的系统分趋势）。`as_json=True` 时输出结构化结果。"""
    if month is None:
        month = conn.execute("SELECT MAX(month) FROM daily_reviews").fetchone()[0]
    if month is None:
        if not as_json:
            print("无任何数据。")
        return None
    n = conn.execute(
        "SELECT COUNT(*) FROM daily_reviews WHERE month=?", (month,)
    ).fetchone()[0]
    if not n:
        if not as_json:
            print(f"月份 {month} 暂无数据。")
        return None

    prev = conn.execute(
        "SELECT MAX(month) FROM daily_reviews WHERE month<?", (month,)
    ).fetchone()[0]
    trend = None
    if prev:
        prev_v = _avg(conn, "system_score", "month=?", (prev,))
        cur_v = _avg(conn, "system_score", "month=?", (month,))
        # 必须取整，否则会打印出 -0.010000000000000675 这种浮点尾差
        delta = round(cur_v - prev_v, 2) if (cur_v is not None and prev_v is not None) else None
        trend = {"prev_month": prev, "prev": prev_v, "current": cur_v, "delta": delta}

    if as_json:
        s = collect(conn, "month=?", (month,), f"月份 {month}")
        if s is not None:
            s["trend"] = trend
            _dump(s)
        return s

    _report(conn, "month=?", (month,), f"月份 {month}")
    if trend:
        d = trend["delta"]
        arrow = "▲" if (d and d > 0) else ("▼" if d and d < 0 else "—")
        print(_line("系统分趋势",
                    f"{trend['prev']} -> {trend['current']}  {arrow} {d}"))
    return None


# ---------------------------------------------------------------------------
# md 落盘（v1.8.0）：结构化骨架，对齐现行手写件的章节 / 表头
# ---------------------------------------------------------------------------

_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _fmt_num(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else str(v)
    return str(v)


def _fmt_bedtime(mins) -> str:
    if mins is None:
        return "—"
    return minutes_to_clock(mins)


def _md_bar(v: float | None, width: int = 10) -> str:
    if v is None:
        return "—"
    filled = max(0, min(width, int(round(float(v) / 10 * width))))
    return "█" * filled + "░" * (width - filled)


def _week_date_span(conn, iso_week: int) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT MIN(date), MAX(date) FROM daily_reviews WHERE iso_week=?",
        (iso_week,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0], row[1]


def _daily_rows(conn, where: str, params: tuple) -> list[dict]:
    cols = (
        "date, weekday, training_day, health_score, work_score, learn_score, "
        "life_score, system_score, sleep_h, sleep_quality, bedtime, phone_h, "
        "deepwork_h, learn_h, life_h, diet_kcal"
    )
    return [dict(r) for r in conn.execute(
        f"SELECT {cols} FROM daily_reviews WHERE {where} ORDER BY date", params
    )]


def render_week_md(conn, iso_week: int) -> str | None:
    """渲染单周总结 markdown（结构化骨架）。无区间无数据返回 None。"""
    s = collect(conn, "iso_week=?", (iso_week,), f"ISO 周 {iso_week}")
    if s is None:
        return None
    span = _week_date_span(conn, iso_week)
    assert span is not None
    d0, d1 = span
    start = datetime.strptime(d0, "%Y-%m-%d")
    end = datetime.strptime(d1, "%Y-%m-%d")
    title = (
        f"# 周总结 · ISO 第 {iso_week} 周（{d0} {_WEEKDAY_CN[start.weekday()]} ~ "
        f"{end.strftime('%m-%d')} {_WEEKDAY_CN[end.weekday()]}）"
    )
    st = s["training"]
    train_txt = (
        f"{st['done']}/{st['total']}（{_pct(st['done'] / st['total'] if st['total'] else None)}）"
        if st["total"] else "无训练日"
    )
    adh = s.get("track_adherence") or {}
    items = adh.get("items") or []
    t_done = sum(i["done"] for i in items)
    t_rec = sum(i["recorded"] for i in items)
    track_txt = f"{t_done}/{t_rec}（{_pct(t_done / t_rec if t_rec else None)}）" if t_rec else "无记录"

    L: list[str] = [
        title, "",
        f"> 由 DailyLumen 周分析脚本（`python -m review_tool week {iso_week} --write`）生成，"
        "数据源为 SQLite 单一库 `review_tool/reviews.db`。",
        f"> 本周共 **{s['days']} 天**记录；数据完整度 "
        f"**{s['completeness']['rate_pct']}%**"
        + (
            "（核心字段缺失: "
            + "、".join(f"{m['field']}×{m['days']}" for m in s['completeness']['missing'][:6])
            + "）。"
            if s["completeness"]["missing"] else "（核心字段无缺失）。"
        ),
        "> ⚠️ **口径提示**：分数取**库的现行口径**。本文件为 `--write` 结构化骨架；"
        "关键发现 / 行动清单等叙事段不自动生成（默认不回填既有手写件）。",
        "",
        "## 一、四维总览",
        "",
        "| 维度 | 周均值 | 可视化 |",
        "|------|--------|--------|",
        f"| 系统 | **{_fmt_num(s['system_avg'])}** | {_md_bar(s['system_avg'])} |",
    ]
    for label, v in s["dims"].items():
        L.append(f"| {label} | **{_fmt_num(v)}** | {_md_bar(v)} |")

    fa = s["field_avgs"]
    L += [
        "",
        "> 客观指标均值："
        f"**睡眠 {_fmt_num(fa.get('睡眠'))}h** ｜ "
        f"**屏幕 {_fmt_num(fa.get('屏幕'))}h** ｜ "
        f"**深度工作 {_fmt_num(fa.get('深度工作'))}h** ｜ "
        f"**饮食 {_fmt_num(fa.get('饮食'), 1)} kcal** ｜ "
        f"早餐按时 **{_pct(s['breakfast_on_time_pct'])}** ｜ "
        f"训练日运动达标 **{train_txt}** ｜ "
        f"打卡完成率 **{track_txt}**",
    ]
    macros = s.get("macros")
    if macros:
        sp = macros["split_pct"]
        L.append(
            f"> 宏量日均（记录 {macros['days']} 天）："
            f"**碳水 {macros['carbs_g']}g ｜ 脂肪 {macros['fat_g']}g ｜ "
            f"蛋白质 {macros['protein_g']}g**"
            f"（估算 {macros['kcal']} kcal，碳水 {sp['carbs']}%・脂肪 {sp['fat']}%・"
            f"蛋白 {sp['protein']}%）"
        )

    L += [
        "",
        f"## 二、每日明细（{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')}）",
        "",
        "| 日期 | 星期 | 训练日 | 健康 | 工作 | 学习 | 生活 | 系统 | "
        "睡眠(h) | 质量 | 入睡 | 屏幕(h) | 深度(h) | 学习(h) | 生活(h) | 饮食(kcal) |",
        "|------|------|--------|------|------|------|------|------|"
        "---------|------|------|---------|---------|---------|---------|-----------|",
    ]
    for r in _daily_rows(conn, "iso_week=?", (iso_week,)):
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        L.append(
            f"| {d.strftime('%m-%d')} | {_WEEKDAY_CN[d.weekday()]} | "
            f"{_fmt_num(r['training_day'], 0)} | "
            f"{_fmt_num(r['health_score'], 0)} | {_fmt_num(r['work_score'], 0)} | "
            f"{_fmt_num(r['learn_score'], 0)} | {_fmt_num(r['life_score'], 0)} | "
            f"{_fmt_num(r['system_score'])} | {_fmt_num(r['sleep_h'])} | "
            f"{_fmt_num(r['sleep_quality'], 0)} | {_fmt_bedtime(r['bedtime'])} | "
            f"{_fmt_num(r['phone_h'])} | {_fmt_num(r['deepwork_h'])} | "
            f"{_fmt_num(r['learn_h'])} | {_fmt_num(r['life_h'])} | "
            f"{_fmt_num(r['diet_kcal'], 0)} |"
        )

    L += ["", "## 三、个人打卡依从率（不计入四维评分）", ""]
    if not items:
        L.append("> 本周无 `personal_tracks` 记录。")
    else:
        L += ["| 类别 | item_key | 完成率 | 次数 | 展示名 |",
              "|------|----------|--------|------|--------|"]
        for it in items:
            L.append(
                f"| {it['category']} | {it['item_key']} | {_pct(it['adherence'])} | "
                f"{it['done']}/{it['recorded']} | {it['item']} |"
            )

    hadh = s.get("habit_adherence") or {}
    hitems = hadh.get("items") or []
    L += ["", "## 四、行为习惯依从率（不计入四维评分 · 与补剂分栏）", ""]
    if not hitems:
        L.append("> 本周无 `habit_logs` 记录。")
    else:
        L += ["| habit_key | 完成率 | 次数 | 展示名 |",
              "|-----------|--------|------|--------|"]
        for it in hitems:
            L.append(
                f"| {it['habit_key']} | {_pct(it['adherence'])} | "
                f"{it['done']}/{it['recorded']} | {it['item']} |"
            )

    ts = s.get("training_structure") or {}
    L += ["", "## 五、训练结构（不计入四维评分）", ""]
    if not ts.get("sessions"):
        L.append("> 本周无 `training_sessions` 记录。")
    else:
        L.append(
            f"> 本周 **{ts['sessions']} 课 / {ts['items']} 条明细**"
            "（明细合计仅在 `运动时长_min` 为空时派生，见 R2）。"
        )
        L += ["", "| 日期 | 计划 | 合计(min) | 动作 |",
              "|------|------|-----------|------|"]
        for day in ts.get("by_date") or []:
            moves = "、".join(day.get("moves") or []) or "—"
            plan = day.get("plan_name") or "—"
            mins = day.get("total_min")
            L.append(
                f"| {day['date']} | {plan} | "
                f"{mins if mins is not None else '—'} | {moves} |"
            )

    lw = s.get("learning_week") or {}
    L += ["", "## 六、学习记录（不计入四维评分）", ""]
    topics = lw.get("topics") or []
    if not topics:
        L.append("> 本周无 `learning_logs` 记录。")
    else:
        total = lw.get("total_minutes")
        total_s = f"{total:.0f} min" if total is not None else "—"
        L.append(
            f"> 本周投入 **{total_s}** · {lw.get('entries', 0)} 条 · "
            f"{len(lw.get('days') or [])} 天。"
        )
        L += ["", "| topic_key | 投入 | 次数 | 展示名 |",
              "|-----------|------|------|--------|"]
        for t in topics:
            m = t.get("minutes")
            ms = f"{m:.0f}" if m is not None else "—"
            L.append(
                f"| {t['topic_key']} | {ms} | {t['entries']} | {t['topic']} |"
            )
        arts = lw.get("artifacts") or []
        if arts:
            L += ["", "**产出物**：", ""]
            for a in arts:
                L.append(f"- {a}")

    L += [
        "",
        "## 七、自动生成说明",
        "",
        "> 本文件由 CLI `--write` 落盘。关键发现 / 与上周对比 / 行动清单等叙事段"
        "请人工补写，或继续沿用既有手写周总结（默认**不**用本渲染器回填历史件）。",
        "",
        "---",
        "",
        f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
        f"数据来源：review_tool/reviews.db（ISO 周 {iso_week}）｜ "
        f"脚本：`python -m review_tool week {iso_week} --write`*",
        "",
    ]
    return "\n".join(L)


def render_month_md(conn, month: int) -> str | None:
    """渲染单月总结 markdown（结构化骨架）。"""
    s = collect(conn, "month=?", (month,), f"月份 {month}")
    if s is None:
        return None
    year, mon = divmod(month, 100)
    span = conn.execute(
        "SELECT MIN(date), MAX(date) FROM daily_reviews WHERE month=?", (month,)
    ).fetchone()
    d0, d1 = span[0], span[1]
    st = s["training"]
    train_txt = (
        f"{st['done']}/{st['total']} = {_pct(st['done'] / st['total'] if st['total'] else None)}"
        if st["total"] else "无训练日"
    )
    adh = s.get("track_adherence") or {}
    items = adh.get("items") or []
    t_done = sum(i["done"] for i in items)
    t_rec = sum(i["recorded"] for i in items)
    miss_bits = "、".join(
        f"{it['field']} × {it['days']}" for it in s["completeness"]["missing"][:6]
    )

    L: list[str] = [
        f"# 月总结 · {year} 年 {mon} 月",
        "",
        f"> 由 DailyLumen 月分析脚本（`python -m review_tool month {month} --write`）生成。",
        f"> 统计窗口：**{d0} ~ {d1}**，共 **{s['days']} 个有效记录日**。",
        f"> 数据完整度 **{s['completeness']['rate_pct']}%**"
        + (f"（核心字段缺失：{miss_bits}）。" if miss_bits else "。"),
        "> ⚠️ **口径提示**：分数取**库的现行口径**。本文件为 `--write` 结构化骨架；"
        "诊断 / 行动清单等叙事段不自动生成。",
        "",
        "## 一、月度核心数字",
        "",
        "| 指标 | 本月 |",
        "|------|------|",
        f"| **系统分** | **{_fmt_num(s['system_avg'])}** |",
    ]
    for label, v in s["dims"].items():
        L.append(f"| {label}分 | {_fmt_num(v)} |")
    fa = s["field_avgs"]
    for key, unit in (("睡眠", "h"), ("睡眠质量", ""), ("屏幕", "h"),
                      ("深度工作", "h"), ("饮食", "kcal")):
        if key in fa:
            cell = f"{_fmt_num(fa[key])} {unit}".strip()
            L.append(f"| {key}均值 | {cell} |")
    track_cell = (
        f"{_pct(t_done / t_rec)} ({t_done}/{t_rec})" if t_rec else "无记录"
    )
    L += [
        f"| 早餐按时 | {_pct(s['breakfast_on_time_pct'])} |",
        f"| 训练日运动达标 | **{train_txt}** |",
        f"| 打卡完成率 | {track_cell} |",
        "",
        "## 二、周趋势（ISO 周）",
        "",
        "| 周 | 日期 | 天数 | 系统 | 健康 | 工作 | 学习 | 生活 |",
        "|----|------|------|------|------|------|------|------|",
    ]

    week_rows = conn.execute(
        "SELECT iso_week, MIN(date), MAX(date), COUNT(*), "
        "AVG(system_score), AVG(health_score), AVG(work_score), "
        "AVG(learn_score), AVG(life_score) "
        "FROM daily_reviews WHERE month=? GROUP BY iso_week ORDER BY iso_week",
        (month,),
    ).fetchall()
    for wr in week_rows:
        wk, a, b, n, sys_v, h, w, le, li = wr
        da = datetime.strptime(a, "%Y-%m-%d").strftime("%m-%d")
        db = datetime.strptime(b, "%Y-%m-%d").strftime("%m-%d")
        L.append(
            f"| W{wk} | {da} ~ {db} | {n} | {_fmt_num(sys_v)} | {_fmt_num(h)} | "
            f"{_fmt_num(w)} | {_fmt_num(le)} | {_fmt_num(li)} |"
        )

    L += ["", "## 三、个人打卡依从率（不计入四维评分）", ""]
    if not items:
        L.append("> 本月无 `personal_tracks` 记录。")
    else:
        L += ["| 类别 | item_key | 完成率 | 次数 |",
              "|------|----------|--------|------|"]
        for it in items:
            L.append(
                f"| {it['category']} | {it['item_key']} | {_pct(it['adherence'])} | "
                f"{it['done']}/{it['recorded']} |"
            )
        weeks = adh.get("by_week") or []
        if len(weeks) >= 2:
            bits = " → ".join(f"W{w['iso_week']} {_pct(w['adherence'])}" for w in weeks)
            L += ["", f"> 周趋势：{bits}"]

    hadh = s.get("habit_adherence") or {}
    hitems = hadh.get("items") or []
    L += ["", "## 四、行为习惯依从率（不计入四维评分 · 与补剂分栏）", ""]
    if not hitems:
        L.append("> 本月无 `habit_logs` 记录。")
    else:
        L += ["| habit_key | 完成率 | 次数 |",
              "|-----------|--------|------|"]
        for it in hitems:
            L.append(
                f"| {it['habit_key']} | {_pct(it['adherence'])} | "
                f"{it['done']}/{it['recorded']} |"
            )
        hweeks = hadh.get("by_week") or []
        if len(hweeks) >= 2:
            bits = " → ".join(
                f"W{w['iso_week']} {_pct(w['adherence'])}" for w in hweeks
            )
            L += ["", f"> 周趋势：{bits}"]

    L += [
        "",
        "## 五、自动生成说明",
        "",
        "> 本文件由 CLI `--write` 落盘。上下半月 / 工作日周末 / 熔断诊断等叙事段"
        "请人工补写（默认**不**回填既有手写月总结）。",
        "",
        "---",
        "",
        f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
        f"数据来源：review_tool/reviews.db（月份 {month}）｜ "
        f"脚本：`python -m review_tool month {month} --write`*",
        "",
    ]
    return "\n".join(L)


def resolve_week_md_path(conn, iso_week: int, *, root: str | None = None) -> str | None:
    span = _week_date_span(conn, iso_week)
    if not span:
        return None
    root = root or GENERATED_DIR
    d0, d1 = span
    start = datetime.strptime(d0, "%Y-%m-%d")
    end = datetime.strptime(d1, "%Y-%m-%d")
    name = (
        f"周总结-W{iso_week}-"
        f"{start.strftime('%Y-%m-%d')}_{end.strftime('%m-%d')}.md"
    )
    return os.path.join(root, d0[:7], name)


def resolve_month_md_path(month: int, *, root: str | None = None) -> str:
    root = root or GENERATED_DIR
    y, m = divmod(month, 100)
    return os.path.join(root, f"{y:04d}-{m:02d}", f"月总结-{month}.md")


def _write_text(path: str, text: str) -> None:
    """写盘并用回读校验（Windows 写盘不可信）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = text.replace("\r\n", "\n").encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    back = open(path, "rb").read()
    if back != data:
        raise OSError(f"写盘回读失败: {path}")


def write_week_md(conn, iso_week: int, *, root: str | None = None,
                  force: bool = False, check_only: bool = False) -> tuple[str, str]:
    """生成并落盘周总结。返回 ``(path, status)``，status ∈ written/skipped/diff/missing。"""
    text = render_week_md(conn, iso_week)
    if text is None:
        return "", "missing"
    path = resolve_week_md_path(conn, iso_week, root=root)
    assert path
    if check_only:
        if not os.path.isfile(path):
            return path, "missing"
        old = open(path, "rb").read().replace(b"\r\n", b"\n").decode("utf-8")
        # 忽略生成时间行再比
        def _strip_gen(t: str) -> str:
            return "\n".join(
                ln for ln in t.splitlines() if not ln.startswith("*生成时间：")
            )
        return path, ("ok" if _strip_gen(old) == _strip_gen(text) else "diff")
    if os.path.isfile(path) and not force:
        return path, "skipped"
    _write_text(path, text)
    return path, "written"


def write_month_md(conn, month: int, *, root: str | None = None,
                   force: bool = False, check_only: bool = False) -> tuple[str, str]:
    text = render_month_md(conn, month)
    if text is None:
        return "", "missing"
    path = resolve_month_md_path(month, root=root)
    if check_only:
        if not os.path.isfile(path):
            return path, "missing"
        old = open(path, "rb").read().replace(b"\r\n", b"\n").decode("utf-8")

        def _strip_gen(t: str) -> str:
            return "\n".join(
                ln for ln in t.splitlines() if not ln.startswith("*生成时间：")
            )
        return path, ("ok" if _strip_gen(old) == _strip_gen(text) else "diff")
    if os.path.isfile(path) and not force:
        return path, "skipped"
    _write_text(path, text)
    return path, "written"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    do_write = "--write" in argv
    do_force = "--force" in argv
    do_check = "--check" in argv
    pos = [a for a in argv if not a.startswith("-")]
    conn = init_db()
    try:
        mode = pos[0] if pos else "month"
        if mode == "week":
            wk = int(pos[1]) if len(pos) > 1 else None
            if do_write or do_check:
                if wk is None:
                    print("用法: week <ISO周> --write|--check [--force]")
                    return 2
                path, status = write_week_md(
                    conn, wk, force=do_force, check_only=do_check)
                if status == "missing" and not path:
                    print(f"ISO 周 {wk} 暂无数据。")
                    return 1
                print(f"[{status}] {path}")
                if not do_check:
                    report_week(conn, wk, as_json=False)
                return 0 if status in ("written", "skipped", "ok") else (1 if status == "diff" else 1)
            report_week(conn, wk, as_json=as_json)
        elif mode == "month":
            mon = int(pos[1]) if len(pos) > 1 else None
            if do_write or do_check:
                if mon is None:
                    mon = conn.execute("SELECT MAX(month) FROM daily_reviews").fetchone()[0]
                if mon is None:
                    print("无任何数据。")
                    return 1
                path, status = write_month_md(
                    conn, mon, force=do_force, check_only=do_check)
                if status == "missing" and not path:
                    print(f"月份 {mon} 暂无数据。")
                    return 1
                print(f"[{status}] {path}")
                if not do_check:
                    report_month(conn, mon, as_json=False)
                return 0 if status in ("written", "skipped", "ok") else 1
            report_month(conn, mon, as_json=as_json)
        else:
            print("用法: python -m review_tool [week|month] [周号|月份] "
                  "[--json] [--write] [--force] [--check]")
            return 2
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
