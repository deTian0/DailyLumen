"""ClickUp 回写通道：复盘已入库 → 勾「每日复盘总结」元任务（v1.7.0）。

用法:
    python -m review_tool clickup-push                 # 默认今天，dry-run
    python -m review_tool clickup-push 2026-10-12      # 指定日，只打印不写
    python -m review_tool clickup-push 2026-10-12 --apply   # 真写 + GET 回读
    python -m review_tool clickup-push --list ID       # 换 list（默认习惯与打卡）

冲突规则（写死）
----------------
1. **权威方向**：复盘库为权威 → ClickUp 为下游。永远不由 ClickUp 反推复盘。
2. **写谁**：只写 ``config.CLICKUP_REVIEW_TASK`` 定位的「每日复盘总结」元任务；
   绝不碰用户手工建的任务 / 用户手动改过的其它状态。
3. **幂等**：已 complete / closed 则跳过；不用「先清空再写」。
4. **默认安全**：默认 dry-run；只有显式 ``--apply`` 才真写。
5. **失败保守**：PUT 后 GET 回读；不符则重试一次；仍失败则非 0 退出 ——
   不信状态码（ClickUp 有「200 但静默忽略」的已知行为）。

退出码：0 = 成功 / 幂等跳过 / dry-run 预览；1 = 网络或写后回读失败；
2 = 用法 / 缺凭据 / 目标日未入库 / 任务定位失败。
"""
from __future__ import annotations

import datetime
import json
import sys
import urllib.error
import urllib.request

from ..config import CLICKUP_REVIEW_TASK, CLICKUP_TIMEOUT_S, DB_PATH
from ..storage.db import init_db
from .clickup import (
    API_BASE,
    CredError,
    fetch_tasks,
    http_get,
    load_creds,
)

USAGE = "clickup-push [YYYY-MM-DD] [--apply] [--dry-run] [--list ID] [--db PATH]"

# PUT 后回读不符时最多再写一次（合计最多 2 次 PUT）
MAX_PUT_ATTEMPTS = 2


# ------------------------------------------------------------------ 状态判定
def is_closed(task: dict) -> bool:
    """任务是否已关闭（幂等跳过 / 回读校验共用）。

    ClickUp 的 ``status`` 是对象：``{"status": "complete", "type": "closed", ...}``。
    任一条成立即视为已完成：``type == closed`` / ``status == complete`` / ``date_closed`` 非空。
    """
    if task.get("date_closed"):
        return True
    st = task.get("status")
    if isinstance(st, dict):
        if (st.get("type") or "").strip().lower() == "closed":
            return True
        if (st.get("status") or "").strip().lower() == "complete":
            return True
    return False


# ------------------------------------------------------------------ 定位任务
def find_review_task(tasks: list[dict], *, name: str,
                     task_id: str | None = None) -> dict:
    """在 list 任务里唯一定位「每日复盘总结」。

    - 若 ``task_id`` 有值：按 id 精确取；找不到 → ValueError。
    - 否则按 ``name`` 精确匹配（strip）；0 条或多条 → ValueError。
    """
    if task_id:
        for t in tasks:
            if t.get("id") == task_id:
                return t
        raise ValueError(f"找不到 task_id={task_id} 的任务")

    target = (name or "").strip()
    if not target:
        raise ValueError("CLICKUP_REVIEW_TASK.name 为空，无法按名字定位")
    hits = [t for t in tasks if (t.get("name") or "").strip() == target]
    if not hits:
        raise ValueError(f"在该 list 里找不到名为「{target}」的任务")
    if len(hits) > 1:
        ids = ", ".join(str(t.get("id")) for t in hits)
        raise ValueError(
            f"名为「{target}」的任务不唯一（{len(hits)} 条：{ids}），"
            "请在 config.CLICKUP_REVIEW_TASK 写死 task_id")
    return hits[0]


# ------------------------------------------------------------------ 库前置条件
def review_exists(conn, day: str) -> bool:
    """目标日是否已在 ``daily_reviews`` 入库。"""
    row = conn.execute(
        "SELECT 1 FROM daily_reviews WHERE date=? LIMIT 1", (day,)
    ).fetchone()
    return row is not None


