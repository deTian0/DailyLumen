"""将桌面语雀历史复盘文件归一化为 DailyLumen 格式，写入 每日复盘/。

处理对象：真实每日文件（跳过 'DD' 占位模板）。
解析策略：
  - 优先解析 `---` 前置 YAML 块（11 个文件）
  - bedtime 从正文「入睡时间」表格行提取（前置块不含该字段）
  - training_day / weekday 由日期推算（周一~三、五、六 = 训练日，与模板约定一致）
  - 7/21 为纯正文（无前置块），走专用解析（健康表 + 四维评分表 + 打卡勾选）
生成：标准 DailyLumen .md（含 ```data 数据块 + 原文），随后由 ingest 入库。
  （注：服药/护肤等个人定制项不再写入通用数据块，改由 ingest 从日常打卡
   勾选写入 personal_tracks 表，不计入通用评分）

用法：
    python -m review_tool import-history            # 转换并写入 每日复盘/
    python -m review_tool import-history --check    # 仅打印解析结果，不写文件
    python -m review_tool import-history --src DIR  # 指定来源目录
"""
from __future__ import annotations

import os
import re
import sys
import datetime

from .config import BASE_DIR, HISTORY_SRC_DIR
from .parse import _to_bool, _to_bedtime_min

OUT_DIR = os.path.join(BASE_DIR, "每日复盘")

TRAIN_WD = {0, 1, 2, 4, 5}  # Mon, Tue, Wed, Fri, Sat
CN_WD = ["一", "二", "三", "四", "五", "六", "日"]


# ---------- 小工具 ----------

def _to_float(v) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def _to_int(v) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def _table_val(text: str, name: str) -> str | None:
    m = re.search(r"\|\s*%s\s*[|｜]\s*([^|\n]+)" % re.escape(name), text)
    return m.group(1).strip() if m else None


def _scores_from_table(text: str) -> dict:
    """从 `| 健康（...） | **5** |` 这类表格行提取四维手填分。"""
    out: dict = {}
    for dim, key in [
        ("health", "health_score"),
        ("work", "work_score"),
        ("learn", "learn_score"),
        ("life", "life_score"),
    ]:
        m = re.search(r"\|\s*%s[（(][^|]+?[）)]\s*[|｜]\s*\**\s*(\d+)" % dim, text)
        if m:
            out[key] = int(m.group(1))
    return out


# ---------- 解析 ----------

def parse_frontmatter(text: str) -> dict:
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    d: dict = {}
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        mm = re.match(r"^([\w一-鿿_]+)\s*[:：]\s*(.*)$", line)
        if mm:
            d[mm.group(1).strip()] = mm.group(2).strip()
    return d


def date_meta(date_str: str) -> tuple[str, int]:
    y, mo, d = map(int, date_str.split("-"))
    wd = datetime.date(y, mo, d).weekday()
    return "星期" + CN_WD[wd], (1 if wd in TRAIN_WD else 0)


def parse_prose_721(text: str) -> dict:
    """7/21 纯正文解析（无前置块）。"""
    row: dict = {}
    row["sleep_h"] = _to_float(_table_val(text, "睡眠时长"))
    q = _table_val(text, "睡眠质量")
    row["sleep_quality"] = (
        None if (q and ("未显示" in q or "___" in q)) else _to_int(q)
    )
    row["exercise_min"] = _to_float(_table_val(text, "运动时长"))
    row["diet_kcal"] = _to_int(_table_val(text, "饮食热量"))
    mc = _table_val(text, "三餐")
    row["meals_count"] = mc.count("✓") if mc else None
    row["phone_h"] = _to_float(_table_val(text, "手机屏幕"))
    cm = _table_val(text, "通勤")
    if cm:
        row["commute_done"] = 0 if "✗" in cm else 1
    m = re.search(r"深度工作[：:]\s*\**\s*([\d.]+)\s*h", text)
    if m:
        row["deepwork_h"] = float(m.group(1))
    row["breakfast_on_time"] = 1 if re.search(r"- \[x\] 早餐", text) else 0
    row.update(_scores_from_table(text))
    return row


# 前置块字段 -> 数据库列 + 目标类型
FM_MAP = {
    "sleep_h": ("sleep_h", "float"),
    "sleep_quality": ("sleep_quality", "int"),
    "exercise_min": ("exercise_min", "float"),
    "commute_done": ("commute_done", "bool"),
    "diet_kcal": ("diet_kcal", "int"),
    "meals_count": ("meals_count", "int"),
    "breakfast_on_time": ("breakfast_on_time", "bool"),
    "phone_h": ("phone_h", "float"),
    "deepwork_h": ("deepwork_h", "float"),
    "health_score": ("health_score", "int"),
    "work_score": ("work_score", "int"),
    "learn_score": ("learn_score", "int"),
    "life_score": ("life_score", "int"),
}


