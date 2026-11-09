"""ClickUp 习惯代勾：受控勾选「练练健身」等 HABITS 元任务（B15 / v1.83.0）。

用法:
    python -m review_tool clickup-habit --habit lianlian              # 默认今天，dry-run
    python -m review_tool clickup-habit --habit lianlian --date D     # 指定归属日
    python -m review_tool clickup-habit --habit lianlian --date D --apply
    python -m review_tool clickup-habit --habit lianlian --yes         # --yes ≡ --apply

产品口径（写死）
----------------
1. **习惯 Continuity 以 ClickUp 为主**：本命令只 PUT ClickUp 任务为 complete；
   **不**直接写 ``habit_logs``（入库仍走既有 ``habits --sync``）。
2. **训练事实仍以练练为准**：不写 ``training_*`` / 不改 ``training_day`` / 不动四维分。
3. **禁止静默自动勾**：须用户 / agent 显式触发；默认 dry-run，``--apply``/``--yes`` 才写。
4. **禁止 ClickUp 反推训练表**。
5. 文案明示：这是**习惯勾选**，≠ 训练明细入库。
6. 练练当日 ``completed`` 仅作旁证提示（不强制）；缺旁证仍允许显式勾。

退出码：0 = 成功 / 幂等跳过 / dry-run；1 = 网络或写后回读失败；
2 = 用法 / 缺凭据 / 任务定位失败 / 习惯 key 不在白名单。
"""
from __future__ import annotations

import datetime
import json
import sys
import urllib.error

from ..config import CLICKUP_TIMEOUT_S, HABITS_LIST_ID
from ..core.habits import habit_by_key
from ..integrations.clickup import Client, CredError, fetch_tasks, load_creds
from ..integrations.flags import IntegrationDisabled, require_enabled
from ..integrations.last_error import record_integration_error
from .clickup import completion_day, day_of, select_habits
from .clickup_sync import _client_from_transport, is_closed, mark_complete

USAGE = (
    "clickup-habit --habit lianlian [--date YYYY-MM-DD] "
    "[--apply|--yes] [--dry-run] [--stdout] [--list ID]"
)

# B15 窄通道：首期只开放「练练健身」
ALLOWED_HABIT_KEYS = frozenset({"lianlian"})

DISCLAIMER = (
    "⚠️ 这是 ClickUp「习惯与打卡」勾选（Continuity），"
    "≠ 练练训练明细入库，也不写 habit_logs / training_* / 四维分。"
)


def find_habit_task_for_day(
    tasks: list[dict],
    habit_key: str,
    day: str,
) -> dict:
    """按日定位某 HABITS key 对应的 ClickUp 任务。

    优先级：
    1. 已完成且 ``completion_day`` == day → 幂等（含次日补勾回拨）；
    2. 未完成且 ``due_date`` 归日 == day；
    3. 任意未完成的同名习惯任务（当前 recurring 实例）；
    4. 找不到 → ValueError。
    """
    selected = [h for h in select_habits(tasks) if h["habit_key"] == habit_key]
    if not selected:
        raise ValueError(f"在习惯 list 里找不到 key={habit_key!r} 的任务")

    for h in selected:
        t = h["task"]
        if t.get("date_closed") and completion_day(t) == day:
            return t

    due_open = []
    any_open = []
    for h in selected:
        t = h["task"]
        if is_closed(t):
            continue
        any_open.append(t)
        due = t.get("due_date")
        if due and day_of(due) == day:
            due_open.append(t)
    if due_open:
        return sorted(due_open, key=lambda t: int(t.get("due_date") or 0))[0]
    if any_open:
        return any_open[0]
    raise ValueError(
        f"找不到 {day} 可勾的「{habit_key}」任务"
        "（无当日完成实例，也无未完成 recurring）"
    )


def keepstrong_completed_hint(
    day: str,
    *,
    ks_client=None,
    env=None,
) -> dict:
    """只读旁证：当日练练是否有 ``status==completed``。失败不抛，返回结构化提示。"""
    out = {
        "checked": False,
        "completed": None,
        "count": 0,
        "message": "练练旁证：未检查",
    }
    try:
        from ..integrations.flags import is_enabled
        if not is_enabled("keepstrong"):
            out["message"] = "练练旁证：集成已关闭（不强制）"
            return out
    except Exception:  # pragma: no cover - 防御
        pass

    try:
        if ks_client is None:
            from ..integrations.keepstrong import Client as KsClient
            from ..integrations.keepstrong import CredError as KsCredError
            from ..integrations.keepstrong import load_api_key

            try:
                key = load_api_key(env=env)
            except KsCredError:
                out["message"] = "练练旁证：无凭据（不强制，仍可显式勾选）"
                return out
            ks_client = KsClient(key)
        records = ks_client.iter_training_records(day, day)
        n = len(records or [])
        out["checked"] = True
        out["count"] = n
        out["completed"] = n > 0
        if n > 0:
            out["message"] = f"练练旁证：当日有 {n} 条 completed 训练（仅提示，非门槛）"
        else:
            out["message"] = (
                "练练旁证：当日无 completed 训练（仍允许显式勾选；"
                "场景含 agent 口述）"
            )
    except Exception as e:  # noqa: BLE001 — 旁证失败不得阻断主流程
        out["message"] = f"练练旁证：检查失败（{type(e).__name__}，不强制）"
    return out


