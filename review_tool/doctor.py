"""体检子命令：一次性回答「数据还准不准、全不全、新不新」。

    python -m review_tool doctor

检查项
------
1. 数据库：schema 版本 / 行数 / 完整性
2. 新鲜度：最新复盘距今多少天，是否该补录
3. 对账：md 文件与数据库的日期集合双向差集（谁多谁少）
4. 归档来源：哪些记录只存在于「历史源复盘」，建议跑 import-history 升级
5. 完整度：核心字段缺失统计
6. 打卡归一化：是否还有未收敛到规范项的 other:* 记录
7. 训练日口径：training_day 与「按星期推算」不一致的天数
"""
from __future__ import annotations

import os
import re
from datetime import date as _date
from datetime import datetime

from .analyze import completeness
from .config import ARCHIVE_SRC_DIR, INPUT_DIR, PROFILE
from .db import SCHEMA_VERSION, init_db

_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")

# 归档目录名（相对 input_dir），与 config.ARCHIVE_SRC_DIR 保持一致
ARCHIVE_SRC_NAME = os.path.basename(ARCHIVE_SRC_DIR)


def _dates_from_dir(directory: str) -> set[str]:
    """从目录下文件名里提取日期集合。"""
    out: set[str] = set()
    if not os.path.isdir(directory):
        return out
    for name in os.listdir(directory):
        if name.endswith(".md"):
            m = _DATE_IN_NAME.search(name)
            if m:
                out.add(m.group(1))
    return out


def _expected_training_day(date_str: str) -> int:
    wd = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    return 1 if wd in PROFILE["training_weekdays"] else 0


