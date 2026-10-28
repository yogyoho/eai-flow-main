"""Flow-chart metadata (ChartServiceImpl port).

A definition snapshot (``flow_instance.def_json``) carries one ``status`` per
node and per edge:

* ``0`` not done (grey)
* ``1`` todo (amber, dashed)
* ``2`` traversed (green; rejection edges render red)
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FlowHisTask, FlowInstance
from ..utils import from_json, to_json
from .definition import get_definition
from .enums import CHART_COLORS, ChartStatus, NodeType, SkipType
from .serializers import build_def_json, skip_key

LEGACY_EDGE_COORDINATE = "250,220;350,220|300,200"


def _needs_layout_repair(snapshot: dict[str, Any]) -> bool:
    return any(
        str(skip.get("coordinate") or "").strip() == LEGACY_EDGE_COORDINATE
        for node in snapshot.get("nodeList") or []
        for skip in node.get("skipList") or []
    )


def _merge_layout(snapshot: dict[str, Any], fresh: dict[str, Any]) -> None:
    """Refresh only coordinates, keeping the instance's frozen statuses/forms."""
    fresh_nodes = {str(node.get("nodeCode")): node for node in fresh.get("nodeList") or []}
    fresh_skips_by_id = {
        str(skip.get("id")): skip
        for node in fresh.get("nodeList") or []
        for skip in node.get("skipList") or []
        if skip.get("id") is not None
    }
    fresh_skips_by_semantics = {
        (
            str(skip.get("nowNodeCode") or ""),
            str(skip.get("nextNodeCode") or ""),
            str(skip.get("skipType") or "PASS"),
            str(skip.get("skipName") or ""),
        ): skip
        for node in fresh.get("nodeList") or []
        for skip in node.get("skipList") or []
    }

    for node in snapshot.get("nodeList") or []:
        fresh_node = fresh_nodes.get(str(node.get("nodeCode")))
        if fresh_node and fresh_node.get("coordinate") is not None:
            node["coordinate"] = fresh_node["coordinate"]
        for skip in node.get("skipList") or []:
            fresh_skip = fresh_skips_by_id.get(str(skip.get("id") or ""))
            if fresh_skip is None:
                fresh_skip = fresh_skips_by_semantics.get(
                    (
                        str(skip.get("nowNodeCode") or ""),
                        str(skip.get("nextNodeCode") or ""),
                        str(skip.get("skipType") or "PASS"),
                        str(skip.get("skipName") or ""),
                    )
                )
            if fresh_skip and fresh_skip.get("coordinate") is not None:
                skip["coordinate"] = fresh_skip["coordinate"]


def prepare_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(payload)
    snapshot["chartStatusColor"] = snapshot.get("chartStatusColor") or CHART_COLORS["CLASSICS"]
    for node in snapshot.get("nodeList") or []:
        node["status"] = ChartStatus.NOT_DONE
        for skip in node.get("skipList") or []:
            skip["status"] = ChartStatus.NOT_DONE
    return snapshot


