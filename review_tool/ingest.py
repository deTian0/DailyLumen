"""入库：扫描每日复盘目录 -> 解析 -> 补全四维评分 -> 写入 SQLite。

用法:
    python -m review_tool ingest            # 入库「每日复盘/」全部 .md
    python -m review_tool ingest 路径.md    # 只入库指定文件
"""
from __future__ import annotations

import os
import sys

from .db import init_db, get_conn, upsert, count, upsert_personal_track
from .parse import parse_file
from .score import compute_scores
from .config import INPUT_DIR, INBOX_DIR, system_score_from


def ingest_path(conn, path: str) -> bool:
    """解析单个 md 文件并 upsert 入库。成功返回 True。"""
    row = parse_file(path)
    if not row.get("date"):
        print(f"  [跳过] {os.path.basename(path)}: 未解析到日期")
        return False
    # 自动补全缺失的四维评分（只补 None，不覆盖手填）
    compute_scores(row)
    # 重算系统分（四维补齐后）
    row["system_score"] = system_score_from(row)
    upsert(conn, row)
    # 写入个人定制打卡（服药/护肤等），独立于通用评分表，不计入四维评分
    for category, item, done in row.get("_personal_tracks", []):
        upsert_personal_track(conn, row["date"], category, item, done)
    conn.commit()
    return True


def iter_markdown(input_dir: str) -> list[str]:
    """递归收集 input_dir 下所有 .md（含子目录，如 复盘/），跳过收件箱。"""
    result: list[str] = []
    for root, dirs, files in os.walk(input_dir):
        rel = os.path.relpath(root, input_dir)
        if "收件箱" in rel.split(os.sep):
            continue
        for f in sorted(files):
            if f.endswith(".md"):
                result.append(os.path.join(root, f))
    return sorted(result)


def ingest_all(conn, input_dir: str = INPUT_DIR) -> int:
    """递归扫描 input_dir 下所有 .md 入库，返回成功条数。"""
    paths = iter_markdown(input_dir)
    ok = 0
    for p in paths:
        if os.path.exists(p) and ingest_path(conn, p):
            ok += 1
            print(f"  [入库] {os.path.relpath(p, input_dir)}")
    return ok


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    conn = init_db()
    before = count(conn)

    if argv:
        paths = [argv[0]]
        ok = 0
        for p in paths:
            if os.path.exists(p):
                if ingest_path(conn, p):
                    ok += 1
                    print(f"  [入库] {os.path.basename(p)}")
            else:
                print(f"  [缺失] {p}")
    else:
        ok = ingest_all(conn, INPUT_DIR)

    after = count(conn)
    print(f"\n完成: 本次入库 {ok} 条, 数据库共 {after} 条 (新增/更新 {after - before})")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