def diagnose(db_path: str | None = None, input_dir: str | None = None,
             *, today: str | None = None) -> dict:
    """执行体检并返回结构化结果（不打印），便于测试与复用。"""
    input_dir = input_dir or INPUT_DIR
    today = today or _date.today().isoformat()
    conn = init_db(db_path)

    result: dict = {}
    try:
        result["schema_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
        result["schema_expected"] = SCHEMA_VERSION
        result["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        result["rows"] = conn.execute("SELECT COUNT(*) FROM daily_reviews").fetchone()[0]
        result["tracks"] = conn.execute("SELECT COUNT(*) FROM personal_tracks").fetchone()[0]

        latest = conn.execute("SELECT MAX(date) FROM daily_reviews").fetchone()[0]
        result["latest_date"] = latest
        result["stale_days"] = (
            (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(latest, "%Y-%m-%d")).days
            if latest else None
        )

        # 对账
        db_dates = {r[0] for r in conn.execute("SELECT date FROM daily_reviews")}
        std_dates: set[str] = set()
        for root, _dirs, files in os.walk(input_dir):
            rel = os.path.relpath(root, input_dir)
            if any(p in ("收件箱", "历史源复盘") for p in rel.split(os.sep)):
                continue
            for f in files:
                if f.endswith(".md"):
                    m = _DATE_IN_NAME.search(f)
                    if m:
                        std_dates.add(m.group(1))
        arch_dates = _dates_from_dir(os.path.join(input_dir, ARCHIVE_SRC_NAME))

        result["orphan_in_db"] = sorted(db_dates - std_dates - arch_dates)
        result["not_ingested"] = sorted(std_dates - db_dates)
        result["archive_only"] = sorted(db_dates - std_dates)

        # 完整度
        rate, missing = completeness(conn, "1=1", ())
        result["completeness"] = round(rate, 4)
        result["missing_fields"] = missing

        # 打卡归一化
        uncollapsed = conn.execute(
            "SELECT item_key, COUNT(*) FROM personal_tracks "
            "WHERE item_key LIKE 'other:%' GROUP BY item_key ORDER BY 2 DESC"
        ).fetchall()
        result["unnormalized_tracks"] = [(r[0], r[1]) for r in uncollapsed]

        # 训练日口径
        drift = []
        for row in conn.execute("SELECT date, training_day FROM daily_reviews"):
            d, td = row[0], row[1]
            if td is None:
                drift.append((d, "缺失"))
            elif td != _expected_training_day(d):
                drift.append((d, f"{td}→应为{_expected_training_day(d)}"))
        result["training_day_drift"] = drift

        # 收件箱
        inbox = os.path.join(input_dir, "收件箱")
        result["inbox_files"] = (
            len([f for f in os.listdir(inbox) if not f.startswith(".")])
            if os.path.isdir(inbox) else 0
        )
    finally:
        conn.close()
    return result


def render(result: dict) -> str:
    """把体检结果渲染成可读文本。"""
    L: list[str] = []
    ok = True

    L.append("=" * 52)
    L.append("DailyLumen 体检报告")
    L.append("=" * 52)

    L.append("")
    L.append("[数据库]")
    v_ok = result["schema_version"] == result["schema_expected"]
    ok &= v_ok
    if v_ok:
        L.append(f"  schema 版本 : {result['schema_version']} ✓")
    else:
        L.append(f"  schema 版本 : {result['schema_version']}"
                 f" ⚠️ 期望 {result['schema_expected']}")
    L.append(f"  完整性检查  : {result['integrity']}")
    L.append(f"  复盘记录    : {result['rows']} 条")
    L.append(f"  打卡记录    : {result['tracks']} 条")
    if result["integrity"] != "ok":
        ok = False

    L.append("")
    L.append("[新鲜度]")
    stale = result["stale_days"]
    if stale is None:
        L.append("  ⚠️ 库中没有任何记录")
        ok = False
    else:
        flag = "✓" if stale <= 1 else f"⚠️ 已有 {stale} 天未补录"
        L.append(f"  最新复盘    : {result['latest_date']}（距今 {stale} 天）{flag}")
        if stale > 1:
            ok = False

    L.append("")
    L.append("[文件 ↔ 数据库对账]")
    if result["not_ingested"]:
        ok = False
        L.append(f"  ⚠️ 有 md 但未入库 ({len(result['not_ingested'])} 天): "
                 + ", ".join(result["not_ingested"][:8]))
        L.append("     → 运行 python -m review_tool ingest")
    if result["orphan_in_db"]:
        ok = False
        L.append(f"  ⚠️ 库中有记录但找不到源文件 ({len(result['orphan_in_db'])} 天): "
                 + ", ".join(result["orphan_in_db"][:8]))
    if not result["not_ingested"] and not result["orphan_in_db"]:
        L.append("  ✓ md 与数据库日期集合完全一致")

    if result["archive_only"]:
        L.append("")
        L.append("[旧格式归档]")
        L.append(f"  {len(result['archive_only'])} 天的数据源只在「历史源复盘」（语雀原始格式）: "
                 + ", ".join(result["archive_only"][:8]))
        L.append("     → 建议升级为标准格式：")
        L.append("       python -m review_tool import-history --src 每日复盘/历史源复盘")

    L.append("")
    L.append("[数据完整度]")
    pct = result["completeness"] * 100
    L.append(f"  核心字段完整度: {pct:.1f}%")
    if result["missing_fields"]:
        L.append("  缺失 TOP（字段×天数）:")
        for col, n in result["missing_fields"][:8]:
            L.append(f"    - {col:16s} {n} 天")
    else:
        L.append("  ✓ 无缺失")

    L.append("")
    L.append("[打卡归一化]")
    if result["unnormalized_tracks"]:
        L.append(f"  ⚠️ 有 {len(result['unnormalized_tracks'])} 类未收敛到规范项:")
        for key, n in result["unnormalized_tracks"][:8]:
            L.append(f"    - {key} × {n}")
        L.append("     → 在 config.PERSONAL_ITEMS 中补 alias 后重跑 ingest")
    else:
        L.append("  ✓ 全部打卡已归一化到规范项")

    L.append("")
    L.append("[训练日口径]")
    if result["training_day_drift"]:
        L.append(f"  提示: {len(result['training_day_drift'])} 天与「按星期推算」不一致"
                 f"（可能是临时调整，非故障）:")
        for d, why in result["training_day_drift"][:8]:
            L.append(f"    - {d}: {why}")
    else:
        L.append("  ✓ training_day 与星期推算一致")

    if result["inbox_files"]:
        L.append("")
        L.append(f"[收件箱] {result['inbox_files']} 个待处理素材")

    L.append("")
    L.append("-" * 52)
    L.append("结论: " + ("✓ 数据健康" if ok else "⚠️ 存在待处理项，见上方标记"))
    return "\n".join(L)


def is_healthy(result: dict) -> bool:
    """是否为「健康」状态（用于退出码 / CI）。

    注意 training_day 与星期约定不符**不算故障**——那可能只是临时调整训练日，
    属于合理的个人差异，只在报告里提示。
    """
    return (
        result["integrity"] == "ok"
        and result["schema_version"] == result["schema_expected"]
        and not result["not_ingested"]
        and not result["orphan_in_db"]
    )


def main(argv: list[str] | None = None) -> int:
    result = diagnose()
    print(render(result))
    return 0 if is_healthy(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
