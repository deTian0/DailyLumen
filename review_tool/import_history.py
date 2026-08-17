"""将桌面语雀历史复盘文件归一化为 DailyLumen 格式，写入 每日复盘/。

处理对象：真实每日文件（跳过 'DD' 占位模板）。
解析策略：
  - 优先解析 `---` 前置 YAML 块（11 个文件）
  - bedtime 从正文「入睡时间」表格行提取（前置块不含该字段）
  - training_day / weekday 由日期推算（周一~三、五、六 = 训练日，与模板约定一致）
  - 7/21 为纯正文（无前置块），走专用解析（健康表 + 四维评分表 + 打卡勾选）
生成：标准 DailyLumen .md（含 ```data 数据块 + 原文），随后由 ingest.py 入库。

用法：
    python import_history.py            # 转换并写入 每日复盘/
    python import_history.py --check    # 仅打印解析结果，不写文件
"""
import os
import re
import sys
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SRC_DIR = r"C:\Users\63516\Desktop\新建文件夹"
OUT_DIR = os.path.join(ROOT, "每日复盘")

TRAIN_WD = {0, 1, 2, 4, 5}  # Mon, Tue, Wed, Fri, Sat
CN_WD = ["一", "二", "三", "四", "五", "六", "日"]


def load_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_frontmatter(text):
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    d = {}
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        mm = re.match(r"^([\w\u4e00-\u9fff_]+)\s*[:：]\s*(.*)$", line)
        if mm:
            d[mm.group(1).strip()] = mm.group(2).strip()
    return d


