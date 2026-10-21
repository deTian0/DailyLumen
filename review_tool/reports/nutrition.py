"""营养缺口报告：当日 / 近窗缺口 + FOOD_LIB 具体动作（独立指标区）。

用法:
    python -m review_tool nutrition
    python -m review_tool nutrition --json
    python -m review_tool nutrition 2026-10-15

每条建议引用 FOOD_LIB 具体项 + 克数，数字可手工复算。
缺口口径与 ``ai_review`` 同源（R1）；不参与四维（G5）；无新增表。
"""
from __future__ import annotations

import json
import sys
from datetime import date

from ..config import FOOD_LIB, NUTRITION_RULES, PROFILE
from ..core.nutrition import (
    avg_field,
    extreme_kcal_streak,
    format_extreme_flag,
    format_suggestion_line,
    gap_analysis,
    meal_structure,
    suggest_foods,
)
from ..core.nutrition_items import MEAL_LABELS, group_by_meal, total_kcal
from ..storage.db import init_db, load_nutrition_items


def _fetch_recent(conn, date_str: str, days: int = 7) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM daily_reviews WHERE date<=? ORDER BY date DESC LIMIT ?",
        (date_str, days),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def collect(conn, *, as_of: str | None = None, recent_days: int = 7) -> dict:
    """汇营养缺口报告数据（结构化，文本 / JSON 共用）。"""
    if as_of is None:
        row = conn.execute("SELECT MAX(date) FROM daily_reviews").fetchone()
        as_of = row[0] if row and row[0] else date.today().isoformat()

    recent = _fetch_recent(conn, as_of, recent_days)
    day = next((r for r in reversed(recent) if r["date"] == as_of), None)
    if day is None:
        row = conn.execute(
            "SELECT * FROM daily_reviews WHERE date=?", (as_of,)
        ).fetchone()
        day = dict(row) if row else None

    targets = dict(PROFILE.get("macro_targets") or {})
    day_gap = gap_analysis(day or {}, targets)

    # 近窗均值（把均值当成「假想日」再算缺口，判定仍走同源函数）
    avg_day = {
        col: avg_field(recent, col)
        for col in ("diet_kcal", "carbs_g", "fat_g", "protein_g",
                    "meals_count", "breakfast_on_time")
    }
    window_gap = gap_analysis(avg_day, targets)

    structure = meal_structure(day or {})
    # 组合建议：优先用当日缺口；当日无宏量记录则退到近窗均值缺口
    source = "day"
    deficits = day_gap["deficits"]
    if day is None or all(
        day.get(c) is None for c in ("carbs_g", "fat_g", "protein_g")
    ):
        source = "window"
        deficits = window_gap["deficits"]

    picks = suggest_foods(
        deficits,
        FOOD_LIB,
        max_foods=int(NUTRITION_RULES.get("max_suggest_foods", 3)),
    )
    ext = extreme_kcal_streak(recent)

    # 当日食物明细（v9 / M25）：只做回看下钻，不参与任何评分或缺口判定
    items = [dict(r) for r in load_nutrition_items(conn, date=as_of)]

    return {
        "as_of": as_of,
        "recent_days": len(recent),
        "window_start": recent[0]["date"] if recent else None,
        "window_end": recent[-1]["date"] if recent else None,
        "day": day,
        "day_gap": day_gap,
        "window_avg": avg_day,
        "window_gap": window_gap,
        "meal_structure": structure,
        "suggestions": picks,
        "suggest_source": source,
        "extreme": ext,
        "targets": targets,
        "food_lib_size": len(FOOD_LIB),
        "items": items,
        "items_total_kcal": total_kcal(items),
    }


