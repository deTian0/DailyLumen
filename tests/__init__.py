"""DailyLumen 测试包。"""
from __future__ import annotations

import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)


def _apply_github_actions_profile_fixture() -> None:
    """CI 无 local/.env：把非密钥个人参数夹具补进 os.environ（setdefault）。

    必须在任何 ``import review_tool.config`` 之前执行；仅 GITHUB_ACTIONS 触发，
    不覆盖本机已导出的环境变量，也不改写本机 local/.env。
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    path = os.path.join(TESTS_DIR, "fixtures", "ci.env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, val.strip())


_apply_github_actions_profile_fixture()
