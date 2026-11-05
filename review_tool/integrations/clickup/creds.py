"""ClickUp 凭据解析（环境变量 / ``local/.env`` / MCP 兼容回退）。"""
from __future__ import annotations

import json
import os

from ...config import CLICKUP_MCP_PATH


class CredError(RuntimeError):
    """凭据缺失 / 不可读 —— 给可读提示，而不是抛裸 KeyError。"""


def load_creds(env=None, path: str | None = None) -> tuple[str, str | None]:
    """解析 ClickUp 凭据：环境变量优先，其次 ``~/.workbuddy/mcp.json``。

    返回 ``(api_key, team_id)``；``team_id`` 允许为 None（仅用于展示）。
    两处都没有 -> :class:`CredError`。
    """
    env = os.environ if env is None else env
    key = (env.get("CLICKUP_API_KEY") or "").strip()
    team = (env.get("CLICKUP_TEAM_ID") or "").strip() or None
    if key:
        return key, team

    p = CLICKUP_MCP_PATH if path is None else path
    try:
        with open(p, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise CredError(
            f"找不到 ClickUp 凭据：{p} 不存在，也没设环境变量 CLICKUP_API_KEY。\n"
            "  → 设 CLICKUP_API_KEY（+ CLICKUP_TEAM_ID），或把 MCP 配置写到该路径的 "
            "mcpServers.clickup.env 下。"
        ) from None
    except (OSError, ValueError) as e:
        raise CredError(
            f"读不了 ClickUp 凭据文件 {p}：{type(e).__name__}: {e}"
        ) from e

    block = (cfg.get("mcpServers", {}) or {}).get("clickup", {}) or {}
    block = block.get("env", {}) or {}
    key = (block.get("CLICKUP_API_KEY") or "").strip()
    team = (block.get("CLICKUP_TEAM_ID") or "").strip() or None
    if not key:
        raise CredError(
            f"{p} 里没有 mcpServers.clickup.env.CLICKUP_API_KEY。\n"
            "  → 补上该配置，或改用环境变量 CLICKUP_API_KEY。"
        )
    return key, team
