"""Regression tests: seeded sales flows keep their edges attached to nodes.

Legacy seeds stored node/edge geometry from earlier layout algorithms, and the
return-to-applicant edges were added with coordinates computed against canonical
node positions instead of the stored ones. The seed's layout repair must snap
such drift back to the canonical layout whenever the flow structure still
matches the seed.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import session_scope
from app.models import FlowDefinition, FlowNode, FlowSkip
from app.seed_sales_approvals import _node_geometry, seed_sales_approvals

FLOW_CODE = "sales_duplicate_merge"

# Layout drift as found in production: nodes from the old layout, the return
# edge computed against canonical positions, and the reject edge duplicated on
# top of the pass edge.
DRIFTED_NODES = {"start": (48, 124), "step_1": (334, 124), "end": (652, 124)}
OVERLAPPING_COORDINATE = "422,124;523,124;523,124;624,124|472,123"
FLOATING_RETURN_COORDINATE = "400,174;400,82;100,82;100,172|250,64"


def _drift_layout() -> None:
    async def drift() -> None:
        async with session_scope() as session:
            definition = (
                await session.execute(select(FlowDefinition).where(FlowDefinition.flow_code == FLOW_CODE))
            ).scalar_one()
            nodes = list(
                (await session.execute(select(FlowNode).where(FlowNode.definition_id == definition.id))).scalars()
            )
            skips = list(
                (await session.execute(select(FlowSkip).where(FlowSkip.definition_id == definition.id))).scalars()
            )
            for node in nodes:
                x, y = DRIFTED_NODES[node.node_code]
                node.coordinate = f"{x},{y}|{x},{y}"
            for skip in skips:
                if skip.next_node_code == "start":
                    skip.coordinate = FLOATING_RETURN_COORDINATE
                elif skip.next_node_code == "end" and str(skip.skip_type) == "REJECT":
                    skip.coordinate = OVERLAPPING_COORDINATE
                elif skip.next_node_code == "end":
                    skip.coordinate = OVERLAPPING_COORDINATE
            await session.flush()

    asyncio.run(drift())


def test_seed_repairs_drifted_sales_layout(api) -> None:
    _drift_layout()

    async def _seed() -> list[str]:
        async with session_scope() as session:
            return await seed_sales_approvals(session)

    created = asyncio.run(_seed())
    assert created == []  # already seeded; only the layout repair should run

    def verify() -> tuple[dict[str, dict], list[FlowSkip]]:
        async def read() -> tuple[dict[str, dict], list[FlowSkip]]:
            async with session_scope() as session:
                definition = (
                    await session.execute(select(FlowDefinition).where(FlowDefinition.flow_code == FLOW_CODE))
                ).scalar_one()
                nodes = {
                    node.node_code: {"coordinate": node.coordinate, "nodeType": node.node_type}
                    for node in (
                        await session.execute(select(FlowNode).where(FlowNode.definition_id == definition.id))
                    ).scalars()
                }
                skips = list(
                    (await session.execute(select(FlowSkip).where(FlowSkip.definition_id == definition.id))).scalars()
                )
                return nodes, skips

        return asyncio.run(read())

    nodes, skips = verify()

    # Nodes are snapped back to the canonical seed layout.
    for code, (x, y) in {"start": (100, 200), "step_1": (400, 200), "end": (660, 200)}.items():
        point = nodes[code]["coordinate"].split("|")[0]
        assert point == f"{x},{y}", (code, point)

    for skip in skips:
        points = [
            tuple(int(value) for value in pair.split(",")) for pair in str(skip.coordinate).split("|")[0].split(";")
        ]
        assert len(points) >= 2, (skip.skip_name, skip.coordinate)
        source = nodes[skip.now_node_code]
        target = nodes[skip.next_node_code]
        for endpoint, node in ((points[0], source), (points[-1], target)):
            x, y, half_w, half_h = _node_geometry(node)
            cx, cy = endpoint
            dx = max(abs(cx - x) - half_w, 0)
            dy = max(abs(cy - y) - half_h, 0)
            assert (dx, dy) == (0, 0), (skip.skip_name, endpoint, node)

    by_name = {str(skip.skip_name): skip for skip in skips}
    reject_coordinate = str(by_name["驳回"].coordinate).split("|")[0]
    pass_coordinate = str(by_name["通过"].coordinate).split("|")[0]
    assert reject_coordinate != pass_coordinate, "reject edge must not overlap the pass edge"

    step_y = nodes["step_1"]["coordinate"].split("|")[0].split(",")[1]
    return_route_y = int(str(by_name["退回申请人"].coordinate).split("|")[0].split(";")[1].split(",")[1])
    assert return_route_y < int(step_y), "return edge must route above the node row"
