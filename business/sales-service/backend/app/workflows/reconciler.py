"""Reconcile stale approval projections with Temporal execution state.

Temporal is the authority for a running workflow. The sales database is the
authority for business facts. When a worker dies between the final activity and
the projection update, this loop repairs the projection without ever approving a
gate on its own.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_maker
from app.domain import utc_now
from app.models import ApprovalRequest
from app.workflows.activities import finalize_request, mark_failed
from app.workflows.client import describe_approval

logger = logging.getLogger(__name__)
settings = get_settings()

TERMINAL_RESULTS = {"approved", "rejected", "returned", "cancelled", "expired"}


def completed_outcome(result: object) -> tuple[str, str | None] | None:
    """Map a workflow return value to a projected terminal status."""
    if isinstance(result, str) and result in TERMINAL_RESULTS:
        return result, None
    return None


def failed_outcome(status_name: str) -> tuple[str, str] | None:
    """Map a failed Temporal execution status to a safe terminal projection."""
    if status_name == "CANCELED":
        return "cancelled", "Temporal 工作流已取消"
    if status_name == "TIMED_OUT":
        return "expired", "Temporal 工作流执行超时"
    if status_name in {"FAILED", "TERMINATED"}:
        return "failed", f"Temporal 工作流状态：{status_name}"
    return None


async def _apply_terminal(request_id: str, status: str, reason: str | None) -> None:
    if status == "failed":
        await mark_failed(request_id, reason or "Temporal 工作流失败")
    else:
        await finalize_request(request_id, status, reason)


async def reconcile_once(limit: int = 50) -> int:
    """Repair at most ``limit`` stale running approvals.

    Temporal being unreachable is a transient condition: this function skips
    the row instead of marking a healthy approval as failed.
    """

    if not settings.temporal_enabled:
        return 0
    cutoff = utc_now() - timedelta(seconds=max(1, settings.temporal_reconcile_stale_seconds))
    async with get_session_maker()() as db:
        rows = list(
            (
                await db.execute(
                    select(ApprovalRequest.id, ApprovalRequest.workflow_id)
                    .where(
                        # pending_start with an id means the start RPC succeeded
                        # but mark_running did not reach the projection.
                        ApprovalRequest.status.in_(["pending_start", "running"]),
                        ApprovalRequest.workflow_id.is_not(None),
                        ApprovalRequest.updated_at < cutoff,
                    )
                    .order_by(ApprovalRequest.updated_at.asc())
                    .limit(limit)
                )
            ).all()
        )

    repaired = 0
    for request_id, workflow_id in rows:
        if not workflow_id:
            continue
        try:
            description = await describe_approval(str(request_id))
        except Exception as exc:  # noqa: BLE001 - Temporal may be temporarily down
            from temporalio.service import RPCError, RPCStatusCode

            # A missing namespace produces the same NOT_FOUND code as a missing
            # execution; never fail business approvals for a config mistake.
            if isinstance(exc, RPCError) and exc.status == RPCStatusCode.NOT_FOUND and "namespace" not in str(exc).lower():
                logger.error("approval %s has no Temporal workflow; marking failed", request_id)
                await mark_failed(str(request_id), "Temporal 工作流不存在，审批已标记失败")
                repaired += 1
            else:
                logger.warning("reconciler cannot describe approval %s: %s", request_id, exc)
            continue

        status_name = description.status.name
        if status_name == "RUNNING" or status_name == "CONTINUED_AS_NEW":
            continue

        try:
            if status_name == "COMPLETED":
                outcome = completed_outcome(await _workflow_result(str(request_id)))
                if outcome is None:
                    logger.error("approval %s completed with an unknown result; marking failed", request_id)
                    await mark_failed(str(request_id), "Temporal 工作流返回未知终态")
                else:
                    await _apply_terminal(str(request_id), outcome[0], outcome[1])
                repaired += 1
                continue

            outcome = failed_outcome(status_name)
            if outcome is None:
                logger.warning("approval %s has unhandled Temporal status %s", request_id, status_name)
                continue
            await _apply_terminal(str(request_id), outcome[0], outcome[1])
            repaired += 1
        except Exception:  # noqa: BLE001 - retry on the next reconcile tick
            logger.exception("reconciler failed to repair approval %s", request_id)
    return repaired


async def _workflow_result(request_id: str):
    from app.workflows.client import get_approval_handle

    handle = await get_approval_handle(request_id)
    timeout = max(1.0, settings.temporal_rpc_timeout_seconds)
    return await handle.result(rpc_timeout=timedelta(seconds=timeout))


async def reconciler_loop() -> None:
    while True:
        try:
            repaired = await reconcile_once()
            if repaired:
                logger.info("reconciled %s stale approval(s)", repaired)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("approval reconciler loop failed")
        await asyncio.sleep(max(10, settings.temporal_reconcile_interval_seconds))
