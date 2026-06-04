from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TemplateApproval, WorkflowDefinition


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
    template_status: str | None = None,
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
    if template_status is not None:
        stmt = stmt.where(WorkflowDefinition.template_status == template_status)
        count_stmt = count_stmt.where(WorkflowDefinition.template_status == template_status)

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
    org_bindings: dict | None = None,
    description: str | None = None,
    visible_dept_ids: list[str] | None = None,
) -> WorkflowDefinition:
    """Create a new workflow definition."""
    definition = WorkflowDefinition(
        name=name,
        report_type=report_type,
        graph_json=graph_json,
        is_template=is_template,
        org_bindings=org_bindings,
        created_by=created_by,
        description=description,
        visible_dept_ids=visible_dept_ids,
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
    definition.template_status = "published"
    await db.commit()
    await db.refresh(definition)
    return definition


# ── Template Approval ──


async def submit_for_approval(db: AsyncSession, template_id: UUID, requester_id: UUID) -> TemplateApproval:
    """Submit a template for approval. Only allowed from draft or rejected status."""
    definition = await db.get(WorkflowDefinition, template_id)
    if not definition:
        raise ValueError("Template not found")
    if definition.template_status not in ("draft", "rejected"):
        raise ValueError(f"Cannot submit template in status '{definition.template_status}'")
    definition.template_status = "pending_approval"
    approval = TemplateApproval(template_id=template_id, requester_id=requester_id, status="pending")
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def review_approval(db: AsyncSession, approval_id: UUID, reviewer_id: UUID, action: str, comment: str | None = None) -> TemplateApproval:
    """Review (approve/reject) a pending approval request."""
    approval = await db.get(TemplateApproval, approval_id)
    if not approval:
        raise ValueError("Approval not found")
    if approval.status != "pending":
        raise ValueError(f"Approval already {approval.status}")
    approval.status = action
    approval.reviewer_id = reviewer_id
    approval.comment = comment
    approval.reviewed_at = datetime.now()
    definition = await db.get(WorkflowDefinition, approval.template_id)
    if definition:
        if action == "approved":
            definition.template_status = "published"
            definition.is_template = True
        elif action == "rejected":
            definition.template_status = "rejected"
    await db.commit()
    await db.refresh(approval)
    return approval


async def withdraw_approval(db: AsyncSession, template_id: UUID, requester_id: UUID) -> bool:
    """Withdraw a pending approval request. Returns True if withdrawn, False if no pending approval."""
    stmt = select(TemplateApproval).where(TemplateApproval.template_id == template_id).where(TemplateApproval.status == "pending")
    result = await db.execute(stmt)
    pending = result.scalars().first()
    if not pending:
        return False
    pending.status = "withdrawn"
    definition = await db.get(WorkflowDefinition, template_id)
    if definition:
        definition.template_status = "draft"
    await db.commit()
    return True


async def list_approvals(db: AsyncSession, template_id: UUID) -> list[TemplateApproval]:
    """List all approval records for a template, ordered by creation time."""
    stmt = select(TemplateApproval).where(TemplateApproval.template_id == template_id).order_by(TemplateApproval.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())