def plan_habit(
    day: str,
    habit_key: str,
    *,
    list_id: str,
    key: str,
    client: Client | None = None,
    fetch=None,
    timeout: float = CLICKUP_TIMEOUT_S,
    ks_client=None,
    env=None,
    check_keepstrong: bool = True,
) -> dict:
    """只读规划：定位任务 + 可选练练旁证。不写 ClickUp / 不写库。"""
    spec = habit_by_key(habit_key)
    if spec is None:
        raise ValueError(f"未知习惯 key: {habit_key}")
    if habit_key not in ALLOWED_HABIT_KEYS:
        raise ValueError(
            f"B15 窄通道仅允许 {sorted(ALLOWED_HABIT_KEYS)}，收到: {habit_key}"
        )

    cu = _client_from_transport(key, client=client, fetch=fetch, timeout=timeout)
    if fetch is not None and client is None:
        tasks = fetch_tasks(list_id, key, fetch=fetch, timeout=timeout)
    else:
        tasks = cu.list_tasks(list_id)

    task = find_habit_task_for_day(tasks, habit_key, day)
    tid = str(task.get("id") or "")
    # find_* 仅在 completion_day==day 时返回已关闭任务，否则为未完成 recurring
    closed_for_day = is_closed(task)
    action = "skip_closed" if closed_for_day else "would_complete"

    hint = (
        keepstrong_completed_hint(day, ks_client=ks_client, env=env)
        if check_keepstrong else
        {"checked": False, "completed": None, "count": 0,
         "message": "练练旁证：已跳过检查"}
    )
    return {
        "day": day,
        "habit_key": habit_key,
        "label": spec["label"],
        "task_id": tid,
        "name": (task.get("name") or "").strip(),
        "closed": closed_for_day,
        "action": action,
        "keepstrong_hint": hint,
        "disclaimer": DISCLAIMER,
        "task": task,
    }


def _format_plan_msg(planned: dict, *, mode: str) -> str:
    hint = (planned.get("keepstrong_hint") or {}).get("message") or ""
    base = (
        f"[{mode}] {planned['day']} · 习惯「{planned['label']}」"
        f"（key={planned['habit_key']}）· 任务「{planned['name']}」"
        f"（{planned['task_id']}）"
    )
    if planned["action"] == "skip_closed":
        body = f"{base} 当日已是完成态 —— 幂等跳过，不写。"
    elif mode == "dry-run":
        body = f"{base} 将标为 complete。加 --apply / --yes 才真写。"
    else:
        body = f"{base} 已标完成，回读校验通过。"
    return f"{DISCLAIMER}\n{body}\n{hint}"


