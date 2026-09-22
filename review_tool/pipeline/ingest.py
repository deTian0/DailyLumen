"""入库：扫描每日复盘目录 -> 解析 -> 补全四维评分 -> 写入 SQLite。

用法:
    python -m review_tool ingest                # 入库「每日复盘/」全部 .md
    python -m review_tool ingest 路径.md        # 只入库指定文件
    python -m review_tool ingest --overwrite    # 整行覆盖（默认只补空、不擦已有值）
    python -m review_tool ingest --prune-tracks # 顺带清理源 md 已无的陈旧打卡行

扫描范围：``每日复盘/`` 递归，但**跳过** 收件箱（原始素材）与
历史源复盘（语雀旧格式归档，需先经 import-history 转成标准格式）。

运动时长：字段为空时，会由「二、今日三件事」的描述折算补全（见 bodyweight 模块），
并在输出里标注「由描述折算」，来源记入 ``exercise_src`` 列。

**训练日未记录按 0 计**（v1.3.2 口径，用户拍板）：折算也没有命中时，
训练日的 ``exercise_min`` 记 0、来源记 ``zero`` —— 「没填」即「没练」，
计入达成分母的「未达标」，不再保留「未记录」豁免态。非训练日不填。

**打卡对账**（v1.4.2）：``upsert_personal_track`` 只增不删，源文本的规范 ID 变化
（如 Move Free 由裸 ``movefree`` 变成 ``movefree@noon`` + ``movefree@evening``）
会让旧键永久留在库里、同一剂量被重复计入依从率。``--prune-tracks`` 按
「一、日常打卡」的解析结果做权威集合删除（章节缺失则跳过，见 parse.has_tracks_section）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from ..config import ARCHIVE_SRC_DIR, INBOX_DIR, INPUT_DIR, PROFILE
from ..core.score import compute_scores, system_score_from
from ..storage.db import (
    count,
    init_db,
    prune_personal_tracks,
    upsert,
    upsert_personal_track,
)
from .parse import parse_file

# 扫描时跳过的子目录（原始素材 / 旧格式归档，都不属于标准复盘）
SKIP_DIRS = (os.path.basename(INBOX_DIR), os.path.basename(ARCHIVE_SRC_DIR))


def fill_training_day(row: dict) -> bool:
    """training_day 为空时按 config.PROFILE['training_weekdays'] 兜底。

    避免「缺失」的天数静默从 `WHERE training_day=1` 过滤中消失。
    返回是否发生了兜底填充。
    """
    if row.get("training_day") is not None or not row.get("date"):
        return False
    try:
        wd = datetime.strptime(row["date"], "%Y-%m-%d").weekday()
    except ValueError:
        return False
    row["training_day"] = 1 if wd in PROFILE["training_weekdays"] else 0
    return True


def fill_exercise_zero(row: dict) -> bool:
    """训练日运动未记录时按口径记 0（v1.3.2，用户拍板）。

    「没填」即「没练」：exercise_min 记 0、来源记 'zero'，计入达成分母的
    未达标，不再保留「未记录」态 —— 否则训练日达标率分母永远存疑。
    折算（bodyweight.estimate）优先于本兜底；非训练日不动（运动不是当天预期）。
    返回是否发生了兜底填充。
    """
    if row.get("training_day") != 1 or row.get("exercise_min") is not None:
        return False
    row["exercise_min"] = 0
    row["exercise_src"] = "zero"
    return True


def ingest_path(conn, path: str, *, overwrite: bool = False,
                prune_tracks: bool = False) -> dict | None:
    """解析单个 md 文件并 upsert 入库。

    成功返回解析出的行 dict（含 ``exercise_src`` 等派生字段），失败返回 None。
    返回值可直接当布尔用（truthy 即成功）。

    ``prune_tracks``：写入打卡后，把该日期下**源 md 已无对应文本**的打卡行删掉
    （见 ``db.prune_personal_tracks``）。仅当「一、日常打卡」章节确实解析到了才
    执行 —— 否则解析失败会被误判成「当天没有这些项」。默认关闭。
    """
    row = parse_file(path)
    if not row.get("date"):
        print(f"  [跳过] {os.path.basename(path)}: 未解析到日期")
        return None
    # 训练日兜底（缺失才填，不覆盖手填）
    fill_training_day(row)
    # 训练日运动未记录按 0 计（折算优先，见 fill_exercise_zero）
    fill_exercise_zero(row)
    # 自动补全缺失的四维评分（只补 None，不覆盖手填）
    compute_scores(row)
    # 重算系统分（四维补齐后）
    row["system_score"] = system_score_from(row)
    upsert(conn, row, overwrite=overwrite)
    # 写入个人定制打卡（补剂/护肤等），独立于通用评分表，不计入四维评分
    tracks = row.get("_personal_tracks", [])
    for category, track_key, item_key, item_label, done in tracks:
        upsert_personal_track(
            conn, row["date"], track_key, category, item_key, item_label, done
        )
    if prune_tracks and row.get("_tracks_section"):
        stale = prune_personal_tracks(conn, row["date"], {t[1] for t in tracks})
        if stale:
            row["_pruned_tracks"] = stale
            print(f"  [打卡对账] {row['date']} 删除 {len(stale)} 条源 md 已无的陈旧打卡: "
                  + ", ".join(stale))
    conn.commit()
    return row


def _report_row(label: str, row: dict) -> None:
    """打印一条入库结果；运动时长若来自描述折算则显式标注。"""
    if row.get("exercise_src") == "derived":
        print(f"  [入库] {label}  ↳ 运动 {row['exercise_min']}min 由描述折算")
    else:
        print(f"  [入库] {label}")


def iter_markdown(input_dir: str) -> list[str]:
    """递归收集 input_dir 下所有 .md（含子目录，如 复盘/YYYY-MM/）。

    跳过收件箱与历史源复盘目录。
    """
    result: list[str] = []
    for root, _dirs, files in os.walk(input_dir):
        rel = os.path.relpath(root, input_dir)
        parts = rel.split(os.sep)
        if any(part in SKIP_DIRS for part in parts):
            continue
        for f in sorted(files):
            if f.endswith(".md"):
                result.append(os.path.join(root, f))
    return sorted(result)


def ingest_all(conn, input_dir: str = INPUT_DIR, *, overwrite: bool = False,
               prune_tracks: bool = False) -> int:
    """递归扫描 input_dir 下所有 .md 入库，返回成功条数。"""
    paths = iter_markdown(input_dir)
    ok = 0
    derived = 0
    for p in paths:
        if not os.path.exists(p):
            continue
        row = ingest_path(conn, p, overwrite=overwrite, prune_tracks=prune_tracks)
        if row is None:
            continue
        ok += 1
        if row.get("exercise_src") == "derived":
            derived += 1
        _report_row(os.path.relpath(p, input_dir), row)
    if derived:
        print(f"  其中 {derived} 天的运动时长由「三件事」描述折算（见 config.BODYWEIGHT_MOVES）")
    return ok


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    overwrite = "--overwrite" in argv or "--force" in argv
    prune_tracks = "--prune-tracks" in argv
    args = [a for a in argv if not a.startswith("--")]

    conn = init_db()
    before = count(conn)
    before_tracks = conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]

    if args:
        ok = 0
        for p in [args[0]]:
            if not os.path.exists(p):
                print(f"  [缺失] {p}")
                continue
            row = ingest_path(conn, p, overwrite=overwrite, prune_tracks=prune_tracks)
            if row is not None:
                ok += 1
                _report_row(os.path.basename(p), row)
    else:
        ok = ingest_all(conn, INPUT_DIR, overwrite=overwrite, prune_tracks=prune_tracks)

    after = count(conn)
    mode = "（整行覆盖模式）" if overwrite else "（保护模式：只补空值）"
    print(f"\n完成: 本次入库 {ok} 条, 数据库共 {after} 条 (新增/更新 {after - before})"
          f" {mode}")
    tracks = conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]
    line = f"个人打卡记录: {tracks} 条"
    if prune_tracks and tracks != before_tracks:
        line += f"（打卡对账删除 {before_tracks - tracks} 条陈旧项）"
    print(line)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
