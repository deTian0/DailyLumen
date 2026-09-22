"""通用小工具：时间格式化、数值转换、打卡项归一化。

原先 `clock()`（ai_review）、`_fmt_min()`（import_history）、
`_to_int/_to_float/_to_bool`（parse / import_history）各自实现过一份，
此处收敛为单一来源，所有模块共用。
"""
from __future__ import annotations

import re

# key: value 行（兼容中英文冒号）
KV_RE = re.compile(r"^([\w一-鿿_]+)\s*[:：]\s*(.*)$")

# 补剂打卡里的多项分隔符：「A ＋ B」「A + B」「A、B」「A / B」
ITEM_SPLIT_RE = re.compile(r"\s*[＋+、]\s*|\s+/\s+")

# 片段里的数量标记（×1 / x2 / *3 / 1粒），归一化 slug 时剔除
_QTY_RE = re.compile(r"[×xX*]\s*\d+|\d+\s*(?:粒|片|颗|袋|次)")


def clock_to_minutes(raw) -> int | None:
    """'HH:MM' / 'HH:MM:SS' -> 距 00:00 的分钟数；解析失败返回 None。

    23:47 -> 1427，00:39 -> 39。
    """
    if raw is None:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", str(raw).strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def minutes_to_clock(minutes) -> str:
    """距 00:00 的分钟数 -> 'HH:MM'；None 返回 '-'。"""
    if minutes is None:
        return "-"
    minutes = int(minutes) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_int(v) -> int | None:
    """从任意文本里取出第一个整数；取不到返回 None。"""
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def to_float(v) -> float | None:
    """从任意文本里取出第一个数值（可含小数）；取不到返回 None。"""
    if v is None or str(v).strip() == "":
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def to_bool(v) -> int | None:
    """yes/y/true/1/是/✓/ok -> 1；no/n/false/0/否/✗/空 -> 0；其余 -> None。"""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes", "y", "true", "1", "是", "✓", "ok"):
        return 1
    if s in ("no", "n", "false", "0", "否", "✗", ""):
        return 0
    return None


def is_late_bedtime(bedtime: int | None, thresholds: dict) -> bool:
    """入睡时间是否落在扣分档（与 score.compute_health_score 口径一致）。

    两端都扣分：0~late_night_max（00:00–06:00）判「熬夜」，
    > ok_max（23:30–23:59）判「晚睡」，中间不扣。
    """
    if bedtime is None:
        return False
    return bedtime <= thresholds["late_night_max"] or bedtime > thresholds["ok_max"]


def slugify(text: str, max_len: int = 24) -> str:
    """把自由文本归一化成稳定的 slug（用于未知打卡项的聚合）。

    剔除数量标记与空白，保留中英文与数字，其余转连字符。
    """
    s = _QTY_RE.sub("", str(text or ""))
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"[^\w一-鿿-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "unknown")[:max_len]


def split_items(text: str) -> list[str]:
    """拆分「CoQ10 ×1 ＋ Exia 早3」这类多项打卡文本。"""
    return [p.strip() for p in ITEM_SPLIT_RE.split(str(text or "")) if p.strip()]
