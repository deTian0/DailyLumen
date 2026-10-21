"""承诺解析纯规则：改进点 / 明日 Top 3 → 条目 + 约束抽取 + 桶分类（v10 / M29）。

零 I/O：禁止 sqlite3 / os / pathlib。

为什么要有这一层
----------------
78 天复盘里写了 308 条「改进点 / 明日 Top 3」，但代码一次都没读过
（``core/bodyweight.py`` 注释明说「那是计划/意愿，不是当天记录」）。结果
「复盘 → 计划 → 执行 → 对账」这条链在最关键的一环断掉：**只写不看**。

权威是源 md
-----------
- ``## 三、一个改进点`` → ``kind='improvement'``
- ``## 四、明日 Top 3``  → ``kind='plan'``

两者都是「对明天」的承诺：``date`` 记**写下承诺那天**，对账对象是次日。

两种「空」语义（同食物明细）
----------------------------
章节存在但无条目 → ``[]``（该日确实没写，ingest 要清空旧行）；
整段缺失 → 该 kind 不出现在返回值里（本次不动库）。
"""
from __future__ import annotations

import re

from ..config import PROMISE_BUCKETS, PROMISE_EMPTY_MARKERS, PROMISE_PROMPT_LINES
from .util import clock_to_minutes, is_blockquote_prose

_IMPROVE_RE = re.compile(
    r"^##[^\n]*改进点[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M
)
_PLAN_RE = re.compile(
    r"^##[^\n]*明日[^\n]*top\s*3[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M | re.I
)

_KIND_RES = {
    "improvement": _IMPROVE_RE,
    "plan": _PLAN_RE,
}

# 列表项：捕获缩进，用来区分顶层项与子项（子项是续行，不是独立承诺）
_BULLET_RE = re.compile(r"^([ \t]*)[-*+]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^([ \t]*)\d+\s*[.、)）]\s+(.+)$")

# 约束：时长（60min / 30 分钟 / 保持 5h）、时刻（22:30）、上限（≤70g / ≤1h / 控制在 1800 大卡）
_MINUTES_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*(min|mins|分钟|h|小时)(?![a-zA-Z])", re.I
)
_CLOCK_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)")
# 带「前 / 之前」的时刻优先：承诺里的目标通常这么写（「23:30 前」「22:00 之前」）。
# 反面教材：「00:43 才入睡（较 10-13 的 22:28 晚了 2 小时）——今晚 22:30 手机离手」
# 若只取第一个时刻，会把**对昨天的描述**当成今天的目标，判定全反。
_CLOCK_BEFORE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})\s*(?:前|之前|以前)"
)
_LIMIT_RE = re.compile(
    r"(?:≤|<=|<|＜|不超过|控制在|低于|上限)\s*(\d+(?:\.\d+)?)\s*"
    r"(g|克|kcal|大卡|千卡|h|小时|min|分钟)?(?![a-zA-Z\u4e00-\u9fff])",
    re.I,
)

_UNIT_MAP = {
    "克": "g", "g": "g",
    "大卡": "kcal", "千卡": "kcal", "kcal": "kcal",
    "h": "h", "小时": "h",
    "min": "min", "分钟": "min",
}

# 小时单位要换算成分钟
_HOUR_UNITS = ("h", "小时")


# 续行判定：缩进达到 2 个空格 / 1 个 tab 即视为上一项的子项
_CONT_INDENT = 2


def section_body(text: str, kind: str) -> str:
    """取某 kind 的章节正文；找不到返回空串。"""
    rx = _KIND_RES.get(kind)
    if rx is None:
        raise ValueError(f"未知承诺类型: {kind}")
    m = rx.search(text or "")
    return m.group(1) if m else ""


def has_section(text: str, kind: str) -> bool:
    """该章节标题是否存在（区分「空章节」与「没这个章节」）。"""
    rx = _KIND_RES.get(kind)
    if rx is None:
        raise ValueError(f"未知承诺类型: {kind}")
    return rx.search(text or "") is not None


def is_prompt_line(text: str) -> bool:
    """是不是模板的**填写提示**（`通常落在：…`）而不是真实承诺。

    9 月版模板把提示写成了列表项，留空的日子里它成了唯一内容。
    归一化后全等比对，不做模糊匹配。
    """
    key = normalize(text)
    return bool(key) and any(key == normalize(p) for p in PROMISE_PROMPT_LINES)


def is_empty_marker(text: str) -> bool:
    """是不是「写了等于没写」的放弃标记（`空` / `忘记了` / `想不到`）。

    这类是 meta 陈述，不是承诺；计成「未兑现」会冤枉，计成空才对。
    全等匹配 —— 「无糖」「空心病」不会中招。
    """
    key = normalize(text)
    return bool(key) and any(key == normalize(m) for m in PROMISE_EMPTY_MARKERS)


