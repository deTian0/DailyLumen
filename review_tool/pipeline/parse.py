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
个人打卡（补剂/护肤）由「一、日常打卡」勾选提取，经 tracks 模块归一化后
落到 personal_tracks 表，不参与通用评分。

徒手训练折算：「运动时长_min」为空但「二、今日三件事」里提到俯卧撑等动作时，
由 bodyweight 模块按确定性模型折算分钟数（并记 exercise_src='derived'）。
字段已有数值时以字段为准，不做叠加。

训练明细（M10）：「附录 · 训练明细」→ ``_training`` 侧车；合计分钟仅在
``exercise_min`` 仍为空时派生（字段优先 → 三件事折算 → 明细合计），
同样标 ``exercise_src='derived'``（R2，不加新枚举）。

学习记录（M13）：「附录 · 学习记录」→ ``_learning`` 侧车（条目列表）；
不参与四维（G5）；ingest 落 ``learning_logs`` 并重建 ``review_queue``。
"""
from __future__ import annotations

import re

from ..config import (
    BODY_FIELD_MAP,
    BODY_FLOAT_FIELDS,
    BODY_TEXT_FIELDS,
    BOOL_FIELDS,
    FLOAT_FIELDS,
    INT_FIELDS,
    SLOT_BY_CN,
    SUPPLEMENT_MARKER,
)
from ..core.bodyweight import estimate
from ..core.learning import parse_section as parse_learning_section
from ..core.score import system_score_from
from ..core.tracks import normalize_supplement_line, resolve_item, resolve_track
from ..core.training import parse_section as parse_training_section
from ..core.util import KV_RE, clock_to_minutes, to_bool, to_float, to_int

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
    "carbs_g": "carbs_g", "碳水_g": "carbs_g", "碳水化合物_g": "carbs_g",
    "carbs": "carbs_g", "碳水": "carbs_g", "碳水化合物": "carbs_g",
    "fat_g": "fat_g", "脂肪_g": "fat_g",
    "fat": "fat_g", "脂肪": "fat_g",
    "protein_g": "protein_g", "蛋白质_g": "protein_g",
    "protein": "protein_g", "蛋白质": "protein_g",
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

# 「日常打卡」小节（历史上也叫过「内核打卡」，也曾编号为「零」）
_SECTION_TRACKS_RE = re.compile(r"##\s*[零一二三四五六]、[^\n]*打卡(.*?)(?=\n##\s|\Z)", re.S)
# 该小节内的时段标题：兼容 **晨间（起床后）** 与 ### 晨间（起床后） 两种写法
_SLOT_HEADER_RE = re.compile(r"^\s*(?:\*\*|#{2,5})\s*(晨间|午间|晚间).*$")
# 打卡行：- [x] / - [ ]
_CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.*)$")


def _coerce(col: str, raw) -> object | None:
    """按字段类型把字符串原始值转换为目标类型。"""
    if raw is None or str(raw).strip() == "":
        return None
    raw = str(raw).strip()
    # 三餐情况: "早✓午✓晚✓" / "早✓午✓晚✗" -> 统计 ✓ 数量
    if col == "meals_count" and "✓" in raw:
        return raw.count("✓")
    if col == "bedtime":
        return clock_to_minutes(raw)
    if col in INT_FIELDS:
        return to_int(raw)
    if col in FLOAT_FIELDS:
        return to_float(raw)
    if col in BOOL_FIELDS:
        return to_bool(raw)
    return raw  # text


def _coerce_body(col: str, raw) -> object | None:
    """体征侧车字段类型转换（独立于 daily_reviews 字段表）。"""
    if raw is None or str(raw).strip() == "":
        return None
    raw = str(raw).strip()
    if col in BODY_FLOAT_FIELDS:
        return to_float(raw)
    if col in BODY_TEXT_FIELDS:
        if col == "src":
            key = raw.lower()
            if key in ("scale", "体脂秤", "秤"):
                return "scale"
            if key in ("manual", "手填", "手动"):
                return "manual"
            return None
        return raw
    return raw


def _extract_block(text: str) -> str | None:
    """优先提取 ```data 代码块；其次 HTML 注释数据块；都没有返回 None。

    注释块的结束标记在历史上出现过两种写法：
        <!-- ===== /数据块 ===== -->      （实际使用）
        <!-- ===== /数据块 -->            （早期文档描述）
    这里统一兼容。
    """
    m = re.search(r"```data\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"<!--\s*=*\s*数据块.*?=*\s*/数据块\s*=*\s*-->", text, re.S)
    if m:
        return m.group(0)
    return None


