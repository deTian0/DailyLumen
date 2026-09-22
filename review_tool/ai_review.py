"""「七、AI 评价与建议」的确定性上下文构建器。

定时任务（晨间收集）在撰写该章节前先运行：

    python -m review_tool ai-context [YYYY-MM-DD]

得到「当日事实 + 近 7 日趋势 + 规则命中的关注点」的结构化摘要，据此撰写
「评价」与「建议」，避免凭印象编造数字。

设计原则
- 本模块只做读库与规则判定，**不调用任何模型**；措辞由调用方（自动化/模型）完成。
- 阈值全部来自 `config.SCORE_THRESHOLDS`，宏量目标来自 `config.PROFILE["macro_targets"]`，
  **包括文案里的时间点**（如「23:30」也是从 `ok_max` 现算的），
  因此改配置不会出现「阈值变了、文案还在说老数字」。
- 规则只陈述客观事实（「入睡 00:35 晚于 23:30」），不给结论，结论留给撰写方。
"""
from __future__ import annotations

import sys
from datetime import date as _date

from .config import PROFILE, SCORE_THRESHOLDS
from .db import init_db
from .score import compute_scores, system_score_from
from .util import is_late_bedtime, minutes_to_clock

# 展示标签
_LABELS = {
    "sleep_h": "睡眠(h)", "sleep_quality": "睡眠质量", "bedtime": "入睡",
    "exercise_min": "运动(min)", "diet_kcal": "饮食(kcal)",
    "carbs_g": "碳水(g)", "fat_g": "脂肪(g)", "protein_g": "蛋白质(g)",
    "phone_h": "屏幕(h)", "deepwork_h": "深度工作(h)",
    "learn_h": "学习(h)", "life_h": "生活(h)",
    "health_score": "健康分", "work_score": "工作分",
    "learn_score": "学习分", "life_score": "生活分", "system_score": "系统分",
}

# 四维展示顺序
_DIMS = [("health_score", "健康"), ("work_score", "工作"),
         ("learn_score", "学习"), ("life_score", "生活")]

# 关注点里使用的无单位简称（避免「碳水(g) 160g」这类冗余）
_FLAG_LABELS = {"carbs_g": "碳水", "protein_g": "蛋白质", "fat_g": "脂肪"}

# 兼容旧调用方的别名
clock = minutes_to_clock


def _bedtime_deadline() -> str:
    """「该几点前睡」的文案（由 config 阈值现算，默认 23:30）。"""
    return minutes_to_clock(SCORE_THRESHOLDS["bedtime"]["ok_max"])


