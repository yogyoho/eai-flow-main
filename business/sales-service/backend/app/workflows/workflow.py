"""Durable sales approval workflow.

The workflow owns ordering, timers and escalation. Every state change is a
Temporal activity so replay never mutates the sales database by itself.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

from app.workflows.contracts import ApprovalWorkflowInput, CancellationSignal, DecisionSignal, WorkflowStep
from app.workflows.parallel import PARALLEL_MODES

_ACTIVITY_TIMEOUT = timedelta(seconds=60)
_DELEGATE_WAIT = timedelta(hours=24)
_ESCALATED_WAIT = timedelta(hours=4)


@workflow.defn(name="SalesApprovalWorkflow")
class SalesApprovalWorkflow:
    def __init__(self) -> None:
        # Keyed by (step_no, assignment_key). Sequential signals use None.
        self.decisions: dict[tuple[int, str | None], DecisionSignal] = {}
        self.cancelled = False
        self.cancel_reason: str | None = None
        self.current_step = 0

    @workflow.run
    async def run(self, payload: ApprovalWorkflowInput) -> str:
        info = workflow.info()
        await workflow.execute_activity(
            "mark_running",
            args=[payload, info.workflow_id, info.run_id],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        try:
            for step in payload.steps:
                if self.cancelled:
                    await self._finalize(payload.request_id, "cancelled", self.cancel_reason or "发起人取消")
                    return "cancelled"
                if self._is_expired(payload):
                    await self._finalize(payload.request_id, "expired", "审批超过整体时限")
                    return "expired"
                self.current_step = step.step_no
                if step.mode in PARALLEL_MODES and workflow.patched("parallel-approval-v1"):
                    outcome, reason = await self._run_parallel_step(payload, step)
                    if outcome == "approved":
                        continue
                    await self._finalize(payload.request_id, outcome, reason or self._outcome_reason(outcome))
                    return outcome

                decision = await self._run_sequential_step(payload, step)
                if decision is None:
                    return "cancelled" if self.cancelled else "expired"
                await workflow.execute_activity(
                    "record_decision",
                    args=[payload.request_id, decision],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                if decision.action == "reject":
                    await self._finalize(payload.request_id, "rejected", decision.comment or "审批驳回")
                    return "rejected"
                if decision.action == "return":
                    await self._finalize(payload.request_id, "returned", decision.comment or "审批退回")
                    return "returned"
            await self._finalize(payload.request_id, "approved", None)
            return "approved"
        except Exception as exc:  # noqa: BLE001 - workflow must persist a terminal signal
            await workflow.execute_activity(
                "mark_failed",
                args=[payload.request_id, str(exc)],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            raise

    async def _run_sequential_step(self, payload: ApprovalWorkflowInput, step: WorkflowStep) -> DecisionSignal | None:
        await workflow.execute_activity(
            "activate_step",
            args=[payload.request_id, step.step_no],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        decision: DecisionSignal | None = None
        wait_hours = max(1, step.sla_hours)
        escalated = False
        escalation_level = 0
        while decision is None:
            timeout, expired_now = self._bounded_timeout(payload, timedelta(hours=wait_hours))
            if expired_now:
                await self._finalize(payload.request_id, "expired", "审批超过整体时限")
                return None
            try:
                await workflow.wait_condition(
                    lambda: (step.step_no, None) in self.decisions or self.cancelled,
                    timeout=timeout,
                )
            except TimeoutError:
                if self.cancelled:
                    await self._finalize(payload.request_id, "cancelled", self.cancel_reason or "发起人取消")
                    return None
                if self._is_expired(payload):
                    await self._finalize(payload.request_id, "expired", "审批超过整体时限")
                    return None
                if escalated:
                    await self._finalize(payload.request_id, "expired", "审批超时且升级后仍未处理")
                    return None
                escalation_level += 1
                escalation_args = [
                    payload.request_id,
                    step.step_no,
                    f"审批超过 {max(1, step.sla_hours)} 小时 SLA，已升级",
                ]
                if workflow.patched("approval-escalation-level-v1"):
                    escalation_args.append(escalation_level)
                await workflow.execute_activity(
                    "escalate_step",
                    args=escalation_args,
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                escalated = True
                wait_hours = 4
                continue
            if self.cancelled:
                await self._finalize(payload.request_id, "cancelled", self.cancel_reason or "发起人取消")
                return None
            candidate = self.decisions.pop((step.step_no, None))
            if candidate.action == "delegate":
                await workflow.execute_activity(
                    "delegate_step",
                    args=[payload.request_id, candidate],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                # A delegation restarts this step's clock for the new approver.
                # Keep 24h to stay aligned with delegate_step's projection.
                wait_hours = 24
                escalated = False
                continue
            decision = candidate
        return decision

    async def _run_parallel_step(self, payload: ApprovalWorkflowInput, step: WorkflowStep) -> tuple[str, str | None]:
        await workflow.execute_activity(
            "activate_parallel_step",
            args=[payload.request_id, step],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        deadline = workflow.now() + timedelta(hours=max(1, step.sla_hours))
        escalated = False
        escalation_level = 0
        while True:
            if self.cancelled:
                return "cancelled", self.cancel_reason
            if self._is_expired(payload):
                return "expired", "审批超过整体时限"
            if workflow.now() >= deadline:
                if escalated:
                    return "expired", "审批超时且升级后仍未处理"
                escalation_level += 1
                result = await workflow.execute_activity(
                    "escalate_parallel_step",
                    args=[payload.request_id, step.step_no, f"审批超过 {max(1, step.sla_hours)} 小时 SLA，已升级", escalation_level],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                if result in {"approved", "rejected", "returned", "cancelled", "expired"}:
                    return result, None
                if result != "active":
                    raise RuntimeError(f"并行审批升级失败：{result}")
                escalated = True
                deadline = workflow.now() + _ESCALATED_WAIT
                continue

            timeout, expired_now = self._bounded_timeout(payload, deadline - workflow.now())
            if expired_now:
                return "expired", "审批超过整体时限"
            try:
                await workflow.wait_condition(
                    lambda: self.cancelled or self._has_parallel_decision(step.step_no),
                    timeout=timeout,
                )
            except TimeoutError:
                # The loop head decides whether this is a normal escalation or
                # the post-escalation expiry.
                continue
            if self.cancelled:
                return "cancelled", self.cancel_reason

            keys = self._parallel_decision_keys(step.step_no)
            for key in keys:
                candidate = self.decisions.pop(key)
                if candidate.action == "delegate":
                    result = await workflow.execute_activity(
                        "delegate_parallel_assignment",
                        args=[payload.request_id, candidate],
                        start_to_close_timeout=_ACTIVITY_TIMEOUT,
                    )
                    if result in {"approved", "rejected", "returned", "cancelled", "expired"}:
                        return result, None
                    if result != "active":
                        raise RuntimeError(f"并行审批转办失败：{result}")
                    deadline = workflow.now() + _DELEGATE_WAIT
                    escalated = False
                    continue
                result = await workflow.execute_activity(
                    "record_parallel_decision",
                    args=[payload.request_id, candidate],
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                if result in {"approved", "rejected", "returned"}:
                    return result, None
                if result != "active":
                    raise RuntimeError(f"并行审批决策失败：{result}")

    def _has_parallel_decision(self, step_no: int) -> bool:
        return any(key_step == step_no and key_assignment is not None for key_step, key_assignment in self.decisions)

    def _parallel_decision_keys(self, step_no: int) -> list[tuple[int, str | None]]:
        return [key for key in self.decisions if key[0] == step_no and key[1] is not None]

    def _is_expired(self, payload: ApprovalWorkflowInput) -> bool:
        return payload.expires_at_epoch is not None and workflow.now().timestamp() >= payload.expires_at_epoch

    def _bounded_timeout(self, payload: ApprovalWorkflowInput, wait: timedelta) -> tuple[timedelta, bool]:
        """Never sleep past the approval's overall deadline."""
        if payload.expires_at_epoch is None:
            return wait, False
        remaining = payload.expires_at_epoch - workflow.now().timestamp()
        if remaining <= 0:
            return timedelta(0), True
        return min(wait, timedelta(seconds=remaining)), False

    def _outcome_reason(self, status: str) -> str | None:
        return {
            "rejected": "审批驳回",
            "returned": "审批退回",
            "cancelled": self.cancel_reason or "发起人取消",
            "expired": "审批超过整体时限",
        }.get(status)

    async def _finalize(self, request_id: str, status: str, reason: str | None) -> None:
        await workflow.execute_activity(
            "finalize_request",
            args=[request_id, status, reason],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

    @workflow.signal(name="decision")
    def receive_decision(self, decision: DecisionSignal) -> None:
        key = (decision.step_no, decision.assignment_key)
        if key not in self.decisions:
            self.decisions[key] = decision

    @workflow.signal(name="cancel")
    def receive_cancel(self, cancellation: CancellationSignal) -> None:
        self.cancelled = True
        self.cancel_reason = cancellation.reason

    @workflow.query(name="state")
    def get_state(self) -> dict:
        return {
            "current_step": self.current_step,
            "cancelled": self.cancelled,
            "decided_steps": sorted({step_no for step_no, _ in self.decisions}),
            "decided_assignments": sorted(str(key) for _, key in self.decisions if key is not None),
        }
