"""练练健身（KeepStrong）域写操作（W17 / FR-J2）。

复用 ``integrations.keepstrong.Client`` 的写方法（须 ``user_confirmed=True``）；
**写回不落库、不作系统状态**（与截图同级的外部副作用）。六种写动作：

- ``ks_set_weight``            设下次重量（空串=沿用历史；⛔ 不用 0）
- ``ks_log_body``              记体征（体重 / 体脂 / 围度）
- ``ks_schedule``             排课（scheduled-workouts）
- ``ks_create_template``       创建 / 更新模板元数据
- ``ks_replace_template_actions``  完整替换模板动作
- ``ks_plan_command``          running-plan 命令（delay / cancel_rest / ...）

两段式：``plan_*`` 只校验 + 出预览（零网络写），``_apply_*`` 才 POST。
错误映射：``CredError`` → 503 ``credentials_missing``；``ApiKeyExpired`` → 401
``upstream_auth``；``SkillUpdateRequired`` → 426 ``skill_update_required``；
``RateLimited`` → 429 ``rate_limited``；``KeepStrongError`` → 502 ``writeback_failed``。
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ..queries import QueryError
from .base import (
    ID_RE,
    TokenStore,
    clean_text,
    plan_out,
    quote_arg,
    register,
    today,
)

# running-plan command 白名单（与 Client.running_plan_command 一致）
_PLAN_COMMANDS = {"delay", "cancel_rest", "add_alternative", "add_temporary_workout"}
# body/logs metric 白名单（与练练 API 参考 §4 一致）
_BODY_METRICS = {"weight", "fat", "bodyRound"}
# 体征单位（metric → unit）；weight/fat 默认 kg/%，bodyRound 围度由用户传 unit
_DEFAULT_BODY_UNIT = {"weight": "kg", "fat": "%"}


def _ks_creds(env=None) -> str:
    """启用检查 + 读 API key；集成关闭 / 凭据缺失在预览阶段就拦下。"""
    from ...integrations.flags import IntegrationDisabled, require_enabled
    from ...integrations.keepstrong import CredError, load_api_key

    try:
        require_enabled("keepstrong")
    except IntegrationDisabled as e:
        raise QueryError(503, "integration_disabled", str(e)) from e
    try:
        return load_api_key(env=env)
    except CredError as e:
        raise QueryError(503, "credentials_missing", str(e)) from e


def _client(api_key: str, ks_client=None):
    """构造 Client；测试可注入假 client（忽略 api_key）。"""
    if ks_client is not None:
        return ks_client
    from ...integrations.keepstrong import Client

    return Client(api_key)


def _map_ks_error(e: Exception) -> QueryError:
    """练练异常 → 结构化 QueryError（文案不含密钥）。"""
    from ...integrations.keepstrong import (
        ApiKeyExpired,
        KeepStrongError,
        RateLimited,
        SkillUpdateRequired,
    )

    if isinstance(e, ApiKeyExpired):
        return QueryError(401, "upstream_auth", str(e))
    if isinstance(e, SkillUpdateRequired):
        return QueryError(426, "skill_update_required", str(e))
    if isinstance(e, RateLimited):
        return QueryError(429, "rate_limited", str(e))
    if isinstance(e, KeepStrongError):
        return QueryError(502, "writeback_failed", str(e))
    if isinstance(e, (urllib.error.URLError, TimeoutError)):
        return QueryError(504, "upstream_unreachable", "练练网络不可达或超时，可重新预览后重试")
    return QueryError(502, "writeback_failed", str(e))


# ---------------------------------------------------------------------------
# plan：每种动作一个入口（校验 + 预览 + token；零网络写）
# ---------------------------------------------------------------------------

def plan_ks_set_weight(tokens: TokenStore, action_id: str, weight, *,
                       weight_unit: str | None = None, template_id: str | None = None,
                       right_weight=None, env=None) -> dict[str, Any]:
    aid = (action_id or "").strip()
    if not ID_RE.match(aid):
        raise QueryError(422, "invalid_param", "actionId 不合法（仅字母数字 _-，≤40）")
    # weight: None/空串 → 沿用历史；显式 0 拒绝（上游会关闭自动取值）
    raw = "" if weight is None else str(weight).strip()
    if raw == "0":
        raise QueryError(422, "invalid_param", "重量不能传 0（会关闭历史自动取值）；未指定请省略")
    _ks_creds(env)
    preview = {
        "actionId": aid, "weight": raw, "weightUnit": weight_unit,
        "templateId": template_id, "rightWeight": right_weight,
        "note": "空串=沿用历史自动重量（⛔ 不用 0）",
    }
    cli = (f"python -m review_tool keepstrong --set-weight {aid} "
           f"{quote_arg(raw if raw else '')} --yes")
    return plan_out(tokens, "ks_set_weight",
                    {"date": today(), "action_id": aid, "weight": raw,
                     "weight_unit": weight_unit, "template_id": template_id,
                     "right_weight": right_weight},
                    preview=preview, cli=cli)


def plan_ks_log_body(tokens: TokenStore, metric: str, value, *,
                     day: str | None = None, unit: str | None = None,
                     env=None) -> dict[str, Any]:
    from ...integrations.keepstrong import to_day_str

    m = (metric or "").strip()
    if m not in _BODY_METRICS:
        raise QueryError(422, "invalid_param", f"metric 须在 {sorted(_BODY_METRICS)}")
    v = str(value).strip()
    if not v:
        raise QueryError(422, "invalid_param", "value 不能为空")
    day_str = to_day_str(day or today())
    u = (unit or _DEFAULT_BODY_UNIT.get(m) or "").strip()
    if not u:
        raise QueryError(422, "invalid_param", "unit 不能为空（如 kg / % / cm）")
    _ks_creds(env)
    preview = {"metric": m, "value": v, "unit": u, "dayStr": day_str,
               "note": "写回练练体征日志，不落库"}
    cli = (f"python -m review_tool keepstrong --log-body {m} {quote_arg(v)} "
           f"--day {day_str} --unit {u} --yes")
    return plan_out(tokens, "ks_log_body",
                    {"date": today(), "metric": m, "value": v,
                     "day_str": day_str, "unit": u},
                    preview=preview, cli=cli)


def plan_ks_schedule(tokens: TokenStore, day: str, name: str, actions: list[dict], *,
                     env=None) -> dict[str, Any]:
    from ...integrations.keepstrong import to_day_str

    nm = clean_text(name, field="课名", limit=60)
    if not isinstance(actions, list) or not actions:
        raise QueryError(422, "invalid_param", "排课 actions 不能为空")
    day_str = to_day_str(day or today())
    _ks_creds(env)
    preview = {"dayStr": day_str, "name": nm, "actions": actions,
               "note": "排课到练练，写回不落库"}
    cli = (f"python -m review_tool keepstrong --schedule --day {day_str} "
           f"--name {quote_arg(nm)} --actions-json <path> --yes")
    return plan_out(tokens, "ks_schedule",
                    {"date": today(), "day_str": day_str, "name": nm,
                     "actions": actions},
                    preview=preview, cli=cli)


def plan_ks_create_template(tokens: TokenStore, name: str, actions: list[dict], *,
                            template_id: str | None = None, env=None) -> dict[str, Any]:
    nm = clean_text(name, field="模板名", limit=60)
    if not isinstance(actions, list) or not actions:
        raise QueryError(422, "invalid_param", "模板 actions 不能为空")
    _ks_creds(env)
    preview = {"name": nm, "templateId": template_id, "actions": actions,
               "note": "创建 / 更新模板元数据，写回不落库"}
    cli = (f"python -m review_tool keepstrong --create-template --name {quote_arg(nm)} "
           f"--actions-json <path> --yes")
    return plan_out(tokens, "ks_create_template",
                    {"date": today(), "name": nm, "template_id": template_id,
                     "actions": actions},
                    preview=preview, cli=cli)


def plan_ks_replace_template_actions(tokens: TokenStore, template_id: str,
                                     actions: list[dict], *, env=None) -> dict[str, Any]:
    tid = (template_id or "").strip()
    if not ID_RE.match(tid):
        raise QueryError(422, "invalid_param", "templateId 不合法")
    if not isinstance(actions, list) or not actions:
        raise QueryError(422, "invalid_param", "模板 actions 不能为空")
    _ks_creds(env)
    preview = {"templateId": tid, "actions": actions,
               "note": "完整替换模板动作（非增量），写回不落库"}
    cli = (f"python -m review_tool keepstrong --replace-template-actions {tid} "
           f"--actions-json <path> --yes")
    return plan_out(tokens, "ks_replace_template_actions",
                    {"date": today(), "template_id": tid, "actions": actions},
                    preview=preview, cli=cli)


def plan_ks_plan_command(tokens: TokenStore, running_plan_id: str, command: str, *,
                         extra: dict[str, Any] | None = None, env=None) -> dict[str, Any]:
    pid = (running_plan_id or "").strip()
    if not ID_RE.match(pid):
        raise QueryError(422, "invalid_param", "runningPlanId 不合法")
    cmd = (command or "").strip()
    if cmd not in _PLAN_COMMANDS:
        raise QueryError(422, "invalid_param",
                         f"command 须在 {sorted(_PLAN_COMMANDS)}")
    _ks_creds(env)
    preview = {"runningPlanId": pid, "command": cmd, "extra": extra or {},
               "note": "running-plan 命令，写回不落库"}
    cli = (f"python -m review_tool keepstrong --plan-command {pid} {cmd} --yes")
    return plan_out(tokens, "ks_plan_command",
                    {"date": today(), "running_plan_id": pid, "command": cmd,
                     "extra": extra or {}},
                    preview=preview, cli=cli)


# ---------------------------------------------------------------------------
# apply：confirm 时才 POST（user_confirmed=True）；写回不落库
# ---------------------------------------------------------------------------

@register("ks_set_weight", "ks_log_body", "ks_schedule", "ks_create_template",
         "ks_replace_template_actions", "ks_plan_command", needs=("env", "ks_client"))
def _apply_ks(p: dict[str, Any], *, env=None, ks_client=None) -> dict[str, Any]:
    key = _ks_creds(env)
    client = _client(key, ks_client)
    action = p["action"]
    try:
        if action == "ks_set_weight":
            resp, idem = client.set_action_weight(
                p["action_id"], p["weight"], user_confirmed=True,
                weight_unit=p.get("weight_unit"), template_id=p.get("template_id"),
                right_weight=p.get("right_weight"))
        elif action == "ks_log_body":
            resp, idem = client.log_body_metric(
                p["metric"], p["value"], unit=p["unit"], day_str=p["day_str"],
                user_confirmed=True)
        elif action == "ks_schedule":
            resp, idem = client.schedule_workout(
                p["day_str"], p["name"], p["actions"], user_confirmed=True)
        elif action == "ks_create_template":
            resp, idem = client.create_template(
                p["name"], p["actions"], template_id=p.get("template_id"),
                user_confirmed=True)
        elif action == "ks_replace_template_actions":
            resp, idem = client.replace_template_actions(
                p["template_id"], p["actions"], user_confirmed=True)
        elif action == "ks_plan_command":
            resp, idem = client.running_plan_command(
                p["running_plan_id"], p["command"], user_confirmed=True,
                **p.get("extra", {}))
        else:  # pragma: no cover - 注册表已限
            raise QueryError(400, "bad_action", "未知练练写动作")
    except QueryError:
        raise
    except Exception as e:
        raise _map_ks_error(e) from e
    return {"written": True, "readback": True, "idempotency_key": idem,
            "upstream": resp, "db_changed": False}
