"""ORM → API/designer serializers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    FlowDefinition,
    FlowForm,
    FlowHisTask,
    FlowInstance,
    FlowNode,
    FlowSkip,
    FlowTask,
    FlowUser,
)
from ..utils import from_json
from .enums import CHART_COLORS, COOPERATE_LABELS, FLOW_STATUS_LABELS, FLOW_STATUS_TONE, NODE_TYPE_VALUE
from .errors import WorkflowError


def node_ext_list(raw: str | None) -> list[dict[str, Any]]:
    value = from_json(raw, [])
    if isinstance(value, dict):
        return [{"code": key, "value": item} for key, item in value.items()]
    return value if isinstance(value, list) else []


def definition_out(definition: FlowDefinition, *, flow_name: str | None = None) -> dict[str, Any]:
    return {
        "id": definition.id,
        "flow_code": definition.flow_code,
        "flow_name": flow_name or definition.flow_name,
        "model_value": "CLASSICS",
        "category": definition.category,
        "version": definition.version,
        "is_publish": definition.is_publish,
        "publish_label": {0: "未发布", 1: "已发布", 9: "已失效"}.get(definition.is_publish, "未知"),
        "form_custom": definition.form_custom,
        "form_path": definition.form_path,
        "activity_status": definition.activity_status,
        "listener_type": definition.listener_type,
        "listener_path": definition.listener_path,
        "ext": definition.ext,
        "create_time": definition.create_time,
        "create_by": definition.create_by,
        "update_time": definition.update_time,
        "update_by": definition.update_by,
        "tenant_id": definition.tenant_id,
    }


def form_out(form: FlowForm) -> dict[str, Any]:
    return {
        "id": form.id,
        "form_code": form.form_code,
        "form_name": form.form_name,
        "version": form.version,
        "is_publish": form.is_publish,
        "form_type": form.form_type,
        "form_content": form.form_content,
        "form_path": form.form_path,
        "ext": form.ext,
        "create_time": form.create_time,
        "create_by": form.create_by,
        "update_time": form.update_time,
        "tenant_id": form.tenant_id,
    }


def instance_out(instance: FlowInstance, *, flow_name: str | None = None) -> dict[str, Any]:
    return {
        "id": instance.id,
        "definition_id": instance.definition_id,
        "business_id": instance.business_id,
        "node_type": instance.node_type,
        "node_code": instance.node_code,
        "node_name": instance.node_name,
        "flow_status": instance.flow_status,
        "flow_status_label": FLOW_STATUS_LABELS.get(instance.flow_status, instance.flow_status),
        "flow_status_tone": FLOW_STATUS_TONE.get(instance.flow_status, "slate"),
        "activity_status": instance.activity_status,
        "variable": from_json(instance.variable, {}),
        "def_json": from_json(instance.def_json, {}),
        "create_time": instance.create_time,
        "create_by": instance.create_by,
        "update_time": instance.update_time,
        "ext": instance.ext,
        "flow_name": flow_name,
    }


def task_out(task: FlowTask, *, flow_name: str | None = None, business_id: str | None = None) -> dict[str, Any]:
    return {
        "id": task.id,
        "definition_id": task.definition_id,
        "instance_id": task.instance_id,
        "node_code": task.node_code,
        "node_name": task.node_name,
        "node_type": task.node_type,
        "flow_status": task.flow_status,
        "flow_status_label": FLOW_STATUS_LABELS.get(task.flow_status, task.flow_status),
        "form_custom": task.form_custom,
        "form_path": task.form_path,
        "create_time": task.create_time,
        "create_by": task.create_by,
        "flow_name": flow_name,
        "business_id": business_id,
    }


def his_out(his: FlowHisTask) -> dict[str, Any]:
    return {
        "id": his.id,
        "definition_id": his.definition_id,
        "instance_id": his.instance_id,
        "task_id": his.task_id,
        "node_code": his.node_code,
        "node_name": his.node_name,
        "node_type": his.node_type,
        "target_node_code": his.target_node_code,
        "target_node_name": his.target_node_name,
        "approver": his.approver,
        "cooperate_type": his.cooperate_type,
        "cooperate_label": COOPERATE_LABELS.get(his.cooperate_type, "审批"),
        "collaborator": his.collaborator,
        "skip_type": his.skip_type,
        "flow_status": his.flow_status,
        "flow_status_label": FLOW_STATUS_LABELS.get(his.flow_status, his.flow_status),
        "message": his.message,
        "variable": from_json(his.variable, {}),
        "create_time": his.create_time,
        "update_time": his.update_time,
        "form_custom": his.form_custom,
        "form_path": his.form_path,
    }


def user_out(user: FlowUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "type": user.type,
        "processed_by": user.processed_by,
        "associated": user.associated,
    }


def node_json(node: FlowNode, skips: list[FlowSkip], *, status: int | None = None) -> dict[str, Any]:
    return {
        "nodeType": node.node_type,
        "nodeCode": node.node_code,
        "nodeName": node.node_name,
        "permissionFlag": node.permission_flag,
        "nodeRatio": node.node_ratio or "0",
        "coordinate": node.coordinate,
        "anyNodeSkip": node.any_node_skip,
        "listenerType": node.listener_type,
        "listenerPath": node.listener_path,
        "formCustom": node.form_custom,
        "formPath": node.form_path,
        "ext": node.ext,
        "extMap": {},
        "status": status,
        "version": node.version,
        "createBy": node.create_by,
        "updateBy": node.update_by,
        "skipList": [skip_json(skip) for skip in skips],
    }


def skip_json(skip: FlowSkip, *, status: int | None = None) -> dict[str, Any]:
    return {
        "id": skip.id,
        "nowNodeCode": skip.now_node_code,
        "nowNodeType": skip.now_node_type,
        "nextNodeCode": skip.next_node_code,
        "nextNodeType": skip.next_node_type,
        "skipName": skip.skip_name,
        "skipType": skip.skip_type,
        "skipCondition": skip.skip_condition,
        "coordinate": skip.coordinate,
        "status": status,
        "expr": skip.skip_condition,
        "extMap": {},
        "promptContent": [],
        "createBy": skip.create_by,
        "updateBy": skip.update_by,
    }


async def _published_forms(session: AsyncSession) -> list[FlowForm]:
    return list(
        (
            await session.execute(
                select(FlowForm)
                .where(FlowForm.form_code.in_(select(FlowForm.form_code).where(FlowForm.is_publish == 1)))
                .order_by(FlowForm.create_time.desc())
            )
        )
        .scalars()
        .all()
    )


async def resolve_form_model(session: AsyncSession, form_path: str | None) -> FlowForm | None:
    """Resolve a pinned ``code:version`` form path, falling back to ``form_path``."""

    if not form_path:
        return None
    stmt = select(FlowForm).where(FlowForm.del_flag == "0")
    if ":" in form_path:
        code, _, version = form_path.partition(":")
        form = (
            await session.execute(
                stmt.where(FlowForm.form_code == code, FlowForm.version == version)
                .order_by(FlowForm.create_time.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if form is not None:
            return form
    return (await session.execute(stmt.where(FlowForm.form_path == form_path).limit(1))).scalar_one_or_none()


def form_snapshot_entry(form: FlowForm) -> dict[str, Any]:
    return {
        "id": form.id,
        "formCode": form.form_code,
        "formName": form.form_name,
        "version": form.version,
        "formType": form.form_type,
        "formPath": form.form_path or f"{form.form_code}:{form.version}",
        "formContent": form.form_content,
        "schema": from_json(form.form_content, {}),
    }


async def build_form_snapshot(session: AsyncSession, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Freeze every form referenced by a definition at instance start.

    A published definition that references a missing form is not startable: an
    empty/rolling form would make the instance's audit trail non-reproducible.
    """

    paths: list[str] = []
    if payload.get("formPath"):
        paths.append(str(payload["formPath"]))
    for node in payload.get("nodeList") or []:
        if node.get("formPath"):
            paths.append(str(node["formPath"]))

    snapshot: dict[str, dict[str, Any]] = {}
    for path in dict.fromkeys(paths):
        form = await resolve_form_model(session, path)
        if form is None:
            raise WorkflowError(f"流程引用的表单不存在：{path}")
        snapshot[path] = form_snapshot_entry(form)
    return snapshot


