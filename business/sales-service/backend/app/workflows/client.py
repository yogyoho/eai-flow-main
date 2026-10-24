"""Temporal client helpers with an optional dependency boundary."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from app.config import get_settings
from app.errors import unavailable

logger = logging.getLogger(__name__)
settings = get_settings()
_client: Any = None
_lock = asyncio.Lock()


def _rpc_timeout() -> timedelta:
    return timedelta(seconds=max(1.0, settings.temporal_rpc_timeout_seconds))


async def _bounded(awaitable, label: str):
    """Hard deadline around an RPC.

    ``rpc_timeout`` bounds the server call, but a client reconnecting after an
    outage can still sit in the channel layer. This outer deadline keeps the
    outbox and API request paths responsive.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=max(1.0, settings.temporal_rpc_timeout_seconds))
    except TimeoutError as exc:
        raise TimeoutError(f"Temporal {label} 超时") from exc


async def get_client():
    global _client
    if not settings.temporal_enabled:
        raise unavailable("审批引擎未启用")
    if _client is not None:
        return _client
    async with _lock:
        if _client is not None:
            return _client
        try:
            from temporalio.client import Client
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise unavailable("Temporal 客户端未安装") from exc
        try:
            _client = await Client.connect(
                settings.temporal_url,
                namespace=settings.temporal_namespace,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Temporal connection failed: %s", exc)
            raise unavailable() from exc
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:  # noqa: BLE001
            pass
        _client = None


def workflow_id_for(request_id: str) -> str:
    return f"{settings.temporal_workflow_id_prefix}-{request_id}"


async def temporal_health() -> dict[str, Any]:
    """Return a bounded, read-only probe used by ``/health``.

    A cached client is not proof that the server is still reachable, so the
    probe performs one cheap RPC with a short timeout. Health checks must never
    block startup or make the API unavailable when Temporal is down.
    """

    result: dict[str, Any] = {
        "enabled": settings.temporal_enabled,
        "url": settings.temporal_url,
        "namespace": settings.temporal_namespace,
        "task_queue": settings.temporal_task_queue,
        "connected": None,
    }
    if not settings.temporal_enabled:
        return result
    try:
        from temporalio.api.workflowservice.v1 import GetSystemInfoRequest

        client = await asyncio.wait_for(get_client(), timeout=settings.temporal_probe_timeout_seconds)
        await asyncio.wait_for(
            client.workflow_service.get_system_info(
                GetSystemInfoRequest(),
                timeout=timedelta(seconds=settings.temporal_probe_timeout_seconds),
            ),
            timeout=settings.temporal_probe_timeout_seconds + 0.5,
        )
        result["connected"] = True
    except Exception as exc:  # noqa: BLE001 - health is best effort
        result["connected"] = False
        result["error"] = f"{exc.__class__.__name__}: {exc}"[:300]
    return result


async def start_approval_workflow(workflow_input, request_id: str):
    from temporalio.common import WorkflowIDReusePolicy

    async def _start():
        client = await get_client()
        return await client.start_workflow(
            "SalesApprovalWorkflow",
            workflow_input,
            id=workflow_id_for(request_id),
            task_queue=settings.temporal_task_queue,
            # A retry after an activity failure is allowed, but a successful run is
            # never silently replaced. The dispatcher still treats
            # WorkflowAlreadyStartedError as the normal idempotent path.
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
            rpc_timeout=_rpc_timeout(),
        )

    return await _bounded(_start(), "start_workflow")


async def get_approval_handle(request_id: str):
    client = await get_client()
    return client.get_workflow_handle(workflow_id_for(request_id))


async def describe_approval(request_id: str):
    async def _describe():
        handle = await get_approval_handle(request_id)
        return await handle.describe(rpc_timeout=_rpc_timeout())

    return await _bounded(_describe(), "describe")


async def signal_decision(request_id: str, signal) -> None:
    from app.workflows.contracts import DecisionSignal  # noqa: F401

    async def _signal():
        handle = await get_approval_handle(request_id)
        await handle.signal("decision", signal, rpc_timeout=_rpc_timeout())

    await _bounded(_signal(), "signal_decision")


async def signal_cancel(request_id: str, signal) -> None:
    from app.workflows.contracts import CancellationSignal  # noqa: F401

    async def _signal():
        handle = await get_approval_handle(request_id)
        await handle.signal("cancel", signal, rpc_timeout=_rpc_timeout())

    await _bounded(_signal(), "signal_cancel")
