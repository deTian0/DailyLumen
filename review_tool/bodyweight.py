"""徒手训练折算：把「三件事」描述里的动作换算成运动分钟数。

背景
----
你确实做了徒手训练（俯卧撑），但「运动时长_min」字段常常留空 —— 该字段为
NULL，而训练日达标率正是按这个字段统计，于是长期显示「0/4 达标」，指标
实际失效（运动占健康分权重 0.25，是全部健康子项里最重的一项）。

规则
----
描述里出现 ``config.BODYWEIGHT_MOVES`` 定义的动作关键词，即按
``config.BODYWEIGHT_RULES`` 的模型折算：

    净执行时间 = 次数 / per_minute
    组间休息   = (组数 - 1) × set_rest_sec
    单日结果   = clamp(Σ , min_session_min, max_session_min)

估算是**确定性**的：同一段文本永远得到同一个分钟数，可重复推导、可审计，
不调用任何外部服务。

扫描范围（重要）
----------------
严格限定「二、今日三件事」—— 那是「今天实际做成的事」。刻意**不扫**：

- 「七、AI 评价与建议」：那里会引用别的日期。例如 9/20 的评语写着
  「你在 9/19 做过 100 个俯卧撑、9/13 做过 10×2」—— 若扫全文，就会把
  9/19 的量算到 9/20 头上（这是历史上真实出现过的误判来源）。
- 「三、一个改进点」「四、明日 Top 3」：那是计划/意愿，不是当天记录。

字段优先级
----------
若「运动时长_min」已有数值（含手填），**以字段为准、不做叠加** —— 否则同一份
运动会被重复计一次。折算只在该字段为空时生效。

数量识别支持的写法
------------------
``俯卧撑 10 * 2``（10 次 × 2 组）、``10 * 10 个俯卧撑``、``100 个俯卧撑``、
``做了二十个俯卧撑``（中文数字）、``俯卧撑 20 个``。

否定句（``没做``/``未做``/``忘了``…）不折算。
"""
from __future__ import annotations

import re

from .config import BODYWEIGHT_MOVES, BODYWEIGHT_RULES

# 全角数字 -> 半角
_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")

_CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

# 一个「数字」token：阿拉伯数字或中文数字
_NUM = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+)"

# 任意数字（兜底）
_NUM_ALL = re.compile(f"({_NUM})")
# 「数字 + 量词」——优先识别，能天然排除「一组」「一共」这类噪声
_COUNTED_RE = re.compile(rf"({_NUM})\s*[个次下]")
# 「N 组」
_SET_RE = re.compile(rf"({_NUM})\s*组")

# 「A * B」写法（A = 每组次数，B = 组数）
_SETS_REPS_RE = re.compile(rf"({_NUM})\s*[*xX×✕]\s*({_NUM})")

# 目标段落：「二、今日三件事」（对编号变化/措辞微调都容错）
_THINGS_SECTION_RE = re.compile(
    r"^##[^\n]*今日三件事[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M
)

# 列表序号前缀（「1. 」「- 」「(2) 」），提取数量前先剥掉，
# 否则「1. 俯卧撑」里的序号会被当成次数。
_LINE_MARKER_RE = re.compile(r"^\s*(?:[-*+>]|\d+\s*[.、)）])\s*")

# 否定/未完成表述：命中则整行跳过（保守取词，避免「没」误伤正常句子）
_NEGATIVE_RE = re.compile(r"没做|没有做|未做|没练|没动|忘了|漏了|没完成|未完成|做不到|放弃")

# 数量词与动作关键词之间允许的最大字符距离（容纳「个」「组」「次」等量词）
_MAX_GAP = 6


def cn_to_int(token) -> int | None:
    """中文/阿拉伯数字 -> int。无法解析返回 None。

    >>> cn_to_int("二十")
    20
    >>> cn_to_int("一百")
    100
    >>> cn_to_int("15")
    15
    """
    if token is None:
        return None
    s = str(token).strip().translate(_FULLWIDTH)
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "." in s:
        try:
            return int(float(s))
        except ValueError:
            return None

    result = 0
    num = 0
    seen = False
    for ch in s:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
            seen = True
        elif ch == "十":
            result += (num or 1) * 10
            num = 0
            seen = True
        elif ch == "百":
            result += (num or 1) * 100
            num = 0
            seen = True
        else:
            return None
    return result + num if seen else None


def section_body(text: str) -> str:
    """取「二、今日三件事」正文；找不到返回空串。"""
    m = _THINGS_SECTION_RE.search(text or "")
    return m.group(1) if m else ""


def _alias_pattern(aliases: list[str]) -> re.Pattern:
    """把别名列表编译成一个不区分大小写的正则（长词优先，避免被短词截断）。"""
    ordered = sorted(aliases, key=len, reverse=True)
    return re.compile("|".join(re.escape(a) for a in ordered), re.I)


