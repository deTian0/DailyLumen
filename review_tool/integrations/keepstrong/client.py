"""练练健身（KeepStrong）HTTP 客户端（integrations 层）。

从 ``pipeline.keepstrong`` 抽离的网关：凭据 / 请求头 / Client 读写端点。
编排与 CLI 仍在 pipeline；本模块**不**依赖 pipeline / storage / reports。
"""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from ...config import KS_DEFAULTS, SETTINGS, TZ_OFFSET_HOURS, WEEKDAY_CN

# 产品名本地常量（避免 integrations → pipeline；render 模块可复用同字面量）
PRODUCT_CN = "练练健身"

TZ_OFFSET_MIN = TZ_OFFSET_HOURS * 60  # 东八区，分钟（API 的 X-Timezone-Offset 要分钟）

# 端点 pageSize 上限（见 API 参考）
RECORDS_PAGE_SIZE = 50
BODY_LOGS_PAGE_SIZE = 100
ACTIONS_PAGE_SIZE = 200
HISTORY_PAGE_SIZE = 50
TEMPLATES_PAGE_SIZE = 50
FOOD_SEARCH_PAGE_SIZE = 30
FOOD_LIST_PAGE_SIZE = 100
MAX_PAGES = 40

# M20：训练日 / 训练明细只认已完成记录（其余状态一律排除，不做延期补偿）
COMPLETED_STATUS = "completed"

# API 失败时 CLI 明示：勿误写「训练日: 否」，留给 ingest.fill_training_day 离线兜底
KeyGuidance = (
    f"请打开「{PRODUCT_CN}」App → 我的 → 连接 AI → 生成新 API Key → "
    "复制「AI 连接信息」→ 写入 `local/.env` 的 `KEEPSTRONG_API_KEY=` 后重试。"
)


class KeepStrongError(RuntimeError):
    """练练健身 API / 凭据相关错误的基类。"""


class CredError(KeepStrongError):
    """缺少 API Key。"""


class ApiKeyExpired(KeepStrongError):
    """401 + apiKeyExpired —— 停手，指引用户重新生成 Key。"""


class SkillUpdateRequired(KeepStrongError):
    """426 + skillUpdateRequired —— 技能文档过期。"""


class RateLimited(KeepStrongError):
    """429 —— 限流；携带 Retry-After 秒数。"""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


# --------------------------------------------------------------------- 日期
def to_day_str(value: str) -> str:
    """``YYYY-MM-DD`` / ``yyyyMMdd`` → ``yyyyMMdd``。"""
    s = (value or "").strip()
    if len(s) == 8 and s.isdigit():
        datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))  # 校验
        return s
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        datetime.date.fromisoformat(s)
        return s.replace("-", "")
    raise ValueError(f"日期格式应为 YYYY-MM-DD 或 yyyyMMdd，收到: {value!r}")


def day_str_to_iso(day_str: str) -> str:
    """``yyyyMMdd`` → ``YYYY-MM-DD``。"""
    d = to_day_str(day_str)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def iso_weekday_cn(iso_day: str) -> str:
    try:
        return WEEKDAY_CN[datetime.date.fromisoformat(iso_day).weekday()]
    except ValueError:
        return ""


def is_completed_record(rec: dict | None) -> bool:
    """``status == "completed"`` 才算已完成；缺失 / 未知取值一律排除。"""
    if not isinstance(rec, dict):
        return False
    status = rec.get("status")
    if status is None:
        return False
    return str(status).strip() == COMPLETED_STATUS


def filter_completed_records(records: list | None) -> list[dict]:
    """只保留已完成训练记录（M20 安全侧默认）。"""
    return [r for r in (records or []) if is_completed_record(r)]


