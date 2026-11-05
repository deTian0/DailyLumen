"""ClickUp 复盘向薄写 CLI（I2）：建任务 / 改状态 / 评论。

用法::

    python -m review_tool clickup-task --create "买菜" [--list ID] [--status open] [--apply]
    python -m review_tool clickup-task --status <task_id> complete [--apply]
    python -m review_tool clickup-task --comment <task_id> "备注" [--apply]

边界（写死）
------------
1. **默认 dry-run**；显式 ``--apply`` 才发网写；写后 GET 回读。
2. **不写** ``habit_logs`` / 不碰补剂勾选；**不参与四维评分**。
3. 与 ``clickup-push`` 分工：push 只勾「每日复盘总结」元任务；本命令管偶发建任务/评论。
4. 批量跨 list / 自定义字段批量仍归本机 ``cu.bat`` / 用户级 skill。
5. 关 ``INTEGRATION_CLICKUP`` 时不发网。

退出码：0 = 成功 / dry-run；1 = 网络或回读失败；2 = 用法 / 凭据 / 集成关闭。
"""
from __future__ import annotations

import sys
import urllib.error

from ..config import CLICKUP_TIMEOUT_S, LIST_DAILY
from ..integrations.clickup import Client, CredError, load_creds
from ..integrations.flags import IntegrationDisabled, require_enabled
from ..integrations.last_error import record_integration_error

USAGE = (
    "clickup-task (--create NAME | --status TASK_ID STATUS | --comment TASK_ID TEXT) "
    "[--list ID] [--apply] [--dry-run]"
)


def _client(
    key: str,
    *,
    client: Client | None = None,
    get=None,
    put=None,
    post=None,
    timeout: float = CLICKUP_TIMEOUT_S,
) -> Client:
    if client is not None:
        return client
    if get is not None or put is not None or post is not None:
        return Client(key, get=get, put=put, post=post, timeout=timeout)
    return Client(key, timeout=timeout)


def run_create(
    name: str,
    *,
    list_id: str,
    status: str | None,
    apply: bool,
    key: str,
    client: Client | None = None,
    get=None,
    put=None,
    post=None,
    timeout: float = CLICKUP_TIMEOUT_S,
) -> tuple[int, str]:
    """建任务；默认 dry-run。"""
    mode = "apply" if apply else "dry-run"
    fields = {}
    if status:
        fields["status"] = status
    if not apply:
        return 0, (
            f"[dry-run] 将在 list={list_id} 创建「{name}」"
            + (f"（status={status}）" if status else "")
            + "。加 --apply 才真写。"
        )
    cu = _client(key, client=client, get=get, put=put, post=post, timeout=timeout)
    try:
        created = cu.create_task(list_id, name, **fields)
        tid = str(created.get("id") or "")
        if not tid:
            return 1, "回写失败: 创建响应缺 task id"
        got = cu.get_task(tid)
        gname = (got.get("name") or "").strip()
        if gname != name.strip():
            return 1, (
                f"回读名不一致：请求 {name!r}，回读 {gname!r}（id={tid}）"
            )
    except urllib.error.HTTPError as e:
        return 1, f"回写失败: HTTP {getattr(e, 'code', '?')}"
    except urllib.error.URLError as e:
        return 1, f"回写失败: 网络不可达 —— {e.reason}"
    return 0, f"[{mode}] 已创建「{name}」({tid})，回读校验通过。"


def run_status(
    task_id: str,
    status: str,
    *,
    apply: bool,
    key: str,
    client: Client | None = None,
    get=None,
    put=None,
    post=None,
    timeout: float = CLICKUP_TIMEOUT_S,
) -> tuple[int, str]:
    """改任务状态；默认 dry-run。"""
    mode = "apply" if apply else "dry-run"
    if not apply:
        return 0, (
            f"[dry-run] 将把 {task_id} 标为 status={status!r}。加 --apply 才真写。"
        )
    cu = _client(key, client=client, get=get, put=put, post=post, timeout=timeout)
    try:
        cu.set_task_status(task_id, status)
        got = cu.get_task(task_id)
        st = got.get("status")
        actual = ""
        if isinstance(st, dict):
            actual = (st.get("status") or "").strip()
        elif isinstance(st, str):
            actual = st.strip()
        if actual.lower() != status.strip().lower():
            return 1, (
                f"回读状态不符：请求 {status!r}，回读 {actual!r}（id={task_id}）"
            )
    except urllib.error.HTTPError as e:
        return 1, f"回写失败: HTTP {getattr(e, 'code', '?')}"
    except urllib.error.URLError as e:
        return 1, f"回写失败: 网络不可达 —— {e.reason}"
    return 0, f"[{mode}] {task_id} → status={status}，回读校验通过。"


