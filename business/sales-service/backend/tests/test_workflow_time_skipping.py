"""Time-skipping tests for approval timers.

These tests use Temporal's test server, not the Docker Temporal cluster. The
test server can jump directly to the next timer, so 24h/4h/7d flows finish in
seconds. The rest of the suite stays offline and does not require a server.

Run explicitly with a downloaded test server:

    $env:TEMPORAL_TEST_SERVER = "C:\\tools\\temporal-test-server.exe"
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_workflow_time_skipping.py -q

If ``TEMPORAL_TEST_SERVER`` is not set, the test server is looked up on
``PATH``; otherwise these tests are skipped.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.workflows.contracts import ApprovalWorkflowInput, DecisionSignal, WorkflowApprover, WorkflowStep
from app.workflows.workflow import SalesApprovalWorkflow


def _test_server_path() -> str | None:
    configured = os.environ.get("TEMPORAL_TEST_SERVER")
    if configured:
        path = Path(configured)
        return str(path) if path.is_file() else shutil.which(configured)
    return shutil.which("temporal-test-server") or shutil.which("temporal-test-server.exe")


TEST_SERVER = _test_server_path()
pytestmark = pytest.mark.skipif(
    TEST_SERVER is None,
    reason="set TEMPORAL_TEST_SERVER to run time-skipping workflow tests",
)


def _payload(
    *,
    start: datetime,
    sla_hours: int,
    expires_in: timedelta,
    mode: str,
) -> ApprovalWorkflowInput:
    step = WorkflowStep(
        step_no=1,
        approver_role="regional_manager",
        sla_hours=sla_hours,
        mode=mode,
    )
    if mode in {"parallel_all", "parallel_any"}:
        step.approvers = [
            WorkflowApprover(key="role:regional_manager", role="regional_manager"),
            WorkflowApprover(key="role:sales_director", role="sales_director"),
        ]
    return ApprovalWorkflowInput(
        request_id=str(uuid.uuid4()),
        request_no="AP-TIME-SKIP",
        opportunity_id="opp-time-skip",
        gate_code="R4_EXCEPTION",
        requested_by="u-applicant",
        steps=[step],
        expires_at_epoch=(start + expires_in).timestamp(),
    )


async def _run_time_skipping_test(
    *,
    sla_hours: int,
    expires_in: timedelta,
    mode: str,
    delegate_after: timedelta | None = None,
) -> tuple[str, list[tuple[str, tuple[Any, ...], datetime]]]:
    calls: list[tuple[str, tuple[Any, ...], datetime]] = []
    task_queue = f"time-skip-{uuid.uuid4()}"
    activated = asyncio.Event()

    @activity.defn(name="mark_running")
    async def mark_running(payload: ApprovalWorkflowInput, workflow_id: str, run_id: str) -> None:
        calls.append(("mark_running", (payload.request_id, workflow_id, run_id), activity.info().scheduled_time))

    @activity.defn(name="activate_step")
    async def activate_step(request_id: str, step_no: int) -> None:
        calls.append(("activate_step", (request_id, step_no), activity.info().scheduled_time))
        activated.set()

    @activity.defn(name="activate_parallel_step")
    async def activate_parallel_step(request_id: str, step: WorkflowStep) -> None:
        calls.append(("activate_parallel_step", (request_id, step.step_no, step.mode), activity.info().scheduled_time))
        activated.set()

    @activity.defn(name="escalate_step")
    async def escalate_step(request_id: str, step_no: int, reason: str, level: int) -> None:
        calls.append(("escalate_step", (request_id, step_no, reason, level), activity.info().scheduled_time))

    @activity.defn(name="escalate_parallel_step")
    async def escalate_parallel_step(request_id: str, step_no: int, reason: str, level: int) -> str:
        calls.append(("escalate_parallel_step", (request_id, step_no, reason, level), activity.info().scheduled_time))
        return "active"

    @activity.defn(name="delegate_parallel_assignment")
    async def delegate_parallel_assignment(request_id: str, decision: DecisionSignal) -> str:
        calls.append(("delegate_parallel_assignment", (request_id, decision.assignment_key), activity.info().scheduled_time))
        return "active"

    @activity.defn(name="finalize_request")
    async def finalize_request(request_id: str, status: str, reason: str | None) -> None:
        calls.append(("finalize_request", (request_id, status, reason), activity.info().scheduled_time))

    async with await WorkflowEnvironment.start_time_skipping(
        test_server_existing_path=TEST_SERVER,
    ) as env:
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[SalesApprovalWorkflow],
            activities=[
                mark_running,
                activate_step,
                activate_parallel_step,
                escalate_step,
                escalate_parallel_step,
                delegate_parallel_assignment,
                finalize_request,
            ],
        ):
            started = await env.get_current_time()
            payload = _payload(start=started, sla_hours=sla_hours, expires_in=expires_in, mode=mode)
            handle = await env.client.start_workflow(
                SalesApprovalWorkflow.run,
                payload,
                id=f"time-skip-{uuid.uuid4()}",
                task_queue=task_queue,
            )
            await asyncio.wait_for(activated.wait(), timeout=10)
            if delegate_after is not None:
                await env.sleep(delegate_after)
                await handle.signal(
                    SalesApprovalWorkflow.receive_decision,
                    DecisionSignal(
                        step_no=1,
                        action="delegate",
                        actor_id="u-regional",
                        actor_role="regional_manager",
                        comment=None,
                        idempotency_key="time-skip-delegate",
                        delegate_to="u-delegate",
                        assignment_key="role:regional_manager",
                    ),
                )
            result = await handle.result()
    return result, calls


async def test_parallel_step_escalates_after_sla_then_expires_after_four_hours() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=24,
        expires_in=timedelta(days=8),
        mode="parallel_all",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == [
        "mark_running",
        "activate_parallel_step",
        "escalate_parallel_step",
        "finalize_request",
    ]
    assert calls[2][1][3] == 1
    assert calls[3][1][1] == "expired"
    assert calls[3][1][2] == "审批超时且升级后仍未处理"
    escalated_after = calls[2][2] - calls[0][2]
    expired_after_escalation = calls[3][2] - calls[2][2]
    assert timedelta(hours=23, minutes=55) <= escalated_after <= timedelta(hours=24, minutes=5)
    assert timedelta(hours=3, minutes=55) <= expired_after_escalation <= timedelta(hours=4, minutes=5)


async def test_overall_expiry_wins_before_a_long_step_sla() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=48,
        expires_in=timedelta(hours=1),
        mode="parallel_all",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == ["mark_running", "activate_parallel_step", "finalize_request"]
    assert calls[-1][1][1] == "expired"
    assert calls[-1][1][2] == "审批超过整体时限"
    elapsed = calls[-1][2] - calls[0][2]
    assert timedelta(minutes=59) <= elapsed <= timedelta(hours=1, minutes=5)


async def test_overall_seven_day_cap_still_expires() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=24 * 10,
        expires_in=timedelta(days=7),
        mode="parallel_all",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == ["mark_running", "activate_parallel_step", "finalize_request"]
    assert calls[-1][1][1] == "expired"
    elapsed = calls[-1][2] - calls[0][2]
    assert timedelta(days=6, hours=23, minutes=55) <= elapsed <= timedelta(days=7, minutes=5)


async def test_parallel_delegation_resets_the_step_clock_then_escalates() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=24,
        expires_in=timedelta(days=8),
        mode="parallel_all",
        delegate_after=timedelta(hours=2),
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == [
        "mark_running",
        "activate_parallel_step",
        "delegate_parallel_assignment",
        "escalate_parallel_step",
        "finalize_request",
    ]
    assert calls[4][1][1] == "expired"
    assert calls[4][1][2] == "审批超时且升级后仍未处理"
    delegated_after = calls[2][2] - calls[0][2]
    escalated_after_delegation = calls[3][2] - calls[2][2]
    expired_after_escalation = calls[4][2] - calls[3][2]
    assert timedelta(hours=1, minutes=55) <= delegated_after <= timedelta(hours=2, minutes=5)
    assert timedelta(hours=23, minutes=55) <= escalated_after_delegation <= timedelta(hours=24, minutes=5)
    assert timedelta(hours=3, minutes=55) <= expired_after_escalation <= timedelta(hours=4, minutes=5)


async def test_sequential_step_escalates_after_sla_then_expires_after_four_hours() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=24,
        expires_in=timedelta(days=8),
        mode="sequential",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == ["mark_running", "activate_step", "escalate_step", "finalize_request"]
    assert calls[2][1][3] == 1
    assert calls[3][1][1] == "expired"
    assert calls[3][1][2] == "审批超时且升级后仍未处理"
    escalated_after = calls[2][2] - calls[0][2]
    expired_after_escalation = calls[3][2] - calls[2][2]
    assert timedelta(hours=23, minutes=55) <= escalated_after <= timedelta(hours=24, minutes=5)
    assert timedelta(hours=3, minutes=55) <= expired_after_escalation <= timedelta(hours=4, minutes=5)


async def test_sequential_overall_expiry_uses_one_hour_cap() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=48,
        expires_in=timedelta(hours=1),
        mode="sequential",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == ["mark_running", "activate_step", "finalize_request"]
    assert calls[-1][1][1] == "expired"
    assert calls[-1][1][2] == "审批超过整体时限"
    elapsed = calls[-1][2] - calls[0][2]
    assert timedelta(minutes=59) <= elapsed <= timedelta(hours=1, minutes=5)


async def test_sequential_overall_seven_day_cap_still_expires() -> None:
    result, calls = await _run_time_skipping_test(
        sla_hours=24 * 10,
        expires_in=timedelta(days=7),
        mode="sequential",
    )

    assert result == "expired"
    names = [name for name, _, _ in calls]
    assert names == ["mark_running", "activate_step", "finalize_request"]
    assert calls[-1][1][1] == "expired"
    elapsed = calls[-1][2] - calls[0][2]
    assert timedelta(days=6, hours=23, minutes=55) <= elapsed <= timedelta(days=7, minutes=5)