def extract_bedtime(text):
    m = re.search(r"入睡时间\**\s*[|｜]\s*\**\s*(\d{1,2})\s*[:：]\s*(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def date_meta(date_str):
    y, mo, d = map(int, date_str.split("-"))
    wd = datetime.date(y, mo, d).weekday()
    return "星期" + CN_WD[wd], (1 if wd in TRAIN_WD else 0)


def to_bool(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes", "y", "true", "1", "是", "✓", "ok"):
        return 1
    if s in ("no", "n", "false", "0", "否", "✗", ""):
        return 0
    return None


def to_float(v):
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def to_int(v):
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def table_val(text, name):
    m = re.search(r"\|\s*%s\s*[|｜]\s*([^|\n]+)" % re.escape(name), text)
    return m.group(1).strip() if m else None


def scores_from_table(text):
    out = {}
    for dim, key in [
        ("health", "health_score"),
        ("work", "work_score"),
        ("learn", "learn_score"),
        ("life", "life_score"),
    ]:
        # 兼容加粗(**5**)与未加粗(5)两种写法
        m = re.search(r"\|\s*%s[（(][^|]+?[）)]\s*[|｜]\s*\**\s*(\d+)" % dim, text)
        if m:
            out[key] = int(m.group(1))
    return out


def parse_prose_721(text):
    """7/21 纯正文解析（无前置块）。"""
    row = {}
    row["sleep_h"] = to_float(table_val(text, "睡眠时长"))
    q = table_val(text, "睡眠质量")
    row["sleep_quality"] = (
        None if (q and ("未显示" in q or "___" in q)) else to_int(q)
    )
    row["exercise_min"] = to_float(table_val(text, "运动时长"))
    row["diet_kcal"] = to_int(table_val(text, "饮食热量"))
    mc = table_val(text, "三餐")
    row["meals_count"] = mc.count("✓") if mc else None
    row["phone_h"] = to_float(table_val(text, "手机屏幕"))
    cm = table_val(text, "通勤")
    if cm:
        row["commute_done"] = 0 if "✗" in cm else 1
    m = re.search(r"深度工作[：:]\s*\**\s*([\d.]+)\s*h", text)
    if m:
        row["deepwork_h"] = float(m.group(1))
    # 补剂：晨间 Exia 早3 未吃 / 晚间 Exia 晚3 未吃 -> 未全完成
    if "Exia 早3（没吃）" in text or ("Exia 晚3" in text and "均未吃" in text):
        row["supps_done"] = 0
    else:
        done = len(re.findall(r"- \[x\] 补剂", text))
        row["supps_done"] = 1 if done >= 3 else 0
    row["breakfast_on_time"] = 1 if re.search(r"- \[x\] 早餐", text) else 0
    row.update(scores_from_table(text))
    return row


# 前置块字段 -> 数据库列
FM_MAP = {
    "sleep_h": ("sleep_h", "float"),
    "sleep_quality": ("sleep_quality", "int"),
    "supps_done": ("supps_done", "bool"),
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


def build_row(path):
    text = load_text(path)
    fm = parse_frontmatter(text)
    date_str = fm.get("date")
    if not date_str:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        if not m:
            return None, text
        date_str = m.group(1)

    row = {}
    for k, (col, kind) in FM_MAP.items():
        if k in fm and fm[k] != "":
            v = fm[k]
            if kind == "float":
                v = to_float(v)
            elif kind == "int":
                v = to_int(v)
            elif kind == "bool":
                v = to_bool(v)
            row[col] = v

    if not fm:  # 纯正文（7/21）
        row.update(parse_prose_721(text))

    bt = extract_bedtime(text)
    if bt is not None:
        row["bedtime"] = bt

    weekday, training_day = date_meta(date_str)
    row["date"] = date_str
    row["weekday"] = weekday
    row["training_day"] = training_day
    return row, text


def render(row, original_text):
    lines = []
    lines.append(f"# 每日复盘 · {row['date']}（{row.get('weekday', '')}）")
    lines.append("")
    lines.append("> 本文件由历史语雀复盘转换导入（DailyLumen）。原始叙述见文末。")
    lines.append("")
    lines.append("## 附录 · 系统数据")
    lines.append("")
    lines.append("```data")
    lines.append(f"日期: {row['date']}")
    lines.append(f"星期: {row.get('weekday', '')}")
    lines.append(f"训练日: {'yes' if row.get('training_day') == 1 else 'no'}")
    lines.append(f"睡眠时长_h: {_fmt(row.get('sleep_h'))}")
    lines.append(f"睡眠质量: {_fmt(row.get('sleep_quality'))}")
    bt = row.get("bedtime")
    lines.append(f"入睡时间: {_fmt_min(bt)}" if bt is not None else "入睡时间:")
    lines.append(f"补剂完成: {_fmt_bool(row.get('supps_done'))}")
    lines.append(f"运动时长_min: {_fmt(row.get('exercise_min'))}")
    lines.append(f"通勤完成: {_fmt_bool(row.get('commute_done'))}")
    lines.append(f"饮食热量_kcal: {_fmt(row.get('diet_kcal'))}")
    lines.append(f"三餐情况: {_fmt(row.get('meals_count'))}")
    lines.append(f"早餐按时: {_fmt_bool(row.get('breakfast_on_time'))}")
    lines.append(f"手机屏幕_h: {_fmt(row.get('phone_h'))}")
    lines.append(f"深度工作_h: {_fmt(row.get('deepwork_h'))}")
    lines.append(f"健康分: {_fmt(row.get('health_score'))}")
    lines.append(f"工作分: {_fmt(row.get('work_score'))}")
    lines.append(f"学习分: {_fmt(row.get('learn_score'))}")
    lines.append(f"生活分: {_fmt(row.get('life_score'))}")
    lines.append("```")
    lines.append("")
    lines.append("## 原始复盘（语雀导入）")
    lines.append("")
    lines.append(original_text.rstrip())
    lines.append("")
    return "\n".join(lines)


def _fmt(v):
    return "" if v is None else str(v)


def _fmt_bool(v):
    if v is None:
        return ""
    return "yes" if v == 1 else "no"


def _fmt_min(minutes):
    if minutes is None:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def main():
    check_only = "--check" in sys.argv
    files = sorted(
        f for f in os.listdir(SRC_DIR) if f.endswith(".md") and "DD" not in f
    )
    print(f"源目录: {SRC_DIR}")
    print(f"待处理文件: {len(files)} 个\n")
    ok = 0
    for fn in files:
        src = os.path.join(SRC_DIR, fn)
        row, text = build_row(src)
        if not row:
            print(f"  [跳过] {fn}: 无法解析日期")
            continue
        # 校验健康分是否会被自动生成（四维分缺失）
        auto = [k for k in ("health_score", "work_score", "learn_score", "life_score") if row.get(k) is None]
        tag = "自动生成" if auto else "手填保留"
        print(
            f"  [OK] {row['date']} {row.get('weekday','')} "
            f"训练={'Y' if row.get('training_day')==1 else 'N'} "
            f"bed={_fmt_min(row.get('bedtime'))} "
            f"睡{_fmt(row.get('sleep_h'))} 质{_fmt(row.get('sleep_quality'))} "
            f"运{_fmt(row.get('exercise_min'))} 食{_fmt(row.get('diet_kcal'))} "
            f"屏{_fmt(row.get('phone_h'))} 深{_fmt(row.get('deepwork_h'))} "
            f"补{_fmt_bool(row.get('supps_done'))} 餐{_fmt(row.get('meals_count'))} "
            f"四维={_vals(row)} ({tag})"
        )
        if not check_only:
            out_path = os.path.join(OUT_DIR, f"{row['date']}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render(row, text))
            ok += 1
    if check_only:
        print(f"\n--check 完成，未写入文件。")
    else:
        print(f"\n完成：已写入 {ok} 个标准文件到 {OUT_DIR}")


def _vals(row):
    return "/".join(
        str(row.get(k)) if row.get(k) is not None else "-"
        for k in ("health_score", "work_score", "learn_score", "life_score")
    )


if __name__ == "__main__":
    main()
