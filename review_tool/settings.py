"""Pydantic Settings 层：默认读 ``local/.env`` + 环境变量覆盖 + 类型校验。

配置分层（见 ``docs/隐私与配置归一路线图.md`` M46–M47 / conventions §6）：

| 层 | 放哪 | 本模块是否管 |
| --- | --- | --- |
| **凭据** | ``local/.env`` only | ✅ ``KEEPSTRONG_API_KEY`` / ``CLICKUP_API_KEY`` |
| **环境差异** | ``local/.env`` 可覆盖，代码给默认值 | ✅ 两源 baseUrl / timeout / DB 路径等 |
| **个人参数** | ``local/.env``（M47）；代码仅安全空默认 | ✅ 身高 / 宏量 / 体重带 / list ID |
| **业务规则** | 代码（``SCORE_THRESHOLDS`` / ``FOOD_LIB`` …） | ⛔ 不进本模块（D7=B） |

运行时依赖：``pydantic`` + ``pydantic-settings``（D2 ✅）。
⛔ 不另引 ``python-dotenv`` 作为项目直接依赖（由 pydantic-settings 间接使用即可）。
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import AliasChoices, Field, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError as PydanticSettingsError

# 与 config 同口径的路径推导（settings 自洽，避免与 config 循环 import）
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_PACKAGE_DIR)
_LOCAL_DIR = os.path.join(_BASE_DIR, "local")
# M45：本机数据归一到 local/（远程仅占位；见 docs/隐私与配置归一路线图.md §2.3）
_DEFAULT_DB_PATH = os.path.join(_LOCAL_DIR, "reviews.db")
_DEFAULT_ENV_PATH = os.path.join(_LOCAL_DIR, ".env")
_LEGACY_ENV_PATH = os.path.join(_BASE_DIR, ".env")

# 练练健身（KeepStrong）内置默认 —— M17 客户端与 .env.example 共用
DEFAULT_KEEPSTRONG_BASE_URL = "https://lianlian.gzyunke.cn"
DEFAULT_KEEPSTRONG_SKILL_VERSION = "1.29.0"
DEFAULT_KEEPSTRONG_AGENT_NAME = "WorkBuddy"
DEFAULT_KEEPSTRONG_TIMEOUT_S = 30.0
DEFAULT_KEEPSTRONG_CACHE_DIR = os.path.join(_BASE_DIR, ".workbuddy", "cache")

# ClickUp 内置默认 —— v1.25.0 起与 KeepStrong 对称纳管
DEFAULT_CLICKUP_BASE_URL = "https://api.clickup.com/api/v2"
DEFAULT_CLICKUP_TIMEOUT_S = 60.0

# DeepSeek（L-1）—— 仅 mode=deepseek 使用；默认与官方 OpenAI 兼容端点对齐
DEFAULT_LLM_MODE = "workbuddy"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_TIMEOUT_S = 60.0
ALLOWED_LLM_MODES = frozenset({"workbuddy", "deepseek"})

# 环境变量名 ↔ 字段（错误消息与手工映射用）
_ENV_TO_FIELD: dict[str, str] = {
    "KEEPSTRONG_API_KEY": "keepstrong_api_key",
    "CLICKUP_API_KEY": "clickup_api_key",
    "CLICKUP_TEAM_ID": "clickup_team_id",
    "DAILYLUMEN_DB_PATH": "db_path",
    "DAILYLUMEN_HISTORY_SRC": "history_src_dir",
    "KEEPSTRONG_BASE_URL": "keepstrong_base_url",
    "KEEPSTRONG_SKILL_VERSION": "keepstrong_skill_version",
    "KEEPSTRONG_AGENT_NAME": "keepstrong_agent_name",
    "KEEPSTRONG_TIMEOUT_S": "keepstrong_timeout_s",
    "KEEPSTRONG_CACHE_DIR": "keepstrong_cache_dir",
    "CLICKUP_BASE_URL": "clickup_base_url",
    "CLICKUP_TIMEOUT_S": "clickup_timeout_s",
    # —— M47 个人参数 / list ID（D5=A）——
    "PROFILE_NAME": "profile_name",
    "PROFILE_HEIGHT_CM": "profile_height_cm",
    "PROFILE_CARBS_G": "profile_carbs_g",
    "PROFILE_PROTEIN_G": "profile_protein_g",
    "PROFILE_FAT_G": "profile_fat_g",
    "PROFILE_TRAINING_WEEKDAYS": "profile_training_weekdays",
    "PROFILE_BREAKFAST_WINDOW": "profile_breakfast_window",
    "BODY_WEIGHT_KG_LOW": "body_weight_kg_low",
    "BODY_WEIGHT_KG_HIGH": "body_weight_kg_high",
    "CLICKUP_LIST_DAILY": "clickup_list_daily",
    "CLICKUP_LIST_HABITS": "clickup_list_habits",
    "CLICKUP_LIST_WORK": "clickup_list_work",
    "CLICKUP_LIST_INCUBATOR": "clickup_list_incubator",
    "CLICKUP_LIST_ANNUAL": "clickup_list_annual",
    # —— L-1 LLM mode / DeepSeek ——
    "DAILYLUMEN_LLM_MODE": "llm_mode",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "DEEPSEEK_BASE_URL": "deepseek_base_url",
    "DEEPSEEK_MODEL": "deepseek_model",
    "DEEPSEEK_TIMEOUT_S": "deepseek_timeout_s",
    # —— 第三方集成能力开关（v1.59.0）——
    "INTEGRATION_CLICKUP_ENABLED": "integration_clickup_enabled",
    "INTEGRATION_KEEPSTRONG_ENABLED": "integration_keepstrong_enabled",
    "INTEGRATION_DEEPSEEK_ENABLED": "integration_deepseek_enabled",
    # —— W14 Web 看板最小鉴权（凭据，只放 local/.env）——
    "DAILYLUMEN_WEB_KEY": "web_key",
}
_FIELD_TO_ENV = {v: k for k, v in _ENV_TO_FIELD.items()}

# 可空数值字段：空串 → None（未配置）
_OPTIONAL_FLOAT_FIELDS = {
    "profile_height_cm",
    "profile_carbs_g",
    "profile_protein_g",
    "profile_fat_g",
    "body_weight_kg_low",
    "body_weight_kg_high",
}


class SettingsError(ValueError):
    """配置值类型非法时抛出；消息含变量名与期望类型。"""


class Settings(BaseSettings):
    """运行时配置快照（不可变）。

    凭据类字段允许空串（未配置）；调用方在真正发请求时再校验缺失。
    优先级：进程环境变量 > env 文件 > 字段默认值。
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,  # 允许 Field alias（如 DAILYLUMEN_LLM_MODE）与字段名并存
        # env_file 在 load_settings 里按路径动态传入，不写死在 model_config
    )

    # —— 凭据（.env only）——
    keepstrong_api_key: str = ""
    clickup_api_key: str = ""
    clickup_team_id: str = ""

    # —— 环境差异（有默认，.env / 环境变量可覆盖）——
    db_path: str = _DEFAULT_DB_PATH
    history_src_dir: str | None = None
    keepstrong_base_url: str = DEFAULT_KEEPSTRONG_BASE_URL
    keepstrong_skill_version: str = DEFAULT_KEEPSTRONG_SKILL_VERSION
    keepstrong_agent_name: str = DEFAULT_KEEPSTRONG_AGENT_NAME
    keepstrong_timeout_s: float = DEFAULT_KEEPSTRONG_TIMEOUT_S
    keepstrong_cache_dir: str = DEFAULT_KEEPSTRONG_CACHE_DIR
    clickup_base_url: str = DEFAULT_CLICKUP_BASE_URL
    clickup_timeout_s: float = DEFAULT_CLICKUP_TIMEOUT_S

    # —— 个人参数（M47；无 env 时为空/None，行为可预期）——
    profile_name: str = ""
    profile_height_cm: float | None = None
    profile_carbs_g: float | None = None
    profile_protein_g: float | None = None
    profile_fat_g: float | None = None
    # 逗号分隔「0=周一…6=周日」；未配置 → 空列表（离线兜底关闭）
    # NoDecode：禁止 pydantic-settings 按 JSON 解 list（我们接受 "0,1,2,4,5"）
    profile_training_weekdays: Annotated[list[int], NoDecode] = []
    profile_breakfast_window: str = "08:00-09:00"
    body_weight_kg_low: float | None = None
    body_weight_kg_high: float | None = None

    # —— ClickUp list ID（D5=A；未配置 → 空串，采集侧会表现为无 list）——
    clickup_list_daily: str = ""
    clickup_list_habits: str = ""
    clickup_list_work: str = ""
    clickup_list_incubator: str = ""
    clickup_list_annual: str = ""

    # —— L-1 LLM（互斥 mode；DeepSeek 凭据仅 deepseek 模式需要）——
    # 环境变量名是 DAILYLUMEN_LLM_MODE（≠ 字段名大写 LLM_MODE），须显式 alias
    llm_mode: str = Field(
        default=DEFAULT_LLM_MODE,
        validation_alias=AliasChoices("DAILYLUMEN_LLM_MODE", "llm_mode"),
    )
    deepseek_api_key: str = ""
    deepseek_base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    deepseek_timeout_s: float = DEFAULT_DEEPSEEK_TIMEOUT_S

    # —— 第三方集成开关（默认开；无 key 时命令友好提示，不静默打网）——
    # DeepSeek 另须 DAILYLUMEN_LLM_MODE=deepseek；开关关则强制不可用
    integration_clickup_enabled: bool = True
    integration_keepstrong_enabled: bool = True
    integration_deepseek_enabled: bool = True

    # —— W14 Web 看板最小鉴权：serve 必需；凭据，永不进日志 / 响应 / 前端 bundle ——
    web_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("DAILYLUMEN_WEB_KEY", "web_key"),
    )

    @field_validator(
        "keepstrong_base_url",
        "keepstrong_skill_version",
        "keepstrong_agent_name",
        "clickup_base_url",
        "deepseek_base_url",
        "deepseek_model",
        mode="before",
    )
    @classmethod
    def _blank_str_to_default_sentinel(cls, v: Any, info: ValidationInfo) -> Any:
        """空串回落默认（与旧 dataclass 层 ``or DEFAULT`` 行为一致）。"""
        if v is None:
            return v
        if isinstance(v, str) and not v.strip():
            defaults = {
                "keepstrong_base_url": DEFAULT_KEEPSTRONG_BASE_URL,
                "keepstrong_skill_version": DEFAULT_KEEPSTRONG_SKILL_VERSION,
                "keepstrong_agent_name": DEFAULT_KEEPSTRONG_AGENT_NAME,
                "clickup_base_url": DEFAULT_CLICKUP_BASE_URL,
                "deepseek_base_url": DEFAULT_DEEPSEEK_BASE_URL,
                "deepseek_model": DEFAULT_DEEPSEEK_MODEL,
            }
            return defaults.get(str(info.field_name), v)
        return v

    @field_validator("llm_mode", mode="before")
    @classmethod
    def _normalize_llm_mode(cls, v: Any) -> str:
        """空 → workbuddy；仅允许 workbuddy|deepseek（互斥）。"""
        if v is None or (isinstance(v, str) and not v.strip()):
            return DEFAULT_LLM_MODE
        s = str(v).strip().lower()
        if s not in ALLOWED_LLM_MODES:
            allowed = " | ".join(sorted(ALLOWED_LLM_MODES))
            raise ValueError(
                f"仅允许 {allowed}（互斥，同时仅一种）；得到 {v!r}"
            )
        return s

    @field_validator("history_src_dir", mode="before")
    @classmethod
    def _empty_history_to_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "profile_height_cm",
        "profile_carbs_g",
        "profile_protein_g",
        "profile_fat_g",
        "body_weight_kg_low",
        "body_weight_kg_high",
        mode="before",
    )
    @classmethod
    def _empty_optional_float(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("profile_training_weekdays", mode="before")
    @classmethod
    def _parse_training_weekdays(cls, v: Any) -> Any:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [int(x) for x in v]
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        return [int(p) for p in parts]

    @field_validator("db_path", "keepstrong_cache_dir", mode="after")
    @classmethod
    def _resolve_relative_path(cls, v: str) -> str:
        if not v:
            return v
        s = v.strip()
        if not os.path.isabs(s):
            s = os.path.normpath(os.path.join(_BASE_DIR, s))
        return s


def parse_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """解析 ``KEY=VALUE`` 文件：支持 ``#`` 注释、空行、值两端单/双引号。

    不存在的路径 → 空 dict（不报错；``.env`` 是可选的）。
    保留自研解析（与 apply_to_environ / 单测对齐）；生产加载走 pydantic-settings。
    """
    p = os.fspath(path)
    if not os.path.isfile(p):
        return {}
    with open(p, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _resolve_env_path(env_path: str | os.PathLike[str] | None) -> str | None:
    """默认 ``local/.env``；不存在则兼容探测仓库根旧 ``.env``；空串 → 不读文件。"""
    if env_path is None:
        if os.path.isfile(_DEFAULT_ENV_PATH):
            return _DEFAULT_ENV_PATH
        if os.path.isfile(_LEGACY_ENV_PATH):
            return _LEGACY_ENV_PATH
        return _DEFAULT_ENV_PATH
    path = os.fspath(env_path)
    return path if path else None


def _wrap_validation_error(exc: ValidationError) -> SettingsError:
    """把 pydantic ValidationError 收成含环境变量名的 SettingsError。"""
    for err in exc.errors():
        loc = err.get("loc") or ()
        field = str(loc[0]) if loc else ""
        env_name = _FIELD_TO_ENV.get(field, field.upper() if field else "CONFIG")
        input_val = err.get("input")
        typ = err.get("type", "")
        if "float" in typ or field.endswith("_timeout_s") or field.endswith("timeout_s"):
            return SettingsError(
                f"{env_name} 期望 float，得到 {input_val!r}（无法转换）"
            )
        if field == "llm_mode":
            return SettingsError(
                f"{env_name} 配置非法：{err.get('msg', exc)}"
            )
        return SettingsError(
            f"{env_name} 配置非法（{typ}）：{err.get('msg', exc)}"
        )
    return SettingsError(str(exc))


def _settings_from_env_map(merged: Mapping[str, str]) -> Settings:
    """仅从给定 KEY=VALUE 映射构造（测试注入；不读真实 os.environ）。

    BaseSettings 对未传入字段仍会查进程环境，故构造期间临时清空 ``os.environ``，
    只靠 init kwargs + 字段默认值，保证 ``environ={}`` 测到的是纯默认。
    """
    kwargs: dict[str, Any] = {}
    for env_key, field in _ENV_TO_FIELD.items():
        if env_key not in merged:
            continue
        raw = merged[env_key]
        if field in {
            "keepstrong_timeout_s",
            "clickup_timeout_s",
            "deepseek_timeout_s",
            "db_path",
            "keepstrong_cache_dir",
        }:
            if isinstance(raw, str) and raw.strip() == "":
                continue  # 空 → 用默认
        if field in _OPTIONAL_FLOAT_FIELDS and isinstance(raw, str) and raw.strip() == "":
            kwargs[field] = None
            continue
        kwargs[field] = raw

    saved = dict(os.environ)
    try:
        os.environ.clear()
        try:
            return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]
        except ValidationError as e:
            raise _wrap_validation_error(e) from e
    finally:
        os.environ.clear()
        os.environ.update(saved)


def load_settings(
    *,
    env_path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    apply_to_environ: bool = True,
) -> Settings:
    """加载 Settings。

    Parameters
    ----------
    env_path:
        ``.env`` 路径；默认 ``local/.env``（若不存在则兼容探测仓库根旧 ``.env``）。
        传空串则跳过文件。
    environ:
        环境变量映射；默认 ``os.environ``。测试可注入（此时不读真实进程环境）。
    apply_to_environ:
        若 True，把 ``.env`` 里**尚未**出现在进程环境的键 ``setdefault`` 进去，
        让既有 ``clickup.load_creds`` 等读 ``os.environ`` 的代码自动看见 ``.env``。
        ⛔ 绝不覆盖已有环境变量（与常见 dotenv 行为一致）。
    """
    path = _resolve_env_path(env_path)
    file_vals = parse_env_file(path) if path else {}

    if apply_to_environ and environ is None and file_vals:
        for k, v in file_vals.items():
            os.environ.setdefault(k, v)

    if environ is not None:
        # 优先级：注入的 environ > 文件；不读真实 os.environ
        merged: dict[str, str] = {**file_vals, **dict(environ)}
        return _settings_from_env_map(merged)

    try:
        # 生产路径：pydantic-settings 读 os.environ + env_file
        return Settings(_env_file=path)  # type: ignore[call-arg]
    except ValidationError as e:
        raise _wrap_validation_error(e) from e
    except PydanticSettingsError as e:
        raise SettingsError(str(e)) from e


# 进程级单例：import config 时使用。测试请调用 ``load_settings(...)`` 注入。
SETTINGS = load_settings()

__all__ = [
    "ALLOWED_LLM_MODES",
    "DEFAULT_CLICKUP_BASE_URL",
    "DEFAULT_CLICKUP_TIMEOUT_S",
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_DEEPSEEK_MODEL",
    "DEFAULT_DEEPSEEK_TIMEOUT_S",
    "DEFAULT_KEEPSTRONG_AGENT_NAME",
    "DEFAULT_KEEPSTRONG_BASE_URL",
    "DEFAULT_KEEPSTRONG_CACHE_DIR",
    "DEFAULT_KEEPSTRONG_SKILL_VERSION",
    "DEFAULT_KEEPSTRONG_TIMEOUT_S",
    "DEFAULT_LLM_MODE",
    "SETTINGS",
    "Settings",
    "SettingsError",
    "load_settings",
    "parse_env_file",
]
