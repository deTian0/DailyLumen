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
8. 运动时长来源：填报 / 描述折算 / 训练日未记录按 0 计 / 未记录 四者的天数分布
9. 分数一致性：库中四维/系统分与「按字段重算」的结果是否相符
10. 打卡对账：库里每条打卡能否在源 md 找到对应勾选（陈旧/重复条目）
11. 熔断检测：单维度连续低分 + 相对基线漂移
"""
from __future__ import annotations

import os
import re
from datetime import date as _date
from datetime import datetime

from ..config import ARCHIVE_SRC_DIR, FUSE_RULES, INPUT_DIR, PROFILE
from ..core.score import (
    compute_health_score,
    compute_learn_score,
    compute_life_score,
    compute_work_score,
    system_score_from,
)
from ..storage.db import SCHEMA_VERSION, init_db
from .analyze import completeness
from .fuse import find_fuses

# 只认可「文件名主干 = 纯日期」的日复盘。历史上用 ``search`` 抓文件名里第一段日期，
# 会把 ``周总结-W36-2026-08-31_09-06.md`` 误当成 08-31 的日复盘 —— 于是当 08-31
# 的日文档真的缺失时，对账反而报「一致」（假阴性）。改为逐文件校验主干是否恰为
# 一个日期，周/月汇总自然被排除。
_DATE_STEM = re.compile(r"^(\d{4}-\d{2}-\d{2})$")

# 归档目录名（相对 input_dir），与 config.ARCHIVE_SRC_DIR 保持一致
ARCHIVE_SRC_NAME = os.path.basename(ARCHIVE_SRC_DIR)


def _date_from_filename(name: str) -> str | None:
    """文件名主干恰为 ``YYYY-MM-DD`` 才返回该日期，否则 None（排除周/月汇总等）。"""
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _DATE_STEM.match(stem)
    return m.group(1) if m else None


def _dates_from_dir(directory: str) -> set[str]:
    """从目录下文件名里提取日期集合（只认主干纯日期的日复盘）。"""
    out: set[str] = set()
    if not os.path.isdir(directory):
        return out
    for name in os.listdir(directory):
        if name.endswith(".md"):
            d = _date_from_filename(name)
            if d:
                out.add(d)
    return out


# ---------------------------------------------------------------------------
# 分数一致性：把「库里的四维分」与「按当前规则从字段重算的结果」逐行比对
# ---------------------------------------------------------------------------

# 维度列 -> 展示名 -> 重算函数
_DIM_COMPUTERS = [
    ("health_score", "健康", compute_health_score),
    ("work_score", "工作", compute_work_score),
    ("learn_score", "学习", compute_learn_score),
    ("life_score", "生活", compute_life_score),
]


def stale_track_rows(conn) -> list[dict]:
    """库中打卡行在源 md 里找不到对应文本（陈旧 / 重复条目）。

    md 是打卡的唯一来源，但 upsert 只增不删 —— 源文本的规范 ID 一变，旧键就永久
    留在库里（例如 Move Free 由裸 ``movefree`` 变成 ``movefree@noon`` +
    ``movefree@evening``），同一剂量被重复计入依从率。这里只**报告**，
    清理走 `python -m review_tool ingest --prune-tracks`。
    """
    from ..pipeline.parse import parse_file
    out: list[dict] = []
    for row in conn.execute(
        "SELECT date, raw_path FROM daily_reviews ORDER BY date"
    ):
        date, path = row["date"], row["raw_path"]
        if not path or not os.path.exists(path):
            continue
        parsed = parse_file(path)
        if not parsed.get("_tracks_section"):
            continue          # 章节缺失 → 解析结果不能当权威集合，跳过
        keep = {t[1] for t in parsed.get("_personal_tracks", [])}
        for r in conn.execute(
            "SELECT track_key, item FROM personal_tracks WHERE date=? ORDER BY track_key",
            (date,),
        ):
            if r["track_key"] not in keep:
                out.append({"date": date, "track_key": r["track_key"],
                            "item": r["item"]})
    return out


def _num_differs(a, b, tol: float) -> bool:
    """两个数值不同（一方 None 另一方非 None 也算不同）。"""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(float(a) - float(b)) > tol


def score_drift(conn, *, tol: float = 1e-9) -> list[dict]:
    """重算四维 + 系统分并与库中存值比对，返回不一致明细。

    为什么需要：v1.4.0 起「库为准、文档由库渲染」，但 ingest 仍会读回 md 数据块里
    写的分数（保留字段供人阅读）。若有人手改了 md 里的分数、或某个维度规则变了却
    没重算历史，库里的值就会与「按字段重算」的结果不符 —— 这正是需要被看见的
    静默漂移。此处只做**只读**检测，不改库。
    """
    out: list[dict] = []
    for row in conn.execute("SELECT * FROM daily_reviews ORDER BY date"):
        rec = dict(row)
        recomp = {col: fn(rec) for col, _label, fn in _DIM_COMPUTERS}
        recomp["system_score"] = system_score_from(recomp)
        for col, label, _fn in _DIM_COMPUTERS + [("system_score", "系统", None)]:
            stored, new = rec.get(col), recomp.get(col)
            if _num_differs(stored, new, tol):
                out.append({
                    "date": rec["date"], "dim": label, "col": col,
                    "stored": stored, "recomputed": new,
                })
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
                    d = _date_from_filename(f)
                    if d:
                        std_dates.add(d)
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

        # 运动时长来源（填报 / 描述折算 / 训练日未记录按 0 计 / 未记录）
        rec, der, zer, miss = conn.execute(
            "SELECT "
            "  SUM(CASE WHEN exercise_min IS NOT NULL "
            "           AND COALESCE(exercise_src, 'record') NOT IN ('derived', 'zero') THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN exercise_src='derived' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN exercise_src='zero' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN exercise_min IS NULL THEN 1 ELSE 0 END) "
            "FROM daily_reviews"
        ).fetchone()
        result["exercise_sources"] = {
            "recorded": rec or 0, "derived": der or 0,
            "zero": zer or 0, "missing": miss or 0,
        }

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
        # 只统计「待处理素材」：忽略隐藏文件、说明文档（README）与 _ 前缀辅助文件
        result["inbox_files"] = (
            len([
                f for f in os.listdir(inbox)
                if not f.startswith((".", "_")) and f != "README.md"
            ])
            if os.path.isdir(inbox) else 0
        )

        # 熔断检测（与数据健康无关，属「人生指标」告警，故不参与 is_healthy）
        result["fuse"] = find_fuses(conn)

        # 分数一致性：库值 vs 字段重算（只读检测，不参与 is_healthy —— 手填覆盖属合法）
        result["score_drift"] = score_drift(conn)

        # 打卡对账：库中打卡行在源 md 找不到对应文本（陈旧/重复条目）
        result["stale_tracks"] = stale_track_rows(conn)
    finally:
        conn.close()
    return result


def render(result: dict) -> str:
    """把体检结果渲染成可读文本。"""
    L: list[str] = []

    L.append("=" * 52)
    L.append("DailyLumen 体检报告")
    L.append("=" * 52)

    L.append("")
    L.append("[数据库]")
    v_ok = result["schema_version"] == result["schema_expected"]
    if v_ok:
        L.append(f"  schema 版本 : {result['schema_version']} ✓")
    else:
        L.append(f"  schema 版本 : {result['schema_version']}"
                 f" ⚠️ 期望 {result['schema_expected']}")
    L.append(f"  完整性检查  : {result['integrity']}")
    L.append(f"  复盘记录    : {result['rows']} 条")
    L.append(f"  打卡记录    : {result['tracks']} 条")

    L.append("")
    L.append("[新鲜度]")
    stale = result["stale_days"]
    if stale is None:
        L.append("  ⚠️ 库中没有任何记录")
    else:
        flag = "✓" if stale <= 1 else f"⚠️ 已有 {stale} 天未补录"
        L.append(f"  最新复盘    : {result['latest_date']}（距今 {stale} 天）{flag}")
        # 新鲜度是**建议性**的：CI 里历史库必然「过期」，但数据本身没问题，
        # 故不让它影响结论/退出码（与 is_healthy 保持一致）。

    L.append("")
    L.append("[文件 ↔ 数据库对账]")
    if result["not_ingested"]:
        L.append(f"  ⚠️ 有 md 但未入库 ({len(result['not_ingested'])} 天): "
                 + ", ".join(result["not_ingested"][:8]))
        L.append("     → 运行 python -m review_tool ingest")
    if result["orphan_in_db"]:
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
    L.append("[运动时长来源]")
    es = result["exercise_sources"]
    L.append(f"  填报 {es['recorded']} 天｜描述折算 {es['derived']} 天"
             f"｜训练日未记录按 0 计 {es.get('zero', 0)} 天｜未记录 {es['missing']} 天")
    if es.get("zero"):
        L.append("     · 训练日未记录按 0 计（v1.3.2 口径）：没填即没练，计入未达标")
    if es["derived"]:
        L.append("     · 折算规则见 config.BODYWEIGHT_MOVES：「三件事」里提到动作即自动计入")
        L.append("     · 想自己控制某天：在数据块填 `运动时长_min`（字段优先，不叠加）")

    L.append("")
    L.append("[训练日口径]")
    if result["training_day_drift"]:
        L.append(f"  提示: {len(result['training_day_drift'])} 天与「按星期推算」不一致"
                 f"（可能是临时调整，非故障）:")
        for d, why in result["training_day_drift"][:8]:
            L.append(f"    - {d}: {why}")
    else:
        L.append("  ✓ training_day 与星期推算一致")

    L.append("")
    L.append("[分数一致性]")
    drift = result.get("score_drift") or []
    if drift:
        L.append(f"  ⚠️ {len(drift)} 处库值与「按字段重算」不符"
                 "（手填覆盖 / 规则变更后未重算）:")
        for it in drift[:8]:
            L.append(f"    - {it['date']} {it['dim']}: "
                     f"库 {it['stored']} → 重算 {it['recomputed']}")
        if len(drift) > 8:
            L.append(f"    … 其余 {len(drift) - 8} 处省略")
        L.append("     → 以字段为准时重算后回写：")
        L.append("       python -m review_tool recompute-scores && python -m review_tool sync-docs")
    else:
        L.append("  ✓ 库中四维 / 系统分与字段重算完全一致")

    L.append("")
    L.append("[打卡对账]")
    stale = result.get("stale_tracks") or []
    if stale:
        by_key: dict[str, int] = {}
        for it in stale:
            by_key[it["track_key"]] = by_key.get(it["track_key"], 0) + 1
        detail = "、".join(f"{k}×{n}" for k, n in
                           sorted(by_key.items(), key=lambda x: -x[1])[:6])
        L.append(f"  ⚠️ {len(stale)} 条打卡在源 md 中找不到对应文本（陈旧/重复）: {detail}")
        L.append("     · 会让同一剂量被重复计入依从率")
        L.append("     → 以源 md 为准清理: python -m review_tool ingest --prune-tracks")
    else:
        L.append("  ✓ 每条打卡都能在源 md 找到对应勾选")

    if result["inbox_files"]:
        L.append("")
        L.append(f"[收件箱] {result['inbox_files']} 个待处理素材")

    fuse = result.get("fuse")
    if fuse and fuse.get("as_of"):
        L.append("")
        L.append("[熔断检测]")
        if fuse["absolute"]:
            for it in fuse["absolute"]:
                flag = "🔴" if not it["long_run"] else "⚠️"
                L.append(f"  {flag} {it['label']}：连续 {it['run']} 天 < {fuse['threshold']}"
                         f"（自 {it['since']} 起）")
            long_runs = [it["label"] for it in fuse["absolute"] if it["long_run"]]
            if long_runs:
                L.append(f"     · {'、'.join(long_runs)} 已连续超过 "
                         f"{FUSE_RULES['long_run_days']} 天，绝对阈值失去分辨力"
                         " → 看下面的相对基线")
        else:
            L.append("  ✓ 无维度触发熔断")
        moved = [d for d in fuse.get("drift", []) if d["moved"]]
        if moved:
            L.append(f"  [相对基线] 近 {FUSE_RULES['recent_days']} 日 vs 之前 "
                     f"{FUSE_RULES['baseline_days']} 日，变化明显的维度:")
            for d in moved:
                arrow = "▲" if d["delta"] > 0 else "▼"
                L.append(f"     {d['label']} {d['baseline']} → {d['recent']}  "
                         f"{arrow} {d['delta']:+.2f}")
        elif fuse.get("drift"):
            L.append("  [相对基线] 各维度均无明显漂移")
        L.append("     → 详情: python -m review_tool fuse")

    L.append("")
    L.append("-" * 52)
    # 结论与退出码共用 is_healthy —— 只有一套口径，不会出现「结论说有问题、退出码说没问题」
    L.append("结论: " + ("✓ 数据健康" if is_healthy(result)
                        else "⚠️ 存在待处理项，见上方标记"))
    return "\n".join(L)


def is_healthy(result: dict) -> bool:
    """是否为「健康」状态（用于退出码 / CI）—— 也是渲染结论的**唯一口径**。

    以下都不算故障，只在报告里提示：

    - ``training_day`` 与星期约定不符：可能只是临时调整训练日，属合理的个人差异；
    - 新鲜度（距上次复盘超过 1 天）：属「该补录了」的建议，CI 里历史库必然过期；
    - 分数一致性 / 打卡对账 / 熔断：手填覆盖合法、陈旧打卡由 `--prune-tracks` 处理、
      熔断属「人生指标」告警，都不代表数据本身坏了。

    真正算故障的是：库损坏、schema 版本不符、md 与库的日期集合对不上、库里一条记录都没有。
    """
    return (
        result["integrity"] == "ok"
        and result["schema_version"] == result["schema_expected"]
        and result["rows"] > 0
        and not result["not_ingested"]
        and not result["orphan_in_db"]
    )


def main(argv: list[str] | None = None) -> int:
    result = diagnose()
    print(render(result))
    return 0 if is_healthy(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