def clean_item(line: str) -> str | None:
    """一行 → 承诺原文（去列表符）；不是数据行返回 None。

    除了引用块说明，还要挡掉 markdown 表格行与分隔线 ——「四、明日 Top 3」
    下方若画了表格，``|---|`` 不该变成一条承诺。
    """
    if is_blockquote_prose(line):
        return None
    s = (line or "").rstrip()
    if not s.strip():
        return None
    stripped = s.strip()
    if stripped.startswith("|") or set(stripped) <= set("-:| "):
        return None
    m = _BULLET_RE.match(s) or _NUMBERED_RE.match(s)
    if m is None:
        return None
    indent = len(m.group(1).replace("\t", " " * _CONT_INDENT))
    if indent >= _CONT_INDENT:
        return None
    body = m.group(2).strip()
    if not body or is_prompt_line(body) or is_empty_marker(body):
        return None
    return body


def parse_items(body: str) -> list[str]:
    """章节正文 → 承诺原文列表（保持书写顺序、按原文去重）。"""
    out: list[str] = []
    seen: set[str] = set()
    for line in (body or "").splitlines():
        item = clean_item(line)
        if item is None:
            continue
        key = normalize(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def parse_section(text: str) -> dict | None:
    """解析两类承诺 → ``{kind: [原文, ...]}``；两个章节都没有返回 None。

    只包含**存在**的 kind：章节缺失 = 本次不动库，章节存在但空 = 清空该 kind。
    """
    out: dict[str, list[str]] = {}
    for kind in _KIND_RES:
        if not has_section(text, kind):
            continue
        out[kind] = parse_items(section_body(text, kind))
    return out or None


def extract_constraints(text: str) -> dict:
    """从承诺原文抽可验证的约束：``minutes`` / ``clock`` / ``limit``。

    抽不出就不给这个键 —— 调用方据此判断「这条承诺能不能自动对账」。
    只认**明确写出来的数字**，不做「一顿减半」这类模糊推断。
    """
    raw = text or ""
    out: dict = {}

    # 上限先抽，再把「≤1h」这段从串里抹掉再找时长 —— 否则「控制番茄小说 ≤1h」
    # 会同时抽出 limit=1h 和 minutes=60，而后者根本不是目标时长。
    scan = raw
    lm = _LIMIT_RE.search(raw)
    if lm:
        unit = _UNIT_MAP.get((lm.group(2) or "").lower())
        out["limit"] = {"op": "lte", "value": float(lm.group(1)), "unit": unit}
        scan = raw[: lm.start()] + " " * (lm.end() - lm.start()) + raw[lm.end():]

    m = _MINUTES_RE.search(scan)
    if m:
        val = float(m.group(1))
        if m.group(2).lower() in _HOUR_UNITS:
            val *= 60
        out["minutes"] = val

    for cm in list(_CLOCK_BEFORE_RE.finditer(raw)) + list(_CLOCK_RE.finditer(raw)):
        mins = clock_to_minutes(f"{cm.group(1)}:{cm.group(2)}")
        if mins is not None and 0 <= mins < 1440:
            out["clock"] = mins
            break

    return out


def classify(text: str, *, buckets: list[dict] | None = None) -> str | None:
    """承诺原文 → 桶 key（``learn`` / ``exercise`` / …）；无法归类返回 None。

    判据是**关键词在句中首次出现的位置**，越靠前越可能是主语 ——
    比起「桶顺序优先」这样能处理跨桶的长句：

    - ``午餐不点肥肠类主菜，脂肪目标 ≤70g；补剂从早上的 CoQ10 开始恢复勾``
      → 「午餐」在 0 位、「CoQ10」在 25 位 → **饮食**（主体确实是吃饭）
    - ``22:30 手机放客厅，23:30 关灯``
      → 「手机放客厅」与「手机」同位置，取更长的关键词 → **睡眠**（判据是入睡时刻）

    位置相同则**长关键词优先**，仍相同才回落到 ``PROMISE_BUCKETS`` 的书写顺序。
    """
    catalog = buckets if buckets is not None else PROMISE_BUCKETS
    low = (text or "").lower()
    if not low.strip():
        return None
    best: tuple[int, int, int, str] | None = None
    for idx, bucket in enumerate(catalog):
        for kw in bucket.get("keywords") or []:
            if not kw:
                continue
            pos = low.find(kw.lower())
            if pos < 0:
                continue
            cand = (pos, -len(kw), idx, bucket["key"])
            if best is None or cand < best:
                best = cand
    return best[3] if best else None


def normalize(text: str) -> str:
    """对账比对用的归一化：小写 + 去空白与标点，只留文字数字。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())


def bucket_label(key: str | None, *, buckets: list[dict] | None = None) -> str:
    """桶 key → 中文标签；未知返回「其他」。"""
    if not key:
        return "其他"
    for bucket in (buckets if buckets is not None else PROMISE_BUCKETS):
        if bucket["key"] == key:
            return bucket.get("label") or key
    return "其他"
