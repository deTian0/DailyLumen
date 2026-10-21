"""monthly —— 月度深评一键聚合（M27 / v1.33.0）。

用法:
    python -m review_tool month 202610 --deep

背景：``month --write`` 只有结构化骨架；``chart`` / ``correlate`` / ``fuse`` /
``stats`` 各自为战，做一次月度回顾要在四五条命令间来回抄。本模块把五路输出聚合成
一份「深评素材 md」，**每个数字都能用对应单命令复现**：

- 一、月份概览      ← ``month <YYYYMM>``（``analyze.collect`` 月窗口）
- 二、本月趋势图    ← ``chart``（同七序列，窗口切到本月，SVG 落 ``exports/charts/``）
- 三、跨维相关      ← ``correlate``（月窗口内计算，n ≥ MIN_SAMPLES 才出 r）
- 四、熔断信号      ← ``fuse``（月窗口内计算：连续段 / 漂移**不跨月**回溯）
- 五、库快照        ← ``stats``

明确不做（路线图 M27）：不写叙事结论；不出 HTML（零依赖约束，md + SVG 够用）；
不改评分与熔断口径。
"""

from __future__ import annotations

import os
from datetime import datetime

from ..config import BASE_DIR, DB_PATH, INPUT_DIR
from ..storage.db import init_db
from . import chart as chart_mod
from . import correlate, fuse
from . import stats as stats_mod
from .analyze import collect as analyze_collect

EXPORT_DIR = os.path.join(BASE_DIR, "exports")
CHART_DIR = os.path.join(EXPORT_DIR, "charts")


def _month_svg(conn, ym: int) -> str:
    """本月窗口的趋势 SVG（与 ``chart`` 同序列、同渲染器）。"""
    prefix = f"{ym // 100:04d}-{ym % 100:02d}-"
    cols = [c for c, *_ in chart_mod.DEFAULT_SERIES]
    dates, series = chart_mod.fetch_series(conn, cols)
    idx = [i for i, d in enumerate(dates) if d.startswith(prefix)]
    md_dates = [dates[i] for i in idx]
    md_series = {c: [series[c][i] for i in idx] for c in cols}
    return chart_mod.render_svg(md_dates, md_series)


