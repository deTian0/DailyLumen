"""周分析 / 月分析: 从 SQLite 用 SQL 聚合, 打印可读报告。

用法:
    python analyze.py week            # 所有周汇总
    python analyze.py week 32         # 指定 ISO 周
    python analyze.py month           # 当月 (最近一个月) 汇总
    python analyze.py month 202608    # 指定月份 202608
"""
import sys
import sqlite3
from datetime import datetime
from db import init_db, get_conn
from config import DIMENSIONS

DIM_LABEL = {
    "health_score": "健康", "work_score": "工作",
    "learn_score": "学习", "life_score": "生活",
}


def _avg(conn, col, where=""):
    sql = f"SELECT AVG({col}) FROM daily_reviews"
    if where:
        sql += f" WHERE {where}"
    v = conn.execute(sql).fetchone()[0]
    return round(v, 2) if v is not None else None


def report_week(conn, iso_week=None):
    cur = conn.execute(
        "SELECT DISTINCT iso_week FROM daily_reviews ORDER BY iso_week"
    )
    weeks = [r[0] for r in cur.fetchall()]
    if iso_week is not None:
        weeks = [w for w in weeks if w == iso_week]
    if not weeks:
        print("无可分析的周数据。")
        return

    for wk in weeks:
        rows = conn.execute(
            "SELECT * FROM daily_reviews WHERE iso_week=? ORDER BY date",
            (wk,),
        ).fetchall()
        n = len(rows)
        print(f"\n{'='*52}")
        print(f"ISO 周 {wk}  (共 {n} 天)")
        print(f"{'='*52}")
        # 基础均值
        print(f"  系统分均值 : {_avg(conn, 'system_score', f'iso_week={wk}')}")
        for dim in DIMENSIONS:
            v = _avg(conn, dim, f"iso_week={wk}")
            bar = _bar(v) if v else "  - "
            print(f"  {DIM_LABEL[dim]:>4}分均值 : {v}  {bar}")
        # 健康行为
        adh = conn.execute(
            "SELECT AVG(supps_done), AVG(commute_done), AVG(breakfast_on_time) "
            "FROM daily_reviews WHERE iso_week=?", (wk,)
        ).fetchone()
        tr_days = conn.execute(
            "SELECT COUNT(*) FROM daily_reviews WHERE iso_week=? AND training_day=1", (wk,)
        ).fetchone()[0]
        tr_done = conn.execute(
            "SELECT COUNT(*) FROM daily_reviews WHERE iso_week=? AND training_day=1 AND exercise_min>0",
            (wk,),
        ).fetchone()[0]
        print(f"  补剂依从   : {pct(adh[0])}")
        print(f"  早餐按时   : {pct(adh[2])}")
        print(f"  通勤完成   : {pct(adh[1])}")
        print(f"  训练日运动达标: {tr_done}/{tr_days} = {pct(tr_done/tr_days if tr_days else None)}")
        # 均值指标
        for col, lbl in [("sleep_h","睡眠"), ("phone_h","屏幕"), ("deepwork_h","深度工作"), ("diet_kcal","饮食")]:
            print(f"  {lbl:>4}均值   : {_avg(conn, col, f'iso_week={wk}')}")
        # 最差维度
        worst = min(
            ((DIM_LABEL[d], _avg(conn, d, f"iso_week={wk}")) for d in DIMENSIONS),
            key=lambda x: x[1] if x[1] is not None else 99,
        )
        print(f"  >> 本周最差维度: {worst[0]} ({worst[1]})")


def report_month(conn, month=None):
    if month is None:
        # 最近一个月
        r = conn.execute("SELECT MAX(month) FROM daily_reviews").fetchone()[0]
        month = r
    rows = conn.execute(
        "SELECT * FROM daily_reviews WHERE month=? ORDER BY date", (month,)
    ).fetchall()
    if not rows:
        print(f"月份 {month} 暂无数据。")
        return
    n = len(rows)
    print(f"\n{'='*52}")
    print(f"月份 {month}  (共 {n} 天)")
    print(f"{'='*52}")
    print(f"  记录天数   : {n}")
    print(f"  系统分均值 : {_avg(conn, 'system_score', f'month={month}')}")
    for dim in DIMENSIONS:
        v = _avg(conn, dim, f"month={month}")
        bar = _bar(v) if v else "  - "
        print(f"  {DIM_LABEL[dim]:>4}分均值 : {v}  {bar}")
    # 行为依从
    adh = conn.execute(
        "SELECT AVG(supps_done), AVG(commute_done), AVG(breakfast_on_time), "
        "AVG(training_day) FROM daily_reviews WHERE month=?", (month,)
    ).fetchone()
    tr_days = conn.execute(
        "SELECT COUNT(*) FROM daily_reviews WHERE month=? AND training_day=1", (month,)
    ).fetchone()[0]
    tr_done = conn.execute(
        "SELECT COUNT(*) FROM daily_reviews WHERE month=? AND training_day=1 AND exercise_min>0",
        (month,),
    ).fetchone()[0]
    print(f"  补剂依从   : {pct(adh[0])}")
    print(f"  早餐按时   : {pct(adh[2])}")
    print(f"  通勤完成   : {pct(adh[1])}")
    print(f"  训练日运动达标: {tr_done}/{tr_days} = {pct(tr_done/tr_days if tr_days else None)}")
    for col, lbl in [("sleep_h","睡眠均值"), ("sleep_quality","睡眠质量"), ("phone_h","屏幕均值"), ("deepwork_h","深度工作"), ("diet_kcal","饮食均值")]:
        print(f"  {lbl:>6}   : {_avg(conn, col, f'month={month}')}")
    # 最差维度
    worst = min(
        ((DIM_LABEL[d], _avg(conn, d, f"month={month}")) for d in DIMENSIONS),
        key=lambda x: x[1] if x[1] is not None else 99,
    )
    print(f"  >> 本月最差维度: {worst[0]} ({worst[1]})")
    # 趋势: 与之前月份比系统分
    prev = conn.execute(
        "SELECT MAX(month) FROM daily_reviews WHERE month<?", (month,)
    ).fetchone()[0]
    if prev:
        prev_v = _avg(conn, "system_score", f"month={prev}")
        cur_v = _avg(conn, "system_score", f"month={month}")
        delta = (cur_v - prev_v) if (cur_v and prev_v) else None
        arrow = "▲" if (delta and delta > 0) else ("▼" if delta and delta < 0 else "—")
        print(f"  系统分趋势 : {prev_v} -> {cur_v}  {arrow} {delta}")


def pct(v):
    return f"{round(v*100)}%" if v is not None else "-"


def _bar(v, width=10):
    if v is None:
        return ""
    filled = int(round(v / 10 * width))
    return "[" + "█" * filled + "·" * (width - filled) + "]"


def main():
    conn = init_db()
    mode = sys.argv[1] if len(sys.argv) > 1 else "month"
    if mode == "week":
        wk = int(sys.argv[2]) if len(sys.argv) > 2 else None
        report_week(conn, wk)
    elif mode == "month":
        mo = int(sys.argv[2]) if len(sys.argv) > 2 else None
        report_month(conn, mo)
    else:
        print("用法: python analyze.py [week|month] [周号|月份]")
    conn.close()


if __name__ == "__main__":
    main()
