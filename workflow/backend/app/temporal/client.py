"""Bounded Temporal client used by the workflow API and worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def get_client():
    """Return a cached Temporal client, connecting on first use."""

    global _client
    if not settings.temporal_enabled:
        raise RuntimeError("Temporal 未启用（TEMPORAL_ENABLED=0）")
    if _client is not None:
        return _client

    async with _get_lock():
        if _client is not None:
            return _client
        try:
            from temporalio.client import Client
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("Temporal 客户端未安装") from exc

        try:
            _client = await asyncio.wait_for(
                Client.connect(
                    settings.temporal_url,
                    namespace=settings.temporal_namespace,
                ),
                timeout=max(1.0, settings.temporal_rpc_timeout_seconds),
            )
        except TimeoutError:
            logger.warning("Temporal connection timed out: %s", settings.temporal_url)
            raise
        except Exception:
            logger.exception("Temporal connection failed: %s", settings.temporal_url)
            raise
        logger.info(
            "Temporal connected: url=%s namespace=%s",
            settings.temporal_url,
            settings.temporal_namespace,
        )
    return _client


async def close_client() -> None:
    """Close the cached client; safe to call when no client exists."""

    global _client
    client, _client = _client, None
    if client is not None:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 - shutdown must not fail
            logger.exception("Temporal client close failed")


async def temporal_health() -> dict[str, Any]:
    """Return a bounded, read-only probe used by ``/health``.

    Health must stay responsive when Temporal is down, so the probe never
    raises and uses a short deadline.
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

        client = await asyncio.wait_for(
            get_client(),
            timeout=settings.temporal_probe_timeout_seconds,
        )
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
