"""Temporal workflows for the workflow platform.

``FlowInstanceWorkflow`` is the real long-running approval orchestrator. It
receives durable command ids over a signal, applies each one through an
idempotent activity, and returns when the instance reaches a terminal state.
``TemporalProbeWorkflow`` remains as a small connectivity smoke test.
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

_ACTIVITY_TIMEOUT = timedelta(seconds=30)
_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=10,
)


@workflow.defn
class FlowInstanceWorkflow:
    """Long-running orchestration for one approval instance.

    The database is the read model/command inbox, not the authority for ordering.
    One workflow handles one instance; every approval mutation arrives as a
    durable command id signal. The activity is idempotent, so a duplicate signal
    or a dispatcher retry cannot apply the same approval twice.
    """

    def __init__(self) -> None:
        self._commands: deque[int] = deque()
        self._last_result: dict[str, Any] | None = None
        self._version = 0
        self._instance_id: int | None = None
        self._stopped = False
        self._stop_reason = ""

    @workflow.run
    async def run(self, instance_id: int) -> dict[str, Any]:
        self._instance_id = instance_id
        initial = await workflow.execute_activity(
            "get_instance_status_activity",
            instance_id,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY,
        )
        if initial.get("terminal"):
            return {
                "instance_id": instance_id,
                "flow_status": initial.get("flow_status"),
                "terminal": True,
                "reason": "already-terminal",
            }

        while True:
            await workflow.wait_condition(lambda: bool(self._commands) or self._stopped)
            if self._stopped:
                return {
                    "instance_id": instance_id,
                    "flow_status": initial.get("flow_status"),
                    "terminal": True,
                    "reason": self._stop_reason or "stopped",
                }
            command_id = self._commands.popleft()
            result = await workflow.execute_activity(
                "apply_command_activity",
                command_id,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_ACTIVITY_RETRY,
            )
            self._last_result = result
            self._version += 1
            if result.get("terminal"):
                return {
                    "instance_id": instance_id,
                    "flow_status": result.get("flow_status"),
                    "terminal": True,
                    "command_id": result.get("id"),
                }

    @workflow.signal(name="command")
    def receive_command(self, payload: dict[str, Any]) -> None:
        try:
            command_id = int(payload.get("id"))
        except (TypeError, ValueError, AttributeError):
            return
        if command_id > 0:
            self._commands.append(command_id)

    @workflow.signal(name="stop")
    def receive_stop(self, reason: str = "") -> None:
        self._stopped = True
        self._stop_reason = reason

    @workflow.query(name="state")
    def get_state(self) -> dict[str, Any]:
        return {
            "instance_id": self._instance_id,
            "queued": list(self._commands),
            "version": self._version,
            "last_result": self._last_result,
        }


@workflow.defn
class TemporalProbeWorkflow:
    """Smoke-test workflow used by local verification and integration tests."""

    @workflow.run
    async def run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        message = str((payload or {}).get("message", "ok"))
        activity_result = await workflow.execute_activity(
            "probe_activity",
            message,
            start_to_close_timeout=timedelta(seconds=5),
        )
        return {
            "status": "ok",
            "message": message,
            "activity_result": activity_result,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
        }
