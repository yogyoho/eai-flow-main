"""Temporal worker entrypoint for sales approvals."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.workflows.activities import (
    activate_parallel_step,
    activate_step,
    delegate_parallel_assignment,
    delegate_step,
    escalate_parallel_step,
    escalate_step,
    finalize_request,
    mark_failed,
    mark_running,
    record_decision,
    record_parallel_decision,
)
from app.workflows.client import get_client
from app.workflows.dispatcher import dispatcher_loop
from app.workflows.reconciler import reconciler_loop
from app.workflows.workflow import SalesApprovalWorkflow

logger = logging.getLogger(__name__)
settings = get_settings()


async def _connect_to_temporal():
    """Wait for Temporal during rolling deploys instead of crash-looping."""
    while True:
        try:
            return await get_client()
        except Exception as exc:  # noqa: BLE001 - startup retry is intentional
            logger.warning("Temporal not ready (%s); retrying in 5s", exc)
            await asyncio.sleep(5)


async def run_worker() -> None:
    from temporalio.worker import Worker

    if not settings.temporal_enabled:
        raise RuntimeError("TEMPORAL_ENABLED=false；Worker 无法启动")
    client = await _connect_to_temporal()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SalesApprovalWorkflow],
        activities=[
            mark_running,
            activate_step,
            activate_parallel_step,
            escalate_step,
            escalate_parallel_step,
            record_decision,
            record_parallel_decision,
            delegate_step,
            delegate_parallel_assignment,
            finalize_request,
            mark_failed,
        ],
        max_concurrent_activities=settings.temporal_max_concurrent_activities,
        max_concurrent_workflow_tasks=settings.temporal_max_concurrent_workflow_tasks,
    )
    background = [
        asyncio.create_task(dispatcher_loop(), name="sales-outbox-dispatcher"),
        asyncio.create_task(reconciler_loop(), name="sales-approval-reconciler"),
    ]
    logger.info("sales worker started on queue=%s", settings.temporal_task_queue)
    try:
        await worker.run()
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
