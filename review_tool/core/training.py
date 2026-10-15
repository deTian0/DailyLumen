"""训练明细纯规则：行解析 / 分钟合计 / 推荐规则所需判定。

零 I/O：禁止 sqlite3 / os / pathlib。解析「附录 · 训练明细」里的确定性行格式，
供 pipeline 入库与 reports/coach 复用；同输入永远同输出（无随机）。

行格式（路线图 M10）
--------------------
- ``名称 组×次``              → sets / reps
- ``名称 组×次 @负重``        → + load_kg
- ``名称 Nmin`` / ``N分钟``   → minutes
- ``名称 组×时长s``（如 3×60s）→ sets + 折算 minutes
- 首行 ``计划：X｜来源：Y``    → session 元信息
"""
from __future__ import annotations

import re
from statistics import mean

from ..config import BODYWEIGHT_MOVES, TRAINING_MOVES

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")

_LINE_MARKER_RE = re.compile(r"^\s*(?:[-*+>]|\d+\s*[.、)）])\s*")

_SECTION_RE = re.compile(
    r"^##[^\n]*训练明细[^\n]*$(.*?)(?=^##\s|\Z)", re.S | re.M
)

_META_RE = re.compile(
    r"计划\s*[:：]\s*(?P<plan>[^｜|\n]+)"
    r"(?:\s*[｜|]\s*来源\s*[:：]\s*(?P<source>[^\n]+))?",
    re.I,
)

_SETS_SEC_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<sets>\d+)\s*[xX×✕*]\s*(?P<sec>\d+)\s*s\s*$",
    re.I,
)
_SETS_REPS_LOAD_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<sets>\d+)\s*[xX×✕*]\s*(?P<reps>\d+)\s*"
    r"@\s*(?P<load>[\d.]+)\s*(?:kg)?\s*$",
    re.I,
)
_SETS_REPS_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<sets>\d+)\s*[xX×✕*]\s*(?P<reps>\d+)\s*$",
    re.I,
)
_MIN_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<min>[\d.]+)\s*(?:min|分钟|分)\s*$",
    re.I,
)

_SRC_MAP = {
    "练练": "lianlian",
    "lianlian": "lianlian",
    "手填": "self",
    "手动": "self",
    "自填": "self",
    "self": "self",
}


def section_body(text: str) -> str:
    """取「附录 · 训练明细」正文；找不到返回空串。"""
    m = _SECTION_RE.search(text or "")
    return m.group(1) if m else ""


def normalize_src(raw: str | None) -> str | None:
    """来源文案 → ``lianlian`` / ``self``；无法识别返回 ``None``。"""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    # 先精确再包含
    for cn, code in _SRC_MAP.items():
        if key == cn.lower() or cn.lower() in key:
            return code
    return None


def resolve_move(name: str, moves: dict | None = None) -> tuple[str, str, dict | None]:
    """动作名 → ``(item_key, 展示名, spec或None)``。

    在 ``TRAINING_MOVES`` 里按 aliases 最长优先匹配；未命中时
    ``item_key`` 用展示名本身（保证主键稳定、可重建）。
    """
    moves = moves if moves is not None else TRAINING_MOVES
    raw = str(name or "").strip()
    if not raw:
        return "unknown", "unknown", None

    best: tuple[int, str, dict] | None = None
    for key, spec in moves.items():
        aliases = list(spec.get("aliases") or [key])
        for alias in aliases:
            if not alias:
                continue
            # 整段相等，或名称以 alias 开头/结尾（容纳「杠铃卧推」）
            if raw == alias or alias in raw:
                score = len(alias)
                if best is None or score > best[0]:
                    best = (score, key, spec)
    if best is not None:
        key, spec = best[1], best[2]
        return key, key, spec
    return raw, raw, None


def parse_meta_line(line: str) -> dict | None:
    """解析 ``计划：A-胸背｜来源：练练``；非元信息行返回 ``None``。"""
    stripped = _LINE_MARKER_RE.sub("", (line or "").strip()).translate(_FULLWIDTH)
    if not stripped:
        return None
    m = _META_RE.search(stripped)
    if not m:
        return None
    plan = (m.group("plan") or "").strip() or None
    src = normalize_src(m.group("source"))
    return {"plan_name": plan, "src": src}


