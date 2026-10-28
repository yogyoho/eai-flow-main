"""Definition service: validation, designer save, publish lifecycle, copy."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import (
    FlowDefinition,
    FlowInstance,
    FlowNode,
    FlowSkip,
)
from ..utils import next_id, to_json, utcnow
from .enums import ActivityStatus, NodeType, PublishStatus, SkipType
from .errors import ConflictError, NotFoundError, WorkflowError
from .serializers import build_def_json

_NODE_FIELDS = {
    "node_type": "nodeType",
    "node_code": "nodeCode",
    "node_name": "nodeName",
    "permission_flag": "permissionFlag",
    "node_ratio": "nodeRatio",
    "coordinate": "coordinate",
    "any_node_skip": "anyNodeSkip",
    "listener_type": "listenerType",
    "listener_path": "listenerPath",
    "form_custom": "formCustom",
    "form_path": "formPath",
}


def _get(payload: dict[str, Any], camel: str, snake: str | None = None, default: Any = None) -> Any:
    if camel in payload:
        return payload[camel]
    if snake and snake in payload:
        return payload[snake]
    return default


def normalize_ext(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        cleaned = [
            {"code": str(item.get("code")), "value": item.get("value")}
            for item in value
            if isinstance(item, dict) and item.get("code") not in (None, "")
        ]
        return json.dumps(cleaned, ensure_ascii=False)
    return to_json(value)


async def next_version(session: AsyncSession, flow_code: str) -> str:
    versions = list(
        (
            await session.execute(
                select(FlowDefinition.version).where(
                    FlowDefinition.flow_code == flow_code,
                    FlowDefinition.del_flag == "0",
                )
            )
        )
        .scalars()
        .all()
    )
    highest = 0
    for version in versions:
        try:
            highest = max(highest, int(version))
        except (TypeError, ValueError):
            continue
    return str(highest + 1)


async def get_definition(session: AsyncSession, definition_id: int) -> FlowDefinition:
    definition = await session.get(FlowDefinition, definition_id)
    if definition is None or definition.del_flag != "0":
        raise NotFoundError("流程定义不存在")
    return definition


async def get_definition_by_code(
    session: AsyncSession, flow_code: str, *, published: bool = False
) -> FlowDefinition | None:
    stmt = select(FlowDefinition).where(
        FlowDefinition.flow_code == flow_code,
        FlowDefinition.del_flag == "0",
    )
    if published:
        stmt = stmt.where(FlowDefinition.is_publish == PublishStatus.PUBLISHED)
    stmt = stmt.order_by(FlowDefinition.create_time.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


def validate_flow(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Port of ``FlowConfigUtil`` structural checks."""

    flow_name = _get(payload, "flowName", "flow_name", "")
    flow_code = _get(payload, "flowCode", "flow_code", "")
    if not flow_code:
        raise WorkflowError(f"【{flow_name or '未命名'}】流程 flowCode 为空")
    if not flow_name:
        raise WorkflowError("流程名称不能为空")

    raw_nodes = _get(payload, "nodeList", "node_list", []) or []
    if not raw_nodes:
        raise WorkflowError(f"【{flow_name}】流程没有节点")

    nodes: list[dict[str, Any]] = []
    codes: set[str] = set()
    start_count = 0
    end_count = 0
    for raw in raw_nodes:
        code = _get(raw, "nodeCode", "node_code")
        if not code:
            raise WorkflowError("节点编码不能为空")
        if code in codes:
            raise WorkflowError(f"节点编码重复：{code}")
        codes.add(code)
        node_type = _get(raw, "nodeType", "node_type", NodeType.BETWEEN)
        if node_type == NodeType.START:
            start_count += 1
        if node_type == NodeType.END:
            end_count += 1
        nodes.append(raw)

    if start_count == 0:
        raise WorkflowError(f"【{flow_name}】流程缺少开始节点")
    if start_count > 1:
        raise WorkflowError(f"【{flow_name}】流程只能有一个开始节点")
    if end_count == 0:
        raise WorkflowError(f"【{flow_name}】流程缺少结束节点")

    all_skips: list[dict[str, Any]] = []
    for raw in raw_nodes:
        now_code = _get(raw, "nodeCode", "node_code")
        for skip in _get(raw, "skipList", "skip_list", []) or []:
            next_code = _get(skip, "nextNodeCode", "next_node_code")
            if not next_code:
                raise WorkflowError(f"节点 {now_code} 存在未指定目标节点的跳转")
            if next_code not in codes:
                raise WorkflowError(f"节点 {now_code} 的跳转目标 {next_code} 不存在")
            target = next(node for node in nodes if _get(node, "nodeCode", "node_code") == next_code)
            skip_type = str(_get(skip, "skipType", "skip_type", SkipType.PASS) or SkipType.PASS)
            if _get(target, "nodeType", "node_type") == NodeType.START and skip_type != SkipType.REJECT:
                raise WorkflowError("只有退回边允许指向开始节点")
            all_skips.append(
                {
                    **skip,
                    "nowNodeCode": _get(skip, "nowNodeCode", "now_node_code", now_code),
                    "nextNodeCode": next_code,
                }
            )

    skip_now = {_get(skip, "nowNodeCode", "now_node_code") for skip in all_skips}
    for node in nodes:
        code = _get(node, "nodeCode", "node_code")
        node_type = _get(node, "nodeType", "node_type")
        if node_type != NodeType.END and code not in skip_now:
            raise WorkflowError(f"节点 {code} 没有配置出口跳转")
        if node_type == NodeType.END and code in skip_now:
            raise WorkflowError(f"结束节点 {code} 不允许配置出口跳转")

    # Ensure every node is reachable from start.
    outgoing: dict[str, list[str]] = {}
    for skip in all_skips:
        outgoing.setdefault(_get(skip, "nowNodeCode", "now_node_code"), []).append(
            _get(skip, "nextNodeCode", "next_node_code")
        )
    start_code = next(
        _get(node, "nodeCode", "node_code") for node in nodes if _get(node, "nodeType", "node_type") == NodeType.START
    )
    reachable: set[str] = {start_code}
    queue = [start_code]
    while queue:
        current = queue.pop()
        for target in outgoing.get(current, []):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    unreachable = codes - reachable
    if unreachable:
        raise WorkflowError(f"存在不可达节点：{', '.join(sorted(unreachable))}")

    return nodes, all_skips