def _scan_kv(body: str, row: dict) -> None:
    """扫描 body 中的 `key: value` 行并写入 row。

    体征字段（体重_kg / 体脂率 / 腰围_cm）写入 ``row["_body_metrics"]`` 侧车，
    **不**写入 daily_reviews 列（G3 / 一表一责）。
    """
    body_side: dict = {}
    for line in body.splitlines():
        mm = KV_RE.match(line.strip())
        if not mm:
            continue
        key, val = mm.group(1).strip(), mm.group(2).strip()
        body_col = BODY_FIELD_MAP.get(key)
        if body_col is not None:
            if val != "":
                body_side[body_col] = _coerce_body(body_col, val)
            continue
        db_col = FIELD_MAP.get(key)
        if db_col and val != "":
            row[db_col] = _coerce(db_col, val)
    if body_side:
        row["_body_metrics"] = body_side


def has_tracks_section(text: str) -> bool:
    """「一、日常打卡」章节是否存在。

    用于区分「当天没有补剂/护肤项」与「该章节压根没解析到」——只有章节存在时，
    解析出的打卡集合才可以当作该日期的**权威集合**去和库里对账（见 ingest
    ``--prune-tracks`` 与 doctor 的 [打卡对账]）。
    """
    return _SECTION_TRACKS_RE.search(text) is not None


def _extract_personal_tracks(text: str) -> list[tuple[str, str, str, str, int]]:
    """从「一、日常打卡」章节提取个人定制勾选（补剂 / 护肤）。

    返回 ``[(category, track_key, item_key, item_label, done), ...]``。

    通用项（早餐 / 通勤）不在此列——它们有独立的通用字段；
    只有 ``config.PERSONAL_ITEMS`` 中定义过的项才会进入 personal_tracks。
    时段由小节标题（``**晨间（起床后）**`` 或 ``### 晨间（起床后）``）决定，
    标题缺失时由项定义的默认时段兜底。
    """
    m = _SECTION_TRACKS_RE.search(text)
    if not m:
        return []

    tracks: list[tuple[str, str, str, str, int]] = []
    slot: str | None = None
    for line in m.group(1).splitlines():
        sm = _SLOT_HEADER_RE.match(line)
        if sm:
            slot = SLOT_BY_CN.get(sm.group(1))
            continue

        mm = _CHECKBOX_RE.match(line)
        if not mm:
            continue
        done = 1 if mm.group(1).lower() == "x" else 0
        label_text = mm.group(2).strip()
        if not label_text:
            continue

        if SUPPLEMENT_MARKER in label_text:
            for cat, track_key, item_key, item_label in normalize_supplement_line(label_text, slot):
                tracks.append((cat, track_key, item_key, item_label, done))
            continue

        # 非补剂行：只记录已在 PERSONAL_ITEMS 定义过的项（护肤等）
        defined = resolve_item(label_text)
        if defined is not None:
            cat, track_key, item_key, item_label = resolve_track(
                label_text, slot=slot, category=defined["category"]
            )
            tracks.append((cat, track_key, item_key, item_label, done))
    return tracks


def parse_text(text: str) -> dict:
    """解析一段复盘文本 -> 结构化行 dict。"""
    body = _extract_block(text)

    row: dict = {}
    if body:
        # 1) 有数据块：只在块内匹配 key: value
        _scan_kv(body, row)
    else:
        # 2) 无数据块：扫描全文 `字段：值` 行（兼容用户直接发的格式）
        _scan_kv(text, row)

    # 3) 补系统分
    if row.get("date"):
        row["system_score"] = system_score_from(row)

    # 4) 训练明细侧车（附录 · 训练明细）—— 先解析、后参与时长派生
    training = parse_training_section(text)
    if training is not None:
        row["_training"] = training

    # 5) 运动时长派生（字段优先、不叠加 —— R2）
    #    优先级：手填字段 → 三件事折算 → 训练明细合计。
    #    exercise_src 记录来源；⛔ 不加新枚举，明细派生复用 'derived'。
    if row.get("exercise_min") is not None:
        row["exercise_src"] = "record"
    else:
        minutes, detail = estimate(text)
        if minutes is not None:
            row["exercise_min"] = minutes
            row["exercise_src"] = "derived"
            row["_exercise_detail"] = detail
        elif training is not None and training.get("total_min") is not None:
            row["exercise_min"] = int(training["total_min"])
            row["exercise_src"] = "derived"
            row["_exercise_detail"] = (
                f"训练明细合计 {training['total_min']}min"
                f"（session={training.get('session_key')}）"
            )

    # 6) 学习记录侧车（附录 · 学习记录）—— 独立指标区，不参与四维
    learning = parse_learning_section(text)
    if learning is not None:
        row["_learning"] = learning

    # 7) 提取「一、日常打卡」下的个人定制勾选 -> personal_tracks（补剂/护肤）
    tracks = _extract_personal_tracks(text)
    if tracks:
        row["_personal_tracks"] = tracks
    # 该章节是否存在（供打卡对账判断「解析结果是否可作为权威集合」）
    row["_tracks_section"] = has_tracks_section(text)

    return row


def parse_file(path: str) -> dict:
    """读取 md 文件并解析。结果附带 raw_path。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    row = parse_text(text)
    row["raw_path"] = path
    return row