def snapshot_node(instance: FlowInstance, node_code: str) -> dict[str, Any] | None:
    snapshot = from_json(instance.def_json, {})
    return next(
        (item for item in snapshot.get("nodeList") or [] if item.get("nodeCode") == node_code),
        None,
    )


def snapshot_form(instance: FlowInstance, form_path: str | None) -> dict[str, Any] | None:
    if not form_path:
        return None
    snapshot = from_json(instance.def_json, {})
    forms = snapshot.get("formSnapshot") or {}
    if form_path in forms:
        return forms[form_path]
    code = form_path.partition(":")[0]
    return next(
        (item for path, item in forms.items() if path == form_path or (code and item.get("formCode") == code)),
        None,
    )


def snapshot_flow_name(instance: FlowInstance, fallback: str | None = None) -> str | None:
    snapshot = from_json(instance.def_json, {})
    return snapshot.get("flowName") or fallback


async def build_def_json(
    session: AsyncSession,
    definition: FlowDefinition,
    *,
    nodes: list[FlowNode] | None = None,
    skips: list[FlowSkip] | None = None,
    instance: FlowInstance | None = None,
) -> dict[str, Any]:
    if nodes is None:
        nodes = list(
            (await session.execute(select(FlowNode).where(FlowNode.definition_id == definition.id))).scalars().all()
        )
    if skips is None:
        skips = list(
            (await session.execute(select(FlowSkip).where(FlowSkip.definition_id == definition.id))).scalars().all()
        )

    grouped: dict[str, list[FlowSkip]] = {}
    for skip in skips:
        grouped.setdefault(skip.now_node_code, []).append(skip)

    # Instance snapshots already carry per-node/per-edge status.
    status_map: dict[str, int] = {}
    skip_status_map: dict[str, int] = {}
    if instance is not None:
        snapshot = from_json(instance.def_json, {})
        for node in snapshot.get("nodeList") or []:
            status_map[node.get("nodeCode")] = node.get("status")
            for skip in node.get("skipList") or []:
                skip_status_map[str(skip.get("id") or skip_key(skip))] = skip.get("status")

    categories = list(
        (
            await session.execute(
                select(FlowDefinition.category)
                .where(FlowDefinition.category.is_not(None), FlowDefinition.del_flag == "0")
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    forms = await _published_forms(session)

    payload: dict[str, Any] = {
        "id": definition.id,
        "flowCode": definition.flow_code,
        "flowName": definition.flow_name,
        "modelValue": "CLASSICS",
        "category": definition.category,
        "version": definition.version,
        "isPublish": definition.is_publish,
        "formCustom": definition.form_custom,
        "formPath": definition.form_path,
        "listenerType": definition.listener_type,
        "listenerPath": definition.listener_path,
        "ext": definition.ext,
        "extMap": from_json(definition.ext, {}),
        "createBy": definition.create_by,
        "updateBy": definition.update_by,
        "chartStatusColor": CHART_COLORS["CLASSICS"],
        "topText": definition.flow_name,
        "topTextShow": True,
        "categoryList": [{"value": item, "label": item} for item in categories if item],
        "formPathList": [
            {
                "value": form.form_path or f"{form.form_code}:{form.version}",
                "label": f"{form.form_name} ({form.version})",
                "id": form.id,
            }
            for form in forms
        ],
        "nodeList": [
            node_json(node, grouped.get(node.node_code, []), status=status_map.get(node.node_code))
            for node in sorted(nodes, key=lambda item: (item.node_type, item.id))
        ],
    }
    if instance is not None:
        payload["instance"] = instance_out(instance)
    return payload


def skip_key(skip: dict[str, Any]) -> str:
    return ":".join(
        [
            str(skip.get("nowNodeCode") or ""),
            str(skip.get("skipType") or ""),
            str(skip.get("skipCondition") or ""),
            str(skip.get("nextNodeCode") or ""),
        ]
    )


def node_type_value(node_type: int | None) -> str:
    return NODE_TYPE_VALUE.get(node_type or 0, "between")
