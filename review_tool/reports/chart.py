"""离线趋势图：手写 SVG（零依赖），可拷走 / 打印。

用法:
    python -m review_tool chart              # 写 exports/trends.svg（四维默认）
    python -m review_tool chart --stdout     # 打印 SVG
    python -m review_tool chart --out DIR
    python -m review_tool chart --type body|training|nutrition|all

M15：体重曲线（目标带 + 7 日均线）、训练量柱状、热量 vs 体重双轴。
均线复用 ``core.body.moving_average``（R1，不另写算法）。
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import datetime

from ..config import BASE_DIR, BODY_TARGETS
from ..core.body import moving_average
from ..storage.db import init_db, load_body_metrics

EXPORT_DIR = os.path.join(BASE_DIR, "exports")

CHART_TYPES = ("trends", "body", "training", "nutrition", "all")

# 图上默认展示的序列：(列名, 图例, 颜色, y 轴提示)
DEFAULT_SERIES = (
    ("system_score", "系统分", "#2563eb", "0-10"),
    ("health_score", "健康", "#16a34a", "0-10"),
    ("work_score", "工作", "#ca8a04", "0-10"),
    ("learn_score", "学习", "#9333ea", "0-10"),
    ("life_score", "生活", "#db2777", "0-10"),
    ("sleep_h", "睡眠h", "#0891b2", "h"),
    ("phone_h", "屏幕h", "#ea580c", "h"),
)


def fetch_series(conn, columns: list[str]) -> tuple[list[str], dict[str, list[float | None]]]:
    """按日期升序取列；缺失为 None。"""
    cols_sql = ", ".join(["date"] + list(columns))
    rows = list(conn.execute(
        f"SELECT {cols_sql} FROM daily_reviews ORDER BY date"
    ))
    dates = [r["date"] for r in rows]
    series: dict[str, list[float | None]] = {c: [] for c in columns}
    for r in rows:
        for c in columns:
            v = r[c]
            series[c].append(None if v is None else float(v))
    return dates, series


def _scale(vals: list[float | None], y0: float, y1: float,
           vmin: float | None = None, vmax: float | None = None) -> list[tuple[float, float] | None]:
    nums = [v for v in vals if v is not None]
    if not nums:
        return [None] * len(vals)
    lo = vmin if vmin is not None else min(nums)
    hi = vmax if vmax is not None else max(nums)
    if hi <= lo:
        hi = lo + 1.0
    out: list[tuple[float, float] | None] = []
    n = max(1, len(vals) - 1)
    for i, v in enumerate(vals):
        if v is None:
            out.append(None)
            continue
        x = i / n
        y = y1 - (v - lo) / (hi - lo) * (y1 - y0)
        out.append((x, y))
    return out


def _domain(vals: list[float | None],
            pad: float = 0.05) -> tuple[float, float]:
    nums = [v for v in vals if v is not None]
    if not nums:
        return 0.0, 1.0
    lo, hi = min(nums), max(nums)
    if hi <= lo:
        return lo - 1.0, hi + 1.0
    span = hi - lo
    return lo - span * pad, hi + span * pad


def _polyline(pts: list[tuple[float, float] | None], pad_l: float, plot_w: float,
              color: str, width: float = 1.8, dash: str | None = None) -> str:
    parts = []
    for p in pts:
        if p is None:
            continue
        x = pad_l + p[0] * plot_w
        y = p[1]
        parts.append(f"{x:.1f},{y:.1f}")
    if not parts:
        return ""
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline fill="none" stroke="{color}" stroke-width="{width}"'
        f'{dash_attr} points="{" ".join(parts)}"/>'
    )


def _svg_shell(title: str, *, width: int, height: int,
               pad_l: int, pad_r: int, pad_t: int, pad_b: int) -> tuple[list[str], int, int]:
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    layers: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
        f'<text x="{pad_l}" y="22" font-family="sans-serif" font-size="14" fill="#111">'
        f"{title}</text>",
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
        f'fill="#fff" stroke="#e5e7eb"/>',
    ]
    for i in range(5):
        y = pad_t + plot_h * i / 4
        layers.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="#f3f4f6" stroke-width="1"/>'
        )
    return layers, plot_w, plot_h


def _date_labels(layers: list[str], dates: list[str], pad_l: int, pad_t: int,
                 plot_w: int, plot_h: int, height: int) -> None:
    if not dates:
        return
    layers.append(
        f'<text x="{pad_l}" y="{height - 28}" font-family="sans-serif" '
        f'font-size="10" fill="#6b7280">{dates[0]}</text>'
    )
    layers.append(
        f'<text x="{pad_l + plot_w}" y="{height - 28}" font-family="sans-serif" '
        f'font-size="10" fill="#6b7280" text-anchor="end">{dates[-1]}</text>'
    )


def render_svg(dates: list[str], series: dict[str, list[float | None]],
               meta: list[tuple[str, str, str, str]] | None = None,
               *, width: int = 960, height: int = 420) -> str:
    """多折线 SVG（每条序列独立归一化到图高，便于同框对照形态）。"""
    meta = meta or list(DEFAULT_SERIES)
    pad_l, pad_r, pad_t, pad_b = 48, 24, 36, 48
    n = len(dates)
    title = (
        f"DailyLumen 趋势（{dates[0] if dates else '-'} ~ "
        f"{dates[-1] if dates else '-'} · {n} 天）"
    )
    layers, plot_w, plot_h = _svg_shell(
        title, width=width, height=height,
        pad_l=pad_l, pad_r=pad_r, pad_t=pad_t, pad_b=pad_b,
    )

    legend_x = pad_l
    for col, label, color, _hint in meta:
        vals = series.get(col) or []
        if col.endswith("_score") or col == "system_score":
            pts = _scale(vals, pad_t, pad_t + plot_h, 0.0, 10.0)
        else:
            pts = _scale(vals, pad_t, pad_t + plot_h)
        pl = _polyline(pts, pad_l, plot_w, color)
        if pl:
            layers.append(pl)
        layers.append(
            f'<text x="{legend_x}" y="{height - 14}" font-family="sans-serif" '
            f'font-size="11" fill="{color}">{label}</text>'
        )
        legend_x += 72

    _date_labels(layers, dates, pad_l, pad_t, plot_w, plot_h, height)
    layers.append("</svg>")
    return "\n".join(layers) + "\n"


def build_chart(conn) -> str:
    cols = [m[0] for m in DEFAULT_SERIES]
    dates, series = fetch_series(conn, cols)
    return render_svg(dates, series, list(DEFAULT_SERIES))


def fetch_body_series(conn) -> tuple[list[str], list[float | None]]:
    """体征体重序列（升序）；无体重行跳过。"""
    rows = load_body_metrics(conn)
    dates: list[str] = []
    weights: list[float | None] = []
    for r in rows:
        w = r["weight_kg"]
        if w is None:
            continue
        dates.append(r["date"])
        weights.append(float(w))
    return dates, weights


def render_body_svg(
    dates: list[str],
    weights: list[float | None],
    *,
    target_low: float | None = None,
    target_high: float | None = None,
    width: int = 960,
    height: int = 420,
) -> str:
    """体重曲线 + 目标带 + 7 日均线（均线算法 = core.body.moving_average）。"""
    pad_l, pad_r, pad_t, pad_b = 56, 24, 36, 56
    n = len(dates)
    title = (
        f"DailyLumen 体重（{dates[0] if dates else '-'} ~ "
        f"{dates[-1] if dates else '-'} · {n} 点）"
    )
    layers, plot_w, plot_h = _svg_shell(
        title, width=width, height=height,
        pad_l=pad_l, pad_r=pad_r, pad_t=pad_t, pad_b=pad_b,
    )

    ma7 = moving_average(weights, window=7)
    domain_vals = list(weights) + [v for v in ma7 if v is not None]
    if target_low is not None:
        domain_vals.append(target_low)
    if target_high is not None:
        domain_vals.append(target_high)
    y_lo, y_hi = _domain(domain_vals)

    # 目标带（矩形）
    if target_low is not None and target_high is not None and y_hi > y_lo:
        lo, hi = (target_low, target_high) if target_low <= target_high else (
            target_high, target_low)
        y_top = pad_t + (1 - (hi - y_lo) / (y_hi - y_lo)) * plot_h
        y_bot = pad_t + (1 - (lo - y_lo) / (y_hi - y_lo)) * plot_h
        band_h = max(1.0, y_bot - y_top)
        layers.append(
            f'<rect id="target-band" x="{pad_l}" y="{y_top:.1f}" '
            f'width="{plot_w}" height="{band_h:.1f}" '
            f'fill="#bbf7d0" fill-opacity="0.45" stroke="none"/>'
        )
        layers.append(
            f'<text x="{pad_l + 4}" y="{y_top + 12:.1f}" font-family="sans-serif" '
            f'font-size="10" fill="#15803d">目标带 {lo:g}–{hi:g} kg</text>'
        )

    pts_w = _scale(weights, pad_t, pad_t + plot_h, y_lo, y_hi)
    pts_ma = _scale(ma7, pad_t, pad_t + plot_h, y_lo, y_hi)
    pl_w = _polyline(pts_w, pad_l, plot_w, "#2563eb", 2.0)
    if pl_w:
        layers.append(pl_w)
    pl_ma = _polyline(pts_ma, pad_l, plot_w, "#ea580c", 1.6, dash="6 3")
    if pl_ma:
        layers.append(pl_ma)

    layers.append(
        f'<text x="{pad_l}" y="{height - 14}" font-family="sans-serif" '
        f'font-size="11" fill="#2563eb">体重</text>'
    )
    layers.append(
        f'<text x="{pad_l + 56}" y="{height - 14}" font-family="sans-serif" '
        f'font-size="11" fill="#ea580c">7日均</text>'
    )
    _date_labels(layers, dates, pad_l, pad_t, plot_w, plot_h, height)
    layers.append("</svg>")
    return "\n".join(layers) + "\n"


def build_body_chart(conn) -> str:
    dates, weights = fetch_body_series(conn)
    low = BODY_TARGETS.get("weight_kg_low")
    high = BODY_TARGETS.get("weight_kg_high")
    return render_body_svg(dates, weights, target_low=low, target_high=high)


def fetch_training_series(conn) -> tuple[list[str], list[float | None]]:
    """训练量：优先 ``exercise_min``（健康分唯一运动输入，R2）。"""
    rows = list(conn.execute(
        "SELECT date, exercise_min FROM daily_reviews ORDER BY date"
    ))
    dates = [r["date"] for r in rows]
    vals: list[float | None] = [
        None if r["exercise_min"] is None else float(r["exercise_min"])
        for r in rows
    ]
    return dates, vals


def render_training_svg(
    dates: list[str],
    volumes: list[float | None],
    *,
    width: int = 960,
    height: int = 420,
) -> str:
    """训练量柱状图（分钟）。"""
    pad_l, pad_r, pad_t, pad_b = 56, 24, 36, 56
    n = len(dates)
    title = (
        f"DailyLumen 训练量（{dates[0] if dates else '-'} ~ "
        f"{dates[-1] if dates else '-'} · {n} 天）"
    )
    layers, plot_w, plot_h = _svg_shell(
        title, width=width, height=height,
        pad_l=pad_l, pad_r=pad_r, pad_t=pad_t, pad_b=pad_b,
    )

    y_lo, y_hi = 0.0, max(_domain(volumes)[1], 1.0)
    # 柱宽：有数据时按点数均分，留间隙
    slot = plot_w / max(n, 1)
    bar_w = max(1.0, slot * 0.65)
    for i, v in enumerate(volumes):
        if v is None:
            continue
        x = pad_l + i * slot + (slot - bar_w) / 2
        frac = (v - y_lo) / (y_hi - y_lo) if y_hi > y_lo else 0.0
        bar_h = max(1.0, frac * plot_h)
        y = pad_t + plot_h - bar_h
        layers.append(
            f'<rect class="training-bar" x="{x:.1f}" y="{y:.1f}" '
            f'width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="#16a34a" fill-opacity="0.85"/>'
        )

    layers.append(
        f'<text x="{pad_l}" y="{height - 14}" font-family="sans-serif" '
        f'font-size="11" fill="#16a34a">训练量(min)</text>'
    )
    _date_labels(layers, dates, pad_l, pad_t, plot_w, plot_h, height)
    layers.append("</svg>")
    return "\n".join(layers) + "\n"


def build_training_chart(conn) -> str:
    dates, volumes = fetch_training_series(conn)
    return render_training_svg(dates, volumes)


def fetch_nutrition_series(
    conn,
) -> tuple[list[str], list[float | None], list[float | None]]:
    """按日对齐：热量（daily_reviews）与体重（body_metrics）。"""
    kcal_rows = {
        r["date"]: None if r["diet_kcal"] is None else float(r["diet_kcal"])
        for r in conn.execute(
            "SELECT date, diet_kcal FROM daily_reviews ORDER BY date"
        )
    }
    weight_rows = {
        r["date"]: None if r["weight_kg"] is None else float(r["weight_kg"])
        for r in load_body_metrics(conn)
    }
    dates = sorted(set(kcal_rows) | set(weight_rows))
    kcals = [kcal_rows.get(d) for d in dates]
    weights = [weight_rows.get(d) for d in dates]
    return dates, kcals, weights


def render_nutrition_svg(
    dates: list[str],
    kcals: list[float | None],
    weights: list[float | None],
    *,
    width: int = 960,
    height: int = 420,
) -> str:
    """热量（左轴折线）vs 体重（右轴折线）双轴图。"""
    pad_l, pad_r, pad_t, pad_b = 56, 56, 36, 56
    n = len(dates)
    title = (
        f"DailyLumen 热量 vs 体重（{dates[0] if dates else '-'} ~ "
        f"{dates[-1] if dates else '-'} · {n} 天）"
    )
    layers, plot_w, plot_h = _svg_shell(
        title, width=width, height=height,
        pad_l=pad_l, pad_r=pad_r, pad_t=pad_t, pad_b=pad_b,
    )

    k_lo, k_hi = _domain(kcals)
    w_lo, w_hi = _domain(weights)
    pts_k = _scale(kcals, pad_t, pad_t + plot_h, k_lo, k_hi)
    pts_w = _scale(weights, pad_t, pad_t + plot_h, w_lo, w_hi)

    pl_k = _polyline(pts_k, pad_l, plot_w, "#ea580c", 1.8)
    if pl_k:
        layers.append(pl_k)
    pl_w = _polyline(pts_w, pad_l, plot_w, "#2563eb", 1.8)
    if pl_w:
        layers.append(pl_w)

    # 轴标注
    layers.append(
        f'<text x="{pad_l}" y="{pad_t - 4}" font-family="sans-serif" '
        f'font-size="10" fill="#ea580c">热量 kcal</text>'
    )
    layers.append(
        f'<text x="{pad_l + plot_w}" y="{pad_t - 4}" font-family="sans-serif" '
        f'font-size="10" fill="#2563eb" text-anchor="end">体重 kg</text>'
    )
    layers.append(
        f'<text x="{pad_l}" y="{height - 14}" font-family="sans-serif" '
        f'font-size="11" fill="#ea580c">热量</text>'
    )
    layers.append(
        f'<text x="{pad_l + 56}" y="{height - 14}" font-family="sans-serif" '
        f'font-size="11" fill="#2563eb">体重</text>'
    )
    _date_labels(layers, dates, pad_l, pad_t, plot_w, plot_h, height)
    layers.append("</svg>")
    return "\n".join(layers) + "\n"


def build_nutrition_chart(conn) -> str:
    dates, kcals, weights = fetch_nutrition_series(conn)
    return render_nutrition_svg(dates, kcals, weights)


def write_chart(svg: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = svg.replace("\r\n", "\n").encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    with open(path, "rb") as f:
        back = f.read()
    if back != data:
        raise OSError(f"写盘回读失败: {path}")
    return path


def _parse_type(argv: list[str]) -> str:
    if "--type" not in argv:
        return "trends"
    i = argv.index("--type")
    if i + 1 >= len(argv):
        raise SystemExit("chart: --type 需要参数 body|training|nutrition|all")
    t = argv[i + 1].strip().lower()
    if t not in ("body", "training", "nutrition", "all", "trends"):
        raise SystemExit(
            f"chart: 未知 --type {t!r}（可选 body|training|nutrition|all）"
        )
    return t


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(
            "用法: chart [--type body|training|nutrition|all] "
            "[--out DIR] [--stdout]\n"
            "  默认（无 --type）写出四维趋势 exports/trends.svg\n"
            "  --type body       体重曲线（目标带 + 7 日均）→ body.svg\n"
            "  --type training   训练量柱状 → training.svg\n"
            "  --type nutrition  热量 vs 体重双轴 → nutrition.svg\n"
            "  --type all        上述三张 + 默认趋势一并写出"
        )
        return 0
    to_stdout = "--stdout" in argv
    out_dir = EXPORT_DIR
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out_dir = argv[i + 1]
    chart_type = _parse_type(argv)

    by_type: dict[str, list[tuple[str, Callable]]] = {
        "trends": [("trends.svg", build_chart)],
        "body": [("body.svg", build_body_chart)],
        "training": [("training.svg", build_training_chart)],
        "nutrition": [("nutrition.svg", build_nutrition_chart)],
        "all": [
            ("trends.svg", build_chart),
            ("body.svg", build_body_chart),
            ("training.svg", build_training_chart),
            ("nutrition.svg", build_nutrition_chart),
        ],
    }
    builders = by_type[chart_type]

    conn = init_db()
    try:
        svgs: list[tuple[str, str]] = []
        for fname, fn in builders:
            svgs.append((fname, fn(conn)))
    finally:
        conn.close()

    if to_stdout:
        # 多图时用注释分隔
        for i, (fname, svg) in enumerate(svgs):
            if i:
                sys.stdout.write(f"\n<!-- {fname} -->\n")
            sys.stdout.write(svg)
        return 0

    for fname, svg in svgs:
        path = os.path.join(out_dir, fname)
        write_chart(svg, path)
        print(f"[chart] {path}  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