def render(data: dict) -> str:
    """人类可读文本；确定性拼装。"""
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 营养缺口报告（不计入四维评分）")
    L.append("=" * 52)
    L.append("")
    L.append(f"[基准日] {data['as_of']}")
    if data.get("window_start"):
        L.append(
            f"[近窗] {data['window_start']} ~ {data['window_end']}"
            f"（{data['recent_days']} 天）｜FOOD_LIB {data['food_lib_size']} 项"
        )
    L.append("")

    # 极端值优先
    ext_msg = format_extreme_flag(data["extreme"])
    if ext_msg:
        L.append(f"[!] 强提示：{ext_msg}")
        L.append("")

    targets = data["targets"]
    dg = data["day_gap"]
    L.append("---- 当日缺口 ----")
    if data["day"] is None:
        L.append("  （库中无该日记录）")
    else:
        dk = dg.get("diet_kcal")
        L.append(f"  热量: {dk if dk is not None else '—'} kcal")
        for col, label in (
            ("protein_g", "蛋白质"),
            ("carbs_g", "碳水"),
            ("fat_g", "脂肪"),
        ):
            tgt = targets.get(col)
            act = dg["actuals"].get(col)
            defi = dg["deficits"].get(col)
            if act is None:
                L.append(f"  {label}: —（目标 {tgt}g）")
            elif defi is not None and defi > 0:
                L.append(
                    f"  {label}: {act:g} − {tgt:g} = 缺 {defi:g}g"
                )
            else:
                L.append(f"  {label}: {act:g}g（达标，目标 {tgt}g）")
    L.append("")

    wg = data["window_gap"]
    L.append("---- 近窗日均缺口 ----")
    wa = data["window_avg"]
    L.append(
        f"  热量日均: "
        f"{wa['diet_kcal'] if wa.get('diet_kcal') is not None else '—'} kcal"
    )
    for col, label in (
        ("protein_g", "蛋白质"),
        ("carbs_g", "碳水"),
        ("fat_g", "脂肪"),
    ):
        tgt = targets.get(col)
        act = wg["actuals"].get(col)
        defi = wg["deficits"].get(col)
        if act is None:
            L.append(f"  {label}: —")
        elif defi is not None and defi > 0:
            L.append(f"  {label}: 日均 {act:g} − {tgt:g} = 缺 {defi:g}g")
        else:
            L.append(f"  {label}: 日均 {act:g}g（达标）")
    L.append("")

    ms = data["meal_structure"]
    L.append("---- 三餐结构 ----")
    L.append(
        f"  餐次: {ms['meals_count'] if ms['meals_count'] is not None else '—'}"
        f" / 预期 {ms['expected_meals']}"
        f"｜早餐按时: "
        f"{'是' if ms['breakfast_on_time'] == 1 else ('否' if ms['breakfast_on_time'] == 0 else '—')}"
    )
    if ms["notes"]:
        for n in ms["notes"]:
            L.append(f"  · {n}")
    L.append(f"  建议补入: {ms['suggest_slot']}")
    L.append("")

    items = data.get("items") or []
    L.append("---- 当日明细（食物 · 不参与评分）----")
    if not items:
        L.append("  （该日无食物明细：M25 附录为可选，漏记不补）")
    else:
        for code, group in group_by_meal(items):
            L.append(f"  {MEAL_LABELS.get(code, code)}")
            for it in group:
                kcal = f"{it['kcal']:g} kcal" if it.get("kcal") is not None else "—"
                macros = " · ".join(
                    f"{label} {it[col]:g}g"
                    for col, label in (
                        ("protein_g", "蛋白"), ("carb_g", "碳水"), ("fat_g", "脂肪"),
                    )
                    if it.get(col) is not None
                )
                tail = f"（{macros}）" if macros else ""
                note = f"  ※{it['note']}" if it.get("note") else ""
                L.append(f"    · {it['item']}　{kcal}{tail}{note}")
        tot = data.get("items_total_kcal")
        if tot is not None:
            block = (data.get("day") or {}).get("diet_kcal")
            if block is None:
                L.append(f"  明细合计: {tot:g} kcal（数据块无当日热量，无法对照）")
            else:
                L.append(
                    f"  明细合计: {tot:g} kcal ｜ 数据块 {block:g} kcal"
                    f"（差 {block - tot:+.0f}，明细为估算值）"
                )
    L.append("")

    L.append("---- 建议（FOOD_LIB）----")
    picks = data.get("suggestions") or []
    if not picks:
        L.append("  （无缺口或 FOOD_LIB 无法覆盖，无需加餐）")
    else:
        src = "当日" if data.get("suggest_source") == "day" else "近窗日均"
        L.append(f"  依据: {src}缺口｜≤{NUTRITION_RULES.get('max_suggest_foods', 3)} 种")
        slot = ms.get("suggest_slot")
        for i, p in enumerate(picks, 1):
            L.append(f"  {i}. {format_suggestion_line(p, slot=slot if i == 1 else None)}")
            L.append(
                f"     补 {p['for_label']}｜key={p['key']}"
            )
    L.append("")
    L.append("数字均可对照 config.FOOD_LIB 手工复算；不做医疗/营养处方。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法: python -m review_tool nutrition [YYYY-MM-DD] [--json] [--db PATH]")
        return 0

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
        # day 行可能含非 JSON 友好类型；只保留报告需要的摘要
        payload = {k: v for k, v in data.items() if k != "day"}
        if data.get("day"):
            d = data["day"]
            payload["day_summary"] = {
                k: d.get(k)
                for k in (
                    "date", "diet_kcal", "carbs_g", "fat_g", "protein_g",
                    "meals_count", "breakfast_on_time",
                )
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