def _fmt(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else str(v)
    return str(v)


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def build_month_deep(
    conn,
    ym: int,
    *,
    input_dir: str | None = None,
    db_path: str | None = None,
    out_dir: str | None = None,
) -> dict | None:
    """聚合月度深评素材并落盘。返回 ``{"md_path", "chart_path", "md"}``。

    月份无数据返回 ``None``。幂等：直接覆盖旧素材（素材非手写件）。
    """
    s = analyze_collect(conn, "month=?", (ym,), f"月份 {ym}")
    if s is None:
        return None
    year, mon = divmod(ym, 100)

    svg = _month_svg(conn, ym)
    out_root = out_dir or EXPORT_DIR
    chart_dir = os.path.join(out_root, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    chart_name = f"month-{ym}.svg"
    chart_path = os.path.join(chart_dir, chart_name)
    with open(chart_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)

    # 三、月窗口跨维相关
    cor = correlate.collect(conn, month=ym)
    # 四、熔断信号（月窗口：连续段 / 漂移不跨月）
    fz = fuse.find_fuses(conn, month=ym)
    # 五、库快照
    snap = stats_mod.collect(conn, input_dir or INPUT_DIR, db_path=db_path or DB_PATH)

    L: list[str] = [
        f"# 月度深评素材 · {year} 年 {mon} 月",
        "",
        f"> 由 `python -m review_tool month {ym} --deep` 生成（"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}）。每个数字都能用对应单命令复现："
        "概览 = `month`、相关 = `correlate`、信号 = `fuse`、快照 = `stats`、"
        "图 = `chart --out`。叙事结论请人工续写 —— 本文件只供数。",
        "",
        "## 一、月份概览（month 口径）",
        "",
        f"记录 **{s['days']} 天** ｜ 数据完整度 **{s['completeness']['rate_pct']}%** ｜ "
        f"最差维度：**{s['worst_dim']['name']}**（{_fmt(s['worst_dim']['value'])}）",
        "",
        "| 维度 | 月均值 |",
        "|------|--------|",
        f"| 系统 | **{_fmt(s['system_avg'])}** |",
    ]
    for label, v in s["dims"].items():
        L.append(f"| {label} | {_fmt(v)} |")
    fa = s["field_avgs"]
    L += [
        "",
        "> 客观指标均值：" + " ｜ ".join(
            f"{lbl} {_fmt(v, 1) if 'kcal' not in lbl else _fmt(v, 0)}"
            for lbl, v in fa.items()
        ),
        f"> 早餐按时 **{_pct(s['breakfast_on_time_pct'])}**",
    ]
    if s.get("macros"):
        sp = s["macros"]["split_pct"]
        L.append(
            f"> 宏量日均（记录 {s['macros']['days']} 天）：碳水 {s['macros']['carbs_g']}g ／ "
            f"脂肪 {s['macros']['fat_g']}g ／ 蛋白 {s['macros']['protein_g']}g"
            f"（碳水 {sp['carbs']}%・脂肪 {sp['fat']}%・蛋白 {sp['protein']}%）"
        )
    st = s["training"]
    if st["total"]:
        L.append(
            f"> 训练日达标 **{st['done']}/{st['total']}**"
            f"（{_pct(st['done'] / st['total'])}；分母 = `training_day` 标记）"
        )
    adh = s.get("track_adherence") or {}
    items = adh.get("items") or []
    if items:
        t_done = sum(i["done"] for i in items)
        t_rec = sum(i["recorded"] for i in items)
        L.append(f"> 个人打卡完成率 **{t_done}/{t_rec}**（{_pct(t_done / t_rec if t_rec else None)}）")
    hadh = s.get("habit_adherence") or {}
    hitems = hadh.get("items") or []
    if hitems:
        h_done = sum(i["done"] for i in hitems)
        h_rec = sum(i["recorded"] for i in hitems)
        L.append(f"> 行为习惯完成率 **{h_done}/{h_rec}**（{_pct(h_done / h_rec if h_rec else None)}）")

    L += [
        "",
        "## 二、本月趋势图",
        "",
        f"![本月趋势](charts/{chart_name})",
        "",
        "> 同 `chart` 默认七序列（"
        + "、".join(lbl for _, lbl, *_ in chart_mod.DEFAULT_SERIES)
        + "），窗口仅本月；完整历史图请跑 `chart --out`。",
        "",
        "## 三、月窗口跨维相关（correlate 口径）",
        "",
        f"> 样本对齐 {cor['date_count']} 天；n ≥ {cor['min_samples']} 才出 r。"
        f"{cor['disclaimer']}",
        "",
        "| 配对 | n | r | 强度 |",
        "|------|---|---|------|",
    ]
    for p_ in cor["pairs"]:
        r_txt = "—" if p_["r"] is None else f"{p_['r']:+.3f}"
        L.append(
            f"| {p_['label']} | {p_['n']} | {r_txt} | {p_['strength'] or '样本不足'} |"
        )

    L += [
        "",
        "## 四、熔断信号（fuse 口径 · 仅本月窗口）",
        "",
        f"> 阈值 {fz['threshold']}、熔断需连续 {fz['days']} 天；"
        "**月窗口内**连续段 / 漂移不跨月回溯（全历史口径请单跑 `fuse`）。",
        "",
    ]
    fused = [i for i in fz["absolute"] if i["fused"]]
    long_run = [i for i in fz["absolute"] if i["long_run"] and not i["fused"]]
    drift = [d for d in fz["drift"] if d["moved"]]
    if fused:
        for i in fused:
            L.append(
                f"- 🔴 **{i['label']}**：连续 {i['run']} 天 < {fz['threshold']}"
                f"（自 {i['since']}）"
            )
    else:
        L.append(f"- 绝对熔断：本月无（连续 < {fz['threshold']} 未达 {fz['days']} 天）")
    for i in long_run:
        L.append(f"- 🟡 {i['label']}：连续 {i['run']} 天偏低（接近熔断，注意）")
    if drift:
        for d in drift:
            L.append(
                f"- 🟡 {d['label']} 相对漂移：近段 {_fmt(d['recent'])} vs 基线 "
                f"{_fmt(d['baseline'])}（Δ {_fmt(d['delta'])}）"
            )
    if not fused and not long_run and not drift:
        L.append("- 相对漂移：本月无显著信号")

    L += [
        "",
        "## 五、库快照（stats 口径）",
        "",
        f"- 入库 **{snap['days']}** 天（最新 {snap['latest_date'] or '—'}）｜ "
        f"打卡 {snap['tracks']} 行 ｜ habit_logs {snap['habit_logs']} 行 ｜ "
        f"体征 {snap['body_metrics']} 条",
        f"- 训练 {snap['training_sessions']} 课 / {snap['training_items']} 动作项 ｜ "
        f"库 {snap['db_size_kb']} KB ｜ schema v{snap['schema_version']}",
        f"- 历史断更 **{len(snap['history_gaps'])}** 处 / 共缺 "
        f"{snap['history_gap_days']} 天（明细见 `stats`）",
        "",
        "---",
        "",
        f"*深评素材：`exports/month-deep-{ym}.md` ｜ 图：`exports/charts/{chart_name}` ｜ "
        f"月窗口 = {year}-{mon:02d}-01 ~ {year}-{mon:02d}-31*",
        "",
    ]
    md = "\n".join(L)
    md_path = os.path.join(out_root, f"month-deep-{ym}.md")
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    return {"md_path": md_path, "chart_path": chart_path, "md": md}


def main(argv: list[str] | None = None) -> int:
    """独立入口：`python -m review_tool.reports.monthly <YYYYMM>`（少用，走 month --deep）。"""
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    pos = [a for a in argv if not a.startswith("-")]
    if not pos or not pos[0].isdigit() or len(pos[0]) != 6:
        print("用法: python -m review_tool month <YYYYMM> --deep")
        return 2
    conn = init_db()
    try:
        res = build_month_deep(conn, int(pos[0]))
    finally:
        conn.close()
    if res is None:
        print(f"月份 {pos[0]} 暂无数据。")
        return 1
    print(f"[written] {res['md_path']}")
    print(f"[chart] {res['chart_path']}")
    return 0