# --------------------------------------------------------------------- 凭据
def load_api_key(*, env=None, settings=None) -> str:
    """读 ``KEEPSTRONG_API_KEY``：进程环境优先，其次 Settings（默认模块单例）。

    显式传入 ``settings=`` 时**不再回落到**模块级 ``SETTINGS``（方便测试注入空 key）。
    """
    env = os.environ if env is None else env
    key = (env.get("KEEPSTRONG_API_KEY") or "").strip()
    if key:
        return key
    src = settings if settings is not None else SETTINGS
    key = (getattr(src, "keepstrong_api_key", None) or "").strip()
    if not key:
        raise CredError(
            f"找不到{PRODUCT_CN} API Key（环境变量 / `.env` 的 KEEPSTRONG_API_KEY）。\n"
            f"  → {KeyGuidance}"
        )
    return key


def build_headers(
    api_key: str,
    *,
    skill_version: str | None = None,
    agent_name: str | None = None,
    timezone_offset: int = TZ_OFFSET_MIN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    """组装必需请求头（只读请求不带 Idempotency-Key）。"""
    h = {
        "Authorization": f"Bearer {api_key}",
        "X-KeepStrong-Skill-Version": skill_version
        or KS_DEFAULTS["skill_version"],
        "X-KeepStrong-Agent-Name": agent_name or KS_DEFAULTS["agent_name"],
        "X-Timezone-Offset": str(int(timezone_offset)),
        "Accept": "application/json",
    }
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
        h["Content-Type"] = "application/json"
    return h


def encode_query(params: dict[str, Any] | None) -> str:
    """查询串：值一律 ``quote``（含中文）；空值跳过。"""
    if not params:
        return ""
    parts: list[str] = []
    for k, v in params.items():
        if v is None:
            continue
        parts.append(
            f"{urllib.parse.quote(str(k), safe='')}="
            f"{urllib.parse.quote(str(v), safe='')}"
        )
    return "&".join(parts)


# --------------------------------------------------------------------- HTTP
def _parse_retry_after(headers) -> float | None:
    raw = None
    try:
        raw = headers.get("Retry-After")
    except Exception:
        raw = None
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def _read_json_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _raise_from_http(code: int, body: Any, headers) -> None:
    """按错误契约转成带指引的异常。"""
    data = body if isinstance(body, dict) else {}
    if code == 401 and data.get("apiKeyExpired"):
        raise ApiKeyExpired(
            f"{PRODUCT_CN} API Key 已失效（401 apiKeyExpired）。\n  → {KeyGuidance}"
        )
    if code == 426 and data.get("skillUpdateRequired"):
        skill_url = data.get("skillUrl") or (
            SETTINGS.keepstrong_base_url.rstrip("/") + "/api/v1/ai/skill"
        )
        raise SkillUpdateRequired(
            f"{PRODUCT_CN} 技能文档过期（426 skillUpdateRequired）。\n"
            f"  → 重新拉取 {skill_url}，替换 docs/练练健身-API参考.md，"
            f"更新 `.env` / KS_DEFAULTS 的 skillVersion 后重试。"
        )
    if code == 429:
        ra = _parse_retry_after(headers)
        msg = f"{PRODUCT_CN} 限流（429）"
        if ra is not None:
            msg += f"；Retry-After={ra}s"
        msg += "。请等待后再试，⛔ 不要紧循环重试。"
        raise RateLimited(msg, retry_after=ra)
    detail = ""
    if isinstance(data, dict) and data:
        detail = f"：{json.dumps(data, ensure_ascii=False)[:200]}"
    raise KeepStrongError(f"{PRODUCT_CN} HTTP {code}{detail}")


Opener = Callable[..., Any]
Sleeper = Callable[[float], None]


class Client:
    """练练健身 HTTP 客户端（可注入 ``urlopen`` / ``sleep``，测试全离线）。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        skill_version: str | None = None,
        agent_name: str | None = None,
        timeout: float | None = None,
        timezone_offset: int = TZ_OFFSET_MIN,
        urlopen: Opener | None = None,
        sleep: Sleeper | None = None,
        cache_dir: str | None = None,
    ):
        self.api_key = api_key
        self.base_url = (base_url or KS_DEFAULTS["base_url"]).rstrip("/")
        self.skill_version = skill_version or KS_DEFAULTS["skill_version"]
        self.agent_name = agent_name or KS_DEFAULTS["agent_name"]
        self.timeout = float(
            timeout if timeout is not None else KS_DEFAULTS["timeout_s"]
        )
        self.timezone_offset = timezone_offset
        self._urlopen = urlopen or urllib.request.urlopen
        self._sleep = sleep or time.sleep
        self.cache_dir = cache_dir or KS_DEFAULTS["cache_dir"]

    def _headers(self) -> dict[str, str]:
        return build_headers(
            self.api_key,
            skill_version=self.skill_version,
            agent_name=self.agent_name,
            timezone_offset=self.timezone_offset,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict | None = None,
        idempotency_key: str | None = None,
        _retried_429: bool = False,
    ) -> Any:
        """发请求；只读默认 GET。写请求（M19）传 body + idempotency_key。"""
        qs = encode_query(params)
        url = self.base_url + path + (("?" + qs) if qs else "")
        headers = self._headers()
        data = None
        if body is not None:
            headers = build_headers(
                self.api_key,
                skill_version=self.skill_version,
                agent_name=self.agent_name,
                timezone_offset=self.timezone_offset,
                idempotency_key=idempotency_key or "",
            )
            if not idempotency_key:
                raise KeepStrongError("写请求必须带 Idempotency-Key")
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return _read_json_body(raw)
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            parsed = _read_json_body(raw)
            try:
                _raise_from_http(int(e.code), parsed, e.headers)
            except RateLimited as rl:
                # 尊重 Retry-After：最多睡一次再试；绝不紧循环
                if not _retried_429 and rl.retry_after is not None and rl.retry_after > 0:
                    self._sleep(float(rl.retry_after))
                    return self.request(
                        method, path, params=params, body=body,
                        idempotency_key=idempotency_key, _retried_429=True,
                    )
                raise
        except urllib.error.URLError as e:
            raise KeepStrongError(
                f"{PRODUCT_CN} 网络不可达：{getattr(e, 'reason', e)}"
            ) from e

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    # ---- 读端点 --------------------------------------------------------
    def training_records_page(
        self,
        start_date: str,
        end_date: str,
        *,
        page: int = 1,
        page_size: int = RECORDS_PAGE_SIZE,
    ) -> dict:
        return self.get(
            "/api/v1/ai/training/records",
            params={
                "startDate": to_day_str(start_date),
                "endDate": to_day_str(end_date),
                "page": page,
                "pageSize": min(int(page_size), RECORDS_PAGE_SIZE),
            },
        ) or {}

    def iter_training_records(self, start_date: str, end_date: str) -> list[dict]:
        """跟 ``hasMore`` 翻页，合并为 list；**只保留** ``status == completed``（M20）。"""
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.training_records_page(start_date, end_date, page=page)
            items = data.get("list") or data.get("records") or data.get("data") or []
            if isinstance(items, dict):
                items = items.get("list") or []
            if isinstance(items, list):
                out.extend(items)
            if not data.get("hasMore"):
                break
        return filter_completed_records(out)

    def running_plans(self) -> Any:
        return self.get("/api/v1/ai/training/running-plans")

    def body_profile(self) -> Any:
        return self.get("/api/v1/ai/body/profile")

    def body_logs(
        self,
        metric: str = "weight",
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        body_type: str | None = None,
    ) -> list[dict]:
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            params: dict[str, Any] = {
                "metric": metric,
                "page": page,
                "pageSize": BODY_LOGS_PAGE_SIZE,
            }
            if start_date:
                params["startDate"] = to_day_str(start_date)
            if end_date:
                params["endDate"] = to_day_str(end_date)
            if body_type:
                params["bodyType"] = body_type
            data = self.get("/api/v1/ai/body/logs", params=params) or {}
            items = data.get("list") or data.get("logs") or data.get("data") or []
            if isinstance(items, dict):
                items = items.get("list") or []
            out.extend(items if isinstance(items, list) else [])
            if not data.get("hasMore"):
                break
        return out

    def search_actions(self, keyword: str) -> list[dict]:
        """动作库搜索；keyword **必须**经 encode_query URL 编码。"""
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.get(
                "/api/v1/ai/training/actions",
                params={
                    "keyword": keyword,
                    "page": page,
                    "pageSize": ACTIONS_PAGE_SIZE,
                },
            ) or {}
            items = data.get("list") or data.get("actions") or data.get("data") or []
            if isinstance(items, dict):
                items = items.get("list") or []
            out.extend(items if isinstance(items, list) else [])
            if not data.get("hasMore"):
                break
        return out

    def action_history(
        self,
        action_id: str,
        start_date: str,
        end_date: str,
        *,
        page_size: int = HISTORY_PAGE_SIZE,
    ) -> list[dict]:
        """GET ``/training/actions/{id}/history``；跟 ``hasMore`` 翻页。

        中文无关；日期仍走 ``to_day_str``。**不**改 completed 过滤语义（本端点无 status）。
        """
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.get(
                f"/api/v1/ai/training/actions/{action_id}/history",
                params={
                    "startDate": to_day_str(start_date),
                    "endDate": to_day_str(end_date),
                    "page": page,
                    "pageSize": min(int(page_size), HISTORY_PAGE_SIZE),
                },
            ) or {}
            items = (
                data.get("list")
                or data.get("history")
                or data.get("records")
                or data.get("data")
                or []
            )
            if isinstance(items, dict):
                items = items.get("list") or []
            out.extend(items if isinstance(items, list) else [])
            if not data.get("hasMore"):
                break
        return out

    def templates(self, *, page_size: int = TEMPLATES_PAGE_SIZE) -> list[dict]:
        """GET ``/training/templates``；跟 ``hasMore`` 翻页。"""
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.get(
                "/api/v1/ai/training/templates",
                params={
                    "page": page,
                    "pageSize": min(int(page_size), TEMPLATES_PAGE_SIZE),
                },
            ) or {}
            items = data.get("list") or data.get("templates") or data.get("data") or []
            if isinstance(items, dict):
                items = items.get("list") or []
            out.extend(items if isinstance(items, list) else [])
            if not data.get("hasMore"):
                break
        return out

    def food_logs(self, day_str: str) -> Any:
        """GET ``/food/logs``（**一次一天**；最近 60 天）。默认不进 daily-pull。

        饮食权威仍在薄荷；本接口仅旁证 / 可选 CLI。
        """
        return self.get(
            "/api/v1/ai/food/logs",
            params={"dayStr": to_day_str(day_str)},
        )

    def food_search(self, keyword: str, *, page_size: int = FOOD_SEARCH_PAGE_SIZE) -> list[dict]:
        """GET ``/food/search``；keyword 经 ``encode_query``（含中文）。"""
        data = self.get(
            "/api/v1/ai/food/search",
            params={
                "keyword": keyword,
                "pageSize": min(int(page_size), FOOD_SEARCH_PAGE_SIZE),
            },
        ) or {}
        items = data.get("list") or data.get("foods") or data.get("data") or []
        if isinstance(items, dict):
            items = items.get("list") or []
        return list(items) if isinstance(items, list) else []

    # ---- 动作缓存（非权威，可丢）---------------------------------------
    def actions_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "keepstrong-actions.json")

    def load_actions_cache(self) -> dict[str, str]:
        """``{actionId: name}``；文件不存在 → 空 dict。"""
        p = self.actions_cache_path()
        if not os.path.isfile(p):
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return {str(k): str(v) for k, v in (data or {}).items()}
        except (OSError, ValueError):
            return {}

    def save_actions_cache(self, mapping: dict[str, str]) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        p = self.actions_cache_path()
        payload = json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True)
        with open(p, "wb") as f:
            f.write(payload.replace("\r\n", "\n").encode("utf-8"))

    def remember_actions(self, actions: list[dict]) -> None:
        """把本次见到的 actionId→name 合并进缓存。"""
        cache = self.load_actions_cache()
        changed = False
        for a in actions or []:
            aid = a.get("actionId") or a.get("id")
            name = a.get("name") or a.get("actionName")
            if aid and name and cache.get(str(aid)) != str(name):
                cache[str(aid)] = str(name)
                changed = True
        if changed:
            self.save_actions_cache(cache)

    # ---- 写端点（M19 · 须 userConfirmed / CLI --yes）-------------------
    def post(
        self,
        path: str,
        body: dict,
        *,
        idempotency_key: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self.request(
            "POST", path, params=params, body=body, idempotency_key=idempotency_key
        )

    def set_action_weight(
        self,
        action_id: str,
        weight: str | float | int | None,
        *,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
        weight_unit: str | None = None,
        template_id: str | None = None,
        right_weight: str | float | int | None = None,
    ) -> tuple[Any, str]:
        """POST ``/training/actions/{id}/weight``。

        ``weight is None`` → 传空串 ``""``（沿用历史）；⛔ 不用 ``0``。
        返回 ``(响应体, idempotency_key)``。
        """
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        key = idempotency_key or new_idempotency_key()
        # 未指定 → 空串；显式 0 也拒绝（上游语义会关闭自动取值）
        if weight is None:
            w = ""
        else:
            w = str(weight).strip()
            if w == "0":
                raise KeepStrongError(
                    "重量不能传 0（会关闭历史自动取值）；未指定请省略参数以传空串"
                )
        body: dict[str, Any] = {"userConfirmed": True, "weight": w}
        if weight_unit is not None:
            body["weightUnit"] = weight_unit
        if template_id is not None:
            body["templateId"] = template_id
        if right_weight is not None:
            body["rightWeight"] = str(right_weight)
        resp = self.post(
            f"/api/v1/ai/training/actions/{action_id}/weight",
            body,
            idempotency_key=key,
        )
        verify_weight_response(action_id, w, resp)
        return resp, key

    def log_body_metric(
        self,
        metric: str,
        value: float | int | str,
        *,
        unit: str,
        day_str: str,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> tuple[Any, str]:
        """POST ``/body/logs``。写回**不落库**。"""
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        key = idempotency_key or new_idempotency_key()
        body = {
            "userConfirmed": True,
            "metric": metric,
            "value": float(value) if not isinstance(value, str) else value,
            "unit": unit,
            "dayStr": to_day_str(day_str),
        }
        resp = self.post("/api/v1/ai/body/logs", body, idempotency_key=key)
        verify_body_log_response(body, resp)
        return resp, key

    def schedule_workout(
        self,
        day_str: str,
        name: str,
        actions: list[dict],
        *,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> tuple[Any, str]:
        """POST ``/training/scheduled-workouts``。首版只支持普通组。"""
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        if not actions:
            raise KeepStrongError("排课 actions 不能为空")
        key = idempotency_key or new_idempotency_key()
        body = {
            "userConfirmed": True,
            "dayStr": to_day_str(day_str),
            "name": name,
            "actions": actions,
        }
        resp = self.post(
            "/api/v1/ai/training/scheduled-workouts", body, idempotency_key=key
        )
        verify_schedule_response(body, resp)
        return resp, key

    def create_template(
        self,
        name: str,
        actions: list[dict],
        *,
        template_id: str | None = None,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> tuple[Any, str]:
        """POST ``/training/templates``（创建或带 templateId 更新元数据）。"""
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        if not actions:
            raise KeepStrongError("模板 actions 不能为空")
        key = idempotency_key or new_idempotency_key()
        body: dict[str, Any] = {
            "userConfirmed": True,
            "name": name,
            "actions": actions,
        }
        if template_id is not None:
            body["templateId"] = template_id
        resp = self.post(
            "/api/v1/ai/training/templates", body, idempotency_key=key
        )
        verify_template_response(body, resp)
        return resp, key

    def replace_template_actions(
        self,
        template_id: str,
        actions: list[dict],
        *,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> tuple[Any, str]:
        """POST ``/training/templates/{id}/actions``（**完整替换**）。"""
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        if not actions:
            raise KeepStrongError("模板 actions 不能为空")
        key = idempotency_key or new_idempotency_key()
        body = {"userConfirmed": True, "actions": actions}
        resp = self.post(
            f"/api/v1/ai/training/templates/{template_id}/actions",
            body,
            idempotency_key=key,
        )
        verify_template_actions_response(template_id, resp)
        return resp, key

    def running_plan_command(
        self,
        running_plan_id: str,
        command: str,
        *,
        user_confirmed: bool = False,
        idempotency_key: str | None = None,
        **extra: Any,
    ) -> tuple[Any, str]:
        """POST ``/training/running-plans/{id}/commands``。

        ``command`` ∈ delay / cancel_rest / add_alternative / add_temporary_workout。
        """
        if not user_confirmed:
            raise KeepStrongError("写操作需要明确确认（userConfirmed / --yes）")
        allowed = {
            "delay",
            "cancel_rest",
            "add_alternative",
            "add_temporary_workout",
        }
        cmd = (command or "").strip()
        if cmd not in allowed:
            raise KeepStrongError(
                f"未知 running-plan command: {command!r}；允许 {sorted(allowed)}"
            )
        key = idempotency_key or new_idempotency_key()
        body: dict[str, Any] = {"userConfirmed": True, "command": cmd, **extra}
        resp = self.post(
            f"/api/v1/ai/training/running-plans/{running_plan_id}/commands",
            body,
            idempotency_key=key,
        )
        if not isinstance(resp, dict):
            raise KeepStrongError(f"计划命令返回体异常（非对象）: {resp!r}")
        return resp, key


def new_idempotency_key() -> str:
    """每次调用唯一；同一逻辑请求重试时应复用调用方持有的 key。"""
    return str(uuid.uuid4())


def verify_weight_response(action_id: str, weight: str, resp: Any) -> None:
    if not isinstance(resp, dict):
        raise KeepStrongError(f"设重量返回体异常（非对象）: {resp!r}")
    rid = resp.get("actionId")
    if rid is not None and str(rid) != str(action_id):
        raise KeepStrongError(
            f"返回 actionId 不一致：请求 {action_id}，返回 {rid}"
        )
    if weight != "" and resp.get("weight") is not None:
        if str(resp.get("weight")) != str(weight):
            raise KeepStrongError(
                f"返回 weight 不一致：请求 {weight!r}，返回 {resp.get('weight')!r}"
            )


def verify_body_log_response(request_body: dict, resp: Any) -> None:
    if not isinstance(resp, dict):
        raise KeepStrongError(f"记体重返回体异常（非对象）: {resp!r}")
    for k in ("metric", "dayStr"):
        if resp.get(k) is not None and str(resp.get(k)) != str(request_body.get(k)):
            raise KeepStrongError(
                f"返回 {k} 不一致：请求 {request_body.get(k)!r}，返回 {resp.get(k)!r}"
            )


def verify_schedule_response(request_body: dict, resp: Any) -> None:
    if not isinstance(resp, dict):
        raise KeepStrongError(f"排课返回体异常（非对象）: {resp!r}")
    if resp.get("dayStr") is not None and str(resp["dayStr"]) != str(
        request_body["dayStr"]
    ):
        raise KeepStrongError(
            f"返回 dayStr 不一致：请求 {request_body['dayStr']}，返回 {resp['dayStr']}"
        )


def verify_template_response(request_body: dict, resp: Any) -> None:
    if not isinstance(resp, dict):
        raise KeepStrongError(f"模板创建返回体异常（非对象）: {resp!r}")
    if resp.get("name") is not None and str(resp["name"]) != str(request_body["name"]):
        raise KeepStrongError(
            f"返回 name 不一致：请求 {request_body['name']!r}，返回 {resp.get('name')!r}"
        )
    req_tid = request_body.get("templateId")
    if req_tid is not None and resp.get("templateId") is not None:
        if str(resp["templateId"]) != str(req_tid):
            raise KeepStrongError(
                f"返回 templateId 不一致：请求 {req_tid}，返回 {resp['templateId']}"
            )


def verify_template_actions_response(template_id: str, resp: Any) -> None:
    if not isinstance(resp, dict):
        raise KeepStrongError(f"模板动作替换返回体异常（非对象）: {resp!r}")
    rid = resp.get("templateId")
    if rid is not None and str(rid) != str(template_id):
        raise KeepStrongError(
            f"返回 templateId 不一致：请求 {template_id}，返回 {rid}"
        )


