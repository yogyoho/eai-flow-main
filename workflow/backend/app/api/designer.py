"""Designer-compatible endpoints (mirrors ``WarmFlowController``)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..demo import ALL_HANDLERS, DEMO_DEPTS, DEMO_ROLES, DEMO_USERS, find_handler
from ..deps import RequestContext, get_context
from ..engine import definition as definition_service
from ..engine import runtime
from ..engine.chart import build_chart
from ..engine.enums import CHART_COLORS, COOPERATE_LABELS, FLOW_STATUS_LABELS, NODE_TYPE_VALUE, UserType
from ..engine.errors import NotFoundError, WorkflowError
from ..engine.serializers import (
    build_def_json,
    form_out,
    his_out,
    instance_out,
    resolve_form_model,
    snapshot_flow_name,
    snapshot_form,
    snapshot_node,
    task_out,
)
from ..models import FlowDefinition, FlowForm, FlowHisTask
from ..schemas import FormContentRequest
from ..utils import from_json, to_json, utcnow

router = APIRouter(prefix="/designer", tags=["workflow-designer"])

Db = Annotated[AsyncSession, Depends(get_db)]
Ctx = Annotated[RequestContext, Depends(get_context)]


def _skeleton() -> dict[str, Any]:
    return {
        "id": None,
        "flowCode": "",
        "flowName": "新建流程",
        "modelValue": "CLASSICS",
        "category": None,
        "version": None,
        "isPublish": 0,
        "formCustom": "N",
        "formPath": None,
        "listenerType": None,
        "listenerPath": None,
        "ext": None,
        "extMap": {},
        "chartStatusColor": CHART_COLORS["CLASSICS"],
        "topText": "新建流程",
        "topTextShow": True,
        "categoryList": [],
        "formPathList": [],
        "nodeList": [],
    }


def _form_payload(form: FlowForm | None) -> dict[str, Any]:
    if form is None:
        return {}
    return {
        "id": form.id,
        "formCode": form.form_code,
        "formName": form.form_name,
        "version": form.version,
        "formType": form.form_type,
        "formPath": form.form_path,
        "formContent": form.form_content,
        "schema": from_json(form.form_content, {}),
    }


@router.post("/save-json")
async def save_json(
    body: dict[str, Any] = Body(...),
    only_node_skip: bool = Header(default=False, alias="onlyNodeSkip"),
    db: Db = None,  # type: ignore[assignment]
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    payload = body.get("defJson") if isinstance(body.get("defJson"), dict) else body
    saved = await definition_service.save_def_json(
        db,
        payload,
        only_node_skip=bool(only_node_skip),
        actor=ctx.handler,
        tenant_id=ctx.tenant_id,
    )
    return {"code": 200, "msg": "保存成功", "data": saved}


@router.get("/query-def")
@router.get("/query-def/{definition_id}")
async def query_def(
    db: Db,
    definition_id: int | None = None,
    id: int | None = Query(default=None),
) -> dict[str, Any]:
    target = definition_id or id
    if not target:
        return _skeleton()
    definition = await definition_service.get_definition(db, target)
    return await build_def_json(db, definition)


@router.get("/query-flow-chart/{instance_id}")
async def query_flow_chart(instance_id: int, db: Db) -> dict[str, Any]:
    instance = await runtime.get_instance(db, instance_id)
    return await build_chart(db, instance)


@router.get("/handler-type")
async def handler_type() -> list[str]:
    return ["用户", "角色", "部门"]


@router.get("/handler-result")
async def handler_result(
    type: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    if type in ("角色", "role"):
        rows = DEMO_ROLES
    elif type in ("部门", "dept"):
        rows = DEMO_DEPTS
    elif type in ("用户", "user"):
        rows = DEMO_USERS
    else:
        rows = ALL_HANDLERS
    if keyword:
        rows = [
            row
            for row in rows
            if keyword in (row.get("handlerName") or "") or keyword in (row.get("handlerCode") or "")
        ]
    total = len(rows)
    start = (page - 1) * size
    paged = [{key: value for key, value in row.items() if key != "roles"} for row in rows[start : start + size]]
    return {
        "handlerAuths": {"rows": paged, "total": total, "page": page, "size": size},
        "treeSelections": [
            {
                "id": "d01",
                "label": "研发部",
                "children": [{"id": "u1001", "label": "张三"}, {"id": "u1004", "label": "赵六"}],
            },
            {"id": "d02", "label": "总经办", "children": [{"id": "u1002", "label": "李四"}]},
            {"id": "d03", "label": "财务部", "children": [{"id": "u1003", "label": "王五"}]},
        ],
    }


@router.get("/handler-feedback")
async def handler_feedback(
    storage_ids: str | None = Query(None, alias="storageIds"),
    handler_codes: str | None = Query(None, alias="handlerCodes"),
) -> list[dict[str, Any]]:
    values = [item.strip() for item in (storage_ids or handler_codes or "").split(",") if item.strip()]
    result = []
    for value in values:
        found = find_handler(value)
        result.append({"storageId": value, "handlerName": found["handlerName"] if found else value})
    return result


@router.get("/handler-dict")
async def handler_dict() -> list[dict[str, Any]]:
    return [{"label": item["handlerName"], "value": item["storageId"]} for item in ALL_HANDLERS]


@router.get("/published-form")
async def published_form(db: Db) -> list[dict[str, Any]]:
    forms = list(
        (
            await db.execute(
                select(FlowForm).where(FlowForm.is_publish == 1, FlowForm.del_flag == "0").order_by(FlowForm.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [form_out(form) for form in forms]


@router.get("/form-content/{form_id}")
async def get_form_content(form_id: int, db: Db) -> str:
    form = await db.get(FlowForm, form_id)
    if form is None or form.del_flag != "0":
        raise NotFoundError("表单不存在")
    return form.form_content or ""


@router.post("/form-content")
async def save_form_content(body: FormContentRequest, db: Db) -> dict[str, Any]:
    form_id = body.id or (body.form or {}).get("id")
    if not form_id:
        raise WorkflowError("表单 id 不能为空")
    form = await db.get(FlowForm, int(form_id))
    if form is None or form.del_flag != "0":
        raise NotFoundError("表单不存在")
    form.form_content = body.form_content or to_json((body.form or {}).get("formContent") or {})
    form.update_time = utcnow()
    await db.commit()
    return {"code": 200, "msg": "保存成功"}


async def _snapshot_form_payload(
    db: AsyncSession,
    instance,
    definition: FlowDefinition,
    form_path: str | None,
) -> dict[str, Any]:
    """Return the form exactly as it looked when the instance started."""

    frozen = snapshot_form(instance, form_path)
    if frozen is not None:
        return frozen
    # Legacy instances (and snapshots created before form freezing) fall back to
    # the current form row; new instances always carry ``formSnapshot``.
    form = await resolve_form_model(db, form_path)
    return _form_payload(form)


@router.get("/execute/load/{task_id}")
async def load_task(task_id: int, db: Db) -> dict[str, Any]:
    task = await runtime.get_task(db, task_id)
    instance = await runtime.get_instance(db, task.instance_id)
    definition = await definition_service.get_definition(db, task.definition_id)
    flow_name = snapshot_flow_name(instance, definition.flow_name)
    node = snapshot_node(instance, task.node_code)
    if node is None:
        payload = await build_def_json(db, definition, instance=instance)
        node = next(
            (item for item in payload.get("nodeList") or [] if item.get("nodeCode") == task.node_code),
            None,
        )
    form = await _snapshot_form_payload(db, instance, definition, task.form_path or definition.form_path)
    users = await runtime.task_users(db, task.id, (UserType.APPROVAL, UserType.TRANSFER, UserType.DEPUTE))
    variables = from_json(instance.variable, {})
    return {
        "id": task.id,
        "formContent": form.get("formContent"),
        "form": form,
        "data": {
            "task": {
                **task_out(task, flow_name=flow_name, business_id=instance.business_id),
                "assignees": [user.processed_by or "" for user in users],
                "variables": variables,
                "chart": from_json(instance.def_json, {}),
            },
            "instance": instance_out(instance, flow_name=flow_name),
            "node": node,
            "variables": variables,
        },
    }


@router.get("/execute/hisLoad/{his_task_id}")
async def his_load(his_task_id: int, db: Db) -> dict[str, Any]:
    his = await db.get(FlowHisTask, his_task_id)
    if his is None or his.del_flag != "0":
        raise NotFoundError("历史任务不存在")
    instance = await runtime.get_instance(db, his.instance_id)
    definition = await definition_service.get_definition(db, his.definition_id)
    flow_name = snapshot_flow_name(instance, definition.flow_name)
    form = await _snapshot_form_payload(db, instance, definition, his.form_path or definition.form_path)
    return {
        "id": his.id,
        "formContent": form.get("formContent"),
        "form": form,
        "data": {
            "hisTask": his_out(his),
            "instance": instance_out(instance, flow_name=flow_name),
            "variables": from_json(his.variable, {}),
        },
    }


@router.post("/execute/handle")
async def handle(
    form_data: dict[str, Any] = Body(default_factory=dict),
    task_id: int = Query(..., alias="taskId"),
    skip_type: str = Query("PASS", alias="skipType"),
    message: str = Query(""),
    node_code: str | None = Query(None, alias="nodeCode"),
    db: Db = None,  # type: ignore[assignment]
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    variables = {**form_data, "formData": form_data}
    instance = await runtime.handle_task(
        db,
        task_id,
        handler=ctx.handler,
        message=message,
        skip_type=skip_type,
        node_code=node_code,
        variables=variables,
        claims=ctx.claims,
    )
    return instance_out(instance)


@router.get("/node-ext")
async def node_ext() -> list[dict[str, Any]]:
    return [
        {"code": "approveType", "name": "审批类型", "type": "select", "options": ["单人", "多人"]},
        {"code": "timeoutHours", "name": "超时小时", "type": "number"},
        {"code": "notifyChannel", "name": "通知渠道", "type": "select", "options": ["站内", "邮件", "IM"]},
        {"code": "businessTip", "name": "业务提示", "type": "text"},
    ]


@router.get("/listener-list")
async def listener_list() -> list[dict[str, Any]]:
    return [
        {"type": "http", "name": "HTTP Webhook", "path": "https://example.com/hooks/flow"},
        {"type": "mq", "name": "消息队列", "path": "workflow.events"},
        {"type": "script", "name": "安全脚本", "path": "builtin://event-log"},
    ]


@router.get("/meta")
async def designer_meta() -> dict[str, Any]:
    return {
        "nodeTypes": NODE_TYPE_VALUE,
        "flowStatus": FLOW_STATUS_LABELS,
        "cooperateTypes": COOPERATE_LABELS,
        "chartColors": CHART_COLORS,
    }
