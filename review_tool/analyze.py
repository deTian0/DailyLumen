"""周分析 / 月分析：从 SQLite 用 SQL 聚合，打印可读报告。

用法:
    python -m review_tool week            # 所有周汇总
    python -m review_tool week 32         # 指定 ISO 周
    python -m review_tool month           # 当月 (最近一个月) 汇总
    python -m review_tool month 202608    # 指定月份 202608

口径说明（重要）
----------------
「训练日运动达标」按**三态**统计，把「未记录」和「未达标」分开：

    达标 0 / 3 天（训练日共 4 天，另有 1 天未记录）

早期版本用 ``exercise_min > 0`` 直接判达标，会把「字段空着」误判成
「没运动」，导致达标率系统性偏低。
"""
from __future__ import annotations

import sys

from .config import DIMENSIONS
from .db import COLUMNS, init_db

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


def _macro_lines(conn, where: str = "", params: tuple = ()) -> str:
    """三大营养素统计：日均碳水/脂肪/蛋白质 + 估算宏量热量与供能占比。

    carbs/fat/protein 按 4/9/4 kcal 每克折算。任一宏量都未记录时返回空串。
    """
    cond = f" WHERE {where}" if where else ""
    n, c, f, p = conn.execute(
        f"SELECT COUNT(carbs_g), AVG(carbs_g), AVG(fat_g), AVG(protein_g) "
        f"FROM daily_reviews{cond}",
        params,
    ).fetchone()
    if not n:
        return ""
    c, f, p = round(c), round(f), round(p)
    kc, kf, kp = 4 * c, 9 * f, 4 * p
    total = kc + kf + kp
    if total <= 0:
        return ""
    pc, pf = round(kc / total * 100), round(kf / total * 100)
    pp = 100 - pc - pf
    return (
        _line("宏量日均", f"碳水 {c}g / 脂肪 {f}g / 蛋白质 {p}g (记录 {n} 天)") + "\n"
        + _line("估算宏量热量", f"{total} kcal ［碳水 {pc}%・脂肪 {pf}%・蛋白质 {pp}%］")
    )


def training_stats(conn, where: str, params: tuple) -> dict:
    """训练日运动三态统计：总训练日 / 有记录 / 达标 / 未记录。"""
    total, recorded, done = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN training_day=1 THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_min IS NOT NULL THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN training_day=1 AND exercise_min > 0 THEN 1 ELSE 0 END) "
        f"FROM daily_reviews WHERE {where}",
        params,
    ).fetchone()
    total = total or 0
    recorded = recorded or 0
    done = done or 0
    return {
        "total": total,
        "recorded": recorded,
        "done": done,
        "missing": total - recorded,
    }


def _training_line(st: dict) -> str:
    total, recorded, done, missing = st["total"], st["recorded"], st["done"], st["missing"]
    if total == 0:
        return _line("训练日运动", "无训练日记录")
    if recorded == 0:
        return _line("训练日运动", f"训练日 {total} 天均未记录运动字段")
    text = f"达标 {done}/{recorded} 天 = {_pct(done / recorded)}"
    if missing:
        text += f"  ⚠️ 另有 {missing} 天未记录（不计入达成分母）"
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


def _report(conn, where: str, params: tuple, title: str) -> None:
    """周 / 月共用的报告主体。"""
    n = conn.execute(
        f"SELECT COUNT(*) FROM daily_reviews WHERE {where}", params
    ).fetchone()[0]
    if not n:
        return
    print(f"\n{'=' * 52}")
    print(f"{title}  (共 {n} 天)")
    print(f"{'=' * 52}")
    print(_line("记录天数", n))
    print(_line("系统分均值", _avg(conn, "system_score", where, params)))
    for dim in DIMENSIONS:
        v = _avg(conn, dim, where, params)
        bar = _bar(v) if v else "  - "
        print(_line(f"{DIM_LABEL[dim]}分均值", f"{v}  {bar}"))

    adh = conn.execute(
        f"SELECT AVG(commute_done), AVG(breakfast_on_time) "
        f"FROM daily_reviews WHERE {where}",
        params,
    ).fetchone()
    print(_line("早餐按时", _pct(adh[1])))
    print(_line("通勤完成", _pct(adh[0])))
    print(_training_line(training_stats(conn, where, params)))

    fields = _MONTH_FIELDS if "month" in where else _WEEK_FIELDS
    for col, lbl in fields:
        print(_line(f"{lbl}均值", _avg(conn, col, where, params)))

    ml = _macro_lines(conn, where, params)
    if ml:
        print(ml)

    rate, missing = completeness(conn, where, params)
    detail = "、".join(f"{c}×{m}" for c, m in missing[:6]) or "无"
    print(_line("数据完整度", f"{_pct(rate)}（核心字段缺失: {detail}）"))

    worst = min(
        ((DIM_LABEL[d], _avg(conn, d, where, params)) for d in DIMENSIONS),
        key=lambda x: x[1] if x[1] is not None else 99,
    )
    print(f"  >> 最差维度: {worst[0]} ({worst[1]})")


def report_week(conn, iso_week: int | None = None) -> None:
    cur = conn.execute("SELECT DISTINCT iso_week FROM daily_reviews ORDER BY iso_week")
    weeks = [r[0] for r in cur.fetchall()]
    if iso_week is not None:
        weeks = [w for w in weeks if w == iso_week]
    if not weeks:
        print("无可分析的周数据。")
        return
    for wk in weeks:
        _report(conn, "iso_week=?", (wk,), f"ISO 周 {wk}")


def report_month(conn, month: int | None = None) -> None:
    if month is None:
        month = conn.execute("SELECT MAX(month) FROM daily_reviews").fetchone()[0]
    if month is None:
        print("无任何数据。")
        return
    n = conn.execute(
        "SELECT COUNT(*) FROM daily_reviews WHERE month=?", (month,)
    ).fetchone()[0]
    if not n:
        print(f"月份 {month} 暂无数据。")
        return
    _report(conn, "month=?", (month,), f"月份 {month}")

    prev = conn.execute(
        "SELECT MAX(month) FROM daily_reviews WHERE month<?", (month,)
    ).fetchone()[0]
    if prev:
        prev_v = _avg(conn, "system_score", "month=?", (prev,))
        cur_v = _avg(conn, "system_score", "month=?", (month,))
        # 必须取整，否则会打印出 -0.010000000000000675 这种浮点尾差
        delta = round(cur_v - prev_v, 2) if (cur_v is not None and prev_v is not None) else None
        arrow = "▲" if (delta and delta > 0) else ("▼" if delta and delta < 0 else "—")
        print(_line("系统分趋势", f"{prev_v} -> {cur_v}  {arrow} {delta}"))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    conn = init_db()
    mode = argv[0] if argv else "month"
    if mode == "week":
        wk = int(argv[1]) if len(argv) > 1 else None
        report_week(conn, wk)
    elif mode == "month":
        mo = int(argv[1]) if len(argv) > 1 else None
        report_month(conn, mo)
    else:
        print("用法: python -m review_tool [week|month] [周号|月份]")
        conn.close()
        return 2
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