def parse_item_line(line: str, moves: dict | None = None) -> dict | None:
    """解析一条动作明细；无法识别返回 ``None``（含元信息行）。"""
    moves = moves if moves is not None else TRAINING_MOVES
    stripped = _LINE_MARKER_RE.sub("", (line or "").strip()).translate(_FULLWIDTH)
    if not stripped:
        return None
    if parse_meta_line(stripped) is not None:
        return None

    sets = reps = minutes = load_kg = None
    name_raw = None

    m = _SETS_SEC_RE.match(stripped)
    if m:
        name_raw = m.group("name").strip()
        sets = int(m.group("sets"))
        sec = int(m.group("sec"))
        minutes = round(sets * sec / 60.0, 2)
    else:
        m = _SETS_REPS_LOAD_RE.match(stripped)
        if m:
            name_raw = m.group("name").strip()
            sets = int(m.group("sets"))
            reps = int(m.group("reps"))
            load_kg = float(m.group("load"))
        else:
            m = _SETS_REPS_RE.match(stripped)
            if m:
                name_raw = m.group("name").strip()
                sets = int(m.group("sets"))
                reps = int(m.group("reps"))
            else:
                m = _MIN_RE.match(stripped)
                if m:
                    name_raw = m.group("name").strip()
                    minutes = float(m.group("min"))
                else:
                    return None

    item_key, label, spec = resolve_move(name_raw, moves)
    # 组×次且无显式 minutes：若目录里有折算参数则估分钟
    if minutes is None and sets is not None and reps is not None:
        minutes = _estimate_sets_reps_minutes(sets, reps, item_key, spec)

    return {
        "item_key": item_key,
        "item": label,
        "sets": sets,
        "reps": reps,
        "minutes": minutes,
        "load_kg": load_kg,
        "body_part": (spec or {}).get("body_part"),
        "raw": stripped,
    }


def _estimate_sets_reps_minutes(
    sets: int, reps: int, item_key: str, spec: dict | None
) -> float | None:
    """组×次 → 分钟；优先 TRAINING_MOVES，其次 BODYWEIGHT_MOVES。"""
    bw = None
    if spec and spec.get("per_minute"):
        bw = spec
    elif item_key in BODYWEIGHT_MOVES:
        bw = BODYWEIGHT_MOVES[item_key]
    if bw and bw.get("per_minute"):
        total_reps = sets * reps
        rest = max(0, sets - 1) * float(bw.get("set_rest_sec") or 0) / 60.0
        return round(total_reps / float(bw["per_minute"]) + rest, 2)
    if spec and spec.get("default_set_min"):
        return round(sets * float(spec["default_set_min"]), 2)
    return None


def parse_section(
    text: str,
    *,
    session_key: str = "main",
    moves: dict | None = None,
) -> dict | None:
    """解析全文中的训练明细章节 → session dict；无章节返回 ``None``。

    返回::

        {
          "session_key": "main",
          "plan_name": "A-胸背" | None,
          "src": "lianlian" | "self" | None,
          "items": [...],
          "total_min": int | None,
        }
    """
    body = section_body(text)
    if not body.strip():
        return None

    plan_name = None
    src = None
    items: list[dict] = []
    for line in body.splitlines():
        meta = parse_meta_line(line)
        if meta is not None:
            if meta.get("plan_name"):
                plan_name = meta["plan_name"]
            if meta.get("src"):
                src = meta["src"]
            continue
        item = parse_item_line(line, moves)
        if item is not None:
            items.append(item)

    if plan_name is None and src is None and not items:
        return None

    total = sum_minutes(items)
    return {
        "session_key": session_key,
        "plan_name": plan_name,
        "src": src,
        "items": items,
        "total_min": total,
    }


def sum_minutes(items: list[dict]) -> int | None:
    """明细合计分钟（有 minutes 的项求和，四舍五入为 int）；全空返回 ``None``。"""
    vals = [float(i["minutes"]) for i in items if i.get("minutes") is not None]
    if not vals:
        return None
    return int(round(sum(vals)))


def volume(sets: int | None, reps: int | None) -> int | None:
    """组×次体积；缺任一返回 ``None``。"""
    if sets is None or reps is None:
        return None
    return int(sets) * int(reps)


def volume_stable(volumes: list[int | float], *, max_cv: float = 0.10) -> bool:
    """近 N 次体积是否稳定（变异系数 ≤ max_cv）；样本 <2 视为不稳定。"""
    vals = [float(v) for v in volumes if v is not None and float(v) > 0]
    if len(vals) < 2:
        return False
    avg = mean(vals)
    if avg == 0:
        return False
    # 总体标准差 / 均值
    var = sum((v - avg) ** 2 for v in vals) / len(vals)
    cv = (var ** 0.5) / avg
    return cv <= max_cv


