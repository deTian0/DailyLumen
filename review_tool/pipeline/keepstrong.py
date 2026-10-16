"""练练健身（KeepStrong）管道（M17 只读 / M18 落 md / M19 受控写回）。

用法::

    python -m review_tool keepstrong --date 20261001
    python -m review_tool keepstrong --date 2026-10-01 --write --ingest
    python -m review_tool keepstrong --set-weight act_xxx 60 --yes
    python -m review_tool keepstrong --log-body weight 82 --day 20261015 --yes
    python -m review_tool keepstrong --schedule --day 20261016 --name 全身A \\
        --actions-json acts.json --yes

边界
----
1. **读**：产 ``收件箱/keepstrong-素材-<日期>.md``；``--write`` 才改复盘 md。
2. **写回（M19）**：须 ``--yes``；不落库、不作系统状态；无确认零网络写调用。
3. **中文文案一律写「练练健身」**；查询参数必须 URL 编码。

退出码：0 = 成功；1 = 取数/写入失败；2 = 用法或凭据缺失。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from ..config import INBOX_DIR, KS_DEFAULTS, SETTINGS, TZ_OFFSET_HOURS, WEEKDAY_CN
from .keepstrong_render import PRODUCT_CN, render_material

# 产品名 PRODUCT_CN 的单一来源在 keepstrong_render（纯模块、零依赖），此处复用
INBOX_PREFIX = "keepstrong-素材"
TZ_OFFSET_MIN = TZ_OFFSET_HOURS * 60  # 东八区，分钟（API 的 X-Timezone-Offset 要分钟）

# 端点 pageSize 上限（见 API 参考）
RECORDS_PAGE_SIZE = 50
BODY_LOGS_PAGE_SIZE = 100
ACTIONS_PAGE_SIZE = 200
MAX_PAGES = 40

KeyGuidance = (
    f"请打开「{PRODUCT_CN}」App → 我的 → 连接 AI → 生成新 API Key → "
    "复制「AI 连接信息」→ 写入仓库根 `.env` 的 `KEEPSTRONG_API_KEY=` 后重试。"
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
        """跟 ``hasMore`` 翻页，合并为 list。"""
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.training_records_page(start_date, end_date, page=page)
            items = data.get("list") or data.get("records") or data.get("data") or []
            if isinstance(items, dict):
                items = items.get("list") or []
            out.extend(items if isinstance(items, list) else [])
            if not data.get("hasMore"):
                break
        return out

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
        records = client.iter_training_records(start_s, end_s)
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
    "keepstrong --set-weight <actionId> <kg|''> [--yes] | "
    "keepstrong --log-body <metric> <value> [--day D] [--unit U] [--yes] | "
    "keepstrong --schedule --day D --name N --actions-json PATH [--yes]"
)


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
    mode = "read"  # read | set_weight | log_body | schedule
    set_weight: list[str] = []
    log_body: list[str] = []
    sch_day = sch_name = sch_json = ""
    body_day = ""
    body_unit = "kg"
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
        elif a == "--name" or a.startswith("--name="):
            if a.startswith("--name="):
                sch_name = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise ValueError("--name 需要课名")
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
            if mode == "schedule":
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
    }


def _run_outbound(opts: dict[str, Any], client: Client) -> int:
    """M19 写回：无 --yes 只预览、零网络写；有 --yes 才 POST。"""
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
            print(f"写入失败: {e}", file=sys.stderr)
            return 1
        print(f"已写入（Idempotency-Key={key}）: {json.dumps(resp, ensure_ascii=False)}")
        print("提示：App 里可能需重启才可见。写回未入 DailyLumen 库。")
        return 0

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
            print(f"写入失败: {e}", file=sys.stderr)
            return 1
        print(f"已写入（Idempotency-Key={key}）: {json.dumps(resp, ensure_ascii=False)}")
        print("提示：App 里可能需重启才可见。写回未入 DailyLumen 库。")
        return 0

    if mode == "schedule":
        path = opts["sch_json"]
        try:
            with open(path, encoding="utf-8") as f:
                actions = json.load(f)
        except (OSError, ValueError) as e:
            print(f"读 actions-json 失败: {e}", file=sys.stderr)
            return 2
        if not isinstance(actions, list):
            print("--actions-json 须为 JSON 数组", file=sys.stderr)
            return 2
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
            print(f"写入失败: {e}", file=sys.stderr)
            return 1
        print(f"已写入（Idempotency-Key={key}）: {json.dumps(resp, ensure_ascii=False)}")
        print("提示：App 里可能需重启才可见。写回未入 DailyLumen 库。")
        return 0

    raise KeepStrongError(f"未知写模式: {mode}")


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

    if opts["mode"] != "read":
        return _run_outbound(opts, client)
    try:
        bundle = collect(
            opts["start"], opts["end"], types=opts["types"], client=client
        )
    except ApiKeyExpired as e:
        print(f"认证失败: {e}", file=sys.stderr)
        return 1
    except SkillUpdateRequired as e:
        print(f"技能过期: {e}", file=sys.stderr)
        return 1
    except RateLimited as e:
        print(f"限流: {e}", file=sys.stderr)
        return 1
    except KeepStrongError as e:
        print(f"取数失败: {e}", file=sys.stderr)
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
        # 若 API 未按日过滤干净，上面筛一遍；空列表 → 不写空章节
        try:
            summary = write_sync(
                md_path,
                records=day_records,
                body_logs=bundle.get("body_logs") or [],
                body_profile=bundle.get("body_profile"),
                day_str=opts["start"],
                dry_run=not opts["write"],
            )
        except OSError as e:
            print(f"写 md 失败: {e}", file=sys.stderr)
            return 1
        mode = "已写入" if opts["write"] and summary.get("changed") else (
            "dry-run" if not opts["write"] else "无变更"
        )
        print(
            f"同步复盘 md（{mode}）: {md_path}；"
            f"训练块={'是' if summary.get('training_written') else '否'}；"
            f"体重={summary.get('weight_kg')}"
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
