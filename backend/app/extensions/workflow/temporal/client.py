import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)

TEMPORAL_TASK_QUEUE = "project-workflow-queue"
TEMPORAL_URL = os.environ.get("TEMPORAL_URL", "localhost:7233")

_temporal_client: Client | None = None


def get_temporal_client() -> Client | None:
    """Get the global Temporal client instance."""
    return _temporal_client


@asynccontextmanager
async def temporal_lifespan(app: FastAPI):
    """FastAPI lifespan manager for Temporal Client + embedded Worker.

    EAI-CUSTOM (bug-3441, 2026-09-26): Temporal 在 EAI dev 是可选组件
    (temporal-workflow-engine-deploy：默认不起 Temporal 容器)。因此连接走
    **后台任务**、完全移出 gateway 就绪临界路径 —— lifespan 立即进入服务
    （上游 test_gateway_lifespan_shutdown 的 <1s 就绪断言依赖这一点）；
    连接成功后 workflow 特性自动挂载，失败/超时(10s)则记录警告保持停用。
    连接阶段与 body 阶段异常语义分离（bug-3401）：body 业务异常原样穿透。
    """
    global _temporal_client

    holder: dict = {}

    async def _connect() -> None:
        try:
            client = await asyncio.wait_for(
                Client.connect(TEMPORAL_URL, namespace="default"),
                timeout=10.0,
            )

            # Import here to avoid circular imports
            # Use unsandboxed runner — the workflow module transitively imports
            # FastAPI (via __init__.py → routers.py) which is incompatible with
            # Temporal's sandbox restrictions (sniffio._ThreadLocal).
            from temporalio.worker import UnsandboxedWorkflowRunner

            from .activities import ALL_ACTIVITIES
            from .workflows import DynamicGraphWorkflow

            worker = Worker(
                client,
                task_queue=TEMPORAL_TASK_QUEUE,
                workflows=[DynamicGraphWorkflow],
                activities=ALL_ACTIVITIES,
                workflow_runner=UnsandboxedWorkflowRunner(),
            )
            wt = asyncio.create_task(worker.run())
            holder["worker"] = wt
            _temporal_client = client
            app.state.temporal_client = client
            logger.info("Temporal client connected, worker started on queue '%s'", TEMPORAL_TASK_QUEUE)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Temporal server not available (%s). Workflow features disabled.", e)

    connect_task = asyncio.create_task(_connect())

    try:
        yield
    finally:
        connect_task.cancel()
        try:
            await connect_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Temporal connect task ended with error during shutdown", exc_info=True)
        worker_task = holder.get("worker")
        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        _temporal_client = None
        if getattr(app.state, "temporal_client", None) is not None:
            app.state.temporal_client = None


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
        result = await db.execute(select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id))
        workflow_id = result.scalar_one_or_none()

    if not workflow_id:
        logger.warning("No active workflow for project %s", project_id)
        return

    handle = client.get_workflow_handle(workflow_id)
    # temporalio 1.27: multi-arg signals must use args=[...] (positional splat
    # raises "signal() takes 2 to 3 positional arguments").
    await handle.signal(signal_name, args=args)


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
        result = await db.execute(select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id))
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

    import uuid as _uuid

    from temporalio.common import WorkflowIDReusePolicy

    from .workflows import DynamicGraphWorkflow

    wf_id = f"project-{params.get('project_id', 'unknown')}-{_uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        DynamicGraphWorkflow.run,
        params,
        id=wf_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    return handle.id
