"""Runtime slot-filling service — checks if required roles for a phase are filled.

When a workflow phase is about to start, this service cross-references the
DAG node's `required_roles` with project members' `phase_duties` to determine
which roles are already filled and which are still missing.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Department, ProjectMember, ReportProject, User

logger = logging.getLogger(__name__)


async def check_phase_readiness(
    db: AsyncSession,
    project_id: UUID,
    phase_node: str,
) -> dict:
    """Check if all required_roles for a phase are filled by project members.

    Returns:
        {
            "ready": bool,
            "phase_node": str,
            "phase_label": str,
            "filled_roles": [{"role_key", "count", "members": [...]}],
            "missing_roles": [{"role_key", "count", "label"}],
            "suggested_members": [{"user_id", "username", "dept_name"}],
        }
    """
    # 1. Get the project
    project_stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(project_stmt)
    project = result.scalar_one_or_none()
    if not project:
        return {"ready": False, "phase_node": phase_node, "error": "Project not found"}

    # 2. Get workflow definition and extract required_roles from the DAG node
    required_roles: list[dict] = []
    phase_label = phase_node

    if project.workflow_id:
        from app.extensions.workflow.models import WorkflowDefinition

        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            for node in defn.graph_json.get("nodes", []):
                if node["id"] == phase_node:
                    phase_label = node.get("data", {}).get("label", phase_node)
                    required_roles = node.get("data", {}).get("required_roles", [])
                    break

    if not required_roles:
        # No required_roles defined → phase is ready by default
        return {
            "ready": True,
            "phase_node": phase_node,
            "phase_label": phase_label,
            "filled_roles": [],
            "missing_roles": [],
            "suggested_members": [],
        }

    # 3. Get project members and their phase_duties
    member_stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    member_result = await db.execute(member_stmt)
    members = member_result.scalars().all()

    # 4. Cross-reference: for each required role, count assigned members
    filled_roles = []
    missing_roles = []

    for role_spec in required_roles:
        role_key = role_spec.get("role_key", role_spec.get("role", ""))
        required_count = role_spec.get("count", 1)
        role_label = role_spec.get("label", role_key)

        assigned_members = []
        for member in members:
            duties = member.phase_duties or {}
            phase_duty = duties.get(phase_node, {})
            if phase_duty.get("duty") == role_key or phase_duty.get("role") == role_key:
                username = await _resolve_username(db, member.user_id)
                assigned_members.append({"user_id": str(member.user_id), "username": username})

        filled_count = len(assigned_members)
        filled_roles.append({
            "role_key": role_key,
            "required_count": required_count,
            "filled_count": filled_count,
            "members": assigned_members,
        })

        if filled_count < required_count:
            missing_roles.append({
                "role_key": role_key,
                "count": required_count - filled_count,
                "label": role_label,
            })

    # 5. Suggest members from the project who don't have duties for this phase yet
    assigned_user_ids = set()
    for member in members:
        duties = member.phase_duties or {}
        if phase_node in duties:
            assigned_user_ids.add(str(member.user_id))

    suggested = []
    for member in members:
        if str(member.user_id) not in assigned_user_ids:
            username = await _resolve_username(db, member.user_id)
            dept_name = await _resolve_dept(db, member.source_org_unit_id)
            suggested.append({"user_id": str(member.user_id), "username": username, "dept_name": dept_name})

    is_ready = len(missing_roles) == 0

    return {
        "ready": is_ready,
        "phase_node": phase_node,
        "phase_label": phase_label,
        "filled_roles": filled_roles,
        "missing_roles": missing_roles,
        "suggested_members": suggested,
    }


async def _resolve_username(db: AsyncSession, user_id: UUID) -> str:
    user = await db.get(User, user_id)
    return user.username if user else str(user_id)


async def _resolve_dept(db: AsyncSession, dept_id: UUID | None) -> str | None:
    if not dept_id:
        return None
    dept = await db.get(Department, dept_id)
    return dept.name if dept else None