def _reps_near(line: str, match: re.Match) -> int | None:
    """在动作关键词附近找「次数」。找不到返回 None。

    两级优先：先看「数字+个/次/下」这种带量词的写法，再看裸数字。这样能避开
    「俯卧撑一组20个」里的「一」、「一共20个」里的「一」被当成次数。
    两侧都看，取离关键词最近的那个。
    """
    start, end = match.span()
    before, after = line[:start], line[end:]

    for pattern in (_COUNTED_RE, _NUM_ALL):
        hits: list[tuple[int, int]] = []
        for m in pattern.finditer(before):
            gap = len(before) - m.end()      # 距关键词的字符数
            n = cn_to_int(m.group(1))
            if n is not None and 0 <= gap <= _MAX_GAP:
                hits.append((gap, n))
        for m in pattern.finditer(after):
            gap = m.start()
            n = cn_to_int(m.group(1))
            if n is not None and gap <= _MAX_GAP:
                hits.append((gap, n))
        if hits:
            hits.sort(key=lambda h: h[0])
            return hits[0][1]
    return None


def _sets_in_line(line: str) -> int | None:
    """读「N 组」里的组数；没写返回 None。"""
    m = _SET_RE.search(line)
    return cn_to_int(m.group(1)) if m else None


def _volume_in_line(line: str, pattern: re.Pattern, spec: dict,
                    rules: dict) -> tuple[int, int, str] | None:
    """从一行里读出 (次数, 组数, 原始片段)。识别不出动作则返回 None。"""
    stripped = _LINE_MARKER_RE.sub("", line.strip())
    m = pattern.search(stripped)
    if not m:
        return None

    # 1) 「A * B」写法：A = 每组次数，B = 组数
    sr = _SETS_REPS_RE.search(stripped)
    if sr:
        each = cn_to_int(sr.group(1))
        sets = cn_to_int(sr.group(2))
        if each and sets and each * sets <= rules["max_reps"]:
            return each * sets, sets, sr.group(0).strip()

    # 2) 关键词附近的单个数字（次数），组数另找「N 组」
    reps = _reps_near(stripped, m)
    default = spec.get("default_reps", 20)
    if reps is None or reps <= 0 or reps > rules["max_reps"]:
        return default, _sets_in_line(stripped) or 1, f"未写数量，按默认 {default} 次估"

    return reps, _sets_in_line(stripped) or 1, f"{reps} 次"


def extract(text: str, moves: dict | None = None,
            rules: dict | None = None) -> list[dict]:
    """扫描「三件事」段落，返回命中的动作明细。

    每项：``{"move", "reps", "sets", "minutes", "source"}``。
    ``source`` 是原文里读到的数量片段，便于人工核对估算依据。
    """
    moves = moves if moves is not None else BODYWEIGHT_MOVES
    rules = rules if rules is not None else BODYWEIGHT_RULES
    body = section_body(text)
    if not body:
        return []

    entries: list[dict] = []
    for line in body.splitlines():
        if _NEGATIVE_RE.search(line):
            continue
        for move_name, spec in moves.items():
            pattern = _alias_pattern(spec["aliases"])
            got = _volume_in_line(line, pattern, spec, rules)
            if got is None:
                continue
            reps, sets, source = got
            minutes = reps / spec["per_minute"] + max(0, sets - 1) * spec["set_rest_sec"] / 60.0
            entries.append({
                "move": move_name, "reps": reps, "sets": sets,
                "minutes": round(minutes, 2), "source": source,
            })
    return entries


def estimate(text: str, moves: dict | None = None,
             rules: dict | None = None) -> tuple[int | None, str]:
    """折算运动分钟数 -> ``(分钟数, 明细说明)``；未命中返回 ``(None, "")``。

    明细形如 ``俯卧撑 100 次（10 组）｜原文「10 * 10」｜净计时 14.0min -> 记 14min``，
    把「原文依据」一起带出来，方便人工核对估算是怎么来的。
    """
    rules = rules if rules is not None else BODYWEIGHT_RULES
    entries = extract(text, moves, rules)
    if not entries:
        return None, ""

    raw = sum(e["minutes"] for e in entries)
    lo, hi = rules["min_session_min"], rules["max_session_min"]
    minutes = int(round(min(raw, hi)))
    floored = minutes < lo
    minutes = max(lo, minutes)

    parts = []
    for e in entries:
        seg = f"{e['move']} {e['reps']} 次"
        if e["sets"] > 1:
            seg += f"（{e['sets']} 组）"
        seg += f"｜原文「{e['source']}」"
        parts.append(seg)

    detail = "；".join(parts) + f"｜净计时 {round(raw, 1)}min -> 记 {minutes}min"
    if floored:
        detail += f"（触发单日下限 {lo}min）"
    return minutes, detail
