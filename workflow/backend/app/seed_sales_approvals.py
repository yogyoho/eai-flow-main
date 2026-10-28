"""Idempotent sales-approval form/process seed for the workflow platform."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import session_scope
from .engine import definition as definition_service
from .models import FlowDefinition, FlowForm, FlowNode, FlowSkip
from .utils import next_id, to_json, utcnow

logger = logging.getLogger("workflow.seed.sales")

NODE_Y = 200
START_X = 100
STEP_X0 = 400
STEP_GAP = 260

FORM_CODE = "sales_approval_form"
FORM_CONTENT = to_json(
    {
        "fields": [
            {"key": "request_no", "label": "审批单号", "type": "text", "required": True},
            {"key": "gate_code", "label": "审批闸门", "type": "text", "required": True},
            {"key": "opportunity_no", "label": "商机编号", "type": "text", "required": True},
            {"key": "opportunity_name", "label": "商机名称", "type": "text", "required": True},
            {"key": "amount", "label": "金额", "type": "number", "required": False},
            {"key": "reason", "label": "申请原因", "type": "textarea", "required": True},
            {"key": "requested_by", "label": "申请人", "type": "text", "required": True},
        ]
    }
)


def _node(
    code: str,
    name: str,
    node_type: int,
    *,
    x: int,
    permission: str | None = None,
    form_path: str | None = None,
    skips: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    node = {
        "nodeType": node_type,
        "nodeCode": code,
        "nodeName": name,
        "coordinate": f"{x},{NODE_Y}|{x},{NODE_Y}",
        "skipList": skips or [],
    }
    if permission:
        node["permissionFlag"] = permission
        node["nodeRatio"] = "0"
    if form_path:
        node["formCustom"] = "Y"
        node["formPath"] = form_path
    return node


def _skip(now: str, next_code: str, name: str, skip_type: str = "PASS") -> dict[str, Any]:
    # Coordinates are filled by _apply_edge_layout once every node exists.
    return {
        "nowNodeCode": now,
        "nextNodeCode": next_code,
        "skipName": name,
        "skipType": skip_type,
        "coordinate": None,
    }


def _node_geometry(node: dict[str, Any]) -> tuple[int, int, int, int]:
    """Return x, y, half-width, half-height for a seeded node."""
    point = str(node.get("coordinate") or "0,0").split("|")[0]
    x_text, y_text = point.split(",", 1)
    x = int(x_text)
    y = int(y_text)
    raw_type = node.get("nodeType")
    node_type = int(raw_type) if raw_type is not None else 1
    if node_type in (0, 2):
        return x, y, 28, 28
    if node_type >= 3:
        return x, y, 30, 30
    return x, y, 88, 26


def _edge_coordinate(
    source: dict[str, Any],
    target: dict[str, Any],
    skip: dict[str, Any],
    reject_offset: int,
) -> str:
    """Build an edge path that starts and ends on the node boundaries.

    PASS edges use a short horizontal path. REJECT edges route below the
    node row so they do not cross the approval nodes between source and end.
    """
    sx, sy, sw, sh = _node_geometry(source)
    tx, ty, tw, th = _node_geometry(target)
    skip_type = str(skip.get("skipType") or "PASS")

    if skip_type == "REJECT":
        if tx < sx:
            # Return-to-applicant edges route above the node row so they read as
            # a loop back to the applicant instead of a terminal rejection.
            start_y = sy - sh
            end_y = ty - th
            route_y = min(start_y, end_y) - 64 - reject_offset * 26
            points = [(sx, start_y), (sx, route_y), (tx, route_y), (tx, end_y)]
            text = ((sx + tx) // 2, route_y - 18)
        else:
            start_y = sy + sh
            end_y = ty + th
            route_y = max(start_y, end_y) + 64 + reject_offset * 26
            points = [(sx, start_y), (sx, route_y), (tx, route_y), (tx, end_y)]
            text = ((sx + tx) // 2, route_y + 16)
    else:
        direction = 1 if tx >= sx else -1
        start = (sx + direction * sw, sy)
        end = (tx - direction * tw, ty)
        if abs(sy - ty) < 6:
            points = [start, end]
        else:
            mid_y = (sy + ty) // 2
            points = [start, (start[0], mid_y), (end[0], mid_y), end]
        text = ((start[0] + end[0]) // 2, min(sy, ty) - 18)

    points_text = ";".join(f"{x},{y}" for x, y in points)
    return f"{points_text}|{text[0]},{text[1]}"


def _apply_edge_layout(nodes: list[dict[str, Any]]) -> None:
    by_code = {node["nodeCode"]: node for node in nodes}
    reject_offset = 0
    for node in nodes:
        for skip in node.get("skipList", []):
            target = by_code.get(str(skip.get("nextNodeCode") or ""))
            if target is None:
                continue
            offset = 0
            if str(skip.get("skipType") or "PASS") == "REJECT":
                offset = reject_offset
                reject_offset += 1
            skip["coordinate"] = _edge_coordinate(node, target, skip, offset)


def _flow(code: str, name: str, form_path: str, steps: list[tuple[str, str]]) -> dict[str, Any]:
    nodes = [
        _node(
            "start",
            "发起",
            0,
            x=START_X,
            skips=[_skip("start", "step_1", "提交")],
        )
    ]
    for index, (role, label) in enumerate(steps, start=1):
        next_code = "end" if index == len(steps) else f"step_{index + 1}"
        nodes.append(
            _node(
                f"step_{index}",
                label,
                1,
                x=STEP_X0 + (index - 1) * STEP_GAP,
                permission=f"role:{role}",
                form_path=form_path,
                skips=[
                    _skip(f"step_{index}", next_code, "通过", "PASS"),
                    _skip(f"step_{index}", "end", "驳回", "REJECT"),
                    _skip(f"step_{index}", "start", "退回申请人", "REJECT"),
                ],
            )
        )
    nodes.append(_node("end", "结束", 2, x=STEP_X0 + len(steps) * STEP_GAP))
    _apply_edge_layout(nodes)
    return {
        "flowCode": code,
        "flowName": name,
        "modelValue": "CLASSICS",
        "category": "营销审批",
        "formCustom": "Y",
        "formPath": form_path,
        "nodeList": nodes,
    }


FLOWS = [
    (
        "sales_r4_exception",
        "营销 R4 新客户例外审批",
        [("regional_manager", "区域经理审批"), ("sales_director", "销售总监审批")],
    ),
    (
        "sales_r6_related_party",
        "营销 R6 关联方合规审批",
        [
            ("regional_manager", "区域经理审批"),
            ("sales_director", "销售总监审批"),
            ("compliance_officer", "合规官审批"),
        ],
    ),
    (
        "sales_duplicate_merge",
        "营销撞单合并审批",
        [("regional_manager", "区域经理审批")],
    ),
]


async def _ensure_form(session: AsyncSession) -> FlowForm:
    form = (
        await session.execute(
            select(FlowForm)
            .where(FlowForm.form_code == FORM_CODE, FlowForm.del_flag == "0")
            .order_by(FlowForm.create_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if form is not None:
        if form.is_publish != 1:
            form.is_publish = 1
            form.form_content = FORM_CONTENT
            form.update_time = utcnow()
            await session.flush()
        return form
    now = utcnow()
    form = FlowForm(
        id=next_id(),
        form_code=FORM_CODE,
        form_name="营销审批申请单",
        version="1",
        is_publish=1,
        form_type=0,
        form_content=FORM_CONTENT,
        form_path=f"{FORM_CODE}:1",
        create_time=now,
        create_by="system",
        update_time=now,
        update_by="system",
        tenant_id=settings.default_tenant,
    )
    session.add(form)
    await session.flush()
    return form


async def _repair_flow_layout(
    session: AsyncSession,
    definition: FlowDefinition,
    payload: dict[str, Any],
) -> bool:
    """Snap a seeded definition's canvas layout back to the canonical seed layout.

    Older seeds stored node/edge geometry from previous layout algorithms, and
    ``_ensure_sales_edges`` used to add return edges whose coordinates were
    computed against canonical node positions instead of the stored ones. The
    result is edges that float next to nodes (return edges) or sit exactly on
    top of the pass edge (reject edges) in the designer.

    Layout is derived data, but the seed is authoritative only for structure:
    definitions whose node codes or edge set were redesigned by an
    administrator (extra/missing nodes or edges) are left untouched.
    """

    canonical_node_codes = {str(node["nodeCode"]) for node in payload["nodeList"]}
    canonical_edges = {
        (
            str(skip.get("nowNodeCode") or ""),
            str(skip.get("nextNodeCode") or ""),
            str(skip.get("skipType") or "PASS"),
        )
        for node in payload["nodeList"]
        for skip in node.get("skipList", [])
    }

    nodes_by_code = {str(node["nodeCode"]): node for node in payload["nodeList"]}
    skips_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    skips_by_semantics: dict[tuple[str, str, str], dict[str, Any]] = {}
    for node in payload["nodeList"]:
        for skip in node.get("skipList", []):
            key = (
                str(skip.get("nowNodeCode") or ""),
                str(skip.get("nextNodeCode") or ""),
                str(skip.get("skipType") or "PASS"),
                str(skip.get("skipName") or ""),
            )
            skips_by_key[key] = skip
            skips_by_semantics[key[:3]] = skip

    db_nodes = list(
        (
            await session.execute(
                select(FlowNode).where(
                    FlowNode.definition_id == definition.id,
                    FlowNode.del_flag == "0",
                )
            )
        ).scalars()
    )
    db_skips = list(
        (
            await session.execute(
                select(FlowSkip).where(
                    FlowSkip.definition_id == definition.id,
                    FlowSkip.del_flag == "0",
                )
            )
        ).scalars()
    )

    # A redesigned flow keeps its own layout; only seed-shaped flows are healed.
    if {node.node_code for node in db_nodes} != canonical_node_codes:
        return False
    db_edges = {(skip.now_node_code, skip.next_node_code, str(skip.skip_type or "PASS")) for skip in db_skips}
    if not db_edges <= canonical_edges:
        return False

    now = utcnow()
    changed = False
    for node in db_nodes:
        fresh = nodes_by_code.get(node.node_code)
        if fresh is not None and node.coordinate != fresh["coordinate"]:
            node.coordinate = fresh["coordinate"]
            node.update_time = now
            node.update_by = "system"
            changed = True

    for skip in db_skips:
        key = (
            skip.now_node_code,
            skip.next_node_code,
            str(skip.skip_type or "PASS"),
            str(skip.skip_name or ""),
        )
        fresh = skips_by_key.get(key) or skips_by_semantics.get(key[:3])
        coordinate = fresh.get("coordinate") if fresh is not None else None
        if skip.coordinate != coordinate:
            skip.coordinate = coordinate
            skip.update_time = now
            skip.update_by = "system"
            changed = True

    if changed:
        definition.update_time = now
        definition.update_by = "system"
        await session.flush()
        logger.info("repaired sales workflow canvas layout: %s", definition.flow_code)
    return changed


async def _ensure_sales_edges(
    session: AsyncSession,
    definition: FlowDefinition,
    payload: dict[str, Any],
) -> bool:
    """Add the return-to-applicant edge to definitions seeded before it existed.

    The seed is authoritative for sales flows: a missing ``step_n -> start``
    REJECT edge is inserted, and the old terminal ``退回`` label is renamed to
    ``驳回``.  Existing coordinates are preserved unless absent.
    """

    nodes_by_code = {str(node["nodeCode"]): node for node in payload["nodeList"]}
    fresh: dict[tuple[str, str, str], dict[str, Any]] = {}
    for node in payload["nodeList"]:
        for skip in node.get("skipList", []):
            fresh[
                (
                    str(skip.get("nowNodeCode") or ""),
                    str(skip.get("nextNodeCode") or ""),
                    str(skip.get("skipType") or "PASS"),
                )
            ] = skip

    db_skips = list(
        (
            await session.execute(
                select(FlowSkip).where(
                    FlowSkip.definition_id == definition.id,
                    FlowSkip.del_flag == "0",
                )
            )
        ).scalars()
    )
    existing: dict[tuple[str, str, str], FlowSkip] = {}
    for skip in db_skips:
        key = (
            skip.now_node_code,
            skip.next_node_code,
            str(skip.skip_type or "PASS"),
        )
        existing.setdefault(key, skip)

    now = utcnow()
    changed = False
    for key, skip in fresh.items():
        now_code, next_code, skip_type = key
        skip_name = str(skip.get("skipName") or "")
        current = existing.get(key)
        if current is not None:
            if skip_type == "REJECT" and str(current.skip_name or "") == "退回":
                current.skip_name = skip_name
                current.update_time = now
                current.update_by = "system"
                changed = True
            if not current.coordinate and skip.get("coordinate"):
                current.coordinate = str(skip["coordinate"])
                current.update_time = now
                current.update_by = "system"
                changed = True
            continue

        now_node = nodes_by_code[now_code]
        next_node = nodes_by_code[next_code]
        session.add(
            FlowSkip(
                id=next_id(),
                definition_id=definition.id,
                now_node_code=now_code,
                now_node_type=int(now_node.get("nodeType") or 1),
                next_node_code=next_code,
                next_node_type=int(next_node.get("nodeType") or 1),
                skip_name=skip_name,
                skip_type=skip_type,
                skip_condition=str(skip.get("skipCondition") or "") or None,
                coordinate=str(skip.get("coordinate") or "") or None,
                create_time=now,
                create_by="system",
                update_time=now,
                update_by="system",
                tenant_id=definition.tenant_id or settings.default_tenant,
            )
        )
        changed = True

    if changed:
        definition.update_time = now
        definition.update_by = "system"
        await session.flush()
        logger.info("ensured sales workflow return edges: %s", definition.flow_code)
    return changed


async def seed_sales_approvals(session: AsyncSession) -> list[str]:
    form = await _ensure_form(session)
    form_path = form.form_path or f"{FORM_CODE}:{form.version}"
    created: list[str] = []
    for flow_code, flow_name, steps in FLOWS:
        payload = _flow(flow_code, flow_name, form_path, steps)
        published = (
            await session.execute(
                select(FlowDefinition)
                .where(
                    FlowDefinition.flow_code == flow_code,
                    FlowDefinition.del_flag == "0",
                    FlowDefinition.is_publish == 1,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if published is not None:
            await _repair_flow_layout(session, published, payload)
            await _ensure_sales_edges(session, published, payload)
            continue
        result = await definition_service.save_def_json(
            session,
            payload,
            actor="system",
        )
        definition_id = int(result["id"])
        await definition_service.publish_definition(session, definition_id, actor="system")
        created.append(flow_code)
        logger.info("seeded sales workflow: %s", flow_code)
    return created


async def _main() -> None:
    async with session_scope() as session:
        created = await seed_sales_approvals(session)
        logger.info("sales approval seed complete: %s", created)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
