"""解析每日复盘文本/Markdown -> 结构化 dict。

支持两种来源:
  A) 用户直接发的结构化表头文本, 例如:
       date: 2026-08-05
       day: 周二
       training_day: yes
       sleep_h: 6.42
       ...
  B) 每日复盘模板 markdown, 顶部有 HTML 注释数据块:
       <!-- ===== 数据块 =====
       日期: YYYY-MM-DD
       睡眠时长_h: 6.42
       ... ===== /数据块 ===== -->
"""
import re
from config import INT_FIELDS, FLOAT_FIELDS, BOOL_FIELDS, TEXT_FIELDS, system_score_from

# 数据块的 YAML 风格字段名 -> 数据库列名
FIELD_MAP = {
    # 兼容两种命名
    "date": "date", "日期": "date",
    "day": "weekday", "星期": "weekday",
    "training_day": "training_day", "训练日": "training_day",
    "sleep_h": "sleep_h", "睡眠时长_h": "sleep_h", "睡眠时长": "sleep_h",
    "sleep_quality": "sleep_quality", "睡眠质量": "sleep_quality",
    "bedtime": "bedtime", "入睡时间": "bedtime",
    "supps_done": "supps_done", "补剂完成": "supps_done",
    "exercise_min": "exercise_min", "运动时长_min": "exercise_min", "运动时长": "exercise_min",
    "commute_done": "commute_done", "通勤完成": "commute_done",
    "diet_kcal": "diet_kcal", "饮食热量_kcal": "diet_kcal", "饮食热量": "diet_kcal",
    "meals_count": "meals_count", "三餐次数": "meals_count", "三餐情况": "meals_count",
    "breakfast_on_time": "breakfast_on_time", "早餐按时": "breakfast_on_time",
    "phone_h": "phone_h", "手机屏幕_h": "phone_h", "手机屏幕": "phone_h",
    "deepwork_h": "deepwork_h", "深度工作_h": "deepwork_h", "深度工作": "deepwork_h",
    "energy": "energy", "精力": "energy",
    "mood": "mood", "心情": "mood",
    "health_score": "health_score", "健康分": "health_score",
    "work_score": "work_score", "工作分": "work_score",
    "learn_score": "learn_score", "学习分": "learn_score",
    "life_score": "life_score", "生活分": "life_score",
    "summary": "summary", "一句话总结": "summary",
}


def _to_bool(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes", "y", "true", "1", "是", "✓", "ok"):
        return 1
    if s in ("no", "n", "false", "0", "否", "✗", ""):
        return 0
    return None


def _to_bedtime_min(raw):
    """'HH:MM' / 'HH:MM:SS' -> 距 00:00 分钟数; 解析失败返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def _coerce(col, raw):
    if raw is None or str(raw).strip() == "":
        return None
    raw = str(raw).strip()
    # 三餐情况: "早✓午✓晚✓" / "早✓午✓晚✗" -> 统计 ✓ 数量
    if col == "meals_count" and "✓" in raw:
        return raw.count("✓")
    # 入睡时间: "00:39" -> 39 (分钟)
    if col == "bedtime":
        return _to_bedtime_min(raw)
    if col in INT_FIELDS:
        m = re.search(r"-?\d+", raw)
        return int(m.group()) if m else None
    if col in FLOAT_FIELDS:
        m = re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(m.group()) if m else None
    if col in BOOL_FIELDS:
        return _to_bool(raw)
    return raw  # text


def parse_text(text: str) -> dict:
    """解析一段复盘文本 -> 结构化行 dict。"""
    # 1) 提取数据块 (优先 markdown 注释块)
    body = text
    m = re.search(r"<!--\s*=====\s*数据块.*?=====\s*/数据块\s*-->", text, re.S)
    if m:
        body = m.group(0)

    # 2) 匹配 key: value 行 (兼容 `key: value` 和 `key：value`)
    row = {}
    for line in body.splitlines():
        line = line.strip()
        mm = re.match(r"^([\w\u4e00-\u9fff_]+)\s*[:：]\s*(.*)$", line)
        if not mm:
            continue
        key, val = mm.group(1).strip(), mm.group(2).strip()
        db_col = FIELD_MAP.get(key)
        if db_col and val != "":
            row[db_col] = _coerce(db_col, val)

    # 3) 若没有数据块, 退而求其次: 扫描全文中 `字段：值` 行 (兼容用户直接发的格式)
    if "date" not in row:
        for line in text.splitlines():
            line = line.strip()
            mm = re.match(r"^([\w\u4e00-\u9fff_]+)\s*[:：]\s*(.*)$", line)
            if not mm:
                continue
            key, val = mm.group(1).strip(), mm.group(2).strip()
            db_col = FIELD_MAP.get(key)
            if db_col and val != "":
                row[db_col] = _coerce(db_col, val)

    # 4) 补系统分
    if row.get("date"):
        row["system_score"] = system_score_from(row)
    return row


def parse_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    row = parse_text(text)
    row["raw_path"] = path
    return row
