"""学习记录纯规则：主题归一化 + 间隔重复队列推算 + md 附录解析。

零 I/O：禁止 sqlite3 / os / pathlib。``review_queue`` 的 stage / due_date
必须能从 ``learning_logs`` 完全重建（硬验收）；同输入永远同输出。

附录格式（「附录 · 学习记录」）
--------------------------------
- ``主题：X｜时长：45min｜来源：self｜产出：笔记``
- 字段可缺；至少要有主题。来源 ∈ {clickup, self, course}（中文别名见下）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..config import LEARNING_TOPICS, SPACED_REPEAT
from .tracks import normalize_item
from .util import is_blockquote_prose, slugify, to_float

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")

_LINE_MARKER_RE = re.compile(r"^\s*(?:[-*+>]|\d+\s*[.、)）])\s*")

_SECTION_RE = re.compile(
    r"^##[^\n]*学习记录[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M
)

_SRC_MAP = {
    "clickup": "clickup",
    "cu": "clickup",
    "self": "self",
    "手填": "self",
    "手动": "self",
    "自填": "self",
    "course": "course",
    "课程": "course",
    "成长课": "course",
    "课": "course",
}

# 行内键值：主题 / 时长 / 来源 / 产出（中英冒号、全角竖线）
_FIELD_RE = re.compile(
    r"(?P<key>主题|topic|时长|minutes?|min|来源|src|source|产出|artifact|产物)"
    r"\s*[:：]\s*(?P<val>[^｜|\n]+)",
    re.I,
)


def section_body(text: str) -> str:
    """取「附录 · 学习记录」正文；找不到返回空串。"""
    m = _SECTION_RE.search(text or "")
    return m.group(1) if m else ""


def normalize_src(raw: str | None) -> str | None:
    """来源文案 → ``clickup`` / ``self`` / ``course``；无法识别返回 None。"""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    if key in _SRC_MAP:
        return _SRC_MAP[key]
    for cn, code in _SRC_MAP.items():
        if cn.lower() in key or key in cn.lower():
            return code
    return None


def resolve_topic(
    text: str, *, topics: list[dict] | None = None
) -> dict:
    """主题文案 → ``{key, label}``。

    先走 ``LEARNING_TOPICS`` 目录（aliases 最长优先）；未命中则
    ``key=slugify(text)``、``label=原文``，保证主键稳定可重建。
    """
    catalog = topics if topics is not None else LEARNING_TOPICS
    raw = str(text or "").strip()
    if not raw:
        return {"key": "unknown", "label": "unknown"}
    hit = normalize_item(raw, catalog) if catalog else None
    if hit is not None:
        return {"key": hit["key"], "label": hit.get("label") or hit["key"]}
    return {"key": slugify(raw), "label": raw}


def intervals_from_config(cfg: dict | None = None) -> list[int]:
    """取出间隔天数列表；非法配置回退到默认 ``[1, 3, 7, 16]``。"""
    src = cfg if cfg is not None else SPACED_REPEAT
    raw = list((src or {}).get("intervals") or [1, 3, 7, 16])
    out = [int(x) for x in raw if int(x) > 0]
    return out or [1, 3, 7, 16]


def stage_from_count(n: int, intervals: list[int] | None = None) -> int:
    """学习次数 → 队列 stage（0-based，封顶在最后一个间隔）。

    n≤0 → 0；否则 ``min(n - 1, len(intervals) - 1)``。
    """
    iv = intervals if intervals is not None else intervals_from_config()
    if n <= 0 or not iv:
        return 0
    return min(n - 1, len(iv) - 1)


def due_from_last(last_seen: str, stage: int,
                  intervals: list[int] | None = None) -> str:
    """``last_seen + intervals[stage]`` → ``YYYY-MM-DD``。"""
    iv = intervals if intervals is not None else intervals_from_config()
    days = iv[min(max(stage, 0), len(iv) - 1)]
    base = datetime.strptime(last_seen, "%Y-%m-%d")
    return (base + timedelta(days=days)).strftime("%Y-%m-%d")


def due_status(as_of: str, due_date: str) -> str:
    """相对锚点日的状态：``pending`` / ``due`` / ``overdue``。"""
    if as_of < due_date:
        return "pending"
    if as_of == due_date:
        return "due"
    return "overdue"


def queue_entry_from_dates(
    topic_key: str,
    topic: str,
    dates: list[str],
    *,
    intervals: list[int] | None = None,
) -> dict | None:
    """单主题的历史学习日 → 一条 ``review_queue`` 行；无日期返回 None。

    ``note`` 恒为 None（派生队列不存无法重建的状态）。
    """
    if not dates:
        return None
    iv = intervals if intervals is not None else intervals_from_config()
    uniq = sorted({d for d in dates if d})
    if not uniq:
        return None
    n = len(uniq)
    stage = stage_from_count(n, iv)
    last_seen = uniq[-1]
    return {
        "topic_key": topic_key,
        "topic": topic,
        "stage": stage,
        "due_date": due_from_last(last_seen, stage, iv),
        "last_seen": last_seen,
        "note": None,
    }


def build_queue(
    logs: list[dict],
    *,
    intervals: list[int] | None = None,
) -> list[dict]:
    """从 ``learning_logs`` 行完全重建 ``review_queue``（按 topic_key 排序）。

    每行需含 ``date`` / ``topic_key`` / ``topic``。同主题取最近一次的展示名。
    """
    iv = intervals if intervals is not None else intervals_from_config()
    buckets: dict[str, dict] = {}
    for r in logs:
        key = r.get("topic_key")
        date = r.get("date")
        if not key or not date:
            continue
        b = buckets.setdefault(key, {"topic": r.get("topic") or key, "dates": []})
        b["dates"].append(date)
        if r.get("topic"):
            b["topic"] = r["topic"]
    out: list[dict] = []
    for key in sorted(buckets):
        entry = queue_entry_from_dates(
            key, buckets[key]["topic"], buckets[key]["dates"], intervals=iv
        )
        if entry is not None:
            out.append(entry)
    return out


def parse_item_line(line: str, *, topics: list[dict] | None = None) -> dict | None:
    """解析一条学习记录行；无法识别返回 None。"""
    stripped = _LINE_MARKER_RE.sub("", (line or "").strip()).translate(_FULLWIDTH)
    if not stripped:
        return None

    fields: dict[str, str] = {}
    for m in _FIELD_RE.finditer(stripped):
        k = m.group("key").lower()
        v = (m.group("val") or "").strip()
        if k in ("主题", "topic"):
            fields["topic"] = v
        elif k in ("时长", "minute", "minutes", "min"):
            fields["minutes_raw"] = v
        elif k in ("来源", "src", "source"):
            fields["src_raw"] = v
        elif k in ("产出", "artifact", "产物"):
            fields["artifact"] = v

    topic_raw = fields.get("topic")
    if not topic_raw:
        # 退化：整行当主题（去掉已知后缀片段）
        topic_raw = stripped.split("｜")[0].split("|")[0].strip()
        if not topic_raw or "：" in topic_raw or ":" in topic_raw:
            # 仍像键值行但没主题 → 放弃
            if "主题" not in stripped and "topic" not in stripped.lower():
                return None
            return None

    resolved = resolve_topic(topic_raw, topics=topics)
    minutes = to_float(fields["minutes_raw"]) if "minutes_raw" in fields else None
    src = normalize_src(fields.get("src_raw"))
    artifact = fields.get("artifact")
    return {
        "topic_key": resolved["key"],
        "topic": resolved["label"],
        "minutes": minutes,
        "src": src,
        "artifact": artifact,
    }


def parse_section(
    text: str, *, topics: list[dict] | None = None
) -> list[dict] | None:
    """解析「附录 · 学习记录」→ 条目列表；无章节返回 None。"""
    body = section_body(text)
    if not body.strip():
        # 章节标题存在但为空 → 仍算有侧车（空列表），便于 ingest 幂等
        if _SECTION_RE.search(text or ""):
            return []
        return None
    items: list[dict] = []
    seen: set[str] = set()
    for line in body.splitlines():
        if is_blockquote_prose(line):
            continue
        item = parse_item_line(line, topics=topics)
        if item is None:
            continue
        key = item["topic_key"]
        if key in seen:
            # 同日同主题后写覆盖前写（确定性：最后一次胜出）
            items = [x for x in items if x["topic_key"] != key]
        seen.add(key)
        items.append(item)
    return items


def week_rollup(logs: list[dict]) -> dict:
    """本周学习汇总：主题 / 投入分钟 / 产出物。

    返回 ``{"topics": [...], "total_minutes": float|None, "artifacts": [...],
    "days": n, "entries": n}``。
    """
    by_topic: dict[str, dict] = {}
    artifacts: list[str] = []
    total = 0.0
    has_min = False
    dates: set[str] = set()
    for r in logs:
        key = r.get("topic_key") or "unknown"
        b = by_topic.setdefault(key, {
            "topic_key": key,
            "topic": r.get("topic") or key,
            "minutes": 0.0,
            "entries": 0,
            "has_min": False,
        })
        b["entries"] += 1
        if r.get("topic"):
            b["topic"] = r["topic"]
        m = r.get("minutes")
        if m is not None:
            b["minutes"] += float(m)
            b["has_min"] = True
            total += float(m)
            has_min = True
        if r.get("date"):
            dates.add(r["date"])
        art = r.get("artifact")
        if art:
            artifacts.append(str(art))
    topics = sorted(by_topic.values(), key=lambda x: (-x["entries"], x["topic_key"]))
    for t in topics:
        if not t["has_min"]:
            t["minutes"] = None
        else:
            t["minutes"] = round(t["minutes"], 2)
        del t["has_min"]
    return {
        "topics": topics,
        "total_minutes": round(total, 2) if has_min else None,
        "days": sorted(dates),
        "entries": sum(t["entries"] for t in topics),
        "artifacts": artifacts,
    }
