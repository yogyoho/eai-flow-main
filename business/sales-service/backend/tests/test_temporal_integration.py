"""Offline tests for the Temporal approval boundary.

These tests deliberately do not start a Temporal server. They cover the parts
that are easy to regress during a refactor: the serializable contract, the
deadline/SLA projection, outbox backoff, and reconciler status mapping.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from temporalio.converter import DataConverter

from app.approval_access import assignment_actionable, assignment_visible, step_actionable
from app.approval_service import _remaining_sla_hours, normalize_template_steps, reset_for_retry, workflow_input_for
from app.auth import Identity
from app.errors import SalesError
from app.workflows import workflow as workflow_module
from app.workflows.activities import _bounded_key
from app.workflows.client import _bounded
from app.workflows.contracts import ApprovalWorkflowInput, DecisionSignal, WorkflowApprover, WorkflowStep
from app.workflows.dispatcher import _event_failure, retry_delay_seconds
from app.workflows.parallel import parallel_step_outcome
from app.workflows.reconciler import completed_outcome, failed_outcome


def _request(expires_at: datetime | None = None):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        request_no="AP2026100001",
        opportunity_id="00000000-0000-0000-0000-000000000002",
        gate_code="R4",
        requested_by="u1001",
        expires_at=expires_at,
        steps=[
            SimpleNamespace(
                step_no=1,
                approver_role="regional_manager",
                approver_id=None,
                mode="sequential",
                sla_due_at=now + timedelta(hours=23, minutes=30),
            ),
            SimpleNamespace(
                step_no=2,
                approver_role="sales_director",
                approver_id="u1002",
                mode="sequential",
                sla_due_at=None,
            ),
        ],
    )


def test_contract_round_trips_through_default_temporal_converter():
    payload = ApprovalWorkflowInput(
        request_id="r1",
        request_no="AP1",
        opportunity_id="o1",
        gate_code="R4",
        requested_by="u1",
        steps=[WorkflowStep(1, "regional_manager", 24)],
        expires_at_epoch=datetime.now(UTC).timestamp(),
    )
    converter = DataConverter.default.payload_converter
    encoded = converter.to_payloads([payload])
    decoded = converter.from_payloads(encoded, [ApprovalWorkflowInput])[0]
    assert decoded == payload


def test_workflow_input_carries_step_mode_and_overall_deadline():
    expires = datetime.now(UTC) + timedelta(days=7)
    request = _request(expires)
    payload = workflow_input_for(request)
    assert payload.expires_at_epoch == expires.timestamp()
    assert payload.steps[0].mode == "sequential"
    assert payload.steps[0].sla_hours == 23
    # A missing SLA uses the 24h fallback needed by legacy rows.
    assert payload.steps[1].sla_hours == 24


def test_contract_round_trips_parallel_approvers():
    payload = ApprovalWorkflowInput(
        request_id="r1",
        request_no="AP1",
        opportunity_id="o1",
        gate_code="R6",
        requested_by="u1",
        steps=[
            WorkflowStep(
                step_no=1,
                approver_role="regional_manager",
                sla_hours=24,
                mode="parallel_all",
                approvers=[WorkflowApprover("role:regional_manager", role="regional_manager"), WorkflowApprover("role:sales_director", role="sales_director")],
            )
        ],
    )
    converter = DataConverter.default.payload_converter
    encoded = converter.to_payloads([payload])
    decoded = converter.from_payloads(encoded, [ApprovalWorkflowInput])[0]
    assert decoded == payload
    assert decoded.steps[0].approvers[1].key == "role:sales_director"


def test_parallel_template_normalization_uses_stable_slot_keys():
    steps = normalize_template_steps(
        [
            {
                "step_no": 1,
                "mode": "parallel_all",
                "sla_hours": 24,
                "approvers": [{"role": "regional_manager"}, {"user_id": "u1002"}],
            }
        ]
    )
    assert steps[0]["approver_role"] == "regional_manager"
    assert steps[0]["approvers"] == [
        {"key": "role:regional_manager", "role": "regional_manager", "user_id": None},
        {"key": "user:u1002", "role": None, "user_id": "u1002"},
    ]


def test_parallel_template_user_only_slots_get_escalation_role():
    steps = normalize_template_steps(
        [
            {
                "step_no": 1,
                "mode": "parallel_any",
                "approvers": [{"user_id": "u1002"}, {"user_id": "u1003"}],
            }
        ]
    )
    assert steps[0]["approver_role"] == "sales_director"
    assert [item["key"] for item in steps[0]["approvers"]] == ["user:u1002", "user:u1003"]


def test_parallel_template_rejects_duplicate_slots():
    with pytest.raises(SalesError):
        normalize_template_steps(
            [
                {
                    "step_no": 1,
                    "mode": "parallel_any",
                    "approvers": [{"role": "sales_director"}, {"role": "sales_director"}],
                }
            ]
        )


def test_workflow_input_includes_parallel_approvers_from_snapshot():
    now = datetime.now(UTC)
    request = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        request_no="AP2026100002",
        opportunity_id="00000000-0000-0000-0000-000000000002",
        gate_code="R6",
        requested_by="u1001",
        expires_at=now + timedelta(days=7),
        payload_json={
            "approval_steps": [
                {
                    "step_no": 1,
                    "mode": "parallel_any",
                    "approver_role": "regional_manager",
                    "sla_hours": 24,
                    "approvers": [
                        {"key": "role:regional_manager", "role": "regional_manager", "user_id": None},
                        {"key": "role:compliance_officer", "role": "compliance_officer", "user_id": None},
                    ],
                }
            ]
        },
        steps=[
            SimpleNamespace(
                step_no=1,
                approver_role="regional_manager",
                approver_id=None,
                mode="parallel_any",
                sla_due_at=now + timedelta(hours=24),
            )
        ],
    )
    payload = workflow_input_for(request)
    assert payload.steps[0].mode == "parallel_any"
    assert [approver.key for approver in payload.steps[0].approvers] == ["role:regional_manager", "role:compliance_officer"]


@pytest.mark.parametrize(
    ("mode", "statuses", "expected"),
    [
        ("parallel_all", ["approved", "approved"], "approved"),
        ("parallel_all", ["approved", "active"], "active"),
        ("parallel_all", ["approved", "rejected"], "rejected"),
        ("parallel_all", ["approved", "returned"], "returned"),
        ("parallel_any", ["approved", "active"], "approved"),
        ("parallel_any", ["rejected", "active"], "active"),
        ("parallel_any", ["rejected", "rejected"], "rejected"),
        ("parallel_any", ["rejected", "returned"], "returned"),
    ],
)
def test_parallel_step_outcome(mode, statuses, expected):
    assert parallel_step_outcome(mode, statuses) == expected


def test_workflow_keeps_parallel_signals_separate_by_slot():
    instance = workflow_module.SalesApprovalWorkflow()
    first = DecisionSignal(1, "approve", "u1", "regional_manager", None, "key-0001", assignment_key="role:regional_manager")
    second = DecisionSignal(1, "approve", "u2", "sales_director", None, "key-0002", assignment_key="role:sales_director")
    instance.receive_decision(first)
    instance.receive_decision(second)
    assert set(instance.decisions) == {(1, "role:regional_manager"), (1, "role:sales_director")}
    assert instance.get_state()["decided_steps"] == [1]
    assert instance.get_state()["decided_assignments"] == ["role:regional_manager", "role:sales_director"]


def test_remaining_sla_never_returns_zero_hours():
    step = SimpleNamespace(sla_due_at=datetime.now(UTC) - timedelta(hours=2))
    assert _remaining_sla_hours(step) == 1


def test_retry_restarts_from_creation_snapshot():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    steps = [
        SimpleNamespace(
            step_no=1,
            approver_role="sales_director",
            approver_id="delegated-user",
            mode="sequential",
            status="cancelled",
            decision="approve",
            comment="stale",
            decided_at=now,
            escalated_at=now,
            escalation_level=2,
            idempotency_key="old-key",
            sla_due_at=now,
        ),
        SimpleNamespace(
            step_no=2,
            approver_role="compliance_officer",
            approver_id="delegated-user",
            mode="sequential",
            status="skipped",
            decision=None,
            comment=None,
            decided_at=None,
            escalated_at=None,
            escalation_level=0,
            idempotency_key=None,
            sla_due_at=None,
        ),
    ]
    request = SimpleNamespace(
        status="failed",
        current_step=2,
        workflow_id="sales-approval-old",
        workflow_run_id="run-old",
        started_at=now,
        completed_at=now,
        failure_reason="boom",
        expires_at=now,
        payload_json={"approval_steps": [{"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24}]},
        steps=steps,
    )
    reset_for_retry(request, now)
    assert request.status == "pending_start"
    assert request.current_step == 1
    assert request.workflow_id is None
    assert request.workflow_run_id is None
    assert request.started_at is None
    assert request.completed_at is None
    assert request.failure_reason is None
    assert request.expires_at == now + timedelta(days=7)
    assert steps[0].approver_role == "regional_manager"
    assert steps[0].approver_id is None
    assert steps[0].status == "pending"
    assert steps[0].decision is None
    assert steps[0].escalation_level == 0
    assert steps[0].idempotency_key is None
    assert steps[0].sla_due_at == now + timedelta(hours=24)
    assert steps[1].status == "pending"
    assert steps[1].approver_id is None
    assert steps[1].sla_due_at == now + timedelta(hours=24)


def test_retry_clears_parallel_assignments_and_restores_snapshot():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    assignments = [SimpleNamespace(assignment_key="role:regional_manager")]
    step = SimpleNamespace(
        step_no=1,
        approver_role="sales_director",
        approver_id="delegated-user",
        mode="sequential",
        status="cancelled",
        decision="reject",
        comment="stale",
        decided_at=now,
        escalated_at=now,
        escalation_level=1,
        idempotency_key="old-key",
        sla_due_at=now,
        assignments=assignments,
    )
    request = SimpleNamespace(
        status="failed",
        current_step=1,
        workflow_id="sales-approval-old",
        workflow_run_id="run-old",
        started_at=now,
        completed_at=now,
        failure_reason="boom",
        expires_at=now,
        payload_json={
            "approval_steps": [
                {
                    "step_no": 1,
                    "mode": "parallel_all",
                    "approver_role": "regional_manager",
                    "sla_hours": 24,
                    "approvers": [{"key": "role:regional_manager", "role": "regional_manager", "user_id": None}],
                }
            ]
        },
        steps=[step],
    )
    reset_for_retry(request, now)
    assert step.mode == "parallel_all"
    assert step.approver_role == "regional_manager"
    assert step.assignments == []
    assert step.status == "pending"
    assert step.sla_due_at == now + timedelta(hours=24)


def test_retry_delay_is_bounded():
    assert retry_delay_seconds(1) == 10
    assert retry_delay_seconds(2) == 20
    assert retry_delay_seconds(50) == 300


@pytest.mark.asyncio
async def test_bounded_rpc_returns_value():
    async def quick():
        return 42

    assert await _bounded(quick(), "quick") == 42


@pytest.mark.asyncio
async def test_bounded_rpc_times_out(monkeypatch):
    monkeypatch.setattr("app.workflows.client.settings.temporal_rpc_timeout_seconds", 0.01)

    async def slow():
        await asyncio.sleep(1)

    with pytest.raises(TimeoutError, match="Temporal slow 超时"):
        await _bounded(slow(), "slow")


def test_outbox_failure_enters_terminal_state_after_max_attempts():
    from app.workflows.dispatcher import settings

    event = SimpleNamespace(
        id="e1",
        attempts=settings.outbox_max_attempts - 1,
        last_error=None,
        status="pending",
        processed_at=None,
        next_retry_at=None,
    )
    request = SimpleNamespace(status="pending_start", completed_at=None, failure_reason=None)
    _event_failure(None, event, request, RuntimeError("temporal down"))
    assert event.status == "failed"
    assert event.attempts == settings.outbox_max_attempts
    assert event.next_retry_at is None
    assert request.status == "failed"
    assert request.completed_at is not None
    assert "temporal down" in request.failure_reason


def test_workflow_timeout_never_exceeds_overall_deadline(monkeypatch):
    fixed_now = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(workflow_module.workflow, "now", lambda: fixed_now)
    instance = workflow_module.SalesApprovalWorkflow()
    payload = ApprovalWorkflowInput(
        request_id="r1",
        request_no="AP1",
        opportunity_id="o1",
        gate_code="R4",
        requested_by="u1",
        expires_at_epoch=(fixed_now + timedelta(seconds=60)).timestamp(),
    )
    timeout, expired = instance._bounded_timeout(payload, timedelta(hours=24))
    assert timeout == timedelta(seconds=60)
    assert expired is False
    assert instance._is_expired(payload) is False

    payload.expires_at_epoch = (fixed_now - timedelta(seconds=1)).timestamp()
    timeout, expired = instance._bounded_timeout(payload, timedelta(hours=24))
    assert timeout == timedelta(0)
    assert expired is True
    assert instance._is_expired(payload) is True


def _identity(*, user_id: str, role_code: str, sales_role: str) -> Identity:
    return Identity(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        role_code=role_code,
        sales_role=sales_role,
        data_scope="self",
    )


def test_parallel_assignment_visibility_and_delegation_narrowing():
    role_user = _identity(user_id="u-manager", role_code="regional_manager", sales_role="regional_manager")
    delegate = _identity(user_id="u-director", role_code="sales_director", sales_role="sales_director")
    assignment = SimpleNamespace(
        assignment_key="role:regional_manager",
        approver_role="regional_manager",
        approver_id=None,
        status="active",
    )
    assert assignment_visible(role_user, assignment) is True
    assert assignment_actionable(role_user, assignment) is True
    role_code_only = _identity(user_id="u-code", role_code="regional_manager", sales_role="sales_rep")
    assert assignment_visible(role_code_only, assignment) is True
    assert assignment_actionable(role_code_only, assignment) is True

    assignment.approver_id = "u-director"
    assignment.delegated_from = "u-manager"
    assert assignment_visible(role_user, assignment) is False
    assert assignment_actionable(role_user, assignment) is False
    assert assignment_actionable(delegate, assignment) is True

    step = SimpleNamespace(mode="parallel_all", status="active", assignments=[assignment])
    assert step_actionable(role_user, step) is False
    assert step_actionable(delegate, step) is True


def test_parallel_step_actionability_ignores_terminal_slots():
    identity = _identity(user_id="u1", role_code="regional_manager", sales_role="regional_manager")
    approved = SimpleNamespace(
        assignment_key="role:regional_manager",
        approver_role="regional_manager",
        approver_id=None,
        status="approved",
    )
    awaiting = SimpleNamespace(
        assignment_key="role:sales_director",
        approver_role="sales_director",
        approver_id=None,
        status="active",
    )
    step = SimpleNamespace(mode="parallel_any", status="active", assignments=[approved, awaiting])
    assert step_actionable(identity, step) is False

    step.status = "approved"
    director = _identity(user_id="u2", role_code="sales_director", sales_role="sales_director")
    assert step_actionable(director, step) is False


def test_generated_todo_keys_fit_the_column_limit():
    short = "approval:short"
    assert _bounded_key(short) == short
    long = "assignment:" + ("x" * 400)
    bounded = _bounded_key(long)
    assert len(bounded) <= 200
    assert bounded.startswith("approval:")
    assert _bounded_key(long) == bounded


def test_completed_and_failed_outcomes_are_safe():
    assert completed_outcome("approved") == ("approved", None)
    assert completed_outcome("expired") == ("expired", None)
    assert completed_outcome("unexpected") is None
    assert failed_outcome("CANCELED")[0] == "cancelled"
    assert failed_outcome("TIMED_OUT")[0] == "expired"
    assert failed_outcome("FAILED")[0] == "failed"
    assert failed_outcome("RUNNING") is None
