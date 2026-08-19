"""解析每日复盘文本/Markdown -> 结构化 dict。

支持三种来源:
  A) 标准 DailyLumen 格式：末尾的 ```data 代码块
       ```data
       日期: 2026-08-05
       睡眠时长_h: 6.42
       ...
       ```
  B) 旧模板格式：顶部 HTML 注释数据块
       <!-- ===== 数据块 ===== 日期: ... ===== /数据块 ===== -->
  C) 用户直接发的结构化表头文本（散落的 `key: value` 行）

字段名兼容中英文两套命名（如 睡眠时长_h / sleep_h）。
"""
from __future__ import annotations

import re

from .config import (
    INT_FIELDS, FLOAT_FIELDS, BOOL_FIELDS, TEXT_FIELDS, system_score_from,
)

# 数据块的 YAML 风格字段名 -> 数据库列名
FIELD_MAP = {
    # 兼容两种命名
    "date": "date", "日期": "date",
    "day": "weekday", "星期": "weekday",
    "training_day": "training_day", "训练日": "training_day",
    "sleep_h": "sleep_h", "睡眠时长_h": "sleep_h", "睡眠时长": "sleep_h",
    "sleep_quality": "sleep_quality", "睡眠质量": "sleep_quality",
    "bedtime": "bedtime", "入睡时间": "bedtime",
    "exercise_min": "exercise_min", "运动时长_min": "exercise_min", "运动时长": "exercise_min",
    "commute_done": "commute_done", "通勤完成": "commute_done",
    "diet_kcal": "diet_kcal", "饮食热量_kcal": "diet_kcal", "饮食热量": "diet_kcal",
    "meals_count": "meals_count", "三餐次数": "meals_count", "三餐情况": "meals_count",
    "breakfast_on_time": "breakfast_on_time", "早餐按时": "breakfast_on_time",
    "phone_h": "phone_h", "手机屏幕_h": "phone_h", "手机屏幕": "phone_h",
    "deepwork_h": "deepwork_h", "深度工作_h": "deepwork_h", "深度工作": "deepwork_h",
    "learn_h": "learn_h", "学习投入_h": "learn_h", "学习_h": "learn_h", "学习投入": "learn_h",
    "life_h": "life_h", "生活投入_h": "life_h", "生活_h": "life_h", "生活投入": "life_h",
    "energy": "energy", "精力": "energy",
    "mood": "mood", "心情": "mood",
    "health_score": "health_score", "健康分": "health_score",
    "work_score": "work_score", "工作分": "work_score",
    "learn_score": "learn_score", "学习分": "learn_score",
    "life_score": "life_score", "生活分": "life_score",
    "summary": "summary", "一句话总结": "summary",
}

# key: value 行（兼容中英文冒号）
_LINE_RE = re.compile(r"^([\w一-鿿_]+)\s*[:：]\s*(.*)$")


def _to_bool(v) -> int | None:
    """yes/y/true/1/是/✓/ok -> 1；no/n/false/0/否/✗/空 -> 0；其余 -> None。"""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes", "y", "true", "1", "是", "✓", "ok"):
        return 1
    if s in ("no", "n", "false", "0", "否", "✗", ""):
        return 0
    return None


def _to_bedtime_min(raw) -> int | None:
    """'HH:MM' / 'HH:MM:SS' -> 距 00:00 分钟数；解析失败返回 None。"""
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


def _coerce(col: str, raw) -> object | None:
    """按字段类型把字符串原始值转换为目标类型。"""
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


def _extract_block(text: str) -> str:
    """优先提取 ```data 代码块；其次 HTML 注释数据块；都没有返回 None。"""
    m = re.search(r"```data\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"<!--\s*=====\s*数据块.*?=====\s*/数据块\s*-->", text, re.S)
    if m:
        return m.group(0)
    return None


def _extract_personal_tracks(text: str) -> list[tuple[str, str, int]]:
    """从「一、日常打卡」章节提取个人定制勾选（服药 / 护肤）。

    返回 [(category, item, done), ...]。通用项（早餐/通勤）不在此列，
    它们有独立的通用字段。结果供 ingest 写入 personal_tracks 表，
    不参与通用评分。
    """
    m = re.search(r"##\s*一、日常打卡(.*?)(?=\n##\s|\Z)", text, re.S)
    if not m:
        return []
    tracks: list[tuple[str, str, int]] = []
    for line in m.group(1).splitlines():
        mm = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*)$", line)
        if not mm:
            continue
        done = 1 if mm.group(1).lower() == "x" else 0
        item = mm.group(2).strip()
        if not item:
            continue
        if "补剂" in item:
            # 去掉「补剂：」前缀，保留具体项（如 CoQ10 ×1 ＋ Exia 早3）
            spec = re.split(r"[：:]", item, maxsplit=1)[-1].strip()
            tracks.append(("服药", spec or item, done))
        elif "护肤" in item:
            tracks.append(("护肤", "护肤", done))
        # 早餐 / 通勤等通用打卡项不进入个人定制表
    return tracks


def parse_text(text: str) -> dict:
    """解析一段复盘文本 -> 结构化行 dict。"""
    body = _extract_block(text)

    row: dict = {}
    # 1) 若找到数据块，只在块内匹配 key: value
    if body:
        for line in body.splitlines():
            line = line.strip()
            mm = _LINE_RE.match(line)
            if not mm:
                continue
            key, val = mm.group(1).strip(), mm.group(2).strip()
            db_col = FIELD_MAP.get(key)
            if db_col and val != "":
                row[db_col] = _coerce(db_col, val)
    else:
        # 2) 无数据块：扫描全文 `字段：值` 行（兼容用户直接发的格式）
        for line in text.splitlines():
            line = line.strip()
            mm = _LINE_RE.match(line)
            if not mm:
                continue
            key, val = mm.group(1).strip(), mm.group(2).strip()
            db_col = FIELD_MAP.get(key)
            if db_col and val != "":
                row[db_col] = _coerce(db_col, val)

    # 3) 补系统分
    if row.get("date"):
        row["system_score"] = system_score_from(row)

    # 4) 提取「一、日常打卡」下的个人定制勾选 -> personal_tracks（服药/护肤）
    tracks = _extract_personal_tracks(text)
    if tracks:
        row["_personal_tracks"] = tracks

    return row


def parse_file(path: str) -> dict:
    """读取 md 文件并解析。结果附带 raw_path。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    row = parse_text(text)
    row["raw_path"] = path
    return row