def run_comment(
    task_id: str,
    text: str,
    *,
    apply: bool,
    key: str,
    client: Client | None = None,
    get=None,
    put=None,
    post=None,
    timeout: float = CLICKUP_TIMEOUT_S,
) -> tuple[int, str]:
    """加评论；默认 dry-run。"""
    mode = "apply" if apply else "dry-run"
    if not apply:
        preview = text if len(text) <= 80 else text[:77] + "..."
        return 0, (
            f"[dry-run] 将给 {task_id} 加评论「{preview}」。加 --apply 才真写。"
        )
    cu = _client(key, client=client, get=get, put=put, post=post, timeout=timeout)
    try:
        created = cu.add_comment(task_id, text)
        cid = created.get("id")
        comments = cu.list_comments(task_id)
        if cid and not any(str(c.get("id")) == str(cid) for c in comments):
            # 部分响应无 id：退化为正文子串匹配
            bodies = [(c.get("comment_text") or c.get("comment") or "") for c in comments]
            if not any(text in str(b) for b in bodies):
                return 1, f"回读未找到刚发的评论（task={task_id}）"
        elif not cid:
            bodies = [
                str(c.get("comment_text") or c.get("comment") or "") for c in comments
            ]
            if not any(text in b for b in bodies):
                return 1, f"回读未找到刚发的评论（task={task_id}）"
    except urllib.error.HTTPError as e:
        return 1, f"回写失败: HTTP {getattr(e, 'code', '?')}"
    except urllib.error.URLError as e:
        return 1, f"回写失败: 网络不可达 —— {e.reason}"
    return 0, f"[{mode}] 已给 {task_id} 加评论，回读校验通过。"


def _parse(argv: list[str]) -> dict:
    """解析 argv → 动作参数；非法抛 ValueError。"""
    apply = False
    list_id = LIST_DAILY
    create_name = ""
    create_status: str | None = None
    status_args: list[str] = []
    comment_args: list[str] = []
    action = ""
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
        elif a == "--create" or a.startswith("--create="):
            if action and action != "create":
                raise ValueError("一次只能选一个动作：--create / --status / --comment")
            action = "create"
            if a.startswith("--create="):
                create_name = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv) or argv[i].startswith("-"):
                    raise ValueError("--create 需要任务名")
                create_name = argv[i]
        elif a == "--task-status" or a.startswith("--task-status="):
            # 建任务时可选初始状态（避免与动作 --status 撞名）
            if a.startswith("--task-status="):
                create_status = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--task-status 需要状态名")
                create_status = argv[i]
        elif a == "--status":
            if action and action != "status":
                raise ValueError("一次只能选一个动作：--create / --status / --comment")
            action = "status"
            if i + 2 >= len(argv):
                raise ValueError("--status 需要 <task_id> <status>")
            status_args = [argv[i + 1], argv[i + 2]]
            i += 2
        elif a == "--comment":
            if action and action != "comment":
                raise ValueError("一次只能选一个动作：--create / --status / --comment")
            action = "comment"
            if i + 2 >= len(argv):
                raise ValueError("--comment 需要 <task_id> <text>")
            comment_args = [argv[i + 1], argv[i + 2]]
            i += 2
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            raise ValueError(f"多余的参数: {a}")
        i += 1

    if not action:
        raise ValueError("须指定 --create / --status / --comment 之一")
    if action == "create" and not (create_name or "").strip():
        raise ValueError("--create 任务名不能为空")
    if action == "create" and apply and not (list_id or "").strip():
        raise ValueError(
            "创建任务需要 --list ID（或配置 local/.env 的 CLICKUP_LIST_DAILY）"
        )
    return {
        "action": action,
        "apply": apply,
        "list_id": list_id,
        "create_name": create_name.strip(),
        "create_status": create_status,
        "status_args": status_args,
        "comment_args": comment_args,
    }


def main(
    argv: list[str] | None = None,
    *,
    env=None,
    client: Client | None = None,
    get=None,
    put=None,
    post=None,
    key: str = "",
) -> int:
    """CLI 入口。transport / key 可注入（测试离线）。"""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print(
            "复盘向薄写：建任务 / 改状态 / 评论。"
            "默认 dry-run；--apply 才写；写后 GET 回读。"
            "不写 habit_logs、不参与四维。"
            "与 clickup-push（只勾「每日复盘总结」）互不替代。"
        )
        return 0

    try:
        require_enabled("clickup")
    except IntegrationDisabled as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        if not key:
            key, _team = load_creds(env=env)
    except CredError as e:
        print(f"凭据错误: {e}", file=sys.stderr)
        return 2

    action = opts["action"]
    try:
        if action == "create":
            rc, msg = run_create(
                opts["create_name"],
                list_id=opts["list_id"],
                status=opts["create_status"],
                apply=opts["apply"],
                key=key,
                client=client,
                get=get,
                put=put,
                post=post,
            )
        elif action == "status":
            rc, msg = run_status(
                opts["status_args"][0],
                opts["status_args"][1],
                apply=opts["apply"],
                key=key,
                client=client,
                get=get,
                put=put,
                post=post,
            )
        else:
            rc, msg = run_comment(
                opts["comment_args"][0],
                opts["comment_args"][1],
                apply=opts["apply"],
                key=key,
                client=client,
                get=get,
                put=put,
                post=post,
            )
    except Exception as e:
        record_integration_error(
            "clickup",
            command="clickup-task",
            error_kind=type(e).__name__,
            error_summary=str(e)[:200],
        )
        raise

    if rc != 0 and opts["apply"]:
        record_integration_error(
            "clickup",
            command="clickup-task",
            error_kind="clickup_task_failed",
            error_summary=msg[:200],
        )
    stream = sys.stdout if rc == 0 else sys.stderr
    print(msg, file=stream)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
