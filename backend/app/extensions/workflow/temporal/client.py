import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)

TEMPORAL_TASK_QUEUE = "project-workflow-queue"
TEMPORAL_URL = "localhost:7233"

_temporal_client: Client | None = None


def get_temporal_client() -> Client | None:
    """Get the global Temporal client instance."""
    return _temporal_client


@asynccontextmanager
async def temporal_lifespan(app: FastAPI):
    """FastAPI lifespan manager for Temporal Client + embedded Worker.

    If Temporal server is unreachable, logs a warning and continues.
    All workflow features will be disabled until server becomes available.
    """
    global _temporal_client

    try:
        client = await Client.connect(TEMPORAL_URL, namespace="default")

        # Import here to avoid circular imports
        from .workflows import DynamicGraphWorkflow
        from .activities import ALL_ACTIVITIES

        worker = Worker(
            client,
            task_queue=TEMPORAL_TASK_QUEUE,
            workflows=[DynamicGraphWorkflow],
            activities=ALL_ACTIVITIES,
        )
        worker_task = asyncio.create_task(worker.run())

        _temporal_client = client
        app.state.temporal_client = client
        logger.info("Temporal client connected, worker started on queue '%s'", TEMPORAL_TASK_QUEUE)

        yield

        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        _temporal_client = None

    except Exception as e:
        logger.warning("Temporal server not available (%s). Workflow features disabled.", e)
        yield
