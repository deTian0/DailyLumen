"""Web 看板路由：P2 写操作第一批（W9）。**仅 ``serve --enable-write`` 时挂载**。

两段式确认流：
1. ``POST /api/write/<动作>/plan`` → 预览 + 一次性 token + 等价 CLI（不写任何东西）
   动作：habits-sync / ai-draft / finalize（W9）· task-create / task-status / ingest（W10）·
   vision / inbox-archive / clickup-pull（W11）· ks-set-weight / ks-log-body / ks-schedule /
   ks-create-template / ks-replace-template-actions / ks-plan-command（W17，练练写回不落库）；
   ``GET /api/write/inbox`` 只读列收件箱图片
2. ``POST /api/write/confirm``（JSON ``{"token": ...}``）→ 执行预览过的内容，写后回读校验

全部是 POST：受 ``app.host_origin_guard`` 的 Host / Origin 校验；confirm 要求 JSON 体，
跨站表单无法构造（非简单请求触发 CORS 预检，而本服务不发 CORS 头）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import write_ops as wo
from .queries import readonly


class PlanOut(BaseModel):
    action: str
    token: str
    expires_in: int
    cli: str
    preview: dict[str, Any]


class ConfirmIn(BaseModel):
    token: str


class TaskCreateIn(BaseModel):
    name: str
    list_id: str | None = None


class TaskStatusIn(BaseModel):
    task_id: str
    status: str
    name: str | None = None


class IngestIn(BaseModel):
    path: str | None = None
    date: str | None = None
    allow_ai_draft: bool = False


class UploadIn(BaseModel):
    name: str | None = None
    data: str  # base64 或 data URL；服务端按文件头判类型、限大小


class VisionIn(BaseModel):
    date: str
    kind: str = "auto"
    uploads: list[UploadIn] = []
    inbox: list[str] = []


class InboxArchiveIn(BaseModel):
    date: str
    files: list[str]


class ClickupPullIn(BaseModel):
    days: int = 14


class BatchItemIn(BaseModel):
    task_id: str
    name: str | None = None


class TaskBatchIn(BaseModel):
    items: list[BatchItemIn]
    status: str = "complete"


# W17：练练写回（写回不落库）
class KsSetWeightIn(BaseModel):
    action_id: str
    weight: str | float | int | None = None
    weight_unit: str | None = None
    template_id: str | None = None
    right_weight: str | float | int | None = None


class KsLogBodyIn(BaseModel):
    metric: str
    value: str | float | int
    day: str | None = None
    unit: str | None = None


class KsScheduleIn(BaseModel):
    day: str
    name: str
    actions: list[dict[str, Any]]


class KsCreateTemplateIn(BaseModel):
    name: str
    actions: list[dict[str, Any]]
    template_id: str | None = None


class KsReplaceTemplateActionsIn(BaseModel):
    template_id: str
    actions: list[dict[str, Any]]


class KsPlanCommandIn(BaseModel):
    running_plan_id: str
    command: str
    extra: dict[str, Any] | None = None


class ConfirmOut(BaseModel):
    action: str
    date: str
    cli: str
    result: dict[str, Any]


def build_router(*, db_path: str | None = None, fetch=None, env=None, client=None,
                 mode: str | None = None, backup_dir: str | None = None,
                 tokens: wo.TokenStore | None = None, cu_client=None,
                 pull_fetch=None, ks_client=None) -> APIRouter:
    # pull_fetch(list_id, key) -> tasks：clickup-pull 用（与 habits 的 fetch(path, key) 签名不同）
    router = APIRouter(prefix="/api/write", tags=["write"])
    store = tokens or wo.TokenStore()

    @router.post("/habits-sync/plan", response_model=PlanOut)
    def plan_habits(date: str | None = Query(default=None)):
        return wo.plan_habits_sync(store, date, fetch=fetch, env=env)

    @router.post("/ai-draft/plan", response_model=PlanOut)
    def plan_ai(date: str | None = Query(default=None)):
        with readonly(db_path) as conn:
            return wo.plan_ai_draft(store, conn, date, client=client, mode=mode)

    @router.post("/finalize/plan", response_model=PlanOut)
    def plan_final(date: str = Query(...)):
        return wo.plan_finalize(store, date)

    @router.post("/task-create/plan", response_model=PlanOut)
    def plan_task_create(body: TaskCreateIn):
        return wo.plan_task_create(store, body.name, body.list_id, env=env)

    @router.post("/task-status/plan", response_model=PlanOut)
    def plan_task_status(body: TaskStatusIn):
        return wo.plan_task_status(store, body.task_id, body.status, name=body.name, env=env)

    # W12：批量改状态（一次预览 + 一个 token 对应一批）
    @router.post("/task-batch/plan", response_model=PlanOut)
    def plan_task_batch(body: TaskBatchIn):
        return wo.plan_task_batch(store, [i.model_dump() for i in body.items], body.status, env=env)

    @router.post("/ingest/plan", response_model=PlanOut)
    def plan_ingest(body: IngestIn):
        return wo.plan_ingest(store, path=body.path, day=body.date,
                              allow_ai_draft=body.allow_ai_draft)

    # W11 / FR-I2：读图日流程（vision → 写 md 数据块）+ 收件箱归档；clickup-pull 快照
    @router.get("/inbox")
    def get_inbox():
        return wo.list_inbox()

    # W12：收件箱缩略图（只读；_inbox_file 只收文件名 + realpath 限定收件箱顶层 + magic 嗅探）
    @router.get("/inbox/image")
    def get_inbox_image(name: str = Query(...)):
        path, media = wo.inbox_image(name)
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store",
                                                             "X-Content-Type-Options": "nosniff"})

    @router.post("/vision/plan", response_model=PlanOut)
    def plan_vision(body: VisionIn):
        return wo.plan_vision(store, body.date, kind=body.kind,
                              uploads=[u.model_dump() for u in body.uploads],
                              inbox=body.inbox, client=client, mode=mode)

    @router.post("/inbox-archive/plan", response_model=PlanOut)
    def plan_archive(body: InboxArchiveIn):
        return wo.plan_inbox_archive(store, body.date, body.files)

    @router.post("/clickup-pull/plan", response_model=PlanOut)
    def plan_pull(body: ClickupPullIn):
        return wo.plan_clickup_pull(store, days=body.days, env=env, fetch=pull_fetch, db_path=db_path)

    # W17：练练写回（写回不落库；预览零网络写，确认才 POST）
    @router.post("/ks-set-weight/plan", response_model=PlanOut)
    def plan_ks_weight(body: KsSetWeightIn):
        return wo.plan_ks_set_weight(store, body.action_id, body.weight,
                                     weight_unit=body.weight_unit,
                                     template_id=body.template_id,
                                     right_weight=body.right_weight, env=env)

    @router.post("/ks-log-body/plan", response_model=PlanOut)
    def plan_ks_log(body: KsLogBodyIn):
        return wo.plan_ks_log_body(store, body.metric, body.value, day=body.day,
                                   unit=body.unit, env=env)

    @router.post("/ks-schedule/plan", response_model=PlanOut)
    def plan_ks_schedule(body: KsScheduleIn):
        return wo.plan_ks_schedule(store, body.day, body.name, body.actions, env=env)

    @router.post("/ks-create-template/plan", response_model=PlanOut)
    def plan_ks_tpl(body: KsCreateTemplateIn):
        return wo.plan_ks_create_template(store, body.name, body.actions,
                                         template_id=body.template_id, env=env)

    @router.post("/ks-replace-template-actions/plan", response_model=PlanOut)
    def plan_ks_tpl_replace(body: KsReplaceTemplateActionsIn):
        return wo.plan_ks_replace_template_actions(store, body.template_id, body.actions, env=env)

    @router.post("/ks-plan-command/plan", response_model=PlanOut)
    def plan_ks_cmd(body: KsPlanCommandIn):
        return wo.plan_ks_plan_command(store, body.running_plan_id, body.command,
                                       extra=body.extra, env=env)

    @router.post("/confirm", response_model=ConfirmOut)
    def post_confirm(body: ConfirmIn):
        return wo.confirm(store, body.token, db_path=db_path, backup_dir=backup_dir,
                          env=env, cu_client=cu_client, ks_client=ks_client)

    return router