def run_habit(
    day: str,
    habit_key: str,
    *,
    apply: bool,
    list_id: str | None = None,
    key: str = "",
    client: Client | None = None,
    fetch=None,
    put=None,
    env=None,
    creds_path: str | None = None,
    timeout: float = CLICKUP_TIMEOUT_S,
    ks_client=None,
    check_keepstrong: bool = True,
    as_json: bool = False,
) -> tuple[int, str]:
    """执行一次代勾。返回 ``(exit_code, message)``。不写 habit_logs。"""
    lid = list_id or HABITS_LIST_ID
    try:
        if not key:
            key, _team = load_creds(env=env, path=creds_path)
    except CredError as e:
        return 2, f"凭据错误: {e}"

    try:
        if habit_key not in ALLOWED_HABIT_KEYS:
            return 2, (
                f"参数错误: B15 窄通道仅允许习惯 "
                f"{sorted(ALLOWED_HABIT_KEYS)}，收到: {habit_key}"
            )
        if habit_by_key(habit_key) is None:
            return 2, f"参数错误: 未知习惯 key: {habit_key}"
    except Exception as e:  # pragma: no cover
        return 2, f"参数错误: {e}"

    cu = _client_from_transport(
        key, client=client, put=put, fetch=fetch, timeout=timeout
    )
    try:
        planned = plan_habit(
            day,
            habit_key,
            list_id=lid,
            key=key,
            client=cu if client is not None else None,
            fetch=fetch,
            timeout=timeout,
            ks_client=ks_client,
            env=env,
            check_keepstrong=check_keepstrong,
        )
    except ValueError as e:
        return 2, f"任务定位失败: {e}"
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        if str(code) == "429":
            record_integration_error(
                "clickup", command="clickup-habit", error_kind="HTTPError",
                error_summary="取数失败: HTTP 429 rate_limited", http_code=code,
            )
            return 1, "取数失败: HTTP 429（rate_limited，请稍后再试）"
        hint = "（401/403 = token 失效或权限不足）" if str(code) in ("401", "403") else ""
        record_integration_error(
            "clickup", command="clickup-habit", error_kind="HTTPError",
            error_summary=f"取数失败: HTTP {code}", http_code=code,
        )
        return 1, f"取数失败: HTTP {code} {hint}"
    except urllib.error.URLError as e:
        record_integration_error(
            "clickup", command="clickup-habit", error_kind="URLError",
            error_summary=str(e.reason)[:200],
        )
        return 1, f"取数失败: 网络不可达 —— {e.reason}"

    mode = "apply" if apply else "dry-run"
    if planned["action"] == "skip_closed":
        msg = _format_plan_msg(planned, mode=mode)
        if as_json:
            return 0, json.dumps({
                "ok": True, "mode": mode, "action": "skip_closed",
                "planned": {k: v for k, v in planned.items() if k != "task"},
                "message": msg,
            }, ensure_ascii=False)
        return 0, msg

    if not apply:
        msg = _format_plan_msg(planned, mode="dry-run")
        if as_json:
            return 0, json.dumps({
                "ok": True, "mode": "dry-run", "action": "would_complete",
                "planned": {k: v for k, v in planned.items() if k != "task"},
                "message": msg,
            }, ensure_ascii=False)
        return 0, msg

    tid = planned["task_id"]
    try:
        mark_complete(
            tid, key, client=cu, put=put, fetch=fetch, timeout=timeout
        )
    except RuntimeError as e:
        record_integration_error(
            "clickup", command="clickup-habit", error_kind="RuntimeError",
            error_summary=str(e)[:200],
        )
        return 1, f"回写失败: {e}"
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        if str(code) == "429":
            record_integration_error(
                "clickup", command="clickup-habit", error_kind="HTTPError",
                error_summary="回写失败: HTTP 429 rate_limited", http_code=code,
            )
            return 1, "回写失败: HTTP 429（rate_limited，请稍后再试）"
        record_integration_error(
            "clickup", command="clickup-habit", error_kind="HTTPError",
            error_summary=f"回写失败: HTTP {code}", http_code=code,
        )
        return 1, f"回写失败: HTTP {code}"
    except urllib.error.URLError as e:
        record_integration_error(
            "clickup", command="clickup-habit", error_kind="URLError",
            error_summary=str(e.reason)[:200],
        )
        return 1, f"回写失败: 网络不可达 —— {e.reason}"

    msg = _format_plan_msg(planned, mode="apply")
    if as_json:
        return 0, json.dumps({
            "ok": True, "mode": "apply", "action": "completed",
            "planned": {k: v for k, v in planned.items() if k != "task"},
            "message": msg,
        }, ensure_ascii=False)
    return 0, msg


def _parse(argv: list[str]) -> tuple[str, str, bool, str | None, bool]:
    """返回 ``(day, habit_key, apply, list_id, as_json)``。"""
    day, habit_key, apply, list_id, as_json = "", "", False, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--apply", "--yes"):
            apply = True
        elif a == "--dry-run":
            apply = False
        elif a == "--stdout":
            as_json = True
        elif a == "--habit" or a.startswith("--habit="):
            if a.startswith("--habit="):
                habit_key = a.split("=", 1)[1].strip()
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--habit 需要跟一个 key（如 lianlian）")
                habit_key = argv[i].strip()
            if not habit_key:
                raise ValueError("--habit 不能为空")
        elif a == "--date" or a.startswith("--date="):
            if a.startswith("--date="):
                day = a.split("=", 1)[1].strip()
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--date 需要跟 YYYY-MM-DD")
                day = argv[i].strip()
        elif a == "--list" or a.startswith("--list="):
            if a.startswith("--list="):
                list_id = a.split("=", 1)[1].strip()
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--list 需要跟一个 list id")
                list_id = argv[i].strip()
            if not list_id:
                raise ValueError("--list 不能为空")
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            # 兼容位置日期：clickup-habit --habit lianlian 2026-11-08
            if day:
                raise ValueError(f"多余的参数: {a}")
            day = a
        i += 1

    if not habit_key:
        raise ValueError("必须指定 --habit（B15 仅开放 lianlian）")
    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    else:
        day = datetime.date.today().isoformat()
    return day, habit_key, apply, list_id, as_json


def main(
    argv: list[str] | None = None,
    *,
    fetch=None,
    put=None,
    env=None,
    ks_client=None,
) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print(DISCLAIMER)
        return 0

    try:
        require_enabled("clickup")
    except IntegrationDisabled as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        day, habit_key, apply, list_id, as_json = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    rc, msg = run_habit(
        day, habit_key, apply=apply, list_id=list_id,
        fetch=fetch, put=put, env=env, ks_client=ks_client, as_json=as_json,
    )
    stream = sys.stdout if rc == 0 else sys.stderr
    print(msg, file=stream)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