def suggest_progression(
    volumes: list[int | float],
    *,
    max_cv: float = 0.10,
    add_sets: int = 1,
    add_reps: int = 2,
) -> dict:
    """渐进建议：稳定 → 加组或加次；波动大 → 维持。

    返回 ``{"action": "increase"|"hold", "add_sets", "add_reps", "mean", "cv_ok", "evidence"}``。
    """
    vals = [float(v) for v in volumes if v is not None]
    ok = volume_stable(vals, max_cv=max_cv)
    avg = round(mean(vals), 1) if vals else None
    evidence = f"近{len(vals)}次体积={vals}，均值={avg}，稳定阈值cv≤{max_cv}→{ok}"
    if ok:
        return {
            "action": "increase",
            "add_sets": add_sets,
            "add_reps": add_reps,
            "mean": avg,
            "cv_ok": True,
            "evidence": evidence,
        }
    return {
        "action": "hold",
        "add_sets": 0,
        "add_reps": 0,
        "mean": avg,
        "cv_ok": False,
        "evidence": evidence,
    }


def consecutive_training_days(dates: list[str]) -> int:
    """按日期升序，从末尾起连续训练天数（相邻差 1 天）。空列表返回 0。"""
    if not dates:
        return 0
    uniq = sorted(set(dates))
    run = 1
    for i in range(len(uniq) - 1, 0, -1):
        prev = uniq[i - 1]
        cur = uniq[i]
        # YYYY-MM-DD 可直接按 ordinal 差
        from datetime import date as _date
        d0 = _date.fromisoformat(prev)
        d1 = _date.fromisoformat(cur)
        if (d1 - d0).days == 1:
            run += 1
        else:
            break
    return run


def needs_recovery(dates: list[str], *, max_consecutive: int = 3) -> dict:
    """连续训练 ≥ max_consecutive → 建议插入恢复日。"""
    n = consecutive_training_days(dates)
    hit = n >= max_consecutive
    return {
        "needed": hit,
        "consecutive": n,
        "max_consecutive": max_consecutive,
        "evidence": f"连续训练 {n} 天（阈值 ≥{max_consecutive}）→ {'需恢复' if hit else '可继续'}",
    }


def body_part_conflict(
    recent: list[tuple[str, str]],
    candidate_part: str | None,
    *,
    hours: int = 48,
) -> dict:
    """同一 body_part 在 ``hours`` 内是否有历史记录（供 coach 再精算间隔）。

    ``recent`` = ``[(iso_date, body_part), ...]``，按时间升序。
    """
    if not candidate_part:
        return {"conflict": False, "evidence": "无部位信息，跳过轮换检查"}
    hits = [(d, p) for d, p in recent if p == candidate_part]
    if not hits:
        return {
            "conflict": False,
            "evidence": f"部位 {candidate_part} 近窗无记录",
        }
    last_date, _ = hits[-1]
    return {
        "conflict": True,  # 有同部位历史；coach 再用 as_of 精算
        "last_date": last_date,
        "body_part": candidate_part,
        "hours_window": hours,
        "evidence": f"部位 {candidate_part} 最近一次在 {last_date}",
    }


def hours_between(d0: str, d1: str) -> float:
    """两日历日之间的小时数（按 00:00 计，整天 ×24）。"""
    from datetime import date as _date
    a = _date.fromisoformat(d0)
    b = _date.fromisoformat(d1)
    return abs((b - a).days) * 24.0


def week_completion_ok(
    completed: int,
    planned: int,
    *,
    min_ratio: float = 0.8,
) -> dict:
    """本周课次是否达加量门槛。"""
    if planned <= 0:
        ratio = 1.0 if completed > 0 else 0.0
        ok = completed > 0
    else:
        ratio = completed / planned
        ok = ratio >= min_ratio
    return {
        "ok": ok,
        "completed": completed,
        "planned": planned,
        "ratio": round(ratio, 3),
        "min_ratio": min_ratio,
        "evidence": (
            f"本周完成 {completed}/{planned} 课"
            f"（比率 {round(ratio, 3)}，门槛 {min_ratio}）→ "
            f"{'可加量' if ok else '先补次数'}"
        ),
    }
