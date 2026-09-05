"""Centralized accessors for singleton objects stored on ``app.state``.

**Getters** (used by routers): raise 503 when a required dependency is
missing, except ``get_store`` which returns ``None``.

``AppConfig`` is intentionally *not* cached on ``app.state``. Routers and the
run path resolve it through :func:`deerflow.config.app_config.get_app_config`,
which performs mtime-based hot reload, so edits to ``config.yaml`` take
effect on the next request without a process restart. The engines created in
:func:`langgraph_runtime` (stream bridge, persistence, checkpointer, store,
run-event store) accept a ``startup_config`` snapshot — they are
restart-required by design and stay bound to that snapshot to keep the live
process consistent with itself.

Initialization is handled directly in ``app.py`` via :class:`AsyncExitStack`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeVar, cast

from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Checkpointer

from deerflow.community.browser_automation.session import browser_multi_worker_error
from deerflow.config.app_config import AppConfig, get_app_config
from deerflow.persistence.feedback import FeedbackRepository
from deerflow.runtime import RunContext, RunManager, StreamBridge

if TYPE_CHECKING:
    # EAI-CUSTOM: lazy-imported scheduled-task repos used as annotations below
    # (imported at runtime inside `initialize`); TYPE_CHECKING keeps ruff happy
    # without a runtime import cycle.
    from deerflow.persistence.scheduled_task_runs import ScheduledTaskRunRepository
    from deerflow.persistence.scheduled_tasks import ScheduledTaskRepository
from deerflow.runtime.checkpoint_mode import freeze_checkpoint_channel_mode, freeze_checkpoint_snapshot_frequency
from deerflow.runtime.events.store.base import RunEventStore
from deerflow.runtime.runs.store.base import RunStore

logger = logging.getLogger(__name__)


# EAI-CUSTOM: ported from upstream bytedance/main (deps.py) so the upstream
# startup-config validation tests (test_agent_storage_backend,
# test_multi_worker_postgres_gate) pass against EAI's deps.py. Both are no-ops
# for the default single-worker EAI deployment (GATEWAY_WORKERS=1).
def _browser_tools_enabled_in_config(config: AppConfig) -> bool:
    """Return whether process-local agentic browser sessions are configured."""
    get_tool_config = getattr(config, "get_tool_config", None)
    if callable(get_tool_config):
        return get_tool_config("browser_navigate") is not None
    return any(getattr(tool, "name", None) == "browser_navigate" for tool in (getattr(config, "tools", None) or []))


def _enforce_postgres_for_multi_worker(config: AppConfig) -> None:
    """Refuse unsafe multi-worker configurations before persistence starts.

    Five checks (all must pass for multi-worker):

    1. The background scheduler must be disabled for ordinary multi-worker
       mode. ``scheduler.multi_instance`` opts into the lease-aware path.
    2. Process-local browser sessions must be disabled.
    3. The DB backend must be Postgres (SQLite write-locks cannot support
       concurrent multi-process access).
    4. ``run_events.backend`` must be ``db`` (memory/JSONL stores are
       process-local).
    5. ``run_ownership.heartbeat_enabled`` must be True (without heartbeat,
       reconciliation treats all inflight runs as orphans).
    """
    try:
        workers = int(os.environ.get("GATEWAY_WORKERS", "1"))
    except (TypeError, ValueError):
        workers = 1

    scheduler = getattr(config, "scheduler", None)
    multi_instance_requested = bool(getattr(scheduler, "multi_instance", False))
    multi_instance_scheduler = bool(getattr(scheduler, "enabled", False) and multi_instance_requested)

    backend = getattr(config.database, "backend", None)
    run_events_backend = getattr(getattr(config, "run_events", None), "backend", None)
    run_ownership = getattr(config, "run_ownership", None)

    if multi_instance_requested and backend != "postgres":
        raise SystemExit(f"scheduler.multi_instance=true requires database.backend='postgres'. database.backend is '{backend}'. Set scheduler.multi_instance=false or configure Postgres.")
    if multi_instance_requested and run_events_backend != "db":
        raise SystemExit(f"scheduler.multi_instance=true requires run_events.backend='db'. run_events.backend is '{run_events_backend}'. Set scheduler.multi_instance=false or configure run_events.backend: db.")
    if multi_instance_requested and (run_ownership is None or not run_ownership.heartbeat_enabled):
        raise SystemExit("scheduler.multi_instance=true requires run_ownership.heartbeat_enabled=true so peer runs retain a valid lease. Set scheduler.multi_instance=false or enable run ownership heartbeats.")

    if workers <= 1:
        return

    if config.scheduler.enabled and not multi_instance_scheduler:
        raise SystemExit(f"GATEWAY_WORKERS={workers} cannot run with scheduler.enabled=true because each worker starts its own scheduler. Set GATEWAY_WORKERS=1, scheduler.multi_instance=true, or scheduler.enabled=false.")

    if _browser_tools_enabled_in_config(config):
        raise SystemExit(browser_multi_worker_error(workers))

    if backend != "postgres":
        raise SystemExit(f"GATEWAY_WORKERS={workers} requires database.backend='postgres', but database.backend is '{backend}'. SQLite cannot support concurrent multi-process access. Set GATEWAY_WORKERS=1 or switch to Postgres.")

    if run_events_backend != "db":
        raise SystemExit(
            f"GATEWAY_WORKERS={workers} requires run_events.backend='db', but run_events.backend is '{run_events_backend}'. "
            "Memory and JSONL event stores are process-local, so delivery receipt singleton guarantees cannot hold across workers. "
            "Set GATEWAY_WORKERS=1 or configure run_events.backend: db."
        )

    if run_ownership is None or not run_ownership.heartbeat_enabled:
        raise SystemExit(
            f"GATEWAY_WORKERS={workers} requires run_ownership.heartbeat_enabled=true. "
            "Without heartbeat, every run has a NULL lease, so reconciliation "
            "treats all inflight runs as orphans — Worker B would kill Worker A's "
            "live runs on every rolling update or scale-up. "
            "Set run_ownership.heartbeat_enabled=true in config.yaml."
        )


def _validate_agent_storage(config: AppConfig) -> None:
    """Fail fast on an agent-storage backend the database cannot support.

    ``agent_storage.backend: db`` needs a durable, shared SQL database — a
    ``memory`` database is per-process, so custom-agent and managed-subagent
    definitions would silently diverge across nodes (and there is no SQL URL
    to open). Mirrors deermem's create_storage fail-fast and the multi-worker
    gate above.

    Also warns when a multi-worker Postgres deployment leaves agent storage on
    ``file``: custom agents created on one node's local disk are invisible to
    the others, exactly the divergence the db backend exists to fix.
    """
    agent_storage = getattr(config, "agent_storage", None)
    backend = getattr(agent_storage, "backend", "file")
    db_backend = getattr(getattr(config, "database", None), "backend", None)
    if backend == "db" and db_backend not in ("sqlite", "postgres"):
        raise SystemExit(
            f"agent_storage.backend='db' requires database.backend to be 'sqlite' or 'postgres', "
            f"but database.backend is '{db_backend}'. A 'memory' database is per-process and cannot "
            "share agent definitions across nodes. Set database.backend, or use agent_storage.backend='file'."
        )
    try:
        workers = int(os.environ.get("GATEWAY_WORKERS", "1"))
    except (TypeError, ValueError):
        workers = 1
    if workers > 1 and db_backend == "postgres" and backend == "file":
        logger.warning(
            "GATEWAY_WORKERS=%s with database.backend='postgres' but agent_storage.backend='file': "
            "custom agents and managed subagents are stored per-node on local disk and are not visible "
            "across workers/nodes. Set agent_storage.backend='db' to share them.",
            workers,
        )


if TYPE_CHECKING:
    from app.gateway.auth.local_provider import LocalAuthProvider
    from app.gateway.auth.repositories.sqlite import SQLiteUserRepository
    from deerflow.persistence.thread_meta.base import ThreadMetaStore
    from deerflow.runtime import RunRecord


T = TypeVar("T")


async def _mark_latest_recovered_threads_error(
    run_manager: RunManager,
    thread_store: ThreadMetaStore,
    recovered_runs: list[RunRecord],
) -> None:
    """Mark thread status as error only when its newest run was recovered."""
    recovered_by_thread: dict[str, set[str]] = {}
    for record in recovered_runs:
        recovered_by_thread.setdefault(record.thread_id, set()).add(record.run_id)

    for thread_id, recovered_run_ids in recovered_by_thread.items():
        try:
            latest_runs = await run_manager.list_by_thread(thread_id, user_id=None, limit=1)
        except Exception:
            logger.warning("Failed to find latest run for thread %s during run reconciliation", thread_id, exc_info=True)
            continue
        if not latest_runs or latest_runs[0].run_id not in recovered_run_ids:
            continue
        try:
            await thread_store.update_status(thread_id, "error", user_id=None)
        except Exception:
            logger.warning("Failed to mark thread %s as error during run reconciliation", thread_id, exc_info=True)


def get_config() -> AppConfig:
    """Return the freshest ``AppConfig`` for the current request.

    Routes through :func:`deerflow.config.app_config.get_app_config`, which
    honours runtime ``ContextVar`` overrides and reloads ``config.yaml`` from
    disk when its mtime changes. ``AppConfig`` is not cached on ``app.state``
    at all — the only startup-time snapshot lives as a local
    ``startup_config`` variable inside ``lifespan()`` and is passed
    explicitly into :func:`langgraph_runtime` for the engines that are
    restart-required by design. Routing every request through
    :func:`get_app_config` closes the bytedance/deer-flow issue #3107 BUG-001
    split-brain where the worker / lead-agent thread saw a stale startup
    snapshot.

    Any failure to materialise the config (missing file, permission denied,
    YAML parse error, validation error) is reported as 503 — semantically
    "the gateway cannot serve requests without a usable configuration" — and
    logged with the original exception so operators have something to debug.
    """
    try:
        return get_app_config()
    except Exception as exc:  # noqa: BLE001 - request boundary: log and degrade gracefully
        logger.exception("Failed to load AppConfig at request time")
        raise HTTPException(status_code=503, detail="Configuration not available") from exc


@asynccontextmanager
async def langgraph_runtime(app: FastAPI, startup_config: AppConfig) -> AsyncGenerator[None, None]:
    """Bootstrap and tear down all LangGraph runtime singletons.

    ``startup_config`` is the ``AppConfig`` snapshot taken once during
    ``lifespan()`` for one-shot infrastructure bootstrap. The engines and
    stores constructed here (stream bridge, persistence engine, checkpointer,
    store, run-event store) are restart-required by design — they hold live
    connections, file handles, or singleton providers — so they bind to this
    snapshot and survive across `config.yaml` edits. Request-time consumers
    must still go through :func:`get_config` for any field that should be
    hot-reloadable. See ``backend/CLAUDE.md`` "Config Hot-Reload Boundary".

    The matching ``run_events_config`` is frozen onto ``app.state`` so
    :func:`get_run_context` pairs a freshly-loaded ``AppConfig`` with the
    *startup-time* run-events configuration the underlying ``event_store``
    was built from — otherwise the runtime could end up combining a live
    new ``run_events_config`` with an event store still bound to the
    previous backend.

    Usage in ``app.py``::

        async with langgraph_runtime(app, startup_config):
            yield
    """
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
    from deerflow.runtime import make_store, make_stream_bridge
    from deerflow.runtime.checkpointer.async_provider import make_checkpointer
    from deerflow.runtime.events.store import make_run_event_store

    # EAI-CUSTOM: multi-worker / agent-storage safety gates (ported from upstream
    # deps.py in the 2026-08-15 sync). No-ops for the default single-worker EAI
    # deployment (GATEWAY_WORKERS unset/1).
    _enforce_postgres_for_multi_worker(startup_config)
    _validate_agent_storage(startup_config)

    async with AsyncExitStack() as stack:
        # Lifecycle and system-model hooks can originate on isolated subagent
        # loops. Bind them to the Gateway's serving loop before any runtime
        # dependency starts, then reset the binding last through the exit
        # stack. Registering the callback synchronously here also covers every
        # startup-failure and cancellation path below.
        try:
            from deerflow.extensions.notify import (
                reset_extension_notify_loop,
                set_extension_notify_loop,
            )

            set_extension_notify_loop(asyncio.get_running_loop())
        except Exception:
            logger.exception("Failed to register the extension notify loop; sync observations will be dropped")
        else:

            def reset_notify_loop_safely() -> None:
                try:
                    reset_extension_notify_loop()
                except Exception:
                    logger.debug(
                        "Failed to reset the extension notify loop (non-fatal)",
                        exc_info=True,
                    )

            stack.callback(reset_notify_loop_safely)

        config = startup_config
        app.state.checkpoint_channel_mode = freeze_checkpoint_channel_mode(config.database.checkpoint_channel_mode)
        app.state.checkpoint_snapshot_frequency = freeze_checkpoint_snapshot_frequency(config.database.checkpoint_delta.snapshot_frequency)

        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge(config))

        # Initialize persistence engine BEFORE checkpointer so that
        # auto-create-database logic runs first (postgres backend).
        # Own cleanup before initialization so partial startup and host
        # cancellation cannot strand an engine created along the way.
        stack.push_async_callback(close_engine)
        await init_engine_from_config(config.database)

        app.state.checkpointer = await stack.enter_async_context(make_checkpointer(config))
        app.state.store = await stack.enter_async_context(make_store(config))

        # Record the checkpointer/Store backend selected from this startup
        # snapshot so GET /health/ready probes what the running process
        # actually uses. These singletons are restart-required by design and
        # are never rebuilt on config.yaml hot reload, so the probe must not
        # re-resolve process-wide configuration per request.
        from app.gateway.health import READINESS_CHECKPOINTER_CONFIG_ATTR, resolve_checkpointer_config

        setattr(app.state, READINESS_CHECKPOINTER_CONFIG_ATTR, resolve_checkpointer_config(config))

        # Initialize repositories — one get_session_factory() call for all.
        sf = get_session_factory()
        if sf is not None:
            from deerflow.persistence.feedback import FeedbackRepository
            from deerflow.persistence.personal_access_tokens import PersonalAccessTokenRepository
            from deerflow.persistence.run import RunRepository

            app.state.run_store = RunRepository(sf)
            app.state.feedback_repo = FeedbackRepository(sf)
            from app.gateway.auth.pat import PAT_LAST_USED_WRITE_INTERVAL_SECONDS

            app.state.pat_repo = PersonalAccessTokenRepository(sf, last_used_write_interval_seconds=PAT_LAST_USED_WRITE_INTERVAL_SECONDS)
        else:
            from deerflow.runtime.runs.store.memory import MemoryRunStore

            app.state.run_store = MemoryRunStore()
            app.state.feedback_repo = None
            # Memory backend has no durable PAT store, so Bearer credentials
            # cannot be validated there and are rejected by the middleware.
            app.state.pat_repo = None

        # Services are app-scoped. Capture this app's immutable extension set
        # once and close over the same object for teardown; the process-wide
        # singleton may be replaced by another app/test before shutdown.
        # (Upstream #4780)
        from deerflow.extensions import EMPTY_EXTENSIONS, record_runtime_diagnostics
        from deerflow.extensions.gateway import start_services, stop_services

        extensions = getattr(app.state, "extensions", EMPTY_EXTENSIONS)
        attempted_services: list[tuple[str, Any]] = []

        async def stop_extension_services() -> None:
            record_runtime_diagnostics(
                await stop_services(
                    extensions,
                    service_entries=attempted_services,
                )
            )

        # Register cleanup before starting: start() can partially acquire
        # resources and then fail or be cancelled.
        stack.push_async_callback(stop_extension_services)
        record_runtime_diagnostics(
            await start_services(
                extensions,
                config,
                sf,
                attempted_services=attempted_services,
            )
        )

        from deerflow.persistence.thread_meta import make_thread_store

        app.state.thread_store = make_thread_store(sf, app.state.store)
        if sf is not None:
            from deerflow.persistence.mcp_tasks import McpTaskRepository
            from deerflow.persistence.scheduled_task_runs import (
                ScheduledTaskRunRepository,
            )
            from deerflow.persistence.scheduled_tasks import ScheduledTaskRepository
            from deerflow.persistence.subagent_batches import SubagentBatchRepository

            app.state.scheduled_task_repo = ScheduledTaskRepository(
                sf,
                run_repository=app.state.run_store,
            )
            app.state.scheduled_task_run_repo = ScheduledTaskRunRepository(
                sf,
                run_repository=app.state.run_store,
            )
            app.state.mcp_task_repo = McpTaskRepository(sf)
            app.state.subagent_batch_repo = SubagentBatchRepository(sf)
        else:
            app.state.mcp_task_repo = None
            app.state.subagent_batch_repo = None
            app.state.scheduled_task_repo = None
            app.state.scheduled_task_run_repo = None

        # Run event store. The store and the matching ``run_events_config`` are
        # both frozen at startup so ``get_run_context`` does not combine a
        # freshly-reloaded ``AppConfig.run_events`` with a store still bound to
        # the previous backend.
        run_events_config = getattr(config, "run_events", None)
        app.state.run_events_config = run_events_config
        app.state.run_event_store = make_run_event_store(run_events_config)

        # RunManager with store backing for persistence
        app.state.run_manager = RunManager(store=app.state.run_store)
        if getattr(config.database, "backend", None) == "sqlite":
            from deerflow.utils.time import now_iso

            # Startup-only recovery: clean shutdowns return no active rows and
            # the thread-status update below becomes a no-op.
            recovered_runs = await app.state.run_manager.reconcile_orphaned_inflight_runs(
                error="Gateway restarted before this run reached a durable final state.",
                before=now_iso(),
            )
            await _mark_latest_recovered_threads_error(app.state.run_manager, app.state.thread_store, recovered_runs)

        yield


# ---------------------------------------------------------------------------
# Getters – called by routers per-request
# ---------------------------------------------------------------------------


def _require(attr: str, label: str) -> Callable[[Request], T]:
    """Create a FastAPI dependency that returns ``app.state.<attr>`` or 503."""

    def dep(request: Request) -> T:
        val = getattr(request.app.state, attr, None)
        if val is None:
            raise HTTPException(status_code=503, detail=f"{label} not available")
        return cast(T, val)

    dep.__name__ = dep.__qualname__ = f"get_{attr}"
    return dep


get_scheduled_task_repo: Callable[[Request], ScheduledTaskRepository] = _require("scheduled_task_repo", "Scheduled task repository")
get_scheduled_task_run_repo: Callable[[Request], ScheduledTaskRunRepository] = _require("scheduled_task_run_repo", "Scheduled task run repository")


async def get_scheduled_task_service(request: Request):
    """Return the scheduled task service or None if not configured."""
    return getattr(request.app.state, "scheduled_task_service", None)


def get_mcp_task_repo(request: Request):
    val = getattr(request.app.state, "mcp_task_repo", None)
    if val is None:
        raise HTTPException(status_code=503, detail="MCP task repo not available")
    return val


def get_mcp_task_service(request: Request):
    val = getattr(request.app.state, "mcp_task_service", None)
    if val is None:
        raise HTTPException(status_code=503, detail="MCP task service not available")
    return val


def get_subagent_batch_repo(request: Request):
    val = getattr(request.app.state, "subagent_batch_repo", None)
    if val is None:
        raise HTTPException(status_code=503, detail="Subagent batch repository not available")
    return val


def get_subagent_batch_service(request: Request):
    val = getattr(request.app.state, "subagent_batch_service", None)
    if val is None:
        raise HTTPException(status_code=503, detail="Subagent batch service not available")
    return val


get_stream_bridge: Callable[[Request], StreamBridge] = _require("stream_bridge", "Stream bridge")
get_run_manager: Callable[[Request], RunManager] = _require("run_manager", "Run manager")
get_checkpointer: Callable[[Request], Checkpointer] = _require("checkpointer", "Checkpointer")
get_run_event_store: Callable[[Request], RunEventStore] = _require("run_event_store", "Run event store")
get_feedback_repo: Callable[[Request], FeedbackRepository] = _require("feedback_repo", "Feedback")
get_run_store: Callable[[Request], RunStore] = _require("run_store", "Run store")


def get_store(request: Request):
    """Return the global store (may be ``None`` if not configured)."""
    return getattr(request.app.state, "store", None)


def get_thread_store(request: Request) -> ThreadMetaStore:
    """Return the thread metadata store (SQL or memory-backed)."""
    val = getattr(request.app.state, "thread_store", None)
    if val is None:
        raise HTTPException(status_code=503, detail="Thread metadata store not available")
    return val


def get_run_context(request: Request) -> RunContext:
    """Build a :class:`RunContext` from ``app.state`` singletons.

    Returns a *base* context with infrastructure dependencies. The
    ``app_config`` field is resolved live so per-run fields (e.g.
    ``models[*].max_tokens``) follow ``config.yaml`` edits; the
    ``event_store`` / ``run_events_config`` pair stays frozen to the snapshot
    captured in :func:`langgraph_runtime` so callers never see a store bound
    to one backend paired with a config pointing at another.
    """
    return RunContext(
        checkpointer=get_checkpointer(request),
        store=get_store(request),
        event_store=get_run_event_store(request),
        run_events_config=getattr(request.app.state, "run_events_config", None),
        thread_store=get_thread_store(request),
        mcp_task_repo=getattr(request.app.state, "mcp_task_repo", None),
        app_config=get_config(),
        checkpoint_channel_mode=getattr(request.app.state, "checkpoint_channel_mode", "full"),
    )


# ---------------------------------------------------------------------------
# Auth helpers (used by authz.py and auth middleware)
# ---------------------------------------------------------------------------

# Cached singletons to avoid repeated instantiation per request
_cached_local_provider: LocalAuthProvider | None = None
_cached_repo: SQLiteUserRepository | None = None


def get_local_provider() -> LocalAuthProvider:
    """Get or create the cached LocalAuthProvider singleton.

    Must be called after ``init_engine_from_config()`` — the shared
    session factory is required to construct the user repository.
    """
    global _cached_local_provider, _cached_repo
    if _cached_repo is None:
        from app.gateway.auth.repositories.sqlite import SQLiteUserRepository
        from deerflow.persistence.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            raise RuntimeError("get_local_provider() called before init_engine_from_config(); cannot access users table")
        _cached_repo = SQLiteUserRepository(sf)
    if _cached_local_provider is None:
        from app.gateway.auth.local_provider import LocalAuthProvider

        _cached_local_provider = LocalAuthProvider(repository=_cached_repo)
    return _cached_local_provider


def get_pat_repo(request: Request):
    """Return the personal-access-token repository from app state.

    Raises 503 when the process runs on the memory backend (no durable PAT
    storage), so PAT management routes fail explicitly instead of silently
    accepting tokens nobody can validate.
    """
    pat_repo = getattr(request.app.state, "pat_repo", None)
    if pat_repo is None:
        raise HTTPException(status_code=503, detail="Personal access tokens require a configured database")
    return pat_repo


async def get_current_user_from_request(request: Request):
    """Get the current authenticated user from the request cookie.

    Raises HTTPException 401 if not authenticated.
    """
    # EAI-CUSTOM (upstream-sync 2026-08-26): state-first short-circuit adopted from
    # upstream — when AuthMiddleware already resolved a trusted user onto
    # request.state (session/auth-disabled/internal source), return it instead of
    # re-decoding the cookie. Also keeps cookie-less request fakes (upstream tests)
    # working when they carry state.user.
    state = getattr(request, "state", None)
    state_user = getattr(state, "user", None)
    from app.gateway.auth_disabled import AUTH_SOURCE_AUTH_DISABLED, AUTH_SOURCE_INTERNAL, AUTH_SOURCE_PAT, AUTH_SOURCE_SESSION

    if state_user is not None and getattr(state, "auth_source", None) in {
        AUTH_SOURCE_SESSION,
        AUTH_SOURCE_AUTH_DISABLED,
        AUTH_SOURCE_INTERNAL,
        AUTH_SOURCE_PAT,
    }:
        return state_user

    from app.gateway.auth import decode_token
    from app.gateway.auth.errors import AuthErrorCode, AuthErrorResponse, TokenError, token_error_to_code

    access_token = getattr(getattr(request, "cookies", None), "get", lambda _k: None)("access_token")
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.NOT_AUTHENTICATED, message="Not authenticated").model_dump(),
        )

    payload = decode_token(access_token)
    if isinstance(payload, TokenError):
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=token_error_to_code(payload), message=f"Token error: {payload.value}").model_dump(),
        )

    provider = get_local_provider()
    user = await provider.get_user(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.USER_NOT_FOUND, message="User not found").model_dump(),
        )

    # Token version mismatch → password was changed, token is stale
    if user.token_version != payload.ver:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.TOKEN_INVALID, message="Token revoked (password changed)").model_dump(),
        )

    return user


async def is_admin_user(request: Request) -> bool:
    """Return whether the authenticated caller is an admin user.

    ``AuthMiddleware`` normally stamps ``request.state.user`` before the request
    reaches a router. Falling back to the strict dependency keeps the route safe
    in tests or alternative ASGI compositions that mount a router without the
    global middleware.

    Centralising this here means a future change to the admin definition (e.g.
    allowing an internal system role, adding audit logging, or switching to a
    permission-based check) lands in one place instead of drifting across the
    per-router copies that previously existed in ``mcp``, ``channel_connections``
    and ``channels``.
    """
    # PAT credentials never carry admin capability: no scope in the PAT
    # universe grants it, so an admin's automation token must not unlock
    # admin-only routes (skill installs, integration credentials, MCP config).
    from app.gateway.auth_disabled import AUTH_SOURCE_PAT

    if getattr(request.state, "auth_source", None) == AUTH_SOURCE_PAT:
        return False
    user = getattr(request.state, "user", None)
    if user is None:
        user = await get_current_user_from_request(request)

    return getattr(user, "system_role", None) == "admin"


async def require_admin_user(request: Request, *, detail: str) -> None:
    """Require the authenticated caller to be an admin user.

    ``detail`` is the route-specific 403 message. The shared predicate keeps
    read-side redaction and write authorization on the same admin definition.
    """

    if not await is_admin_user(request):
        raise HTTPException(status_code=403, detail=detail)


async def get_optional_user_from_request(request: Request):
    """Get optional authenticated user from request.

    Returns None if not authenticated.
    """
    try:
        return await get_current_user_from_request(request)
    except HTTPException:
        return None


async def get_current_user(request: Request) -> str | None:
    """Extract user_id from request cookie, or None if not authenticated.

    Thin adapter that returns the string id for callers that only need
    identification (e.g., ``feedback.py``). Full-user callers should use
    ``get_current_user_from_request`` or ``get_optional_user_from_request``.
    """
    user = await get_optional_user_from_request(request)
    return str(user.id) if user else None