# ------------------------------------------------------------------ HTTP PUT
def http_put(path: str, key: str, body: dict, *, timeout: float = CLICKUP_TIMEOUT_S) -> dict:
    """PUT 一个 ClickUp API 路径，返回解析后的 JSON。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API_BASE + path, data=data, method="PUT")
    req.add_header("Authorization", key)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def mark_complete(task_id: str, key: str, *, put=None, fetch=None,
                  timeout: float = CLICKUP_TIMEOUT_S) -> dict:
    """PUT 置 complete，再 GET 回读校验；不符则再试一次。

    ``put`` / ``fetch`` 可注入（测试离线）。成功返回回读到的任务 dict；
    仍失败抛 ``RuntimeError``。
    """
    put = http_put if put is None else put
    fetch = http_get if fetch is None else fetch
    path = f"/task/{task_id}"
    last: dict | None = None
    for _ in range(MAX_PUT_ATTEMPTS):
        put(path, key, {"status": "complete"}, timeout=timeout)
        last = fetch(path, key, timeout=timeout) or {}
        if is_closed(last):
            return last
    raise RuntimeError(
        f"写后回读仍未关闭：task_id={task_id} "
        f"status={((last or {}).get('status') or {})} "
        f"date_closed={(last or {}).get('date_closed')!r}"
        "（已重试一次）")


# ----------------------------------------------------------------------- 核心
def plan_push(day: str, *, list_id: str, name: str, task_id: str | None,
              key: str, fetch=None, timeout: float = CLICKUP_TIMEOUT_S) -> dict:
    """只读规划：取任务、判状态。不写。

    返回 ``{task_id, name, closed, action}``，``action`` 为
    ``skip_closed`` / ``would_complete``。
    """
    tasks = fetch_tasks(list_id, key, fetch=fetch, timeout=timeout)
    task = find_review_task(tasks, name=name, task_id=task_id)
    tid = str(task.get("id") or "")
    closed = is_closed(task)
    return {
        "task_id": tid,
        "name": (task.get("name") or "").strip(),
        "closed": closed,
        "action": "skip_closed" if closed else "would_complete",
        "task": task,
    }


def run_push(day: str, *, apply: bool, list_id: str | None = None,
             db_path: str | None = None, key: str = "",
             fetch=None, put=None, env=None, creds_path: str | None = None,
             timeout: float = CLICKUP_TIMEOUT_S) -> tuple[int, str]:
    """执行一次 clickup-push。返回 ``(exit_code, message)``。

    不直接读 ``sys.argv`` —— CLI 与测试都走这里。
    ``creds_path`` 仅测试注入（覆盖默认 ``~/.workbuddy/mcp.json``）。
    """
    cfg = CLICKUP_REVIEW_TASK
    lid = list_id or cfg["list_id"]
    name = cfg["name"]
    tid_cfg = cfg.get("task_id") or None

    try:
        if not key:
            key, _team = load_creds(env=env, path=creds_path)
    except CredError as e:
        return 2, f"凭据错误: {e}"

    conn = init_db(db_path=db_path or DB_PATH)
    try:
        if not review_exists(conn, day):
            return 2, (
                f"目标日 {day} 尚未入库（daily_reviews 无此行）。"
                "权威是复盘库 —— 请先 ingest 再 clickup-push。"
            )
    finally:
        conn.close()

    try:
        planned = plan_push(
            day, list_id=lid, name=name, task_id=tid_cfg,
            key=key, fetch=fetch, timeout=timeout)
    except ValueError as e:
        return 2, f"任务定位失败: {e}"
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        hint = "（401/403 = token 失效或权限不足）" if str(code) in ("401", "403") else ""
        return 1, f"取数失败: HTTP {code} {hint}"
    except urllib.error.URLError as e:
        return 1, f"取数失败: 网络不可达 —— {e.reason}"

    tid = planned["task_id"]
    tname = planned["name"]
    mode = "apply" if apply else "dry-run"

    if planned["action"] == "skip_closed":
        return 0, (
            f"[{mode}] {day} · 「{tname}」({tid}) 已是完成态 —— 幂等跳过，不写。"
        )

    if not apply:
        return 0, (
            f"[dry-run] {day} · 将把「{tname}」({tid}) 标为 complete。"
            "加 --apply 才真写。"
        )

    try:
        mark_complete(tid, key, put=put, fetch=fetch, timeout=timeout)
    except RuntimeError as e:
        return 1, f"回写失败: {e}"
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", "?")
        return 1, f"回写失败: HTTP {code}"
    except urllib.error.URLError as e:
        return 1, f"回写失败: 网络不可达 —— {e.reason}"

    return 0, f"[apply] {day} · 「{tname}」({tid}) 已标完成，回读校验通过。"


# ----------------------------------------------------------------------- CLI
def _parse(argv: list[str]) -> tuple[str, bool, str | None, str | None]:
    """返回 ``(day, apply, list_id, db_path)``；非法参数抛 ValueError。"""
    day, apply, list_id, db_path = "", False, None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--apply":
            apply = True
        elif a == "--dry-run":
            apply = False
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
        elif a == "--db" or a.startswith("--db="):
            if a.startswith("--db="):
                db_path = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--db 需要跟一个路径")
                db_path = argv[i]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day:
                raise ValueError(f"多余的参数: {a}（日期只接受一个）")
            day = a
        i += 1

    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    else:
        day = datetime.date.today().isoformat()
    return day, apply, list_id, db_path


def main(argv: list[str] | None = None, *, fetch=None, put=None,
         env=None, db_path: str | None = None) -> int:
    """CLI 入口。``fetch`` / ``put`` / ``env`` / ``db_path`` 可注入（测试离线）。"""
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        return 0

    try:
        day, apply, list_id, db_arg = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    rc, msg = run_push(
        day, apply=apply, list_id=list_id,
        db_path=db_path if db_path is not None else db_arg,
        fetch=fetch, put=put, env=env,
    )
    stream = sys.stdout if rc == 0 else sys.stderr
    print(msg, file=stream)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
