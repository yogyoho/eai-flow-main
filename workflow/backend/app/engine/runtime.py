"""Runtime engine: start, approve/reject, revoke, terminate, delegate, chart."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import (
    FlowDefinition,
    FlowHisTask,
    FlowInstance,
    FlowNode,
    FlowTask,
    FlowUser,
)
from ..utils import from_json, next_id, split_permissions, to_json, utcnow
from .chart import build_chart, prepare_snapshot, skip_metadata, start_metadata
from .definition import get_definition, get_definition_by_code
from .enums import (
    ActivityStatus,
    ChartStatus,
    CooperateType,
    FlowStatus,
    NodeType,
    SkipType,
    UserType,
    is_end,
    is_start,
)
from .errors import ConflictError, ForbiddenError, NotFoundError, WorkflowError
from .expression import evaluate_condition, resolve_handlers
from .graph import FlowGraph, FlowGraphError, graph_from_snapshot, load_graph
from .serializers import build_def_json, build_form_snapshot, skip_key, snapshot_flow_name

# ---------------------------------------------------------------------------
# Lookups / helpers
# ---------------------------------------------------------------------------


async def get_instance(session: AsyncSession, instance_id: int) -> FlowInstance:
    instance = await session.get(FlowInstance, instance_id)
    if instance is None or instance.del_flag != "0":
        raise NotFoundError("流程实例不存在")
    return instance


async def get_task(session: AsyncSession, task_id: int) -> FlowTask:
    task = await session.get(FlowTask, task_id)
    if task is None or task.del_flag != "0":
        raise NotFoundError("待办任务不存在")
    return task


async def task_users(session: AsyncSession, task_id: int, types: tuple[str, ...] | None = None) -> list[FlowUser]:
    stmt = select(FlowUser).where(FlowUser.associated == task_id, FlowUser.del_flag == "0")
    if types:
        stmt = stmt.where(FlowUser.type.in_(types))
    return list((await session.execute(stmt)).scalars().all())


def user_matches(token: str | None, handler: str | None, claims: list[str] | None = None) -> bool:
    if not token:
        return False
    claims = claims or []
    # EAI administrators receive "*" from the identity resolver. It grants
    # platform-wide task handling without weakening definition-level handler
    # matching for regular users.
    if "*" in claims:
        return True
    if token == handler:
        return True
    if token in claims:
        return True
    for prefix in ("user:", "role:", "dept:"):
        if token.startswith(prefix):
            value = token[len(prefix) :]
            if prefix == "user:" and value == handler:
                return True
            if token in claims or value in claims or f"{prefix}{value}" in claims:
                return True
    return False


def _is_authorized(users: list[FlowUser], handler: str, claims: list[str] | None) -> bool:
    if not users:
        # Definitions without explicit handlers are intentionally claimable by
        # any authenticated user in this standalone port.
        return True
    return any(user_matches(user.processed_by, handler, claims) for user in users)


async def _definition_name(session: AsyncSession, definition_id: int) -> str | None:
    definition = await session.get(FlowDefinition, definition_id)
    return definition.flow_name if definition else None


async def _instance_graph(
    session: AsyncSession,
    instance: FlowInstance,
    definition: FlowDefinition,
) -> FlowGraph:
    """Use the frozen snapshot; only legacy instances fall back to live rows."""

    snapshot = from_json(instance.def_json, {})
    if snapshot.get("nodeList"):
        return graph_from_snapshot(snapshot, definition)
    return await load_graph(session, definition.id)


def _task_status(node_type: int, skip_type: str) -> str:
    if next(iter([node_type])) == NodeType.START:
        return FlowStatus.TO_BE_SUBMIT
    if node_type == NodeType.END:
        return FlowStatus.FINISHED
    if skip_type == SkipType.REJECT:
        return FlowStatus.REJECT
    return FlowStatus.APPROVAL


async def _add_users(
    session: AsyncSession,
    task: FlowTask,
    node: FlowNode,
    variables: dict[str, Any],
    *,
    actor: str,
) -> list[FlowUser]:
    tokens: list[str] = []
    for raw in split_permissions(node.permission_flag):
        tokens.extend(resolve_handlers(raw, variables))
    if not tokens:
        tokens = [actor or "system"]
    if (node.node_ratio or "").endswith("@@sequence"):
        tokens = tokens[:1]

    users: list[FlowUser] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        user = FlowUser(
            id=next_id(),
            type=UserType.APPROVAL,
            processed_by=token,
            associated=task.id,
            create_time=utcnow(),
            create_by=actor,
            update_time=utcnow(),
            update_by=actor,
            tenant_id=task.tenant_id,
        )
        session.add(user)
        users.append(user)
    return users


async def _create_task(
    session: AsyncSession,
    node: FlowNode,
    instance: FlowInstance,
    definition: FlowDefinition,
    *,
    actor: str,
    variables: dict[str, Any],
    assignee: str | None = None,
) -> FlowTask:
    task = FlowTask(
        id=next_id(),
        definition_id=definition.id,
        instance_id=instance.id,
        node_code=node.node_code,
        node_name=node.node_name,
        node_type=node.node_type,
        flow_status=_task_status(node.node_type, SkipType.PASS),
        form_custom=node.form_custom if node.form_path else definition.form_custom,
        form_path=node.form_path or definition.form_path,
        create_time=utcnow(),
        create_by=actor,
        update_time=utcnow(),
        update_by=actor,
        tenant_id=instance.tenant_id,
    )
    session.add(task)
    await session.flush()
    if node.node_type != NodeType.END:
        if assignee:
            await _add_task_users(session, task, [assignee], UserType.APPROVAL, actor)
        else:
            await _add_users(session, task, node, variables, actor=actor)
    return task


def _apply_variables(instance: FlowInstance, variables: dict[str, Any]) -> dict[str, Any]:
    merged = from_json(instance.variable, {})
    if not isinstance(merged, dict):
        merged = {}
    merged.update(variables or {})
    instance.variable = to_json(merged)
    return merged


def _join(values: list[str | None]) -> str:
    return ",".join(str(value) for value in values if value)


def _make_his(
    *,
    task: FlowTask,
    instance: FlowInstance,
    approver: str,
    skip_type: str,
    flow_status: str,
    targets: list[FlowNode] | None = None,
    message: str = "",
    variables: dict[str, Any] | None = None,
    cooperate_type: int = 0,
    collaborator: str | None = None,
    target_override: FlowNode | None = None,
    actor: str = "system",
) -> FlowHisTask:
    targets = targets or []
    if target_override is not None:
        target_codes = target_override.node_code
        target_names = target_override.node_name or target_override.node_code
    else:
        target_codes = _join([node.node_code for node in targets])
        target_names = _join([node.node_name or node.node_code for node in targets])
    return FlowHisTask(
        id=next_id(),
        definition_id=task.definition_id,
        instance_id=instance.id,
        task_id=task.id,
        node_code=task.node_code,
        node_name=task.node_name,
        node_type=task.node_type,
        target_node_code=target_codes or None,
        target_node_name=target_names or None,
        approver=approver,
        cooperate_type=cooperate_type,
        collaborator=collaborator,
        skip_type=skip_type,
        flow_status=flow_status,
        form_custom=task.form_custom,
        form_path=task.form_path,
        message=message,
        variable=to_json(variables or {}),
        create_time=utcnow(),
        update_time=utcnow(),
        create_by=actor,
        update_by=actor,
        tenant_id=instance.tenant_id,
    )


async def _remove_task(session: AsyncSession, task: FlowTask) -> None:
    await session.execute(delete(FlowUser).where(FlowUser.associated == task.id))
    task.del_flag = "1"
    task.update_time = utcnow()


async def _persist(session: AsyncSession, entity: Any, *, commit: bool) -> Any:
    """Commit a runtime mutation, or flush it into the caller's transaction.

    Temporal activities call runtime functions with ``commit=False`` so the
    domain writes, the command status and the outbox event commit atomically.
    The standalone/demo path keeps the original commit behaviour.
    """

    if commit:
        await session.commit()
        await session.refresh(entity)
    else:
        await session.flush()
    return entity


async def _skip_keys(
    graph: FlowGraph,
    now_code: str,
    targets: list[FlowNode],
    skip_type: str,
) -> list[str]:
    target_codes = {node.node_code for node in targets}
    keys: list[str] = []
    for skip in graph.outgoing.get(now_code, []):
        if (skip.skip_type or SkipType.PASS) != skip_type:
            continue
        if skip.next_node_code in target_codes:
            keys.append(
                str(skip.id)
                if skip.id
                else skip_key(
                    {
                        "nowNodeCode": skip.now_node_code,
                        "skipType": skip.skip_type,
                        "skipCondition": skip.skip_condition,
                        "nextNodeCode": skip.next_node_code,
                    }
                )
            )
    return keys


def _snapshot_geometry(node: dict[str, Any]) -> tuple[int, int, int, int]:
    point = str(node.get("coordinate") or "0,0").split("|")[0]
    try:
        x_text, y_text = point.split(",", 1)
        x, y = int(x_text), int(y_text)
    except (TypeError, ValueError):
        x, y = 0, 0
    node_type = int(node.get("nodeType") or NodeType.BETWEEN)
    if node_type in (NodeType.START, NodeType.END):
        return x, y, 28, 28
    if node_type >= NodeType.SERIAL:
        return x, y, 30, 30
    return x, y, 88, 26


def _return_edge_coordinate(source: dict[str, Any], target: dict[str, Any]) -> str:
    """Route a return edge above the row so it cannot be mistaken for a reject edge."""

    sx, sy, _, sh = _snapshot_geometry(source)
    tx, ty, _, th = _snapshot_geometry(target)
    start_y = sy - sh
    end_y = ty - th
    route_y = min(start_y, end_y) - 64
    points = [(sx, start_y), (sx, route_y), (tx, route_y), (tx, end_y)]
    points_text = ";".join(f"{x},{y}" for x, y in points)
    text = ((sx + tx) // 2, route_y - 18)
    return f"{points_text}|{text[0]},{text[1]}"


async def _ensure_return_skip(
    session: AsyncSession,
    instance: FlowInstance,
    definition: FlowDefinition,
    now_node: FlowNode,
    start_node: FlowNode,
) -> tuple[dict[str, Any], str]:
    """Ensure the frozen instance snapshot contains its edge back to start."""

    snapshot = from_json(instance.def_json, {})
    nodes = {str(node.get("nodeCode")): node for node in snapshot.get("nodeList") or []}
    source = nodes.get(now_node.node_code)
    target = nodes.get(start_node.node_code)
    if source is None or target is None:
        raise WorkflowError("流程节点快照不完整，无法退回申请人")

    for skip in source.get("skipList") or []:
        if (
            str(skip.get("skipType") or "") == SkipType.REJECT
            and str(skip.get("nextNodeCode") or "") == start_node.node_code
        ):
            return snapshot, str(skip.get("id") or skip_key(skip))

    fresh = await build_def_json(session, definition)
    coordinate: str | None = None
    for node in fresh.get("nodeList") or []:
        if str(node.get("nodeCode") or "") != now_node.node_code:
            continue
        for skip in node.get("skipList") or []:
            if (
                str(skip.get("skipType") or "") == SkipType.REJECT
                and str(skip.get("nextNodeCode") or "") == start_node.node_code
            ):
                coordinate = str(skip.get("coordinate") or "") or None
                break
    entry = {
        "nowNodeCode": now_node.node_code,
        "nowNodeType": now_node.node_type,
        "nextNodeCode": start_node.node_code,
        "nextNodeType": start_node.node_type,
        "skipName": "退回申请人",
        "skipType": SkipType.REJECT,
        "skipCondition": None,
        "coordinate": coordinate or _return_edge_coordinate(source, target),
        "status": ChartStatus.NOT_DONE,
    }
    source.setdefault("skipList", []).append(entry)
    return snapshot, skip_key(entry)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


async def start_instance(
    session: AsyncSession,
    *,
    flow_code: str,
    business_id: str = "",
    handler: str = "system",
    variables: dict[str, Any] | None = None,
    flow_status: str | None = None,
    ext: str | None = None,
    tenant_id: str | None = None,
    commit: bool = True,
) -> FlowInstance:
    variables = variables or {}
    if not flow_code:
        raise WorkflowError("flowCode 不能为空")
    definition = await get_definition_by_code(session, flow_code, published=True)
    if definition is None:
        raise WorkflowError("未找到已发布的流程定义")
    if definition.activity_status == ActivityStatus.SUSPENDED:
        raise WorkflowError("流程定义已挂起")

    graph = await load_graph(session, definition.id)
    start = graph.start_node
    targets = graph.next_nodes(start, skip_type=SkipType.PASS, variables=variables)
    if not targets:
        raise WorkflowError("开始节点没有可到达的后续节点")

    payload = await build_def_json(session, definition, nodes=list(graph.nodes.values()), skips=graph.skips)
    # Freeze every referenced form alongside the definition graph. Existing
    # instances must remain reproducible after forms/definitions are edited.
    payload["formSnapshot"] = await build_form_snapshot(session, payload)
    snapshot = prepare_snapshot(payload)

    now = utcnow()
    instance = FlowInstance(
        id=next_id(),
        definition_id=definition.id,
        business_id=business_id or f"biz-{next_id()}",
        node_type=targets[0].node_type,
        node_code=targets[0].node_code,
        node_name=targets[0].node_name,
        variable=to_json(variables),
        flow_status=flow_status or FlowStatus.TO_BE_SUBMIT,
        activity_status=ActivityStatus.ACTIVITY,
        def_json="{}",
        create_time=now,
        create_by=handler,
        update_time=now,
        update_by=handler,
        ext=ext,
        tenant_id=tenant_id or definition.tenant_id or settings.default_tenant,
    )
    session.add(instance)
    await session.flush()

    start_task = FlowTask(
        id=next_id(),
        definition_id=definition.id,
        instance_id=instance.id,
        node_code=start.node_code,
        node_name=start.node_name,
        node_type=start.node_type,
        flow_status=FlowStatus.TO_BE_SUBMIT,
        create_time=now,
        create_by=handler,
        update_time=now,
        update_by=handler,
        tenant_id=instance.tenant_id,
    )
    his = _make_his(
        task=start_task,
        instance=instance,
        approver=handler,
        skip_type=SkipType.PASS,
        flow_status=flow_status or FlowStatus.TO_BE_SUBMIT,
        targets=targets,
        message="发起流程",
        variables=variables,
    )
    session.add(his)

    snapshot = start_metadata(
        snapshot,
        path_node_codes=[start.node_code],
        path_skip_keys=await _skip_keys(graph, start.node_code, targets, SkipType.PASS),
        target_node_codes=[node.node_code for node in targets],
    )

    has_end = any(is_end(node.node_type) for node in targets)
    for node in targets:
        if is_end(node.node_type):
            continue
        await _create_task(session, node, instance, definition, actor=handler, variables=variables)

    if has_end:
        end_node = next(node for node in targets if is_end(node.node_type))
        instance.node_type = end_node.node_type
        instance.node_code = end_node.node_code
        instance.node_name = end_node.node_name
        instance.flow_status = FlowStatus.FINISHED
    else:
        first = targets[0]
        instance.node_type = first.node_type
        instance.node_code = first.node_code
        instance.node_name = first.node_name
        instance.flow_status = flow_status or FlowStatus.TO_BE_SUBMIT

    instance.def_json = to_json(snapshot)
    instance.update_time = now
    return await _persist(session, instance, commit=commit)


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


async def handle_task(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    message: str = "",
    skip_type: str = SkipType.PASS,
    node_code: str | None = None,
    variables: dict[str, Any] | None = None,
    cooperate_type: int | None = None,
    ignore: bool = False,
    ignore_cooperate: bool = False,
    flow_status: str | None = None,
    his_status: str | None = None,
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowInstance:
    variables = variables or {}
    if skip_type not in (SkipType.PASS, SkipType.REJECT):
        raise WorkflowError("跳转类型必须是 PASS 或 REJECT")

    task = await get_task(session, task_id)
    if task.flow_status in (FlowStatus.FINISHED, FlowStatus.REJECT, FlowStatus.CANCEL, FlowStatus.TERMINATE):
        raise ConflictError("该任务已处理")
    instance = await get_instance(session, task.instance_id)
    if instance.activity_status == ActivityStatus.SUSPENDED:
        raise ConflictError("流程实例已挂起，无法审批")
    if instance.flow_status in (FlowStatus.FINISHED, FlowStatus.TERMINATE, FlowStatus.CANCEL, FlowStatus.NULLIFY):
        raise ConflictError("流程实例已结束")

    definition = await get_definition(session, instance.definition_id)
    graph = await _instance_graph(session, instance, definition)
    now_node = graph.node(task.node_code)
    merged = _apply_variables(instance, variables)

    users = await task_users(session, task.id, (UserType.APPROVAL, UserType.TRANSFER, UserType.DEPUTE))
    if not ignore and not _is_authorized(users, handler, claims):
        raise ForbiddenError("当前用户没有该任务的处理权限")

    # ---- countersign / vote-sign ----------------------------------------
    ratio = (now_node.node_ratio or "0").strip()
    approval_users = [u for u in users if u.type in (UserType.APPROVAL, UserType.TRANSFER)]
    total = len(approval_users)
    pending_others = [u for u in approval_users if not user_matches(u.processed_by, handler, claims)]
    done_stmt = select(FlowHisTask).where(
        FlowHisTask.instance_id == instance.id,
        FlowHisTask.node_code == task.node_code,
        FlowHisTask.cooperate_type == 0,
        FlowHisTask.skip_type.in_([SkipType.PASS, SkipType.REJECT]),
        FlowHisTask.del_flag == "0",
    )
    done = list((await session.execute(done_stmt)).scalars().all())
    pass_done = sum(1 for item in done if item.skip_type == SkipType.PASS)
    reject_done = sum(1 for item in done if item.skip_type == SkipType.REJECT)
    decided = True
    if not ignore_cooperate and total > 1:
        if ratio == "100":
            decided = not pending_others
        elif ratio.startswith("passCount="):
            threshold = int(ratio.split("=", 1)[1] or 0)
            decided = (skip_type == SkipType.PASS and pass_done + 1 >= threshold) or (
                skip_type == SkipType.REJECT and reject_done + 1 > total - threshold
            )
        elif ratio.startswith("rejectCount="):
            threshold = int(ratio.split("=", 1)[1] or 0)
            decided = (skip_type == SkipType.REJECT and reject_done + 1 >= threshold) or (
                skip_type == SkipType.PASS and pass_done + 1 > total - threshold
            )
        elif ratio.startswith(("default@@", "spel@@")):
            result = [item for item in done if evaluate_condition(ratio, {**merged, "skipType": skip_type})]
            decided = bool(result)
        else:
            try:
                threshold = float(ratio)
            except ValueError:
                threshold = 0
            if 0 < threshold < 100:
                pass_pct = (pass_done + (1 if skip_type == SkipType.PASS else 0)) / total * 100
                reject_pct = (reject_done + (1 if skip_type == SkipType.REJECT else 0)) / total * 100
                if skip_type == SkipType.PASS:
                    decided = pass_pct >= threshold
                else:
                    decided = reject_pct > (100 - threshold)
            else:
                decided = True

        if not decided:
            pending = _make_his(
                task=task,
                instance=instance,
                approver=handler,
                skip_type=skip_type,
                flow_status=FlowStatus.APPROVAL,
                message=message,
                variables=merged,
                target_override=now_node,
                actor=handler,
            )
            session.add(pending)
            for user in approval_users:
                if user_matches(user.processed_by, handler, claims):
                    user.del_flag = "1"
            instance.def_json = to_json(
                skip_metadata(
                    from_json(instance.def_json, {}),
                    path_node_codes=[now_node.node_code],
                    path_skip_keys=[],
                    target_node_codes=[now_node.node_code],
                    skip_type=skip_type,
                )
            )
            instance.update_time = utcnow()
            return await _persist(session, instance, commit=commit)

        if skip_type == SkipType.REJECT:
            # Countersign rejection: the remaining votes are no longer needed.
            for user in pending_others:
                user.del_flag = "1"

    # ---- compute next nodes ---------------------------------------------
    try:
        next_nodes = graph.next_nodes(now_node, node_code, skip_type, merged)
    except FlowGraphError as exc:
        raise WorkflowError(str(exc)) from exc

    targets = next_nodes
    has_end = any(is_end(node.node_type) for node in targets)
    target_codes = [node.node_code for node in targets]

    snapshot = skip_metadata(
        from_json(instance.def_json, {}),
        path_node_codes=[now_node.node_code],
        path_skip_keys=await _skip_keys(graph, now_node.node_code, targets, skip_type),
        target_node_codes=target_codes,
        skip_type=skip_type,
    )

    resolved_his_status = his_status or (
        FlowStatus.FINISHED if has_end else FlowStatus.REJECT if skip_type == SkipType.REJECT else FlowStatus.PASS
    )
    his = _make_his(
        task=task,
        instance=instance,
        approver=handler,
        skip_type=skip_type,
        flow_status=resolved_his_status,
        targets=targets,
        message=message,
        variables=merged,
        cooperate_type=cooperate_type or CooperateType.APPROVAL,
        actor=handler,
    )
    session.add(his)

    await _remove_task(session, task)

    # A rejection is a one-vote veto for sibling tasks on the same instance.
    if skip_type == SkipType.REJECT:
        siblings = list(
            (
                await session.execute(
                    select(FlowTask).where(
                        FlowTask.instance_id == instance.id,
                        FlowTask.del_flag == "0",
                        FlowTask.id != task.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for sibling in siblings:
            void = _make_his(
                task=sibling,
                instance=instance,
                approver=handler,
                skip_type=SkipType.NONE,
                flow_status=FlowStatus.INVALID,
                targets=[],
                message="流程退回，任务失效",
                variables=merged,
                actor=handler,
            )
            session.add(void)
            await _remove_task(session, sibling)

    # ---- create next tasks ----------------------------------------------
    for node in targets:
        if is_end(node.node_type):
            continue
        await _create_task(session, node, instance, definition, actor=handler, variables=merged)

    if has_end:
        end_node = next(node for node in targets if is_end(node.node_type))
        instance.node_type = end_node.node_type
        instance.node_code = end_node.node_code
        instance.node_name = end_node.node_name
        instance.flow_status = flow_status or FlowStatus.FINISHED
        await _finish_remaining(session, instance, handler, merged)
    else:
        first = targets[0]
        instance.node_type = first.node_type
        instance.node_code = first.node_code
        instance.node_name = first.node_name
        instance.flow_status = flow_status or (
            FlowStatus.REJECT if skip_type == SkipType.REJECT else FlowStatus.APPROVAL
        )

    instance.def_json = to_json(snapshot)
    instance.update_time = utcnow()
    instance.update_by = handler
    return await _persist(session, instance, commit=commit)


async def _finish_remaining(
    session: AsyncSession, instance: FlowInstance, handler: str, variables: dict[str, Any]
) -> None:
    remaining = list(
        (await session.execute(select(FlowTask).where(FlowTask.instance_id == instance.id, FlowTask.del_flag == "0")))
        .scalars()
        .all()
    )
    for task in remaining:
        session.add(
            _make_his(
                task=task,
                instance=instance,
                approver=handler,
                skip_type=SkipType.NONE,
                flow_status=FlowStatus.FINISHED,
                targets=[],
                message="流程完成，未处理任务自动归档",
                variables=variables,
                actor=handler,
            )
        )
        await _remove_task(session, task)


# ---------------------------------------------------------------------------
# Revoke / terminate
# ---------------------------------------------------------------------------


async def revoke_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    handler: str,
    message: str = "",
    flow_status: str | None = None,
    ignore: bool = False,
    commit: bool = True,
) -> FlowInstance:
    instance = await get_instance(session, instance_id)
    if not ignore and instance.create_by != handler:
        raise ForbiddenError("只有流程发起人可以撤销")
    if instance.flow_status in (FlowStatus.FINISHED, FlowStatus.TERMINATE, FlowStatus.CANCEL):
        raise WorkflowError("流程已结束，无法撤销")
    definition = await get_definition(session, instance.definition_id)
    graph = await _instance_graph(session, instance, definition)
    start = graph.start_node
    merged = _apply_variables(instance, {})
    targets = graph.next_nodes(start, skip_type=SkipType.PASS, variables=merged)

    tasks = list(
        (await session.execute(select(FlowTask).where(FlowTask.instance_id == instance.id, FlowTask.del_flag == "0")))
        .scalars()
        .all()
    )
    for task in tasks:
        session.add(
            _make_his(
                task=task,
                instance=instance,
                approver=handler,
                skip_type=SkipType.REJECT,
                flow_status=FlowStatus.CANCEL,
                targets=targets,
                message=message or "发起人撤销",
                variables=merged,
                actor=handler,
            )
        )
        await _remove_task(session, task)

    for node in targets:
        if not is_end(node.node_type):
            await _create_task(session, node, instance, definition, actor=handler, variables=merged)

    snapshot = skip_metadata(
        from_json(instance.def_json, {}),
        path_node_codes=[instance.node_code],
        path_skip_keys=[],
        target_node_codes=[node.node_code for node in targets],
        skip_type=SkipType.REJECT,
    )
    first = targets[0]
    instance.node_type = first.node_type
    instance.node_code = first.node_code
    instance.node_name = first.node_name
    instance.flow_status = flow_status or FlowStatus.CANCEL
    instance.def_json = to_json(snapshot)
    instance.update_time = utcnow()
    instance.update_by = handler
    return await _persist(session, instance, commit=commit)


async def terminate_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    handler: str,
    message: str = "",
    flow_status: str | None = None,
    commit: bool = True,
) -> FlowInstance:
    instance = await get_instance(session, instance_id)
    if instance.flow_status in (FlowStatus.FINISHED, FlowStatus.TERMINATE):
        raise WorkflowError("流程已结束")
    definition = await get_definition(session, instance.definition_id)
    graph = await _instance_graph(session, instance, definition)
    try:
        end = graph.end_node
    except FlowGraphError:
        end = None

    tasks = list(
        (await session.execute(select(FlowTask).where(FlowTask.instance_id == instance.id, FlowTask.del_flag == "0")))
        .scalars()
        .all()
    )
    for task in tasks:
        session.add(
            _make_his(
                task=task,
                instance=instance,
                approver=handler,
                skip_type=SkipType.PASS,
                flow_status=FlowStatus.TERMINATE,
                targets=[end] if end else [],
                message=message or "流程终止",
                variables=_apply_variables(instance, {}),
                actor=handler,
            )
        )
        await _remove_task(session, task)

    if end is not None:
        instance.node_type = end.node_type
        instance.node_code = end.node_code
        instance.node_name = end.node_name
        snapshot = skip_metadata(
            from_json(instance.def_json, {}),
            path_node_codes=[instance.node_code],
            path_skip_keys=[],
            target_node_codes=[end.node_code],
            skip_type=SkipType.PASS,
        )
        instance.def_json = to_json(snapshot)
    instance.flow_status = flow_status or FlowStatus.TERMINATE
    instance.update_time = utcnow()
    instance.update_by = handler
    return await _persist(session, instance, commit=commit)


# ---------------------------------------------------------------------------
# Delegation / signatures
# ---------------------------------------------------------------------------


async def _require_handler(
    session: AsyncSession, task: FlowTask, handler: str, claims: list[str] | None
) -> list[FlowUser]:
    users = await task_users(session, task.id)
    if not _is_authorized(users, handler, claims):
        raise ForbiddenError("当前用户没有该任务的处理权限")
    return users


async def _add_task_users(
    session: AsyncSession,
    task: FlowTask,
    handlers: list[str],
    user_type: str,
    actor: str,
) -> None:
    for value in handlers:
        if not value:
            continue
        session.add(
            FlowUser(
                id=next_id(),
                type=user_type,
                processed_by=value,
                associated=task.id,
                create_time=utcnow(),
                create_by=actor,
                update_time=utcnow(),
                update_by=actor,
                tenant_id=task.tenant_id,
            )
        )
    task.update_time = utcnow()
    task.update_by = actor


async def transfer_task(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    add_handlers: list[str],
    message: str = "",
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowTask:
    task = await get_task(session, task_id)
    users = await _require_handler(session, task, handler, claims)
    if not add_handlers:
        raise WorkflowError("请选择转办人")
    for user in users:
        if user_matches(user.processed_by, handler, claims):
            user.del_flag = "1"
    await _add_task_users(session, task, add_handlers, UserType.TRANSFER, handler)
    session.add(
        _make_his(
            task=task,
            instance=await get_instance(session, task.instance_id),
            approver=handler,
            skip_type=SkipType.NONE,
            flow_status=FlowStatus.APPROVAL,
            targets=[],
            message=message or f"转办给 {', '.join(add_handlers)}",
            variables={},
            cooperate_type=CooperateType.TRANSFER,
            collaborator=",".join(add_handlers),
            target_override=None,
            actor=handler,
        )
    )
    return await _persist(session, task, commit=commit)


async def depute_task(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    add_handlers: list[str],
    message: str = "",
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowTask:
    task = await get_task(session, task_id)
    await _require_handler(session, task, handler, claims)
    if not add_handlers:
        raise WorkflowError("请选择委托人")
    await _add_task_users(session, task, add_handlers, UserType.DEPUTE, handler)
    instance = await get_instance(session, task.instance_id)
    session.add(
        _make_his(
            task=task,
            instance=instance,
            approver=handler,
            skip_type=SkipType.NONE,
            flow_status=FlowStatus.APPROVAL,
            targets=[],
            message=message or f"委派给 {', '.join(add_handlers)}",
            variables={},
            cooperate_type=CooperateType.DEPUTE,
            collaborator=",".join(add_handlers),
            actor=handler,
        )
    )
    return await _persist(session, task, commit=commit)


async def add_signature(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    add_handlers: list[str],
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowTask:
    task = await get_task(session, task_id)
    await _require_handler(session, task, handler, claims)
    if not add_handlers:
        raise WorkflowError("请选择加签人")
    await _add_task_users(session, task, add_handlers, UserType.APPROVAL, handler)
    session.add(
        _make_his(
            task=task,
            instance=await get_instance(session, task.instance_id),
            approver=handler,
            skip_type=SkipType.NONE,
            flow_status=FlowStatus.APPROVAL,
            targets=[],
            message=f"加签 {', '.join(add_handlers)}",
            variables={},
            cooperate_type=CooperateType.ADD_SIGNATURE,
            collaborator=",".join(add_handlers),
            actor=handler,
        )
    )
    return await _persist(session, task, commit=commit)


async def reduce_signature(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    reduce_handlers: list[str],
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowTask:
    task = await get_task(session, task_id)
    users = await _require_handler(session, task, handler, claims)
    if not reduce_handlers:
        raise WorkflowError("请选择减签人")
    approval = [user for user in users if user.type == UserType.APPROVAL]
    if len(approval) - len([u for u in approval if u.processed_by in reduce_handlers]) < 1:
        raise WorkflowError("至少需要保留一位审批人")
    for user in approval:
        if user.processed_by in reduce_handlers:
            user.del_flag = "1"
    session.add(
        _make_his(
            task=task,
            instance=await get_instance(session, task.instance_id),
            approver=handler,
            skip_type=SkipType.NONE,
            flow_status=FlowStatus.APPROVAL,
            targets=[],
            message=f"减签 {', '.join(reduce_handlers)}",
            variables={},
            cooperate_type=CooperateType.REDUCTION_SIGNATURE,
            collaborator=",".join(reduce_handlers),
            actor=handler,
        )
    )
    return await _persist(session, task, commit=commit)


async def return_to_applicant(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    message: str = "",
    variables: dict[str, Any] | None = None,
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowInstance:
    """Return the same instance to its applicant for correction.

    Unlike ``reject_last`` this targets the start node explicitly.  The start
    node is normally forbidden as a transition target, so this runtime path
    bypasses graph routing and creates an applicant task directly.
    """

    variables = variables or {}
    task = await get_task(session, task_id)
    if task.flow_status in (FlowStatus.FINISHED, FlowStatus.REJECT, FlowStatus.CANCEL, FlowStatus.TERMINATE):
        raise ConflictError("该任务已处理")
    instance = await get_instance(session, task.instance_id)
    if instance.activity_status == ActivityStatus.SUSPENDED:
        raise ConflictError("流程实例已挂起，无法退回")
    if instance.flow_status in (FlowStatus.FINISHED, FlowStatus.TERMINATE, FlowStatus.CANCEL, FlowStatus.NULLIFY):
        raise ConflictError("流程实例已结束")

    definition = await get_definition(session, instance.definition_id)
    graph = await _instance_graph(session, instance, definition)
    now_node = graph.node(task.node_code)
    if is_start(now_node.node_type) or is_end(now_node.node_type):
        raise WorkflowError("当前节点不允许退回申请人")
    start = graph.start_node
    await _require_handler(session, task, handler, claims)

    merged = _apply_variables(instance, variables)
    snapshot, return_key = await _ensure_return_skip(session, instance, definition, now_node, start)
    snapshot = skip_metadata(
        snapshot,
        path_node_codes=[now_node.node_code],
        path_skip_keys=[return_key],
        target_node_codes=[start.node_code],
        skip_type=SkipType.REJECT,
    )

    session.add(
        _make_his(
            task=task,
            instance=instance,
            approver=handler,
            skip_type=SkipType.REJECT,
            flow_status=FlowStatus.REJECT,
            target_override=start,
            message=message or "退回申请人修改",
            variables=merged,
            actor=handler,
        )
    )
    await _remove_task(session, task)

    siblings = list(
        (
            await session.execute(
                select(FlowTask).where(
                    FlowTask.instance_id == instance.id,
                    FlowTask.del_flag == "0",
                    FlowTask.id != task.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for sibling in siblings:
        session.add(
            _make_his(
                task=sibling,
                instance=instance,
                approver=handler,
                skip_type=SkipType.NONE,
                flow_status=FlowStatus.INVALID,
                targets=[],
                message="流程退回申请人，任务失效",
                variables=merged,
                actor=handler,
            )
        )
        await _remove_task(session, sibling)

    assignee = instance.create_by or task.create_by or handler
    await _create_task(
        session,
        start,
        instance,
        definition,
        actor=handler,
        variables=merged,
        assignee=assignee,
    )

    instance.node_type = start.node_type
    instance.node_code = start.node_code
    instance.node_name = start.node_name
    instance.flow_status = FlowStatus.REJECT
    instance.def_json = to_json(snapshot)
    instance.update_time = utcnow()
    instance.update_by = handler
    return await _persist(session, instance, commit=commit)


async def reject_last(
    session: AsyncSession,
    task_id: int,
    *,
    handler: str,
    message: str = "",
    claims: list[str] | None = None,
    commit: bool = True,
) -> FlowInstance:
    task = await get_task(session, task_id)
    await _require_handler(session, task, handler, claims)
    his_list = list(
        (
            await session.execute(
                select(FlowHisTask)
                .where(
                    FlowHisTask.instance_id == task.instance_id,
                    FlowHisTask.skip_type == SkipType.PASS,
                    FlowHisTask.node_type == NodeType.BETWEEN,
                    FlowHisTask.node_code != "start",
                    FlowHisTask.del_flag == "0",
                    FlowHisTask.target_node_code.is_not(None),
                )
                .order_by(FlowHisTask.id.desc())
            )
        )
        .scalars()
        .all()
    )
    previous = None
    for item in his_list:
        targets = (item.target_node_code or "").split(",")
        if task.node_code in targets:
            previous = item
            break
    if previous is None:
        raise WorkflowError("当前节点之前没有可退回的审批节点")
    return await handle_task(
        session,
        task_id,
        handler=handler,
        message=message,
        skip_type=SkipType.REJECT,
        node_code=previous.node_code,
        claims=claims,
        commit=commit,
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_tasks(
    session: AsyncSession,
    *,
    handler: str | None = None,
    instance_id: int | None = None,
    node_code: str | None = None,
    claims: list[str] | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(FlowTask, FlowInstance)
        .join(FlowInstance, FlowInstance.id == FlowTask.instance_id)
        .where(FlowTask.del_flag == "0", FlowInstance.del_flag == "0")
        .order_by(FlowTask.create_time.desc())
    )
    if instance_id:
        stmt = stmt.where(FlowTask.instance_id == instance_id)
    if node_code:
        stmt = stmt.where(FlowTask.node_code == node_code)
    rows = (await session.execute(stmt)).all()

    result: list[dict[str, Any]] = []
    for task, instance in rows:
        users = await task_users(session, task.id, (UserType.APPROVAL, UserType.TRANSFER, UserType.DEPUTE))
        assignees = [user.processed_by or "" for user in users]
        if handler and assignees and not any(user_matches(value, handler, claims) for value in assignees):
            continue
        definition = await session.get(FlowDefinition, task.definition_id)
        result.append(
            {
                **{
                    "id": task.id,
                    "definition_id": task.definition_id,
                    "instance_id": task.instance_id,
                    "node_code": task.node_code,
                    "node_name": task.node_name,
                    "node_type": task.node_type,
                    "flow_status": task.flow_status,
                    "form_custom": task.form_custom,
                    "form_path": task.form_path,
                    "create_time": task.create_time,
                    "create_by": task.create_by,
                },
                "flow_name": snapshot_flow_name(instance, definition.flow_name if definition else None),
                "business_id": instance.business_id,
                "assignees": assignees,
            }
        )
    return result


async def list_history(
    session: AsyncSession,
    *,
    handler: str | None = None,
    instance_id: int | None = None,
) -> list[FlowHisTask]:
    stmt = select(FlowHisTask).where(FlowHisTask.del_flag == "0").order_by(FlowHisTask.id.desc())
    if handler:
        stmt = stmt.where(FlowHisTask.approver == handler)
    if instance_id:
        stmt = stmt.where(FlowHisTask.instance_id == instance_id)
    return list((await session.execute(stmt)).scalars().all())


async def instance_detail(session: AsyncSession, instance_id: int) -> dict[str, Any]:
    instance = await get_instance(session, instance_id)
    definition = await session.get(FlowDefinition, instance.definition_id)
    tasks = await list_tasks(session, instance_id=instance_id)
    history = await list_history(session, instance_id=instance_id)
    from .serializers import his_out, instance_out

    return {
        "instance": instance_out(
            instance,
            flow_name=snapshot_flow_name(instance, definition.flow_name if definition else None),
        ),
        "tasks": tasks,
        "history": [his_out(item) for item in history],
        "chart": await build_chart(session, instance),
    }


async def instance_count(session: AsyncSession, definition_id: int) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(FlowInstance).where(FlowInstance.definition_id == definition_id)
        )
    ).scalar_one()
