"""跨维关联统计：睡眠 / 训练 / 体重 / 热量 / 学习的联合观察。

用法:
    python -m review_tool correlate
    python -m review_tool correlate --json
    python -m review_tool correlate --min-samples 10

设计（M15 / v1.19.0）
-------------------
- 相关系数由本模块脚本计算（Pearson），⛔ 不许手写数字进文案。
- 样本 < ``MIN_SAMPLES``（默认 10）时只输出「观察」，
  文案含「样本不足，仅作观察」，**不输出数字结论**（无 r / 强度档）。
- 相关 ≠ 因果：文案一律陈述相关性，不下因果判断。
- 数据复用既有表字段（R1）；不改四维、不碰 schema。
"""
from __future__ import annotations

import json
import math
import sys

from ..storage.db import init_db, load_body_metrics

# 样本门槛：低于此值只输出观察，不输出相关系数结论
MIN_SAMPLES = 10

# (左键, 右键, 显示名) —— 键对应 collect 里对齐后的列
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("sleep_h", "exercise_min", "睡眠 ↔ 训练量"),
    ("sleep_h", "learn_h", "睡眠 ↔ 学习投入"),
    ("exercise_min", "weight_kg", "训练量 ↔ 体重"),
    ("diet_kcal", "weight_kg", "热量 ↔ 体重"),
    ("diet_kcal", "exercise_min", "热量 ↔ 训练量"),
    ("learn_h", "exercise_min", "学习投入 ↔ 训练量"),
)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson 积矩相关系数；样本 < 2 或方差为 0 时返回 None。"""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx2 = 0.0
    dy2 = 0.0
    for x, y in zip(xs, ys, strict=True):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    if dx2 <= 0.0 or dy2 <= 0.0:
        return None
    return num / math.sqrt(dx2 * dy2)


def strength_label(r: float | None) -> str | None:
    """相关强度档（仅陈述强度，不下因果）。``None`` 表示无法分档。"""
    if r is None:
        return None
    a = abs(r)
    if a < 0.2:
        return "很弱"
    if a < 0.4:
        return "弱"
    if a < 0.6:
        return "中等"
    if a < 0.8:
        return "较强"
    return "强"


def _aligned_series(conn) -> dict[str, dict[str, float | None]]:
    """按日对齐多维序列；键为日期。"""
    by_date: dict[str, dict[str, float | None]] = {}
    for r in conn.execute(
        "SELECT date, sleep_h, exercise_min, diet_kcal, learn_h "
        "FROM daily_reviews ORDER BY date"
    ):
        by_date[r["date"]] = {
            "sleep_h": None if r["sleep_h"] is None else float(r["sleep_h"]),
            "exercise_min": (
                None if r["exercise_min"] is None else float(r["exercise_min"])
            ),
            "diet_kcal": (
                None if r["diet_kcal"] is None else float(r["diet_kcal"])
            ),
            "learn_h": None if r["learn_h"] is None else float(r["learn_h"]),
            "weight_kg": None,
        }
    for r in load_body_metrics(conn):
        d = r["date"]
        w = None if r["weight_kg"] is None else float(r["weight_kg"])
        if d not in by_date:
            by_date[d] = {
                "sleep_h": None,
                "exercise_min": None,
                "diet_kcal": None,
                "learn_h": None,
                "weight_kg": w,
            }
        else:
            by_date[d]["weight_kg"] = w
    return by_date


def _pair_samples(
    by_date: dict[str, dict[str, float | None]],
    left: str,
    right: str,
) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for d in sorted(by_date):
        row = by_date[d]
        a, b = row.get(left), row.get(right)
        if a is None or b is None:
            continue
        xs.append(a)
        ys.append(b)
    return xs, ys


def collect(conn, *, min_samples: int = MIN_SAMPLES) -> dict:
    """汇聚跨维关联（结构化，供文本 / JSON 共用）。"""
    by_date = _aligned_series(conn)
    pairs_out: list[dict] = []
    for left, right, label in PAIRS:
        xs, ys = _pair_samples(by_date, left, right)
        n = len(xs)
        sufficient = n >= min_samples
        entry: dict = {
            "left": left,
            "right": right,
            "label": label,
            "n": n,
            "sufficient": sufficient,
            "r": None,
            "strength": None,
        }
        if sufficient:
            r = pearson(xs, ys)
            entry["r"] = None if r is None else round(r, 3)
            entry["strength"] = strength_label(r)
        pairs_out.append(entry)

    return {
        "min_samples": min_samples,
        "date_count": len(by_date),
        "pairs": pairs_out,
        "disclaimer": "相关≠因果：以下仅陈述相关性，不下因果判断。",
    }


def render(data: dict) -> str:
    """人类可读文本。样本不足时不输出数字结论。"""
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 跨维关联")
    L.append("=" * 52)
    L.append("")
    L.append(f"  {data['disclaimer']}")
    L.append(f"  样本门槛: ≥ {data['min_samples']} 组才输出相关系数")
    L.append(f"  对齐日期: {data['date_count']} 天")
    L.append("")

    for p in data["pairs"]:
        L.append(f"[{p['label']}]  n={p['n']}")
        if not p["sufficient"]:
            L.append("  样本不足，仅作观察（不输出数字结论）")
            L.append("  观察：配对天数尚少，待更多同日记录后再看相关性。")
        else:
            r = p["r"]
            if r is None:
                L.append("  相关系数无法计算（方差为 0 或退化）")
            else:
                strength = p["strength"] or "?"
                direction = "正" if r > 0 else ("负" if r < 0 else "零")
                L.append(
                    f"  相关系数 r={r:+.3f}（{direction}相关 · 强度 {strength}）"
                )
                L.append(
                    "  陈述：两指标同日取值呈上述相关；"
                    "相关不等于因果，勿据此改训练/饮食处方。"
                )
        L.append("")

    return "\n".join(L).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(
            "用法: correlate [--json] [--min-samples N]\n"
            "  跨维关联（睡眠/训练/体重/热量/学习）；样本 < 10 仅观察、无数字结论。\n"
            "  相关≠因果。"
        )
        return 0
    as_json = "--json" in argv
    min_samples = MIN_SAMPLES
    if "--min-samples" in argv:
        i = argv.index("--min-samples")
        if i + 1 >= len(argv):
            print("correlate: --min-samples 需要整数", file=sys.stderr)
            return 2
        try:
            min_samples = int(argv[i + 1])
        except ValueError:
            print("correlate: --min-samples 需要整数", file=sys.stderr)
            return 2
        if min_samples < 2:
            print("correlate: --min-samples 至少为 2", file=sys.stderr)
            return 2

    conn = init_db()
    try:
        data = collect(conn, min_samples=min_samples)
    finally:
        conn.close()

    if as_json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
