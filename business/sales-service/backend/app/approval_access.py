"""Approval visibility and action checks shared by HTTP routers.

Sequential steps remain role/assignee based. Parallel steps delegate the same
rules to their participant slots, with one important difference: once a slot has
been delegated, only the delegate (or an admin) may act on it.
"""

from __future__ import annotations

from sqlalchemy import and_, or_

from app.auth import Identity
from app.models import ApprovalAssignment, ApprovalStep
from app.workflows.parallel import PARALLEL_MODES


def assignment_visible(identity: Identity, assignment: ApprovalAssignment) -> bool:
    if identity.is_admin or identity.data_scope == "all":
        return True
    if assignment.approver_id:
        return assignment.approver_id == identity.user_id
    return assignment.approver_role in {identity.sales_role, identity.role_code}


def assignment_actionable(identity: Identity, assignment: ApprovalAssignment) -> bool:
    if identity.is_admin:
        return True
    if assignment.approver_id:
        return assignment.approver_id == identity.user_id
    return identity.sales_role == assignment.approver_role or identity.role_code == assignment.approver_role


def step_visible(identity: Identity, step: ApprovalStep) -> bool:
    if identity.is_admin or identity.data_scope == "all":
        return True
    if step.mode in PARALLEL_MODES:
        return any(assignment_visible(identity, assignment) for assignment in step.assignments)
    if step.approver_id:
        return step.approver_id == identity.user_id
    return step.approver_role in {identity.sales_role, identity.role_code}


def step_actionable(identity: Identity, step: ApprovalStep) -> bool:
    if step.status != "active":
        return False
    if identity.is_admin:
        return True
    if step.mode in PARALLEL_MODES:
        return any(assignment.status == "active" and assignment_actionable(identity, assignment) for assignment in step.assignments)
    if step.approver_id:
        return step.approver_id == identity.user_id
    return identity.sales_role == step.approver_role or identity.role_code == step.approver_role


def active_step_scope_condition(identity: Identity):
    """SQL predicate for "this request has an active step I can act on"."""
    roles = {identity.sales_role, identity.role_code}
    sequential = and_(
        ApprovalStep.mode == "sequential",
        or_(
            and_(ApprovalStep.approver_id.is_(None), ApprovalStep.approver_role.in_(roles)),
            ApprovalStep.approver_id == identity.user_id,
        ),
    )
    parallel = and_(
        ApprovalStep.mode.in_(list(PARALLEL_MODES)),
        ApprovalStep.assignments.any(
            and_(
                ApprovalAssignment.status == "active",
                or_(
                    ApprovalAssignment.approver_id == identity.user_id,
                    and_(ApprovalAssignment.approver_id.is_(None), ApprovalAssignment.approver_role.in_(roles)),
                ),
            )
        ),
    )
    return and_(ApprovalStep.status == "active", or_(sequential, parallel))
