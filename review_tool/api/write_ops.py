"""Web 看板写操作门面（W9 起；W13 按域拆到 ``api/writes/``，本模块只做稳定导出）。

两段式：``plan_*`` 只算预览（不写任何东西），把「将要写的确切内容」存进服务端一次性
确认 token；``confirm(token)`` 才执行，且执行的正是预览过的内容（不二次拉 ClickUp /
不二次调 DeepSeek）。约束见 ``writes/base.py``；各域：

- ``writes/habits``     habits sync → ``habit_logs``（不碰 ``personal_tracks``，R3）
- ``writes/review_md``  AI 草稿写入 / 定稿（只写 md）
- ``writes/clickup``    建任务 / 改状态 / 批量 / clickup-pull 快照
- ``writes/ingest``     ingest 单文件（路径白名单、写前备份、写后回读）
- ``writes/vision``     读图 → 数据块、收件箱归档 / 缩略图
- ``writes/keepstrong`` 练练写回（W17：设重量 / 记体征 / 排课 / 模板 / 计划命令；写回不落库）

``confirm`` 分派走 ``writes.base`` 的注册表（``@register(action, needs=...)``）。
"""
from __future__ import annotations

from . import writes as _writes  # noqa: F401  （导入即登记全部动作）
from .writes.base import (
    TOKEN_TTL_S,
    TokenStore,
    confirm,
    registered_actions,
)
from .writes.clickup import (
    MAX_BATCH,
    plan_clickup_pull,
    plan_task_batch,
    plan_task_create,
    plan_task_status,
)
from .writes.habits import plan_habits_sync
from .writes.ingest import plan_ingest
from .writes.keepstrong import (
    plan_ks_create_template,
    plan_ks_log_body,
    plan_ks_plan_command,
    plan_ks_replace_template_actions,
    plan_ks_schedule,
    plan_ks_set_weight,
)
from .writes.review_md import plan_ai_draft, plan_finalize
from .writes.vision import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    inbox_image,
    list_inbox,
    plan_inbox_archive,
    plan_vision,
)

__all__ = [
    "MAX_BATCH", "MAX_IMAGES", "MAX_IMAGE_BYTES", "TOKEN_TTL_S", "TokenStore", "confirm",
    "inbox_image", "list_inbox", "plan_ai_draft", "plan_clickup_pull", "plan_finalize",
    "plan_habits_sync", "plan_inbox_archive", "plan_ingest", "plan_ks_create_template",
    "plan_ks_log_body", "plan_ks_plan_command", "plan_ks_replace_template_actions",
    "plan_ks_schedule", "plan_ks_set_weight", "plan_task_batch", "plan_task_create",
    "plan_task_status", "plan_vision", "registered_actions",
]
