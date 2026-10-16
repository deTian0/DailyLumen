"""零依赖 Settings 层：``.env`` 解析 + 环境变量覆盖 + 类型校验。

配置分层（见 ``docs/生活管家路线图.md`` M16 / 硬规则 12）：

| 层 | 放哪 | 本模块是否管 |
| --- | --- | --- |
| **凭据** | ``.env`` only | ✅ ``KEEPSTRONG_API_KEY`` / ``CLICKUP_API_KEY`` |
| **环境差异** | ``.env`` 可覆盖，代码给默认值 | ✅ 两源 baseUrl / timeout / DB 路径等 |
| **个人参数** | ``config.PROFILE``（入 git） | ⛔ 不进本模块 |
| **业务规则** | 代码（``SCORE_THRESHOLDS`` / ``FOOD_LIB`` …） | ⛔ 不进本模块 |

⛔ 零依赖：不引 pydantic / python-dotenv；标准库 ``dataclass`` + ``os.environ`` 即可。
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# 与 config 同口径的路径推导（settings 自洽，避免与 config 循环 import）
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = os.path.dirname(_PACKAGE_DIR)
_DEFAULT_DB_PATH = os.path.join(_PACKAGE_DIR, "reviews.db")
_DEFAULT_ENV_PATH = os.path.join(_BASE_DIR, ".env")

# 练练健身（KeepStrong）内置默认 —— M17 客户端与 .env.example 共用
DEFAULT_KEEPSTRONG_BASE_URL = "https://lianlian.gzyunke.cn"
DEFAULT_KEEPSTRONG_SKILL_VERSION = "1.28.0"
DEFAULT_KEEPSTRONG_AGENT_NAME = "WorkBuddy"
DEFAULT_KEEPSTRONG_TIMEOUT_S = 30.0
DEFAULT_KEEPSTRONG_CACHE_DIR = os.path.join(_BASE_DIR, ".workbuddy", "cache")

# ClickUp 内置默认 —— v1.25.0 起与 KeepStrong 对称纳管（此前 base_url 写死在
# ``pipeline/clickup.py``、timeout 默认值散在 7 处函数签名）
DEFAULT_CLICKUP_BASE_URL = "https://api.clickup.com/api/v2"
DEFAULT_CLICKUP_TIMEOUT_S = 60.0


class SettingsError(ValueError):
    """配置值类型非法时抛出；消息含变量名与期望类型。"""


@dataclass(frozen=True)
class Settings:
    """运行时配置快照（不可变）。

    凭据类字段允许空串（未配置）；调用方在真正发请求时再校验缺失。
    """

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


def parse_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """解析 ``KEY=VALUE`` 文件：支持 ``#`` 注释、空行、值两端单/双引号。

    不存在的路径 → 空 dict（不报错；``.env`` 是可选的）。
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


def _pick(
    key: str,
    *,
    environ: Mapping[str, str],
    file_vals: Mapping[str, str],
) -> str | None:
    """优先级：进程环境变量 > ``.env`` 文件 > 未设置（返回 None）。"""
    if key in environ:
        return environ[key]
    if key in file_vals:
        return file_vals[key]
    return None


def _as_str(name: str, raw: str | None, default: str = "") -> str:
    if raw is None:
        return default
    return raw.strip() if isinstance(raw, str) else str(raw)


def _as_optional_str(name: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    return s if s else None


def _as_float(name: str, raw: str | None, default: float) -> float:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise SettingsError(
            f"{name} 期望 float，得到 {raw!r}（无法转换）"
        ) from e


def _as_path(name: str, raw: str | None, default: str) -> str:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    s = raw.strip()
    if not os.path.isabs(s):
        s = os.path.normpath(os.path.join(_BASE_DIR, s))
    return s


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
        ``.env`` 路径；默认仓库根 ``.env``。传空串则跳过文件。
    environ:
        环境变量映射；默认 ``os.environ``。测试可注入。
    apply_to_environ:
        若 True，把 ``.env`` 里**尚未**出现在进程环境的键 ``setdefault`` 进去，
        让既有 ``clickup.load_creds`` 等读 ``os.environ`` 的代码自动看见 ``.env``。
        ⛔ 绝不覆盖已有环境变量（与常见 dotenv 行为一致）。
    """
    env_map: Mapping[str, str] = os.environ if environ is None else environ
    path = _DEFAULT_ENV_PATH if env_path is None else os.fspath(env_path)
    file_vals = parse_env_file(path) if path else {}

    if apply_to_environ and environ is None and file_vals:
        for k, v in file_vals.items():
            os.environ.setdefault(k, v)

    def g(key: str) -> str | None:
        return _pick(key, environ=env_map, file_vals=file_vals)

    cache_raw = g("KEEPSTRONG_CACHE_DIR")
    if cache_raw is None or not str(cache_raw).strip():
        cache_dir = DEFAULT_KEEPSTRONG_CACHE_DIR
    else:
        cache_dir = _as_path("KEEPSTRONG_CACHE_DIR", cache_raw, DEFAULT_KEEPSTRONG_CACHE_DIR)

    return Settings(
        keepstrong_api_key=_as_str("KEEPSTRONG_API_KEY", g("KEEPSTRONG_API_KEY"), ""),
        clickup_api_key=_as_str("CLICKUP_API_KEY", g("CLICKUP_API_KEY"), ""),
        clickup_team_id=_as_str("CLICKUP_TEAM_ID", g("CLICKUP_TEAM_ID"), ""),
        db_path=_as_path("DAILYLUMEN_DB_PATH", g("DAILYLUMEN_DB_PATH"), _DEFAULT_DB_PATH),
        history_src_dir=_as_optional_str(
            "DAILYLUMEN_HISTORY_SRC", g("DAILYLUMEN_HISTORY_SRC")
        ),
        keepstrong_base_url=_as_str(
            "KEEPSTRONG_BASE_URL", g("KEEPSTRONG_BASE_URL"), DEFAULT_KEEPSTRONG_BASE_URL
        ) or DEFAULT_KEEPSTRONG_BASE_URL,
        keepstrong_skill_version=_as_str(
            "KEEPSTRONG_SKILL_VERSION",
            g("KEEPSTRONG_SKILL_VERSION"),
            DEFAULT_KEEPSTRONG_SKILL_VERSION,
        ) or DEFAULT_KEEPSTRONG_SKILL_VERSION,
        keepstrong_agent_name=_as_str(
            "KEEPSTRONG_AGENT_NAME",
            g("KEEPSTRONG_AGENT_NAME"),
            DEFAULT_KEEPSTRONG_AGENT_NAME,
        ) or DEFAULT_KEEPSTRONG_AGENT_NAME,
        keepstrong_timeout_s=_as_float(
            "KEEPSTRONG_TIMEOUT_S", g("KEEPSTRONG_TIMEOUT_S"), DEFAULT_KEEPSTRONG_TIMEOUT_S
        ),
        keepstrong_cache_dir=cache_dir,
        clickup_base_url=_as_str(
            "CLICKUP_BASE_URL", g("CLICKUP_BASE_URL"), DEFAULT_CLICKUP_BASE_URL
        ) or DEFAULT_CLICKUP_BASE_URL,
        clickup_timeout_s=_as_float(
            "CLICKUP_TIMEOUT_S", g("CLICKUP_TIMEOUT_S"), DEFAULT_CLICKUP_TIMEOUT_S
        ),
    )


# 进程级单例：import config 时使用。测试请调用 ``load_settings(...)`` 注入。
SETTINGS = load_settings()
