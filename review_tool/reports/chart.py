"""离线趋势图：手写 SVG（零依赖），可拷走 / 打印。

用法:
    python -m review_tool chart              # 写 exports/trends.svg
    python -m review_tool chart --stdout     # 打印 SVG
    python -m review_tool chart --out DIR

候选序列：系统分、四维分、睡眠、屏幕（可按列扩展）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from ..config import BASE_DIR
from ..storage.db import init_db

EXPORT_DIR = os.path.join(BASE_DIR, "exports")

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


def render_svg(dates: list[str], series: dict[str, list[float | None]],
               meta: list[tuple[str, str, str, str]] | None = None,
               *, width: int = 960, height: int = 420) -> str:
    """多折线 SVG（每条序列独立归一化到图高，便于同框对照形态）。"""
    meta = meta or list(DEFAULT_SERIES)
    pad_l, pad_r, pad_t, pad_b = 48, 24, 36, 48
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(dates)
    layers: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
        f'<text x="{pad_l}" y="22" font-family="sans-serif" font-size="14" fill="#111">'
        f"DailyLumen 趋势（{dates[0] if dates else '-'} ~ {dates[-1] if dates else '-'} · {n} 天）</text>",
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
        f'fill="#fff" stroke="#e5e7eb"/>',
    ]
    # 网格
    for i in range(5):
        y = pad_t + plot_h * i / 4
        layers.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="#f3f4f6" stroke-width="1"/>'
        )

    legend_x = pad_l
    for col, label, color, _hint in meta:
        vals = series.get(col) or []
        # 分数量纲 0-10；时长用数据自域
        if col.endswith("_score") or col == "system_score":
            pts = _scale(vals, pad_t, pad_t + plot_h, 0.0, 10.0)
        else:
            pts = _scale(vals, pad_t, pad_t + plot_h)
        parts = []
        for p in pts:
            if p is None:
                continue
            x = pad_l + p[0] * plot_w
            y = p[1]
            parts.append(f"{x:.1f},{y:.1f}")
        if parts:
            layers.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="1.8" '
                f'points="{" ".join(parts)}"/>'
            )
        layers.append(
            f'<text x="{legend_x}" y="{height - 14}" font-family="sans-serif" '
            f'font-size="11" fill="{color}">{label}</text>'
        )
        legend_x += 72

    # x 轴起止日期
    if dates:
        layers.append(
            f'<text x="{pad_l}" y="{height - 28}" font-family="sans-serif" '
            f'font-size="10" fill="#6b7280">{dates[0]}</text>'
        )
        layers.append(
            f'<text x="{pad_l + plot_w}" y="{height - 28}" font-family="sans-serif" '
            f'font-size="10" fill="#6b7280" text-anchor="end">{dates[-1]}</text>'
        )
    layers.append("</svg>")
    return "\n".join(layers) + "\n"


def build_chart(conn) -> str:
    cols = [m[0] for m in DEFAULT_SERIES]
    dates, series = fetch_series(conn, cols)
    return render_svg(dates, series, list(DEFAULT_SERIES))


def write_chart(svg: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = svg.replace("\r\n", "\n").encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    back = open(path, "rb").read()
    if back != data:
        raise OSError(f"写盘回读失败: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    to_stdout = "--stdout" in argv
    out_dir = EXPORT_DIR
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out_dir = argv[i + 1]
    conn = init_db()
    try:
        svg = build_chart(conn)
    finally:
        conn.close()
    if to_stdout:
        sys.stdout.write(svg)
        return 0
    path = os.path.join(out_dir, "trends.svg")
    write_chart(svg, path)
    print(f"[chart] {path}  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
