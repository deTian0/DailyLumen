"""ClickUp 完成任务名的解析（零 I/O）。

任务的命名约定是**工时流水**，不是「待办标题」::

    李扬-2h-排查开发环境和生产环境 502 问题        # 姓名-工时-描述
    2h-更新及协调平果铝厂端站点配置                # 工时-描述（本人，无姓名前缀）
    常哲-xh-知识库底座需求会                       # 工时写不出（xh）但仍是流水

这个约定比「待办」有用得多：**工时是可直接比对的数字**。因此本模块只做两件事：
把名字拆成 ``(owner, minutes, subject)``，以及判断这条记录属不属于本人。

⛔ 明确不做：**不把承诺文本和任务描述做语义匹配**。
理由（2026-10-21 实测）：本人工时记录只有 2026-08-20 之前那批，
承诺对账的 79 天窗口（8-10 月）与它几乎零重叠；硬做词重叠匹配，
产出的是「猜出来的兑现率」，比不做更糟。判定只用**工时这个数**，
判不了就照实说判不了。
"""
from __future__ import annotations

import re

# 工时段：`2h` / `0.5h` / `2.5h` / `10h`；`xh` 这种写不出的也认，但解析为 None
_HOUR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*h$", re.I)
_HOUR_UNKNOWN_RE = re.compile(r"^[xX×?？]+h$", re.I)

# 分隔符：任务名用半角 `-`，但手滑写全角 `－`／`—` 的也见过
_SEP = "-－—"

# 段数上限：描述里可能还有 `-`（如「修复-a-b 问题」），只切前两刀
_MAX_SPLIT = 2


def _split(name: str) -> list[str]:
    """按第一个分隔符切，最多切两刀（保留描述里的连字符）。"""
    out: list[str] = []
    rest = (name or "").strip()
    for _ in range(_MAX_SPLIT):
        idx = min((rest.find(ch) for ch in _SEP if ch in rest), default=-1)
        if idx < 0:
            break
        out.append(rest[:idx])
        rest = rest[idx + 1:]
    out.append(rest)
    return out


def parse_hours(seg: str) -> tuple[float | None, bool]:
    """``'2.5h'`` → ``(150.0, True)``；``'xh'`` → ``(None, True)``；``'李扬'`` → ``(None, False)``。

    第二个返回值是「这段**看起来**就是工时」—— ``xh`` 是工时位但写不出数，
    这和「这段根本不是工时位」要分开，否则 ``常哲-xh-需求会`` 会被当成人名错位。
    """
    s = (seg or "").strip()
    m = _HOUR_RE.match(s)
    if m:
        return float(m.group(1)) * 60.0, True
    if _HOUR_UNKNOWN_RE.match(s):
        return None, True
    return None, False


def parse_task_name(name: str) -> dict:
    """任务名 → ``{owner, minutes, subject, hours_raw}``。

    四种形态（``minutes`` 为 ``None`` 表示**写不出或没有工时**，不是 0）：

    ==============================  =========  ==========  =============
    任务名                            owner      minutes     subject
    ==============================  =========  ==========  =============
    ``李扬-2h-排查502``               李扬        120         排查502
    ``2h-平果铝厂配置``               None        120         平果铝厂配置
    ``常哲-xh-需求会``                常哲        None        需求会
    ``随手记的一条``                  None        None        随手记的一条
    ==============================  =========  ==========  =============
    """
    raw = (name or "").strip()
    parts = _split(raw)

    if len(parts) >= 3:
        first, second = parts[0], parts[1]
        minutes, is_hour = parse_hours(second)
        if is_hour:
            # 姓名-工时-描述
            return {
                "owner": first.strip() or None,
                "minutes": minutes,
                "subject": parts[2].strip() or None,
                "hours_raw": second.strip(),
            }
        # 姓名-xh-描述 或「A-B-描述」但 B 不是工时：仍按姓名位处理
        return {
            "owner": first.strip() or None,
            "minutes": None,
            "subject": parts[2].strip() or None,
            "hours_raw": None,
        }

    if len(parts) == 2:
        minutes, is_hour = parse_hours(parts[0])
        if is_hour:
            # 工时-描述（本人，无姓名前缀）
            return {
                "owner": None,
                "minutes": minutes,
                "subject": parts[1].strip() or None,
                "hours_raw": parts[0].strip(),
            }
        return {"owner": None, "minutes": None, "subject": raw or None,
                "hours_raw": None}

    return {"owner": None, "minutes": None, "subject": raw or None, "hours_raw": None}


