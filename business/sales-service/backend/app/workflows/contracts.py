"""Serializable Temporal workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowApprover:
    """A participant slot in a parallel approval step."""

    key: str
    role: str | None = None
    user_id: str | None = None


@dataclass
class WorkflowStep:
    step_no: int
    approver_role: str
    sla_hours: int
    approver_id: str | None = None
    mode: str = "sequential"
    # Populated only for ``parallel_all`` / ``parallel_any``. ``approver_role``
    # remains the display/primary role for compatibility with the QW2 schema.
    approvers: list[WorkflowApprover] = field(default_factory=list)


@dataclass
class ApprovalWorkflowInput:
    request_id: str
    request_no: str
    opportunity_id: str
    gate_code: str
    requested_by: str
    steps: list[WorkflowStep] = field(default_factory=list)
    # Absolute Unix timestamp. Kept as a float (not datetime) so the default
    # Temporal JSON converter can serialize the DTO without a custom converter.
    expires_at_epoch: float | None = None


@dataclass
class DecisionSignal:
    step_no: int
    action: str
    actor_id: str
    actor_role: str | None
    comment: str | None
    idempotency_key: str
    delegate_to: str | None = None
    # Required for parallel steps; ``None`` keeps the sequential wire format.
    assignment_key: str | None = None


@dataclass
class CancellationSignal:
    actor_id: str
    reason: str | None = None
