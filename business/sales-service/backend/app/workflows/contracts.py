"""Serializable Temporal workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowStep:
    step_no: int
    approver_role: str
    sla_hours: int
    approver_id: str | None = None
    # ``sequential`` is the only mode used by the QW2 templates today. The field
    # is part of the wire contract so a future parallel/any-of step can be added
    # without changing the workflow input shape.
    mode: str = "sequential"


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


@dataclass
class CancellationSignal:
    actor_id: str
    reason: str | None = None