def build_row(path: str) -> tuple[dict | None, str]:
    """解析单文件 -> (row, 原文)。无法解析日期返回 (None, 原文)。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm = parse_frontmatter(text)
    date_str = fm.get("date")
    if not date_str:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        if not m:
            return None, text
        date_str = m.group(1)

    row: dict = {}
    for k, (col, kind) in FM_MAP.items():
        if k in fm and fm[k] != "":
            v = fm[k]
            if kind == "float":
                v = _to_float(v)
            elif kind == "int":
                v = _to_int(v)
            elif kind == "bool":
                v = _to_bool(v)
            row[col] = v

    if not fm:  # 纯正文（7/21）
        row.update(parse_prose_721(text))

    bt = _to_bedtime_min(_table_val(text, "入睡时间"))
    if bt is not None:
        row["bedtime"] = bt

    weekday, training_day = date_meta(date_str)
    row["date"] = date_str
    row["weekday"] = weekday
    row["training_day"] = training_day
    return row, text


# ---------- 渲染 ----------

def _fmt(v) -> str:
    return "" if v is None else str(v)


def _fmt_bool(v) -> str:
    if v is None:
        return ""
    return "yes" if v == 1 else "no"


def _fmt_min(minutes) -> str:
    if minutes is None:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _vals(row: dict) -> str:
    return "/".join(
        str(row.get(k)) if row.get(k) is not None else "-"
        for k in ("health_score", "work_score", "learn_score", "life_score")
    )


def render(row: dict, original_text: str) -> str:
    lines = [
        f"# 每日复盘 · {row['date']}（{row.get('weekday', '')}）",
        "",
        "> 本文件由历史语雀复盘转换导入（DailyLumen）。原始叙述见文末。",
        "",
        "## 附录 · 系统数据",
        "",
        "```data",
        f"日期: {row['date']}",
        f"星期: {row.get('weekday', '')}",
        f"训练日: {'yes' if row.get('training_day') == 1 else 'no'}",
        f"睡眠时长_h: {_fmt(row.get('sleep_h'))}",
        f"睡眠质量: {_fmt(row.get('sleep_quality'))}",
    ]
    bt = row.get("bedtime")
    lines.append(f"入睡时间: {_fmt_min(bt)}" if bt is not None else "入睡时间:")
    lines += [
        f"运动时长_min: {_fmt(row.get('exercise_min'))}",
        f"通勤完成: {_fmt_bool(row.get('commute_done'))}",
        f"饮食热量_kcal: {_fmt(row.get('diet_kcal'))}",
        f"三餐情况: {_fmt(row.get('meals_count'))}",
        f"早餐按时: {_fmt_bool(row.get('breakfast_on_time'))}",
        f"手机屏幕_h: {_fmt(row.get('phone_h'))}",
        f"深度工作_h: {_fmt(row.get('deepwork_h'))}",
        f"健康分: {_fmt(row.get('health_score'))}",
        f"工作分: {_fmt(row.get('work_score'))}",
        f"学习分: {_fmt(row.get('learn_score'))}",
        f"生活分: {_fmt(row.get('life_score'))}",
        "```",
        "",
        "## 原始复盘（语雀导入）",
        "",
        original_text.rstrip(),
        "",
    ]
    return "\n".join(lines)


# ---------- 入口 ----------

def run(source_dir: str | None = None, check_only: bool = False) -> int:
    source_dir = source_dir or HISTORY_SRC_DIR
    files = sorted(
        f for f in os.listdir(source_dir) if f.endswith(".md") and "DD" not in f
    )
    print(f"源目录: {source_dir}")
    print(f"待处理文件: {len(files)} 个\n")
    ok = 0
    for fn in files:
        src = os.path.join(source_dir, fn)
        row, text = build_row(src)
        if not row:
            print(f"  [跳过] {fn}: 无法解析日期")
            continue
        auto = [k for k in ("health_score", "work_score", "learn_score", "life_score") if row.get(k) is None]
        tag = "自动生成" if auto else "手填保留"
        print(
            f"  [OK] {row['date']} {row.get('weekday', '')} "
            f"训练={'Y' if row.get('training_day') == 1 else 'N'} "
            f"bed={_fmt_min(row.get('bedtime'))} "
            f"睡{_fmt(row.get('sleep_h'))} 质{_fmt(row.get('sleep_quality'))} "
            f"运{_fmt(row.get('exercise_min'))} 食{_fmt(row.get('diet_kcal'))} "
            f"屏{_fmt(row.get('phone_h'))} 深{_fmt(row.get('deepwork_h'))} "
            f"餐{_fmt(row.get('meals_count'))} "
            f"四维={_vals(row)} ({tag})"
        )
        if not check_only:
            out_path = os.path.join(OUT_DIR, f"{row['date']}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render(row, text))
            ok += 1
    if check_only:
        print("\n--check 完成，未写入文件。")
    else:
        print(f"\n完成：已写入 {ok} 个标准文件到 {OUT_DIR}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in argv
    src = None
    if "--src" in argv:
        i = argv.index("--src")
        src = argv[i + 1] if i + 1 < len(argv) else None
    return run(source_dir=src, check_only=check_only)


if __name__ == "__main__":
    raise SystemExit(main())