def _all_skips(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [skip for node in snapshot.get("nodeList") or [] for skip in node.get("skipList") or []]


def _restore_reject_paths(snapshot: dict[str, Any], history: list[FlowHisTask]) -> None:
    """Correct reject paths stored before rejected transitions were marked DONE.

    Older snapshots kept both the traversed reject edge and the acting node at
    status 0, so the chart drew a used path grey and hid the node where the
    rejection happened. History is the source of truth: any reject transition
    recorded there was traversed, so its edge renders red and its acting node
    renders as processed. Active nodes are never downgraded.
    """
    nodes = {str(node.get("nodeCode")): node for node in snapshot.get("nodeList") or []}
    for item in history:
        if item.skip_type != SkipType.REJECT:
            continue
        node = nodes.get(str(item.node_code))
        if node is None:
            continue
        if node.get("status") == ChartStatus.NOT_DONE:
            node["status"] = ChartStatus.DONE
        reject_skips = [skip for skip in node.get("skipList") or [] if skip.get("skipType") == SkipType.REJECT]
        targets = {value for value in str(item.target_node_code or "").split(",") if value}
        matched = [skip for skip in reject_skips if str(skip.get("nextNodeCode")) in targets]
        if not matched and len(reject_skips) == 1:
            matched = reject_skips
        for skip in matched:
            skip["status"] = ChartStatus.DONE


def start_metadata(
    snapshot: dict[str, Any],
    *,
    path_node_codes: list[str],
    path_skip_keys: list[str],
    target_node_codes: list[str],
) -> dict[str, Any]:
    node_map = {node.get("nodeCode"): node for node in snapshot.get("nodeList") or []}
    skip_map = {str(skip.get("id") or skip_key(skip)): skip for skip in _all_skips(snapshot)}

    for code in path_node_codes:
        if code in node_map:
            node_map[code]["status"] = ChartStatus.DONE
    for key in path_skip_keys:
        if key in skip_map:
            skip_map[key]["status"] = ChartStatus.DONE
    for code in target_node_codes:
        node = node_map.get(code)
        if node:
            node["status"] = ChartStatus.DONE if node.get("nodeType") == NodeType.END else ChartStatus.TO_DO
    return snapshot


def skip_metadata(
    snapshot: dict[str, Any],
    *,
    path_node_codes: list[str],
    path_skip_keys: list[str],
    target_node_codes: list[str],
    skip_type: str,
) -> dict[str, Any]:
    snapshot = deepcopy(snapshot)
    node_map = {node.get("nodeCode"): node for node in snapshot.get("nodeList") or []}
    skip_map = {str(skip.get("id") or skip_key(skip)): skip for skip in _all_skips(snapshot)}

    for code in path_node_codes:
        node = node_map.get(code)
        if node is None:
            continue
        # Both outcomes mark the acting node as traversed: an approval moves
        # the flow forward, and a rejection was still processed here. The red
        # reject edge conveys the outcome; downstream nodes stay untouched.
        node["status"] = ChartStatus.DONE

    for key in path_skip_keys:
        skip = skip_map.get(key)
        if skip is None:
            continue
        # A rejection edge was traversed too. Keep it as DONE so the chart can
        # render the path red; the reset below only clears downstream PASS edges.
        if skip_type in (SkipType.PASS, SkipType.REJECT):
            skip["status"] = ChartStatus.DONE

    for code in target_node_codes:
        node = node_map.get(code)
        if node is None:
            continue
        node["status"] = ChartStatus.DONE if node.get("nodeType") == NodeType.END else ChartStatus.TO_DO

    if skip_type == SkipType.REJECT:
        # Reset everything downstream of the reject target, mirroring
        # ChartServiceImpl#rejectReset.
        next_map: dict[str, list[dict[str, Any]]] = {}
        for skip in _all_skips(snapshot):
            if skip.get("skipType") != SkipType.REJECT:
                next_map.setdefault(skip.get("nowNodeCode"), []).append(skip)

        def reset(code: str, guard: set[str]) -> None:
            if code in guard:
                return
            guard.add(code)
            for skip in next_map.get(code, []):
                if skip.get("status") != ChartStatus.NOT_DONE:
                    skip["status"] = ChartStatus.NOT_DONE
                target = skip.get("nextNodeCode")
                node = node_map.get(target)
                if node and node.get("status") != ChartStatus.NOT_DONE:
                    node["status"] = ChartStatus.NOT_DONE
                    reset(target, guard)

        for code in target_node_codes:
            reset(code, set())

    if any(node_map.get(code, {}).get("nodeType") == NodeType.END for code in target_node_codes):
        for node in snapshot.get("nodeList") or []:
            if node.get("status") == ChartStatus.TO_DO:
                node["status"] = ChartStatus.NOT_DONE

    return snapshot


async def build_chart(session: AsyncSession, instance: FlowInstance) -> dict[str, Any]:
    definition = await get_definition(session, instance.definition_id)
    snapshot = from_json(instance.def_json, {})
    if not snapshot or not snapshot.get("nodeList"):
        payload = await build_def_json(session, definition)
        snapshot = prepare_snapshot(payload)
        instance.def_json = to_json(snapshot)
    elif _needs_layout_repair(snapshot):
        payload = await build_def_json(session, definition)
        _merge_layout(snapshot, payload)
        instance.def_json = to_json(snapshot)

    history = list(
        (
            await session.execute(
                select(FlowHisTask).where(
                    FlowHisTask.instance_id == instance.id,
                    FlowHisTask.del_flag == "0",
                    FlowHisTask.skip_type == SkipType.REJECT,
                )
            )
        )
        .scalars()
        .all()
    )
    _restore_reject_paths(snapshot, history)

    snapshot["instance"] = {
        "id": instance.id,
        "definitionId": instance.definition_id,
        "businessId": instance.business_id,
        "nodeType": instance.node_type,
        "nodeCode": instance.node_code,
        "nodeName": instance.node_name,
        "flowStatus": instance.flow_status,
        "activityStatus": instance.activity_status,
        "createBy": instance.create_by,
        "createTime": instance.create_time,
    }
    snapshot["topText"] = snapshot.get("flowName") or definition.flow_name
    snapshot["topTextShow"] = True
    snapshot["chartStatusColor"] = snapshot.get("chartStatusColor") or CHART_COLORS.get(
        definition.model_value, CHART_COLORS["CLASSICS"]
    )
    return snapshot