def _bedtime_is_late(bt: int | None) -> bool:
    """入睡时间是否落在扣分档。

    字段语义 = 距 00:00 的分钟数，与 score.compute_health_score 口径一致：
    0~late_night_max（00:00–06:00）判「熬夜」，> ok_max（23:30–23:59）判「晚睡」，
    两端都扣分，中间不扣。
    """
    return is_late_bedtime(bt, SCORE_THRESHOLDS["bedtime"])


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def fetch_day(conn, date_str: str) -> dict | None:
    """取某一天的行；不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM daily_reviews WHERE date=?", (date_str,)
    ).fetchone()
    return dict(row) if row else None


def fetch_recent(conn, date_str: str, days: int = 7) -> list[dict]:
    """取 date_str 之前（含当日）最近 days 天，按日期升序。"""
    rows = conn.execute(
        "SELECT * FROM daily_reviews WHERE date<=? ORDER BY date DESC LIMIT ?",
        (date_str, days),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _avg(rows: list[dict], col: str) -> float | None:
    vals = [r[col] for r in rows if r.get(col) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _streak(recent: list[dict], predicate) -> int:
    """从最近一天往前数，连续满足 predicate 的天数。"""
    n = 0
    for r in reversed(recent):
        if predicate(r):
            n += 1
        else:
            break
    return n


def attention_flags(day: dict, recent: list[dict],
                    macro_targets: dict | None = None) -> list[str]:
    """规则命中的关注点（客观陈述，不给结论）。"""
    if not day:
        return []
    T = SCORE_THRESHOLDS
    deadline = _bedtime_deadline()
    flags: list[str] = []

    # --- 睡眠 ---
    sh = day.get("sleep_h")
    if sh is not None and sh < T["sleep"]["good"]:
        flags.append(f"睡眠 {sh:g}h 低于 {T['sleep']['good']:g}h 良好线")
    bt = day.get("bedtime")
    if _bedtime_is_late(bt):
        flags.append(f"入睡 {clock(bt)} 未在 {deadline} 前（触发熬夜/晚睡档，睡眠时点扣分）")
    q = day.get("sleep_quality")
    if q is not None and q < 80:
        flags.append(f"睡眠质量 {q} 偏低（<80）")

    # --- 运动 ---
    if day.get("training_day") == 1 and not day.get("exercise_min"):
        flags.append("训练日但未记录运动")
    if day.get("exercise_src") == "derived":
        flags.append(
            f"运动 {day.get('exercise_min')}min 由「三件事」描述折算得到（非计时记录）"
        )

    # --- 饮食 / 宏量 ---
    dk = day.get("diet_kcal")
    if dk is not None:
        if dk < T["diet"]["good_low"]:
            flags.append(f"饮食 {dk}kcal 低于 {T['diet']['good_low']} 下限")
        elif dk > T["diet"]["good_high"]:
            flags.append(f"饮食 {dk}kcal 高于 {T['diet']['good_high']} 上限")
    mt = macro_targets if macro_targets is not None else (PROFILE.get("macro_targets") or {})
    for col, tgt in mt.items():
        v = day.get(col)
        if v is not None and v < tgt:
            flags.append(f"{_FLAG_LABELS.get(col, _LABELS.get(col, col))} {v}g 低于目标 {tgt}g")

    # --- 屏幕 ---
    ph = day.get("phone_h")
    if ph is not None and ph > T["phone"]["bad"]:
        flags.append(f"屏幕 {ph:g}h 高于 {T['phone']['bad']:g}h（已是差档）")

    # --- 四维最低档 ---
    for dim, label in _DIMS[1:]:  # 工作/学习/生活（健康由子项体现）
        v = day.get(dim)
        if v is not None and v <= 3:
            flags.append(f"{label}分 {v}（最低档）")

    # --- 趋势：连续性问题 ---
    s_bed = _streak(recent, lambda r: _bedtime_is_late(r.get("bedtime")))
    if s_bed >= 3:
        flags.append(f"连续 {s_bed} 天入睡未在 {deadline} 前")
    s_learn = _streak(recent, lambda r: r.get("learn_score") is not None and r["learn_score"] <= 3)
    if s_learn >= 3:
        flags.append(f"连续 {s_learn} 天学习分 ≤3（学习维度持续垫底）")
    s_phone = _streak(recent, lambda r: (r.get("phone_h") or 0) > T["phone"]["bad"])
    if s_phone >= 3:
        flags.append(f"连续 {s_phone} 天屏幕超过 {T['phone']['bad']:g}h")
    return flags


def build_context(date_str: str | None = None, db_path: str | None = None,
                  recent_days: int = 7) -> dict:
    """构建「AI 评价与建议」所需上下文。"""
    conn = init_db(db_path)
    try:
        if not date_str:
            row = conn.execute("SELECT MAX(date) FROM daily_reviews").fetchone()
            date_str = row[0] if row and row[0] else _date.today().isoformat()
        day = fetch_day(conn, date_str)
        recent = fetch_recent(conn, date_str, recent_days)
    finally:
        conn.close()

    if day:
        # 补齐四维（不覆盖已有值）与系统分，便于评价引用
        day = compute_scores(dict(day))
        if day.get("system_score") is None:
            day["system_score"] = system_score_from(day)

    avgs = {col: _avg(recent, col) for col in
            ("system_score", "health_score", "work_score", "learn_score", "life_score",
             "sleep_h", "phone_h", "deepwork_h", "learn_h", "life_h",
             "diet_kcal", "carbs_g", "fat_g", "protein_g")}

    return {
        "date": date_str,
        "day": day,
        "recent": recent,
        "recent_days": len(recent),
        "avgs": avgs,
        "flags": attention_flags(day, recent) if day else [],
    }


def render_markdown(ctx: dict) -> str:
    """把上下文渲染成一段可读摘要（供撰写方引用）。"""
    date_str = ctx["date"]
    day = ctx["day"]
    lines = [f"# AI 评价上下文 · {date_str}", ""]
    if not day:
        lines.append(f"（库中无 {date_str} 记录，请先 ingest 该日复盘）")
        return "\n".join(lines)

    lines.append(f"近 {ctx['recent_days']} 日窗口：{ctx['recent'][0]['date']} ~ {ctx['recent'][-1]['date']}")
    lines.append("")

    # 当日事实
    lines.append("## 当日事实")
    lines.append(f"- 星期 {_fmt(day.get('weekday'))}｜训练日 {'是' if day.get('training_day') == 1 else '否'}")
    ex = day.get("exercise_min")
    if ex is None:
        ex_text = "未记录"
    elif day.get("exercise_src") == "derived":
        ex_text = f"{ex}min（由「三件事」描述折算，非计时记录）"
    else:
        ex_text = f"{ex}min"
    lines.append(f"- 睡眠 {_fmt(day.get('sleep_h'))}h｜质量 {_fmt(day.get('sleep_quality'))}"
                 f"｜入睡 {clock(day.get('bedtime'))}"
                 f"｜运动 {ex_text}")
    lines.append(f"- 饮食 {_fmt(day.get('diet_kcal'))}kcal"
                 f"（碳水 {_fmt(day.get('carbs_g'))}g / 脂肪 {_fmt(day.get('fat_g'))}g"
                 f" / 蛋白 {_fmt(day.get('protein_g'))}g）")
    lines.append(f"- 屏幕 {_fmt(day.get('phone_h'))}h"
                 f"｜深度工作 {_fmt(day.get('deepwork_h'))}h"
                 f"｜学习 {_fmt(day.get('learn_h'))}h｜生活 {_fmt(day.get('life_h'))}h")
    dims = " / ".join(f"{label} {_fmt(day.get(dim))}" for dim, label in _DIMS)
    lines.append(f"- 四维：{dims}｜系统 {_fmt(day.get('system_score'))}")
    if day.get("summary"):
        lines.append(f"- 一句话总结：{day['summary']}")
    lines.append("")

    # 近 7 日均值
    lines.append(f"## 近 {ctx['recent_days']} 日均值（含当日）")
    a = ctx["avgs"]
    lines.append(f"- 系统 {_fmt(a['system_score'])}｜健康 {_fmt(a['health_score'])}"
                 f"｜工作 {_fmt(a['work_score'])}｜学习 {_fmt(a['learn_score'])}"
                 f"｜生活 {_fmt(a['life_score'])}")
    lines.append(f"- 睡眠 {_fmt(a['sleep_h'])}h｜屏幕 {_fmt(a['phone_h'])}h"
                 f"｜深度工作 {_fmt(a['deepwork_h'])}h｜饮食 {_fmt(a['diet_kcal'])}kcal")
    lines.append(f"- 宏量日均：碳水 {_fmt(a['carbs_g'])}g / 脂肪 {_fmt(a['fat_g'])}g / 蛋白 {_fmt(a['protein_g'])}g")
    lines.append("")

    # 关注点
    lines.append("## 规则命中的关注点")
    if ctx["flags"]:
        for f in ctx["flags"]:
            lines.append(f"- {f}")
    else:
        lines.append("- （无规则命中，指标均在阈值内）")
    lines.append("")

    lines.append("> 撰写要求：先给「评价」（做得好 / 需留意，2–3 条，引用上面的数字），")
    lines.append("> 再给「建议」（2–4 条可执行动作，带具体时间锚点或目标值）。不要编造未列出的数据。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    date_str = argv[0] if argv else None
    ctx = build_context(date_str)
    print(render_markdown(ctx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
