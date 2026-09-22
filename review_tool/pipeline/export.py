"""导出子命令：把库里的结构化数据导出为 CSV / JSON，便于外部工具或作图使用。

    python -m review_tool export                     # 默认导出 CSV 到 exports/
    python -m review_tool export --format json       # 导出单个 JSON
    python -m review_tool export --out D:/somewhere  # 指定输出目录
    python -m review_tool export --stdout            # 直接打印到终端

CSV 使用 ``utf-8-sig`` 编码，可直接被 Excel 打开不乱码；
personal_tracks 同时导出**明细**（每日每项）与**按规范项聚合的依从率**。
"""
from __future__ import annotations

import csv
import json
import os
import sys

from ..config import BASE_DIR
from ..storage.db import COLUMNS, init_db

DEFAULT_OUT_DIR = os.path.join(BASE_DIR, "exports")


def _daily_rows(conn):
    return [dict(r) for r in conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM daily_reviews ORDER BY date"
    )]


def _track_rows(conn):
    return [dict(r) for r in conn.execute(
        "SELECT date, track_key, category, item_key, item, done, note "
        "FROM personal_tracks ORDER BY date, item_key, track_key"
    )]


def _adherence(conn) -> list[dict]:
    """按规范项聚合依从率：完成天数 / 有记录天数。"""
    rows = conn.execute(
        "SELECT category, item_key, item, "
        "       COUNT(*) AS recorded, SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) AS done "
        "FROM personal_tracks GROUP BY category, item_key "
        "ORDER BY category, item_key"
    ).fetchall()
    out = []
    for r in rows:
        recorded = r["recorded"] or 0
        done = r["done"] or 0
        out.append({
            "category": r["category"],
            "item_key": r["item_key"],
            "item": r["item"],
            "recorded": recorded,
            "done": done,
            "adherence": round(done / recorded, 4) if recorded else None,
        })
    return out


def _write_csv(path: str, rows: list[dict], columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def export(db_path: str | None = None, fmt: str = "csv",
           out_dir: str | None = None, *, to_stdout: bool = False) -> list[str]:
    """执行导出，返回写出的文件路径列表（stdout 模式返回空列表）。"""
    conn = init_db(db_path)
    try:
        daily = _daily_rows(conn)
        tracks = _track_rows(conn)
        adherence = _adherence(conn)
    finally:
        conn.close()

    if to_stdout:
        payload = {"daily_reviews": daily, "personal_tracks": tracks,
                   "adherence": adherence}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return []

    out_dir = out_dir or DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []

    if fmt == "json":
        path = os.path.join(out_dir, "dailylumen.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"daily_reviews": daily, "personal_tracks": tracks,
                 "adherence": adherence},
                f, ensure_ascii=False, indent=2,
            )
        written.append(path)
        return written

    if fmt != "csv":
        raise ValueError(f"不支持的格式: {fmt!r}（可选 csv / json）")

    for name, rows, cols in (
        ("daily_reviews.csv", daily, COLUMNS),
        ("personal_tracks.csv", tracks,
         ["date", "track_key", "category", "item_key", "item", "done", "note"]),
        ("adherence.csv", adherence,
         ["category", "item_key", "item", "recorded", "done", "adherence"]),
    ):
        path = os.path.join(out_dir, name)
        _write_csv(path, rows, cols)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    fmt = "csv"
    if "--format" in argv:
        i = argv.index("--format")
        fmt = argv[i + 1] if i + 1 < len(argv) else "csv"
    out_dir = None
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = argv[i + 1] if i + 1 < len(argv) else None
    to_stdout = "--stdout" in argv

    try:
        written = export(fmt=fmt, out_dir=out_dir, to_stdout=to_stdout)
    except ValueError as e:
        print(e)
        return 2
    for p in written:
        print(f"  [导出] {p}")
    if written:
        print(f"\n完成: 共 {len(written)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