def is_self_task(
    task: dict,
    parsed: dict,
    *,
    self_names: tuple[str, ...] = (),
    teammates: tuple[str, ...] = (),
) -> bool:
    """是不是**本人**的记录。

    ⛔ **不看 assignee**：实测工作 list 的 704 条任务 assignee 全是本人
    （团队工时表用本人账号建，同事条目也挂在本人名下），按 assignee 判会把
    整个团队的工时都算成自己的证据。

    只看任务名的**姓名位**：

    - 命中 ``self_names``（如「梁帅」）        → True
    - 命中 ``teammates``（如「李扬」）        → False
    - 其它（无前缀 / `其他任务` 这类分类标签）→ True

    默认 True 是刻意的：无前缀条目就是本人手填的流水（实测 593 条），
    漏算自己的比错算同事的代价更大 —— 后者会直接让兑现率虚高。
    """
    owner = (parsed.get("owner") or "").strip()
    if owner:
        if any(n == owner for n in self_names if n):
            return True
        if any(n == owner for n in teammates if n):
            return False
    return True


def to_row(task: dict, list_id: str, day: str, *, self_spec: dict | None = None) -> dict:
    """ClickUp 任务 + 归属日 → ``clickup_done`` 的一行。

    ``self_spec`` 形如 ``{"self_names": (...), "teammates": (...)}``，默认从 config 取。
    """
    if self_spec is None:
        from ..config import CLICKUP_SELF_NAMES, CLICKUP_TEAMMATES

        self_spec = {"self_names": CLICKUP_SELF_NAMES, "teammates": CLICKUP_TEAMMATES}

    name = task.get("name") or ""
    parsed = parse_task_name(name)
    status = task.get("status") or {}
    return {
        "date": day,
        "task_id": str(task.get("id") or ""),
        "list_id": str(list_id),
        "name": name,
        "owner": parsed["owner"],
        "minutes": parsed["minutes"],
        "subject": parsed["subject"],
        "is_self": is_self_task(
            task,
            parsed,
            self_names=self_spec.get("self_names") or (),
            teammates=self_spec.get("teammates") or (),
        ),
        "status": status.get("status") if isinstance(status, dict) else None,
    }


def summarize(rows: list[dict]) -> dict:
    """一天的完成记录 → 汇总（报告 / doctor 用）。

    ⚠️ **不把 ``minutes`` 求和当「工作了多少小时」**。任务名里的工时是
    **任务级估算**，同一天多条可以重叠（实测 2026-10-13 十条合计 57h，
    物理上不可能）。所以这里给的是：

    - ``self_count``   本人记录条数（存在性证据，最硬）
    - ``self_max``     最长单条工时（「至少投入了这么久」的下界）
    - ``self_sum``     合计，**仅供人工参考**，不参与任何判定

    ``self_count == 0`` 时 ``self_minutes`` 为 ``None`` —— 表示那天在 ClickUp
    里没有你的记录（可能是没填），**不等于没工作**。
    """
    mine = [r for r in rows if r.get("is_self")]
    mins = [float(r["minutes"]) for r in mine if r.get("minutes") is not None]
    return {
        "count": len(rows),
        "self_count": len(mine),
        "self_max": max(mins) if mins else None,
        "self_sum": sum(mins) if mins else None,
        "self_no_hours": sum(1 for r in mine if r.get("minutes") is None),
        "subjects": [r.get("subject") or r.get("name") or "" for r in mine],
    }
