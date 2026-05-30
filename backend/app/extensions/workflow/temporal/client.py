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


def _get_client():
    """Return the Temporal client if connected, else None."""
    return _temporal_client


async def send_signal(project_id: str, signal_name: str, args: list) -> None:
    """Send a signal to the running workflow for a project."""
    client = _get_client()
    if client is None:
        logger.warning("Temporal unavailable — signal %s for project %s dropped", signal_name, project_id)
        return

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id)
        )
        workflow_id = result.scalar_one_or_none()

    if not workflow_id:
        logger.warning("No active workflow for project %s", project_id)
        return

    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(signal_name, *args)


async def get_workflow_status(project_id: str) -> dict | None:
    """Query Temporal for the current workflow execution status."""
    client = _get_client()
    if client is None:
        return None

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(
                ReportProject.workflow_id,
                ReportProject.temporal_workflow_id,
                ReportProject.current_phase_node,
                ReportProject.status,
            ).where(ReportProject.id == project_id)
        )
        row = result.first()

    if not row or not row.temporal_workflow_id:
        return None

    try:
        handle = client.get_workflow_handle(row.temporal_workflow_id)
        desc = await handle.describe()
        return {
            "workflow_id": str(row.workflow_id) if row.workflow_id else None,
            "temporal_workflow_id": row.temporal_workflow_id,
            "current_phase_node": row.current_phase_node,
            "status": "running" if desc.status == 1 else "completed" if desc.status == 2 else "failed",
            "close_time": str(desc.close_time) if desc.close_time else None,
        }
    except Exception:
        logger.exception("Failed to query workflow status for project %s", project_id)
        return None


async def cancel_workflow(project_id: str) -> bool:
    """Cancel the running workflow for a project."""
    client = _get_client()
    if client is None:
        return False

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id)
        )
        workflow_id = result.scalar_one_or_none()

    if not workflow_id:
        return False

    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
        return True
    except Exception:
        logger.exception("Failed to cancel workflow for project %s", project_id)
        return False


async def start_workflow(workflow_name: str, params: dict) -> str | None:
    """Start a new Temporal workflow execution. Returns the workflow ID or None."""
    client = _get_client()
    if client is None:
        logger.warning("Temporal unavailable — cannot start workflow")
        return None

    from temporalio.common import WorkflowIDReusePolicy
    from .workflows import DynamicGraphWorkflow

    import uuid as _uuid
    wf_id = f"project-{params.get('project_id', 'unknown')}-{_uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        DynamicGraphWorkflow.run,
        params,
        id=wf_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    return handle.id
