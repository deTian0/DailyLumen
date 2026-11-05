"""练练健身（KeepStrong）管道（M17 只读 / M18 落 md / M19 受控写回 / M20 训练日）。

用法::

    python -m review_tool keepstrong --date 20261001
    python -m review_tool keepstrong --date 2026-10-01 --write --ingest
    python -m review_tool keepstrong --action-history act_xxx [--date|--range]
    python -m review_tool keepstrong --templates
    python -m review_tool keepstrong --food-logs 20261015   # 可选；非 daily-pull
    python -m review_tool keepstrong --set-weight act_xxx 60 --yes
    python -m review_tool keepstrong --create-template --name N --actions-json P --yes
    python -m review_tool keepstrong --replace-template-actions TID --actions-json P --yes
    python -m review_tool keepstrong --plan-command PLAN_ID delay --yes

边界
----
1. **读**：产 ``收件箱/keepstrong-素材-<日期>.md``；``--write`` 才改复盘 md。
2. **写回（M19/I4）**：须 ``--yes``；不落库、不作系统状态；无确认零网络写调用。
3. **中文文案一律写「练练健身」**；查询参数必须 URL 编码。
4. **饮食权威在薄荷**；``--food-*`` 只读旁证，默认不写回 ``POST food/logs``。

HTTP 客户端已迁 ``review_tool.integrations.keepstrong``；本模块保留编排与 CLI。

退出码：0 = 成功；1 = 取数/写入失败；2 = 用法或凭据缺失 / 集成关闭。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
from collections.abc import Callable
from typing import Any

from ..config import INBOX_DIR, SETTINGS
from ..integrations.flags import IntegrationDisabled, require_enabled
from ..integrations.keepstrong import (
    ACTIONS_PAGE_SIZE,
    BODY_LOGS_PAGE_SIZE,
    COMPLETED_STATUS,
    MAX_PAGES,
    PRODUCT_CN,
    RECORDS_PAGE_SIZE,
    TZ_OFFSET_MIN,
    ApiKeyExpired,
    Client,
    CredError,
    KeepStrongError,
    KeyGuidance,
    RateLimited,
    SkillUpdateRequired,
    build_headers,
    day_str_to_iso,
    encode_query,
    filter_completed_records,
    is_completed_record,
    iso_weekday_cn,
    new_idempotency_key,
    to_day_str,
    verify_body_log_response,
    verify_schedule_response,
    verify_weight_response,
)
from ..integrations.keepstrong import load_api_key as _load_api_key
from ..integrations.keepstrong.client import Opener, Sleeper
from ..integrations.last_error import record_integration_error
from .keepstrong_render import render_material


def load_api_key(*, env=None, settings=None) -> str:
    """兼容旧测试：默认 settings 走本模块 ``SETTINGS``（可 patch）。"""
    return _load_api_key(
        env=env,
        settings=SETTINGS if settings is None else settings,
    )

INBOX_PREFIX = "keepstrong-素材"

OFFLINE_FALLBACK_HINT = (
    "训练日将走离线兜底（config.PROFILE['training_weekdays']）；"
    "未写入「训练日」字段，避免把「拉不到」误记成「没练」。"
)

def format_write_preview(kind: str, payload: dict) -> str:
    """写前展示完整变更（给人确认）。"""
    lines = [f"即将向「{PRODUCT_CN}」写入（{kind}）：", ""]
    for k, v in payload.items():
        if k == "actions" and isinstance(v, list):
            lines.append(f"- actions（{len(v)}）：")
            for i, a in enumerate(v, 1):
                lines.append(f"  {i}. {json.dumps(a, ensure_ascii=False)}")
        else:
            lines.append(f"- {k}: {v}")
    lines += [
        "",
        "⚠️ 写回不落 DailyLumen 库、不作系统状态。",
        "⚠️ App 里可能需重启才可见。",
        "确认后请加 --yes 再执行。",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------- 采集
def collect(
    start: str,
    end: str,
    *,
    types: set[str],
    client: Client,
) -> dict[str, Any]:
    """按类型拉取素材数据（纯网络，不渲染）。"""
    start_s, end_s = to_day_str(start), to_day_str(end)
    bundle: dict[str, Any] = {
        "start": start_s,
        "end": end_s,
        "records": [],
        "body_profile": None,
        "body_logs": [],
        "plan": None,
    }
    if "records" in types:
        # iter_training_records 已过滤；再滤一次防注入/旧客户端绕过
        records = filter_completed_records(
            client.iter_training_records(start_s, end_s)
        )
        bundle["records"] = records
        for rec in records:
            acts = rec.get("actions") or []
            if isinstance(acts, list):
                client.remember_actions(acts)
    if "body" in types:
        bundle["body_profile"] = client.body_profile()
        bundle["body_logs"] = client.body_logs(
            "weight", start_date=start_s, end_date=end_s
        )
    if "plan" in types:
        bundle["plan"] = client.running_plans()
    return bundle


# ----------------------------------------------------------------------- CLI
USAGE = (
    "keepstrong [--date D] [--range S E] [--type …] [--write] [--ingest] [--stdout] | "
    "keepstrong --action-history <actionId> [--date|--range] [--stdout] | "
    "keepstrong --templates [--stdout] | "
    "keepstrong --food-logs <day> | --food-search <kw> [--stdout] | "
    "keepstrong --set-weight <actionId> <kg|''> [--yes] | "
    "keepstrong --log-body <metric> <value> [--day D] [--unit U] [--yes] | "
    "keepstrong --schedule --day D --name N --actions-json PATH [--yes] | "
    "keepstrong --create-template --name N --actions-json PATH [--yes] | "
    "keepstrong --replace-template-actions <templateId> --actions-json PATH [--yes] | "
    "keepstrong --plan-command <planId> <command> [--yes]"
)

_WRITE_MODES = frozenset({
    "set_weight",
    "log_body",
    "schedule",
    "create_template",
    "replace_template_actions",
    "plan_command",
})
_EXTRA_READ_MODES = frozenset({
    "action_history",
    "templates",
    "food_logs",
    "food_search",
})


def _parse_types(raw: str) -> set[str]:
    allowed = {"records", "body", "plan"}
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    bad = parts - allowed
    if bad:
        raise ValueError(f"--type 只接受 {sorted(allowed)}，未知: {sorted(bad)}")
    return parts or {"records", "body", "plan"}


def _parse(argv: list[str]) -> dict[str, Any]:
    date_one = ""
    range_start = range_end = ""
    types_raw = "records,body,plan"
    out_dir = INBOX_DIR
    to_stdout = False
    do_write = False
    do_ingest = False
    yes = False
    mode = "read"
    set_weight: list[str] = []
    log_body: list[str] = []
    sch_day = sch_name = sch_json = ""
    body_day = ""
    body_unit = "kg"
    action_history_id = ""
    food_day = ""
    food_keyword = ""
    template_id = ""
    plan_id = ""
    plan_cmd = ""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--stdout",):
            to_stdout = True
        elif a in ("--write",):
            do_write = True
        elif a in ("--ingest",):
            do_ingest = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--set-weight":
            if i + 2 >= len(argv):
                raise ValueError("--set-weight 需要 <actionId> <kg|''>")
            mode = "set_weight"
            set_weight = [argv[i + 1], argv[i + 2]]
            i += 2
        elif a == "--log-body":
            if i + 2 >= len(argv):
                raise ValueError("--log-body 需要 <metric> <value>")
            mode = "log_body"
            log_body = [argv[i + 1], argv[i + 2]]
            i += 2
        elif a == "--schedule":
            mode = "schedule"
        elif a == "--action-history":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise ValueError("--action-history 需要 <actionId>")
            mode = "action_history"
            action_history_id = argv[i + 1]
            i += 1
        elif a == "--templates":
            mode = "templates"
        elif a == "--food-logs":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise ValueError("--food-logs 需要 <day>")
            mode = "food_logs"
            food_day = argv[i + 1]
            i += 1
        elif a == "--food-search":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise ValueError("--food-search 需要 <keyword>")
            mode = "food_search"
            food_keyword = argv[i + 1]
            i += 1
        elif a == "--create-template":
            mode = "create_template"
        elif a == "--replace-template-actions":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise ValueError("--replace-template-actions 需要 <templateId>")
            mode = "replace_template_actions"
            template_id = argv[i + 1]
            i += 1
        elif a == "--plan-command":
            if i + 2 >= len(argv):
                raise ValueError("--plan-command 需要 <planId> <command>")
            mode = "plan_command"
            plan_id, plan_cmd = argv[i + 1], argv[i + 2]
            i += 2
        elif a == "--name" or a.startswith("--name="):
            if a.startswith("--name="):
                sch_name = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--name 需要课名/模板名")
                sch_name = argv[i]
        elif a == "--actions-json" or a.startswith("--actions-json="):
            if a.startswith("--actions-json="):
                sch_json = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--actions-json 需要路径")
                sch_json = argv[i]
        elif a == "--unit" or a.startswith("--unit="):
            if a.startswith("--unit="):
                body_unit = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--unit 需要单位")
                body_unit = argv[i]
        elif a == "--day" or a.startswith("--day="):
            if a.startswith("--day="):
                raw_day = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--day 需要日期")
                raw_day = argv[i]
            if mode in ("schedule", "create_template"):
                sch_day = raw_day
            else:
                body_day = raw_day
        elif a == "--date" or a.startswith("--date="):
            if a.startswith("--date="):
                date_one = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--date 需要跟一个日期")
                date_one = argv[i]
        elif a == "--range" or a.startswith("--range="):
            if a.startswith("--range="):
                bits = a.split("=", 1)[1].split(",")
                if len(bits) != 2:
                    raise ValueError("--range 需要 START,END 或 --range START END")
                range_start, range_end = bits[0].strip(), bits[1].strip()
            else:
                if i + 2 >= len(argv):
                    raise ValueError("--range 需要 START END 两个日期")
                range_start, range_end = argv[i + 1], argv[i + 2]
                i += 2
        elif a == "--type" or a.startswith("--type="):
            if a.startswith("--type="):
                types_raw = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--type 需要跟 records,body,plan")
                types_raw = argv[i]
        elif a == "--out" or a.startswith("--out="):
            if a.startswith("--out="):
                out_dir = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--out 需要跟一个目录")
                out_dir = argv[i]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            raise ValueError(f"多余的参数: {a}")
        i += 1

    if mode == "schedule":
        if not sch_day or not sch_name or not sch_json:
            raise ValueError("--schedule 需要 --day / --name / --actions-json")
    if mode == "create_template":
        if not sch_name or not sch_json:
            raise ValueError("--create-template 需要 --name / --actions-json")
    if mode == "replace_template_actions":
        if not template_id or not sch_json:
            raise ValueError(
                "--replace-template-actions 需要 <templateId> 与 --actions-json"
            )
    if mode == "log_body" and not body_day:
        body_day = datetime.date.today().strftime("%Y%m%d")

    types = _parse_types(types_raw)
    if range_start or range_end:
        if not (range_start and range_end):
            raise ValueError("--range 需要起止两个日期")
        start, end = to_day_str(range_start), to_day_str(range_end)
    elif date_one:
        start = end = to_day_str(date_one)
    else:
        today = datetime.date.today().strftime("%Y%m%d")
        start = end = today
    if start > end:
        raise ValueError(f"起始日期不能晚于结束日期: {start} > {end}")
    return {
        "mode": mode,
        "start": start,
        "end": end,
        "types": types,
        "out_dir": out_dir,
        "to_stdout": to_stdout,
        "write": do_write,
        "ingest": do_ingest,
        "yes": yes,
        "set_weight": set_weight,
        "log_body": log_body,
        "body_day": body_day,
        "body_unit": body_unit,
        "sch_day": sch_day,
        "sch_name": sch_name,
        "sch_json": sch_json,
        "action_history_id": action_history_id,
        "food_day": food_day,
        "food_keyword": food_keyword,
        "template_id": template_id,
        "plan_id": plan_id,
        "plan_cmd": plan_cmd,
    }


def _load_actions_json(path: str) -> tuple[list | None, int]:
    """读 actions JSON；成功返回 (list, 0)；失败打印并返回 (None, rc)。"""
    try:
        with open(path, encoding="utf-8") as f:
            actions = json.load(f)
    except (OSError, ValueError) as e:
        print(f"读 actions-json 失败: {e}", file=sys.stderr)
        return None, 2
    if not isinstance(actions, list):
        print("--actions-json 须为 JSON 数组", file=sys.stderr)
        return None, 2
    return actions, 0


def _write_ok(resp: Any, key: str) -> int:
    print(f"已写入（Idempotency-Key={key}）: {json.dumps(resp, ensure_ascii=False)}")
    print("提示：App 里可能需重启才可见。写回未入 DailyLumen 库。")
    return 0


def _write_fail(e: Exception) -> int:
    print(f"写入失败: {e}", file=sys.stderr)
    kind = type(e).__name__
    code = None
    if isinstance(e, ApiKeyExpired):
        code = 401
    elif isinstance(e, SkillUpdateRequired):
        code = 426
    elif isinstance(e, RateLimited):
        code = 429
    record_integration_error(
        "keepstrong",
        command="keepstrong",
        error_kind=kind,
        error_summary=str(e)[:200],
        http_code=code,
    )
    return 1


def _run_outbound(opts: dict[str, Any], client: Client) -> int:
    """M19/I4 写回：无 --yes 只预览、零网络写；有 --yes 才 POST。"""
    mode = opts["mode"]
    yes = bool(opts["yes"])

    if mode == "set_weight":
        action_id, raw_w = opts["set_weight"]
        weight: str | None
        if raw_w in ("", "''", '""'):
            weight = None  # → 空串
        else:
            weight = raw_w
        preview = {
            "actionId": action_id,
            "weight": "" if weight is None else weight,
            "note": "空串=沿用历史自动重量",
        }
        print(format_write_preview("设下次重量", preview))
        if not yes:
            return 0
        try:
            resp, key = client.set_action_weight(
                action_id, weight, user_confirmed=True
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    if mode == "log_body":
        metric, value = opts["log_body"]
        preview = {
            "metric": metric,
            "value": value,
            "unit": opts["body_unit"],
            "dayStr": to_day_str(opts["body_day"]),
        }
        print(format_write_preview("记体征", preview))
        if not yes:
            return 0
        try:
            resp, key = client.log_body_metric(
                metric,
                value,
                unit=opts["body_unit"],
                day_str=opts["body_day"],
                user_confirmed=True,
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    if mode == "schedule":
        actions, rc = _load_actions_json(opts["sch_json"])
        if actions is None:
            return rc
        preview = {
            "dayStr": to_day_str(opts["sch_day"]),
            "name": opts["sch_name"],
            "actions": actions,
        }
        print(format_write_preview("排课", preview))
        if not yes:
            return 0
        try:
            resp, key = client.schedule_workout(
                opts["sch_day"],
                opts["sch_name"],
                actions,
                user_confirmed=True,
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    if mode == "create_template":
        actions, rc = _load_actions_json(opts["sch_json"])
        if actions is None:
            return rc
        preview = {"name": opts["sch_name"], "actions": actions}
        print(format_write_preview("创建模板", preview))
        if not yes:
            return 0
        try:
            resp, key = client.create_template(
                opts["sch_name"], actions, user_confirmed=True
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    if mode == "replace_template_actions":
        actions, rc = _load_actions_json(opts["sch_json"])
        if actions is None:
            return rc
        preview = {"templateId": opts["template_id"], "actions": actions}
        print(format_write_preview("替换模板动作", preview))
        if not yes:
            return 0
        try:
            resp, key = client.replace_template_actions(
                opts["template_id"], actions, user_confirmed=True
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    if mode == "plan_command":
        preview = {
            "runningPlanId": opts["plan_id"],
            "command": opts["plan_cmd"],
        }
        print(format_write_preview("计划命令", preview))
        if not yes:
            return 0
        try:
            resp, key = client.running_plan_command(
                opts["plan_id"], opts["plan_cmd"], user_confirmed=True
            )
        except KeepStrongError as e:
            return _write_fail(e)
        return _write_ok(resp, key)

    raise KeepStrongError(f"未知写模式: {mode}")


def _run_extra_read(opts: dict[str, Any], client: Client) -> int:
    """I3：action history / templates / food 只读；默认 stdout，--write 才落收件箱 md。"""
    mode = opts["mode"]
    try:
        if mode == "action_history":
            items = client.action_history(
                opts["action_history_id"], opts["start"], opts["end"]
            )
            payload = {
                "kind": "action_history",
                "actionId": opts["action_history_id"],
                "start": opts["start"],
                "end": opts["end"],
                "items": items,
            }
            label = f"history-{opts['action_history_id']}-{opts['start']}"
        elif mode == "templates":
            items = client.templates()
            payload = {"kind": "templates", "items": items}
            label = "templates"
        elif mode == "food_logs":
            day = to_day_str(opts["food_day"])
            data = client.food_logs(day)
            payload = {"kind": "food_logs", "dayStr": day, "data": data}
            label = f"food-{day_str_to_iso(day)}"
        elif mode == "food_search":
            items = client.food_search(opts["food_keyword"])
            payload = {
                "kind": "food_search",
                "keyword": opts["food_keyword"],
                "items": items,
            }
            label = "food-search"
        else:
            raise KeepStrongError(f"未知只读扩展模式: {mode}")
    except ApiKeyExpired as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind="ApiKeyExpired",
            error_summary=str(e)[:200], http_code=401,
        )
        print(f"认证失败: {e}", file=sys.stderr)
        return 1
    except SkillUpdateRequired as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind="SkillUpdateRequired",
            error_summary=str(e)[:200], http_code=426,
        )
        print(f"技能过期: {e}", file=sys.stderr)
        return 1
    except KeepStrongError as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind=type(e).__name__,
            error_summary=str(e)[:200],
        )
        print(f"取数失败: {e}", file=sys.stderr)
        return 1

    text = (
        f"# {PRODUCT_CN} · {payload.get('kind')}\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    # 默认 stdout；--write 落收件箱（仍禁止只进库）
    if opts["write"]:
        out_dir = opts["out_dir"]
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{INBOX_PREFIX}-{label}.md")
        with open(out, "wb") as f:
            f.write(text.replace("\r\n", "\n").encode("utf-8"))
        print(f"已生成: {out}")
        print("这是素材旁证；饮食权威仍在薄荷；⛔ 禁止只进库不落 md。")
        return 0
    print(text)
    return 0


def main(
    argv: list[str] | None = None,
    *,
    env=None,
    urlopen: Opener | None = None,
    sleep: Sleeper | None = None,
    now: Callable[[], str] | None = None,
) -> int:
    """CLI 入口。``urlopen`` / ``env`` / ``sleep`` / ``now`` 可注入（测试离线）。"""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print(f"「{PRODUCT_CN}」读素材 / 落 md / 受控写回（写回须 --yes）。")
        return 0

    try:
        require_enabled("keepstrong")
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
        # 测试可传 env={}；若同时希望绕过本机 .env，应 mock SETTINGS
        key = load_api_key(env=env)
    except CredError as e:
        print(f"凭据错误: {e}", file=sys.stderr)
        return 2

    client = Client(key, urlopen=urlopen, sleep=sleep)

    if opts["mode"] in _WRITE_MODES:
        return _run_outbound(opts, client)
    if opts["mode"] in _EXTRA_READ_MODES:
        return _run_extra_read(opts, client)
    try:
        bundle = collect(
            opts["start"], opts["end"], types=opts["types"], client=client
        )
    except ApiKeyExpired as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind="ApiKeyExpired",
            error_summary=str(e)[:200], http_code=401,
        )
        print(f"认证失败: {e}", file=sys.stderr)
        print(f"离线兜底: {OFFLINE_FALLBACK_HINT}", file=sys.stderr)
        return 1
    except SkillUpdateRequired as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind="SkillUpdateRequired",
            error_summary=str(e)[:200], http_code=426,
        )
        print(f"技能过期: {e}", file=sys.stderr)
        print(f"离线兜底: {OFFLINE_FALLBACK_HINT}", file=sys.stderr)
        return 1
    except RateLimited as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind="RateLimited",
            error_summary=str(e)[:200], http_code=429,
        )
        print(f"限流: {e}", file=sys.stderr)
        print(f"离线兜底: {OFFLINE_FALLBACK_HINT}", file=sys.stderr)
        return 1
    except KeepStrongError as e:
        record_integration_error(
            "keepstrong", command="keepstrong", error_kind=type(e).__name__,
            error_summary=str(e)[:200],
        )
        print(f"取数失败: {e}", file=sys.stderr)
        print(f"离线兜底: {OFFLINE_FALLBACK_HINT}", file=sys.stderr)
        return 1

    stamp = now() if callable(now) else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # 单日文件名用 start；跨天则用 start_end
    if opts["start"] == opts["end"]:
        label = day_str_to_iso(opts["start"])
    else:
        label = f"{day_str_to_iso(opts['start'])}_{day_str_to_iso(opts['end'])}"
    text = render_material(
        bundle,
        label_day=label,
        generated_at=stamp,
        types=opts["types"],
    )

    # 素材不得含密钥
    if key and key in text:
        print("内部错误：素材内容含 API Key，已拒绝写出。", file=sys.stderr)
        return 1

    # M18：同步进当日复盘 md（默认 dry-run；--write 才落盘）
    if opts["write"] or opts["ingest"]:
        from .keepstrong_sync import review_md_path, write_sync

        if opts["start"] != opts["end"]:
            print(
                "同步到复盘 md 仅支持单日（--date）；跨天请逐日执行。",
                file=sys.stderr,
            )
            return 2
        md_path = review_md_path(label)
        if not os.path.isfile(md_path):
            print(f"找不到复盘 md：{md_path}", file=sys.stderr)
            return 2
        day_records = [
            r for r in (bundle.get("records") or [])
            if str(r.get("dayStr") or r.get("date") or "").replace("-", "")
            == opts["start"]
        ]
        # 成功拉到（含空）：显式写训练日 是/否；API 失败不会走到这里（见上方 except）
        training_day = bool(day_records)
        try:
            summary = write_sync(
                md_path,
                records=day_records,
                body_logs=bundle.get("body_logs") or [],
                body_profile=bundle.get("body_profile"),
                day_str=opts["start"],
                training_day=training_day,
                dry_run=not opts["write"],
            )
        except OSError as e:
            print(f"写 md 失败: {e}", file=sys.stderr)
            return 1
        mode = "已写入" if opts["write"] and summary.get("changed") else (
            "dry-run" if not opts["write"] else "无变更"
        )
        td_label = summary.get("training_day")
        td_s = (
            "是" if td_label is True
            else ("否" if td_label is False else "未写")
        )
        print(
            f"同步复盘 md（{mode}）: {md_path}；"
            f"训练块={'是' if summary.get('training_written') else '否'}；"
            f"训练日={td_s}；"
            f"体重={summary.get('weight_kg')}"
        )
        # M40：空 completed 不静默假装「训练明细已写入」
        n_raw = len(bundle.get("records") or [])
        if opts["write"] and not summary.get("training_written"):
            if n_raw == 0 and not day_records:
                print(
                    "⚠️ 当日无 status=completed 训练记录：未写入「附录 · 训练明细」"
                    "（合法空结果；训练日已按「否」处理，勿当成写入成功）。",
                    file=sys.stderr,
                )
            elif n_raw and not day_records:
                print(
                    f"⚠️ 拉到 {n_raw} 条记录但无一匹配当日 {opts['start']}："
                    "未写入训练明细（检查 dayStr/date 归日）。",
                    file=sys.stderr,
                )
        if opts["ingest"]:
            if not opts["write"]:
                print(
                    "--ingest 需要同时加 --write（禁止只进库不落 md / G1）。",
                    file=sys.stderr,
                )
                return 2
            from ..storage.db import init_db
            from .ingest import ingest_path

            conn = init_db()
            try:
                ingest_path(conn, os.path.abspath(md_path))
            finally:
                conn.close()
            print(f"已 ingest: {md_path}")

    if opts["to_stdout"]:
        print(text)
        return 0

    # 未要求 stdout / 仅 sync 时仍落收件箱素材（方便对照）；纯 --write 也产一份
    out_dir = opts["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{INBOX_PREFIX}-{label}.md")
    with open(out, "wb") as f:
        f.write(text.replace("\r\n", "\n").encode("utf-8"))
    n_rec = len(bundle.get("records") or [])
    print(f"已生成: {out}")
    print(
        f"训练记录 {n_rec} 条；这是**素材**，不是复盘成品 —— "
        f"来源「{PRODUCT_CN}」，按 skill daily-review-intake / M18 再落 md。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