async def save_def_json(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    only_node_skip: bool = False,
    actor: str = "system",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Port of ``DefServiceImpl.saveDef`` / ``WarmFlowService.saveJson``."""

    payload = dict(payload)
    if isinstance(payload.get("json"), str):
        payload = json.loads(payload["json"])

    raw_id = _get(payload, "id")
    definition = await session.get(FlowDefinition, int(raw_id)) if raw_id else None
    if raw_id and (definition is None or definition.del_flag != "0"):
        raise NotFoundError("流程定义不存在")

    nodes, skips = validate_flow(payload)

    now = utcnow()
    if definition is None:
        flow_code = str(_get(payload, "flowCode", "flow_code"))
        version = await next_version(session, flow_code)
        definition = FlowDefinition(
            id=next_id(),
            flow_code=flow_code,
            flow_name=str(_get(payload, "flowName", "flow_name")),
            model_value="CLASSICS",
            category=_get(payload, "category"),
            version=version,
            is_publish=PublishStatus.UNPUBLISHED,
            form_custom=str(_get(payload, "formCustom", "form_custom", "N") or "N"),
            form_path=_get(payload, "formPath", "form_path"),
            activity_status=ActivityStatus.ACTIVITY,
            listener_type=_get(payload, "listenerType", "listener_type"),
            listener_path=_get(payload, "listenerPath", "listener_path"),
            ext=normalize_ext(_get(payload, "ext")),
            create_time=now,
            create_by=actor,
            update_time=now,
            update_by=actor,
            tenant_id=tenant_id or str(_get(payload, "tenantId", "tenant_id", settings.default_tenant)),
        )
        session.add(definition)
        await session.flush()
    else:
        if not only_node_skip:
            definition.flow_name = str(_get(payload, "flowName", "flow_name", definition.flow_name))
            definition.model_value = "CLASSICS"
            definition.category = _get(payload, "category", default=definition.category)
            definition.form_custom = str(_get(payload, "formCustom", "form_custom", definition.form_custom) or "N")
            definition.form_path = _get(payload, "formPath", "form_path", definition.form_path)
            definition.listener_type = _get(payload, "listenerType", "listener_type", definition.listener_type)
            definition.listener_path = _get(payload, "listenerPath", "listener_path", definition.listener_path)
            definition.ext = normalize_ext(_get(payload, "ext", default=definition.ext))
            definition.update_time = now
            definition.update_by = actor

        await session.execute(delete(FlowNode).where(FlowNode.definition_id == definition.id))
        await session.execute(delete(FlowSkip).where(FlowSkip.definition_id == definition.id))
        await session.flush()

    tenant = definition.tenant_id
    version = definition.version
    for raw in nodes:
        node = FlowNode(
            id=next_id(),
            node_type=int(_get(raw, "nodeType", "node_type", NodeType.BETWEEN)),
            definition_id=definition.id,
            node_code=str(_get(raw, "nodeCode", "node_code")),
            node_name=_get(raw, "nodeName", "node_name"),
            permission_flag=_get(raw, "permissionFlag", "permission_flag"),
            node_ratio=str(_get(raw, "nodeRatio", "node_ratio", "0") or "0"),
            coordinate=_get(raw, "coordinate"),
            any_node_skip=_get(raw, "anyNodeSkip", "any_node_skip"),
            listener_type=_get(raw, "listenerType", "listener_type"),
            listener_path=_get(raw, "listenerPath", "listener_path"),
            form_custom=str(_get(raw, "formCustom", "form_custom", "N") or "N"),
            form_path=_get(raw, "formPath", "form_path"),
            version=version,
            ext=normalize_ext(_get(raw, "ext")),
            create_time=now,
            create_by=actor,
            update_time=now,
            update_by=actor,
            tenant_id=tenant,
        )
        session.add(node)

    # Map node code -> type for skip denormalized columns.
    code_types = {
        str(_get(raw, "nodeCode", "node_code")): int(_get(raw, "nodeType", "node_type", NodeType.BETWEEN))
        for raw in nodes
    }
    for raw in skips:
        now_code = str(_get(raw, "nowNodeCode", "now_node_code"))
        next_code = str(_get(raw, "nextNodeCode", "next_node_code"))
        skip = FlowSkip(
            id=next_id(),
            definition_id=definition.id,
            now_node_code=now_code,
            now_node_type=code_types.get(now_code),
            next_node_code=next_code,
            next_node_type=code_types.get(next_code),
            skip_name=_get(raw, "skipName", "skip_name"),
            skip_type=str(_get(raw, "skipType", "skip_type", SkipType.PASS) or SkipType.PASS),
            skip_condition=_get(raw, "skipCondition", "skip_condition"),
            coordinate=_get(raw, "coordinate"),
            create_time=now,
            create_by=actor,
            update_time=now,
            update_by=actor,
            tenant_id=tenant,
        )
        session.add(skip)

    await session.commit()
    await session.refresh(definition)
    return await build_def_json(session, definition)


async def create_definition(
    session: AsyncSession,
    *,
    flow_code: str,
    flow_name: str,
    category: str | None = None,
    form_custom: str = "N",
    form_path: str | None = None,
    listener_type: str | None = None,
    listener_path: str | None = None,
    ext: str | None = None,
    actor: str = "system",
    tenant_id: str | None = None,
) -> FlowDefinition:
    version = await next_version(session, flow_code)
    now = utcnow()
    definition = FlowDefinition(
        id=next_id(),
        flow_code=flow_code,
        flow_name=flow_name,
        model_value="CLASSICS",
        category=category,
        version=version,
        is_publish=PublishStatus.UNPUBLISHED,
        form_custom=form_custom or "N",
        form_path=form_path,
        activity_status=ActivityStatus.ACTIVITY,
        listener_type=listener_type,
        listener_path=listener_path,
        ext=ext,
        create_time=now,
        create_by=actor,
        update_time=now,
        update_by=actor,
        tenant_id=tenant_id or settings.default_tenant,
    )
    session.add(definition)
    await session.commit()
    await session.refresh(definition)
    return definition


async def update_definition(
    session: AsyncSession,
    definition_id: int,
    values: dict[str, Any],
    *,
    actor: str = "system",
) -> FlowDefinition:
    definition = await get_definition(session, definition_id)
    for field in (
        "flow_name",
        "category",
        "form_custom",
        "form_path",
        "listener_type",
        "listener_path",
        "ext",
    ):
        if field in values:
            setattr(definition, field, values[field])
    definition.update_by = actor
    definition.update_time = utcnow()
    await session.commit()
    await session.refresh(definition)
    return definition


async def delete_definition(session: AsyncSession, definition_id: int) -> None:
    definition = await get_definition(session, definition_id)
    count = (
        await session.execute(
            select(func.count()).select_from(FlowInstance).where(FlowInstance.definition_id == definition_id)
        )
    ).scalar_one()
    if count:
        raise ConflictError("该流程定义已产生实例，禁止删除")
    await session.execute(delete(FlowNode).where(FlowNode.definition_id == definition_id))
    await session.execute(delete(FlowSkip).where(FlowSkip.definition_id == definition_id))
    definition.del_flag = "1"
    definition.update_time = utcnow()
    await session.commit()


async def publish_definition(session: AsyncSession, definition_id: int, *, actor: str = "system") -> FlowDefinition:
    definition = await get_definition(session, definition_id)
    node_count = (
        await session.execute(select(func.count()).select_from(FlowNode).where(FlowNode.definition_id == definition_id))
    ).scalar_one()
    if not node_count:
        raise WorkflowError("请先绘制流程再发布")

    others = list(
        (
            await session.execute(
                select(FlowDefinition).where(
                    FlowDefinition.flow_code == definition.flow_code,
                    FlowDefinition.id != definition.id,
                    FlowDefinition.is_publish == PublishStatus.PUBLISHED,
                    FlowDefinition.del_flag == "0",
                )
            )
        )
        .scalars()
        .all()
    )
    for other in others:
        used = (
            await session.execute(
                select(func.count()).select_from(FlowInstance).where(FlowInstance.definition_id == other.id)
            )
        ).scalar_one()
        other.is_publish = PublishStatus.EXPIRED if used else PublishStatus.UNPUBLISHED
        other.update_time = utcnow()
        other.update_by = actor

    definition.is_publish = PublishStatus.PUBLISHED
    definition.update_time = utcnow()
    definition.update_by = actor
    await session.commit()
    await session.refresh(definition)
    return definition


async def unpublish_definition(session: AsyncSession, definition_id: int, *, actor: str = "system") -> FlowDefinition:
    definition = await get_definition(session, definition_id)
    count = (
        await session.execute(
            select(func.count()).select_from(FlowInstance).where(FlowInstance.definition_id == definition_id)
        )
    ).scalar_one()
    if count:
        raise ConflictError("该流程定义已产生实例，禁止取消发布")
    definition.is_publish = PublishStatus.UNPUBLISHED
    definition.update_time = utcnow()
    definition.update_by = actor
    await session.commit()
    await session.refresh(definition)
    return definition


async def set_activity(
    session: AsyncSession, definition_id: int, active: bool, *, actor: str = "system"
) -> FlowDefinition:
    definition = await get_definition(session, definition_id)
    target = ActivityStatus.ACTIVITY if active else ActivityStatus.SUSPENDED
    if definition.activity_status == target:
        raise WorkflowError("流程已处于目标状态")
    definition.activity_status = target
    definition.update_time = utcnow()
    definition.update_by = actor
    await session.commit()
    await session.refresh(definition)
    return definition


async def copy_definition(session: AsyncSession, definition_id: int, *, actor: str = "system") -> FlowDefinition:
    source = await get_definition(session, definition_id)
    nodes = list(
        (await session.execute(select(FlowNode).where(FlowNode.definition_id == definition_id))).scalars().all()
    )
    skips = list(
        (await session.execute(select(FlowSkip).where(FlowSkip.definition_id == definition_id))).scalars().all()
    )
    version = await next_version(session, source.flow_code)
    now = utcnow()
    clone = FlowDefinition(
        id=next_id(),
        flow_code=source.flow_code,
        flow_name=source.flow_name,
        model_value="CLASSICS",
        category=source.category,
        version=version,
        is_publish=PublishStatus.UNPUBLISHED,
        form_custom=source.form_custom,
        form_path=source.form_path,
        activity_status=ActivityStatus.ACTIVITY,
        listener_type=source.listener_type,
        listener_path=source.listener_path,
        ext=source.ext,
        create_time=now,
        create_by=actor,
        update_time=now,
        update_by=actor,
        tenant_id=source.tenant_id,
    )
    session.add(clone)
    await session.flush()
    for node in nodes:
        session.add(
            FlowNode(
                id=next_id(),
                node_type=node.node_type,
                definition_id=clone.id,
                node_code=node.node_code,
                node_name=node.node_name,
                permission_flag=node.permission_flag,
                node_ratio=node.node_ratio,
                coordinate=node.coordinate,
                any_node_skip=node.any_node_skip,
                listener_type=node.listener_type,
                listener_path=node.listener_path,
                form_custom=node.form_custom,
                form_path=node.form_path,
                version=version,
                ext=node.ext,
                create_time=now,
                create_by=actor,
                update_time=now,
                update_by=actor,
                tenant_id=clone.tenant_id,
            )
        )
    for skip in skips:
        session.add(
            FlowSkip(
                id=next_id(),
                definition_id=clone.id,
                now_node_code=skip.now_node_code,
                now_node_type=skip.now_node_type,
                next_node_code=skip.next_node_code,
                next_node_type=skip.next_node_type,
                skip_name=skip.skip_name,
                skip_type=skip.skip_type,
                skip_condition=skip.skip_condition,
                coordinate=skip.coordinate,
                create_time=now,
                create_by=actor,
                update_time=now,
                update_by=actor,
                tenant_id=clone.tenant_id,
            )
        )
    await session.commit()
    await session.refresh(clone)
    return clone


async def import_def_json(
    session: AsyncSession, payload: dict[str, Any], *, actor: str = "system", tenant_id: str | None = None
) -> FlowDefinition:
    payload = dict(payload)
    payload.pop("id", None)
    payload.pop("version", None)
    payload.pop("isPublish", None)
    payload["flowCode"] = payload.get("flowCode") or payload.get("flow_code")
    payload["flowName"] = payload.get("flowName") or payload.get("flow_name") or payload["flowCode"]
    await save_def_json(session, payload, actor=actor, tenant_id=tenant_id)
    definition = await get_definition_by_code(session, str(payload["flowCode"]))
    if definition is None:  # pragma: no cover - defensive
        raise WorkflowError("导入失败")
    return definition


async def export_def_json(session: AsyncSession, definition_id: int) -> dict[str, Any]:
    definition = await get_definition(session, definition_id)
    payload = await build_def_json(session, definition)
    payload["isPublish"] = None
    return payload
