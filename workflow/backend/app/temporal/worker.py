"""Temporal worker entry point.

Run with::

    python -m app.temporal.worker

The worker is intentionally a separate process from the FastAPI application so
workflow tasks are not competing with HTTP requests for the API event loop.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import settings
from .client import close_client, get_client
from .workflow import FlowInstanceWorkflow, TemporalProbeWorkflow

logger = logging.getLogger(__name__)


async def _connect_with_retry():
    """Wait for Temporal during rolling deploys instead of crash-looping."""

    while True:
        try:
            return await get_client()
        except Exception as exc:  # noqa: BLE001 - startup retry is intentional
            logger.warning("Temporal not ready (%s); retrying in 5s", exc)
            await asyncio.sleep(5)


async def run_worker() -> None:
    if not settings.temporal_enabled:
        raise RuntimeError("TEMPORAL_ENABLED=0；Temporal worker 无法启动")

    from temporalio.worker import Worker

    from .activities import (
        apply_command_activity,
        get_instance_status_activity,
        probe_activity,
    )

    client = await _connect_with_retry()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[FlowInstanceWorkflow, TemporalProbeWorkflow],
        activities=[probe_activity, get_instance_status_activity, apply_command_activity],
        max_concurrent_activities=settings.temporal_max_concurrent_activities,
        max_concurrent_workflow_tasks=settings.temporal_max_concurrent_workflow_tasks,
    )
    logger.info(
        "workflow Temporal worker started: queue=%s namespace=%s",
        settings.temporal_task_queue,
        settings.temporal_namespace,
    )
    try:
        await worker.run()
    finally:
        await close_client()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
