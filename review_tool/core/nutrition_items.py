"""食物明细纯规则：md 附录表格解析 + 餐次归一化（M25 / schema v9）。

零 I/O：禁止 sqlite3 / os / pathlib。明细**不参与四维评分**（G5），
只用于「回看某天吃了什么」下钻；kcal 为估算值，不做精确化。

附录格式（「附录 · 食物明细」）
--------------------------------
::

    | 餐次 | 食物 | 估算 kcal | 备注 |
    |------|------|-----------|------|
    | 早 | 燕麦 40g ＋ 牛奶 250ml | 380 | 估算 |
    | 午 | 食堂两荤一素 | 约 700 |  |

- 列**按表头名匹配**（餐次 / 食物 / kcal / 蛋白 / 碳水 / 脂肪 / 备注），顺序可变、可缺列；
- 「食物」为空的整行跳过（模板空行、「没提到的行删掉」的残留）；
- kcal 允许 ``约 380`` / ``380 kcal`` / ``≈380`` 写法，取第一个数值；
- 同日顺序即表内顺序，落库为 ``seq``，保证从 md 100% 可重建。
"""
from __future__ import annotations

import re

from .util import to_float

_SECTION_RE = re.compile(
    r"^##[^\n]*食物明细[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M
)

# 餐次归一化：展示值 → 稳定 code（落库用 code，展示走 MEAL_LABELS）
_MEAL_MAP = {
    "早": "breakfast",
    "早餐": "breakfast",
    "早饭": "breakfast",
    "breakfast": "breakfast",
    "午": "lunch",
    "午餐": "lunch",
    "午饭": "lunch",
    "中餐": "lunch",
    "lunch": "lunch",
    "晚": "dinner",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "dinner": "dinner",
    "加餐": "snack",
    "夜宵": "snack",
    "宵夜": "snack",
    "零食": "snack",
    "snack": "snack",
}

MEAL_LABELS = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
    "other": "其他",
}
MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack", "other"]

# 表头 → 列名（同一列可有多别名，中文 / 英文都收）
_HEADER_ALIASES = {
    "meal": ("餐次", "餐", "顿", "meal"),
    "desc": ("食物", "食品", "名称", "内容", "desc", "food", "item"),
    "kcal": ("估算 kcal", "kcal", "千卡", "热量", "大卡"),
    "protein_g": ("蛋白", "蛋白质", "protein"),
    "carb_g": ("碳水", "碳水化合物", "carb"),
    "fat_g": ("脂肪", "fat"),
    "note": ("备注", "说明", "note", "remark"),
}

_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def section_body(text: str) -> str:
    """取「附录 · 食物明细」正文；找不到返回空串。"""
    m = _SECTION_RE.search(text or "")
    return m.group(1) if m else ""


def normalize_meal(raw: str | None) -> str:
    """餐次文案 → ``breakfast`` / ``lunch`` / ``dinner`` / ``snack`` / ``other``。

    匹配优先级：**全等** → 多字别名**包含** → 单字别名**首尾**。
    单字别名（早/午/晚）不做子串匹配，否则「下午茶」会被判成午餐。
    """
    key = str(raw or "").strip().lower().replace(" ", "")
    if not key:
        return "other"
    if key in _MEAL_MAP:
        return _MEAL_MAP[key]
    for cn, code in _MEAL_MAP.items():
        if len(cn) >= 2 and cn in key:
            return code
    for cn, code in _MEAL_MAP.items():
        if len(cn) == 1 and (key.startswith(cn) or key.endswith(cn)):
            return code
    return "other"


def _split_row(line: str) -> list[str] | None:
    """把一行 markdown 表格拆成单元格；不是表格行返回 None。"""
    s = (line or "").strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def _header_index(cells: list[str]) -> dict[str, int] | None:
    """表头行 → ``{列名: 下标}``；认不出「食物」列就返回 None。"""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(cells):
        # 长别名优先，避免「蛋白」先被「蛋」之类短词吃掉
        low = cell.strip().lower()
        for col, aliases in _HEADER_ALIASES.items():
            if col in mapping:
                continue
            if any(alias.lower() == low for alias in aliases):
                mapping[col] = idx
                break
    return mapping if "desc" in mapping else None


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c.strip()) for c in cells)


def _cell(cells: list[str], mapping: dict[str, int], col: str) -> str | None:
    idx = mapping.get(col)
    if idx is None or idx >= len(cells):
        return None
    value = cells[idx].strip()
    return value or None


def parse_table(body: str) -> list[dict]:
    """解析附录正文里的表格 → 条目列表（保持表内顺序）。"""
    lines = (body or "").splitlines()
    items: list[dict] = []
    mapping: dict[str, int] | None = None

    for line in lines:
        cells = _split_row(line)
        if cells is None:
            # 表格结束；后续若还有另一张表，重新找表头
            mapping = None
            continue
        if mapping is None:
            mapping = _header_index(cells)
            continue
        if _is_separator(cells):
            continue

        desc = _cell(cells, mapping, "desc")
        if not desc:
            continue  # 模板空行 / 已删掉的行
        items.append({
            "meal": normalize_meal(_cell(cells, mapping, "meal")),
            "desc": desc,
            "kcal": to_float(_cell(cells, mapping, "kcal")),
            "protein_g": to_float(_cell(cells, mapping, "protein_g")),
            "carb_g": to_float(_cell(cells, mapping, "carb_g")),
            "fat_g": to_float(_cell(cells, mapping, "fat_g")),
            "note": _cell(cells, mapping, "note"),
        })

    for i, item in enumerate(items):
        item["seq"] = i
    return items


def parse_section(text: str) -> list[dict] | None:
    """解析「附录 · 食物明细」→ 条目列表；无该章节返回 None。

    章节存在但表格为空 → 返回空列表（供 ingest 判定「当日确实没有明细」，
    与「该文件压根没有这个附录」区分开，前者要清空该日旧行）。
    """
    body = section_body(text)
    if not _SECTION_RE.search(text or ""):
        return None
    return parse_table(body)


def total_kcal(items: list[dict]) -> float | None:
    """明细 kcal 合计；一条都没有估值时返回 None（不返回 0，避免误判「吃了 0 kcal」）。"""
    vals = [it["kcal"] for it in items if it.get("kcal") is not None]
    return sum(vals) if vals else None


def group_by_meal(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """按餐次顺序分组 → ``[(meal_code, items), ...]``；空组不返回。"""
    buckets: dict[str, list[dict]] = {}
    for item in items:
        buckets.setdefault(item.get("meal") or "other", []).append(item)
    return [(code, buckets[code]) for code in MEAL_ORDER if code in buckets]
