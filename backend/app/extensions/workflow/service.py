from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WorkflowDefinition


# ── DAG Validation ──


def validate_dag(graph: dict) -> dict:
    """Validate a DAG graph_json structure. Returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return {"valid": False, "errors": ["Graph is empty — must have at least one node"], "warnings": []}

    node_ids = {n["id"] for n in nodes}

    # Check edge references
    for edge in edges:
        if edge["source"] not in node_ids:
            errors.append(f"Edge references unknown source node '{edge['source']}'")
        if edge["target"] not in node_ids:
            errors.append(f"Edge references unknown target node '{edge['target']}'")

    # Cycle detection (DFS)
    adjacency = defaultdict(list)
    for edge in edges:
        if edge["source"] in node_ids and edge["target"] in node_ids:
            adjacency[edge["source"]].append(edge["target"])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}

    def has_cycle(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and has_cycle(neighbor):
                return True
        color[node_id] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if has_cycle(nid):
                errors.append("Graph contains a cycle")
                break

    # Disconnected node detection
    sources = {e["source"] for e in edges}
    targets = {e["target"] for e in edges}
    connected = sources | targets
    for node in nodes:
        if node["id"] not in connected and len(nodes) > 1:
            warnings.append(f"Node '{node['id']}' ({node.get('data', {}).get('label', '')}) is disconnected")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def topological_sort(graph: dict) -> list[str]:
    """Return nodes in topological order."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    adjacency = defaultdict(list)
    in_degree = defaultdict(int)
    node_ids = [n["id"] for n in nodes]

    for nid in node_ids:
        in_degree[nid] = 0

    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        in_degree[edge["target"]] += 1

    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


# ── Workflow Definition CRUD ──


async def list_definitions(
    db: AsyncSession,
    is_template: bool | None = None,
    report_type: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[WorkflowDefinition], int]:
    """List workflow definitions with optional filters. Returns (items, total)."""
    stmt = select(WorkflowDefinition)
    count_stmt = select(func.count()).select_from(WorkflowDefinition)

    if is_template is not None:
        stmt = stmt.where(WorkflowDefinition.is_template == is_template)
        count_stmt = count_stmt.where(WorkflowDefinition.is_template == is_template)
    if report_type is not None:
        stmt = stmt.where(WorkflowDefinition.report_type == report_type)
        count_stmt = count_stmt.where(WorkflowDefinition.report_type == report_type)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(WorkflowDefinition.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all(), total


async def get_definition(db: AsyncSession, definition_id: UUID) -> WorkflowDefinition | None:
    """Get a single workflow definition by ID."""
    return await db.get(WorkflowDefinition, definition_id)


async def create_definition(
    db: AsyncSession,
    name: str,
    graph_json: dict,
    created_by: UUID,
    report_type: str | None = None,
    is_template: bool = False,
) -> WorkflowDefinition:
    """Create a new workflow definition."""
    definition = WorkflowDefinition(
        name=name,
        report_type=report_type,
        graph_json=graph_json,
        is_template=is_template,
        created_by=created_by,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


async def update_definition(
    db: AsyncSession,
    definition_id: UUID,
    update_data: dict,
) -> WorkflowDefinition | None:
    """Update an existing workflow definition. Returns None if not found."""
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        return None
    for key, value in update_data.items():
        setattr(definition, key, value)
    await db.commit()
    await db.refresh(definition)
    return definition


async def delete_definition(db: AsyncSession, definition_id: UUID) -> bool:
    """Delete a workflow definition. Returns True if deleted, False if not found."""
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        return False
    await db.delete(definition)
    await db.commit()
    return True


async def publish_as_template(db: AsyncSession, definition_id: UUID) -> WorkflowDefinition | None:
    """Mark a workflow definition as a published template."""
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        return None
    definition.is_template = True
    await db.commit()
    await db.refresh(definition)
    return definition
