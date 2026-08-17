"""入库: 扫描每日复盘目录 -> 解析 -> 写入 SQLite。

用法:
    python ingest.py            # 扫描 INPUT_DIR 下所有 .md
    python ingest.py 路径.md    # 只入库指定文件
"""
import os
import sys
from db import init_db, get_conn, upsert, count
from parse import parse_file
from score import compute_scores
from config import INPUT_DIR, system_score_from


def ingest_path(conn, path):
    row = parse_file(path)
    if not row.get("date"):
        print(f"  [跳过] {os.path.basename(path)}: 未解析到日期")
        return False
    # 自动补全缺失的四维评分 (健康分基于客观指标, 工作分基于深度工作_h)
    compute_scores(row)
    # 重算系统分 (四维补齐后)
    row["system_score"] = system_score_from(row)
    upsert(conn, row)
    conn.commit()
    return True


def main():
    conn = init_db()
    before = count(conn)

    if len(sys.argv) > 1:
        paths = [sys.argv[1]]
    else:
        paths = [
            os.path.join(INPUT_DIR, f)
            for f in sorted(os.listdir(INPUT_DIR))
            if f.endswith(".md")
        ]

    ok = 0
    for p in paths:
        if os.path.exists(p):
            if ingest_path(conn, p):
                ok += 1
                print(f"  [入库] {os.path.basename(p)}")
        else:
            print(f"  [缺失] {p}")

    after = count(conn)
    print(f"\n完成: 本次入库 {ok} 条, 数据库共 {after} 条 (新增/更新 {after - before})")
    conn.close()


if __name__ == "__main__":
    main()
