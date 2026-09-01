import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from deerflow_extension_api import EXTENSION_PRINCIPAL_RESOLVER_KEY, ExtensionPrincipal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.extensions.app_center import router as app_center_router
from app.extensions.approval import router as approval_router
from app.extensions.auth.permission_routers import router as permissions_router
from app.extensions.auth.policy_routers import router as policy_router
from app.extensions.auth.routers import router as auth_router
from app.extensions.contract_price import router as contract_price_router
from app.extensions.dashboard.routers import router as dashboard_router
from app.extensions.data_source.routers import router as data_source_router
from app.extensions.dept.routers import router as dept_router
from app.extensions.docmgr.collab_ai_chat import router as collab_ai_chat_router
from app.extensions.docmgr.collab_routers import router as collab_router
from app.extensions.docmgr.routers import router as docmgr_router
from app.extensions.geo_samples import router as geo_samples_router
from app.extensions.knowledge import kb_router as knowledge_router
from app.extensions.knowledge_factory.routers import router as knowledge_factory_router
from app.extensions.law import router as law_router
from app.extensions.license.routers import router as license_router

# EAI-CUSTOM: ontology(统一语义层)——纯只读投影(registry YAML + 通用引擎),无自有表;
# router 供语义地图/管理查询(/api/extensions/ontology/*), admin-gated(system:access)。
from app.extensions.ontology.routers import router as ontology_router
from app.extensions.output.routers import router as output_router
from app.extensions.project import router as project_router
from app.extensions.role.routers import router as role_router
from app.extensions.settings.routers import router as settings_router

# EAI-CUSTOM: spare_parts(备品备件价格分析)——导入包即把 csp_ 表注册到 Base.metadata
# (init_db create_all 建表);router 供管理层 API 挂载(/api/extensions/spare-parts/*)。
from app.extensions.spare_parts import router as spare_parts_router  # noqa: F401
from app.extensions.user.routers import router as user_router
from app.extensions.web_scraper import web_scraper_router
from app.extensions.workflow import router as workflow_router
from app.extensions.workflow.timeline.routers import router as timeline_router
from app.extensions.workspace import router as workspace_router  # EAI-CUSTOM: Collab Workspace
from app.gateway.auth_disabled import AUTH_SOURCE_INTERNAL, AUTH_SOURCE_PAT, warn_if_auth_disabled_enabled
from app.gateway.auth_middleware import AuthMiddleware
from app.gateway.browser_capability import ensure_browser_runtime_available
from app.gateway.config import get_gateway_config
from app.gateway.csrf_middleware import CORS_EXPOSED_HEADERS, CSRFMiddleware, get_configured_cors_origins
from app.gateway.deps import langgraph_runtime
from app.gateway.routers import (
    agents,
    artifacts,
    assistants_compat,
    auth,
    channel_connections,
    channels,
    features,
    feedback,
    input_polish,
    mcp,
    mcp_tasks,
    memory,
    models,
    runs,
    scheduled_tasks,
    skills,
    subagent_batches,
    subagents,
    suggestions,
    thread_runs,
    threads,
    ui,
    uploads,
)
from deerflow.config import app_config as deerflow_app_config
from deerflow.logging_config import configure_logging
from deerflow.uploads.manager import cleanup_stale_upload_staging_files

AppConfig = deerflow_app_config.AppConfig
get_app_config = deerflow_app_config.get_app_config

# Default logging; lifespan overrides from config.yaml log_level.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Upper bound (seconds) each lifespan shutdown hook is allowed to run.
# Bounds worker exit time so uvicorn's reload supervisor does not keep
# firing signals into a worker that is stuck waiting for shutdown cleanup.
_SHUTDOWN_HOOK_TIMEOUT_SECONDS = 5.0
_RETRIEVAL_WARM_SHUTDOWN_TIMEOUT_SECONDS = 1.0


async def _ensure_admin_user(app: FastAPI) -> None:
    """Startup hook: handle first boot and migrate orphan threads otherwise.

    After admin creation, migrate orphan threads from the LangGraph
    store (metadata.user_id unset) to the admin account. This is the
    "no-auth → with-auth" upgrade path: users who ran DeerFlow without
    authentication have existing LangGraph thread data that needs an
    owner assigned.
        First boot (no admin exists):
            - Does NOT create any user accounts automatically.
            - The operator must visit ``/setup`` to create the first admin.

    Subsequent boots (admin already exists):
      - Runs the one-time "no-auth → with-auth" orphan thread migration for
        existing LangGraph thread metadata that has no user_id.

    No SQL persistence migration is needed: the four user_id columns
    (threads_meta, runs, run_events, feedback) only come into existence
    alongside the auth module via create_all, so freshly created tables
    never contain NULL-owner rows.
    """
    from sqlalchemy import select

    from app.gateway.deps import get_local_provider
    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.user.model import UserRow

    try:
        provider = get_local_provider()
    except RuntimeError:
        # Auth persistence may not be initialized in some test/boot paths.
        # Skip admin migration work rather than failing gateway startup.
        logger.warning("Auth persistence not ready; skipping admin bootstrap check")
        return

    sf = get_session_factory()
    if sf is None:
        return

    admin_count = await provider.count_admin_users()

    if admin_count == 0:
        logger.info("=" * 60)
        logger.info("  First boot detected — no admin account exists.")
        logger.info("  Visit /setup to complete admin account creation.")
        logger.info("=" * 60)
        return

    # Admin already exists — run orphan thread migration for any
    # LangGraph thread metadata that pre-dates the auth module.
    async with sf() as session:
        stmt = select(UserRow).where(UserRow.system_role == "admin").limit(1)
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        return  # Should not happen (admin_count > 0 above), but be safe.

    admin_id = str(row.id)

    # LangGraph store orphan migration — non-fatal.
    # This covers the "no-auth → with-auth" upgrade path for users
    # whose existing LangGraph thread metadata has no user_id set.
    store = getattr(app.state, "store", None)
    if store is not None:
        try:
            migrated = await _migrate_orphaned_threads(store, admin_id)
            if migrated:
                logger.info("Migrated %d orphan LangGraph thread(s) to admin", migrated)
        except Exception:
            logger.exception("LangGraph thread migration failed (non-fatal)")


async def _iter_store_items(store, namespace, *, page_size: int = 500):
    """Paginated async iterator over a LangGraph store namespace.

    Replaces the old hardcoded ``limit=1000`` call with a cursor-style
    loop so that environments with more than one page of orphans do
    not silently lose data. Terminates when a page is empty OR when a
    short page arrives (indicating the last page).
    """
    offset = 0
    while True:
        batch = await store.asearch(namespace, limit=page_size, offset=offset)
        if not batch:
            return
        for item in batch:
            yield item
        if len(batch) < page_size:
            return
        offset += page_size


async def _migrate_orphaned_threads(store, admin_user_id: str) -> int:
    """Migrate LangGraph store threads with no user_id to the given admin.

    Uses cursor pagination so all orphans are migrated regardless of
    count. Returns the number of rows migrated.
    """
    migrated = 0
    async for item in _iter_store_items(store, ("threads",)):
        metadata = item.value.get("metadata", {})
        if not metadata.get("user_id"):
            metadata["user_id"] = admin_user_id
            item.value["metadata"] = metadata
            await store.aput(("threads",), item.key, item.value)
            migrated += 1
    return migrated


async def _warm_memory_retrieval(manager) -> None:
    """Rebuild the derived retrieval index without delaying Gateway readiness."""
    try:
        rebuilt = await asyncio.to_thread(manager.warm_retrieval)
        if rebuilt:
            logger.info("Memory retrieval index rebuilt successfully")
        else:
            logger.warning("Memory retrieval index rebuild failed; scoped searches will retry lazily")
    except Exception:
        logger.warning("Memory retrieval index rebuild skipped", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""

    # Load config and check necessary environment variables at startup.
    # `startup_config` is a local snapshot used only for one-shot bootstrap
    # work (logging level, langgraph_runtime engines, channels). Request-time
    # config resolution always routes through `get_app_config()` in
    # `app/gateway/deps.py::get_config()` so `config.yaml` edits become
    # visible without a process restart. We deliberately do NOT cache this
    # snapshot on `app.state` to keep that contract enforceable.
    try:
        startup_config = get_app_config()
        from deerflow.config.subagent_batches_config import SubagentBatchesConfig
        from deerflow.config.subagent_runtime_config import SubagentRuntimeConfig
        from deerflow.subagents.capacity import configure_subagent_execution_capacity

        subagent_runtime_config = getattr(startup_config, "subagent_runtime", None)
        if not isinstance(subagent_runtime_config, SubagentRuntimeConfig):
            subagent_runtime_config = SubagentRuntimeConfig()
        subagent_batches_config = getattr(startup_config, "subagent_batches", None)
        if not isinstance(subagent_batches_config, SubagentBatchesConfig):
            subagent_batches_config = SubagentBatchesConfig()
        configure_subagent_execution_capacity(subagent_runtime_config)
        configure_logging(startup_config)
        ensure_browser_runtime_available(startup_config)
        logger.info("Configuration loaded successfully")
        warn_if_auth_disabled_enabled()
    except Exception as e:
        error_msg = f"Failed to load configuration during gateway startup: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e
    config = get_gateway_config()
    logger.info(f"Starting API Gateway on {config.host}:{config.port}")

    from deerflow.skills.projection import ensure_public_skill_projection

    public_projection_ready = await asyncio.to_thread(ensure_public_skill_projection, app_config=startup_config)
    if public_projection_ready:
        logger.info("Ensured the public skill projection; user projections repair lazily on sandbox acquire")

    # Rebuild the derived memory retrieval index in the background. Scoped
    # searches remain correct while this runs because DeerMem lazily rebuilds
    # the requested scope when the full warm-up has not completed yet.
    retrieval_warm_task: asyncio.Task[None] | None = None
    try:
        from deerflow.agents.memory import get_memory_manager

        if startup_config.memory.enabled:
            manager = await asyncio.to_thread(get_memory_manager)
            warm_retrieval = getattr(manager, "warm_retrieval", None)
            if callable(warm_retrieval):
                retrieval_warm_task = asyncio.create_task(
                    _warm_memory_retrieval(manager),
                    name="memory-retrieval-warm-up",
                )
        else:
            logger.info("Memory is disabled; skipping retrieval index rebuild")
    except Exception:
        logger.warning("Memory retrieval index rebuild skipped", exc_info=True)

    # Pre-warm tiktoken encoding cache so the first memory-injection request
    # never blocks on the BPE data download (which hits an OpenAI/Azure URL
    # that may be unreachable in restricted networks — see issue #3402).
    # Warm-up runs via the manager's `warm()` tier-3 hook. DeerMem.warm re-checks
    # token_counting=="char" and returns early, so char-mode backends never touch
    # tiktoken (avoids even the 5s probe in network-restricted deployments - see
    # issue #3429). A backend with nothing to warm (e.g. noop) returns None from
    # the base default -- log "skipping" instead of the misleading "warmed
    # successfully" so the log reflects what actually happened.
    try:
        from deerflow.agents.memory import get_memory_manager

        manager = await asyncio.to_thread(get_memory_manager)
        warmed = await asyncio.wait_for(
            asyncio.to_thread(manager.warm),
            timeout=5,
        )
        if warmed is None:
            logger.info("Memory backend %s has nothing to warm; skipping tiktoken warm-up", type(manager).__name__)
        elif warmed:
            logger.info("tiktoken encoding cache warmed successfully")
        else:
            logger.warning("tiktoken encoding cache warm-up failed; token counting will use character-based fallback until tiktoken loads successfully")
    except TimeoutError:
        logger.warning("tiktoken encoding cache warm-up timed out; token counting will use character-based fallback until tiktoken loads successfully")
    except Exception:
        logger.warning("tiktoken warm-up skipped", exc_info=True)

    # Initialize extensions database eagerly when possible, but clear any failed
    # startup state so request-time lazy init starts from a clean engine/session.
    extensions_db_ready = False
    try:
        from app.extensions.database import init_engine

        await init_engine()
        logger.info("Database engine initialized successfully")
        extensions_db_ready = True
    except Exception as e:
        logger.warning("Database engine init failed (will retry on first request): %s", e)
        from app.extensions.database import close_db

        await close_db()

    if extensions_db_ready:
        try:
            from app.extensions.database import init_db, migrate_db, seed_db

            await init_db()
            await migrate_db()
            await seed_db()
            logger.info("Extensions database initialized successfully")
        except Exception as e:
            logger.warning("Extensions database init failed (may already exist): %s", e)
            from app.extensions.database import close_db

            await close_db()

    try:
        removed_upload_staging_files = await asyncio.to_thread(cleanup_stale_upload_staging_files)
        if removed_upload_staging_files:
            logger.info("Removed %d stale upload staging file(s)", removed_upload_staging_files)
    except Exception:
        logger.warning("Upload staging file cleanup skipped", exc_info=True)

    # Initialize LangGraph runtime components (StreamBridge, RunManager, checkpointer, store)
    async with langgraph_runtime(app, startup_config):
        logger.info("LangGraph runtime initialised")

        # Register present_files → docmgr sync callback.
        # When agent calls present_files to show outputs, auto-create
        # AIDocument records so files appear in 文档空间.
        try:
            from app.extensions.docmgr.service import AIDocumentService
            from deerflow.tools.callbacks import register_present_files_callback

            async def _sync_to_docmgr(user_id, thread_id, virtual_paths):
                await AIDocumentService.sync_outputs_to_docmgr(
                    user_id,
                    thread_id,
                    virtual_paths,
                )

            register_present_files_callback(_sync_to_docmgr)
            logger.info("Registered present_files → docmgr sync callback")
        except Exception as e:
            logger.warning("Failed to register present_files callback: %s", e)

        # Check admin bootstrap state and migrate orphan threads after admin exists.
        # Must run AFTER langgraph_runtime so app.state.store is available for thread migration
        await _ensure_admin_user(app)

        # Start Temporal client + embedded worker (non-blocking if Temporal is unavailable)
        from app.extensions.workflow.temporal.client import temporal_lifespan

        # EAI-CUSTOM (upstream-sync 2026-08-26): lifespan body wrapped in
        # temporal_lifespan so the embedded Temporal workflow worker starts and
        # stops with the gateway. Inner body tracks upstream bytedance/main:
        # channels get_stream_bridge closure, scheduler queue_timeout_seconds,
        # MCP task drivers + submitter/config snapshot, subagent batches, and
        # the OIDC/channel/scheduler/mcp/batch/browser/memory shutdown order.
        async with temporal_lifespan(app):
            # Start IM channel service if any channels are configured
            try:
                from app.channels.service import start_channel_service

                channel_service = await start_channel_service(
                    startup_config,
                    get_stream_bridge=lambda: getattr(app.state, "stream_bridge", None),
                )
                logger.info("Channel service started: %s", channel_service.get_status())
            except Exception:
                logger.exception("No IM channels configured or channel service failed to start")

            try:
                from app.gateway.services import launch_scheduled_thread_run
                from app.scheduler import ScheduledTaskService

                if getattr(app.state, "scheduled_task_repo", None) is not None and getattr(app.state, "scheduled_task_run_repo", None) is not None:
                    scheduled_task_service = ScheduledTaskService(
                        task_repo=app.state.scheduled_task_repo,
                        task_run_repo=app.state.scheduled_task_run_repo,
                        launch_run=lambda **kwargs: launch_scheduled_thread_run(app=app, **kwargs),
                        poll_interval_seconds=startup_config.scheduler.poll_interval_seconds,
                        lease_seconds=startup_config.scheduler.lease_seconds,
                        max_concurrent_runs=startup_config.scheduler.max_concurrent_runs,
                        queue_timeout_seconds=startup_config.scheduler.queue_timeout_seconds,
                        multi_instance=startup_config.scheduler.multi_instance,
                        run_lease_grace_seconds=startup_config.run_ownership.grace_seconds,
                    )
                    app.state.scheduled_task_service = scheduled_task_service
                    if startup_config.scheduler.enabled:
                        await scheduled_task_service.start()
            except Exception:
                logger.exception("Failed to initialize scheduled task service")

            from app.gateway.services import launch_mcp_task_notification_run
            from app.mcp_tasks import McpTaskService
            from deerflow.config.extensions_config import ExtensionsConfig
            from deerflow.config.mcp_tasks_config import McpTasksConfig
            from deerflow.mcp.task_tool_caller import McpTaskToolCaller
            from deerflow.mcp.tasks import (
                ORDINARY_MCP_TASK_DRIVER,
                McpTaskDriverRegistry,
                OrdinaryMcpTaskDriver,
            )
            from deerflow.mcp.tasks.runtime import (
                configured_task_toolset_count,
                set_mcp_task_config_snapshot,
                set_mcp_task_submitter,
                validate_mcp_task_runtime_configuration,
            )

            task_extensions_config = ExtensionsConfig.from_file()
            mcp_tasks_config = getattr(startup_config, "mcp_tasks", McpTasksConfig())
            mcp_task_repo = getattr(app.state, "mcp_task_repo", None)
            app.state.mcp_tasks_available = False
            set_mcp_task_submitter(None)
            set_mcp_task_config_snapshot(task_extensions_config)
            validate_mcp_task_runtime_configuration(
                mcp_tasks_config=mcp_tasks_config,
                extensions_config=task_extensions_config,
                repository_available=mcp_task_repo is not None,
            )
            if mcp_task_repo is not None:
                mcp_task_drivers = McpTaskDriverRegistry()
                if configured_task_toolset_count(task_extensions_config):
                    mcp_task_drivers.register(
                        ORDINARY_MCP_TASK_DRIVER,
                        OrdinaryMcpTaskDriver(McpTaskToolCaller(task_extensions_config)),
                    )
                mcp_task_service = McpTaskService(
                    repository=mcp_task_repo,
                    drivers=mcp_task_drivers,
                    poll_interval_seconds=mcp_tasks_config.poll_interval_seconds,
                    lease_seconds=mcp_tasks_config.lease_seconds,
                    max_concurrent_polls=mcp_tasks_config.max_concurrent_polls,
                    max_poll_backoff_seconds=mcp_tasks_config.max_poll_backoff_seconds,
                    input_required_poll_interval_seconds=mcp_tasks_config.input_required_poll_interval_seconds,
                    tracking_degraded_after_errors=mcp_tasks_config.tracking_degraded_after_errors,
                    max_result_bytes=mcp_tasks_config.max_result_bytes,
                    result_preview_max_chars=mcp_tasks_config.result_preview_max_chars,
                    launch_notification=lambda **kwargs: launch_mcp_task_notification_run(app=app, **kwargs),
                    get_run=lambda run_id, **kwargs: app.state.run_manager.get(
                        run_id,
                        raise_on_store_error=True,
                        **kwargs,
                    ),
                )
                app.state.mcp_task_drivers = mcp_task_drivers
                app.state.mcp_task_service = mcp_task_service
                if mcp_tasks_config.enabled:
                    await mcp_task_service.start()
                    set_mcp_task_submitter(mcp_task_service)
                    app.state.mcp_tasks_available = True

            from app.subagent_batches import SubagentBatchService
            from deerflow.subagents.batch_runtime import set_subagent_batch_submitter

            batch_repo = getattr(app.state, "subagent_batch_repo", None)
            app.state.subagent_batches_available = False
            set_subagent_batch_submitter(None)
            if subagent_batches_config.enabled and batch_repo is None:
                raise RuntimeError("subagent_batches.enabled requires database.backend sqlite or postgres")
            if batch_repo is not None:
                batch_service = SubagentBatchService(
                    repository=batch_repo,
                    config=subagent_batches_config,
                    runtime_config=subagent_runtime_config,
                )
                app.state.subagent_batch_service = batch_service
                if subagent_batches_config.enabled:
                    await batch_service.start()
                    set_subagent_batch_submitter(batch_service)
                    app.state.subagent_batches_available = True

            yield

            try:
                await auth.close_oidc_service()
            except Exception:
                logger.exception("Failed to close OIDC service")

            # Stop channel service on shutdown (bounded to prevent worker hang)
            try:
                from app.channels.service import stop_channel_service

                await asyncio.wait_for(
                    stop_channel_service(),
                    timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "Channel service shutdown exceeded %.1fs; proceeding with worker exit.",
                    _SHUTDOWN_HOOK_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.exception("Failed to stop channel service")

            if getattr(app.state, "scheduled_task_service", None) is not None:
                try:
                    await app.state.scheduled_task_service.stop()
                except Exception:
                    logger.exception("Failed to stop scheduled task service")

            if getattr(app.state, "mcp_task_service", None) is not None:
                app.state.mcp_tasks_available = False
                try:
                    await app.state.mcp_task_service.stop()
                except Exception:
                    logger.exception("Failed to stop MCP task service")
                finally:
                    from deerflow.mcp.tasks.runtime import set_mcp_task_submitter

                    set_mcp_task_submitter(None)
            from deerflow.mcp.tasks.runtime import set_mcp_task_config_snapshot

            set_mcp_task_config_snapshot(None)

            if getattr(app.state, "subagent_batch_service", None) is not None:
                app.state.subagent_batches_available = False
                try:
                    await app.state.subagent_batch_service.stop()
                except Exception:
                    logger.exception("Failed to stop subagent batch service")
                finally:
                    from deerflow.subagents.batch_runtime import set_subagent_batch_submitter

                    set_subagent_batch_submitter(None)

            try:
                from deerflow.community.browser_automation import get_browser_session_manager

                closed = await asyncio.wait_for(
                    get_browser_session_manager().close_all_sessions(),
                    timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
                )
                if closed:
                    logger.info("Closed %d browser session(s)", closed)
            except TimeoutError:
                logger.warning(
                    "Browser session shutdown exceeded %.1fs; proceeding with worker exit.",
                    _SHUTDOWN_HOOK_TIMEOUT_SECONDS,
                )
            except Exception:
                logger.exception("Failed to close browser sessions")

            # Drain the memory update queue's pending buffer before exit (best-effort,
            # bounded). IM channels are already stopped above, so no new IM updates
            # arrive during the drain. Without this, anything enqueued since the last
            # debounce Timer fire is lost on restart / SIGTERM - the queue is pure
            # in-memory and the Timer is a daemon thread. Upstream #4181.
            retrieval_warm_finished = True
            if retrieval_warm_task is not None and not retrieval_warm_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(retrieval_warm_task),
                        timeout=min(
                            _RETRIEVAL_WARM_SHUTDOWN_TIMEOUT_SECONDS,
                            startup_config.memory.shutdown_flush_timeout_seconds,
                        ),
                    )
                except TimeoutError:
                    retrieval_warm_finished = False
                    logger.warning("Memory retrieval index rebuild is still running; leaving its connection open during shutdown")

            manager = None
            try:
                # Memory shutdown runs on a worker thread and can trigger detached
                # system-model callbacks. Stop accepting those callbacks before
                # flushing, while keeping the registered loop alive for awaited
                # task hooks until langgraph_runtime drains runs and subagents.
                from deerflow.extensions.notify import suspend_extension_system_observations

                suspend_extension_system_observations()
            except Exception:
                logger.debug("Failed to suspend extension system observations (non-fatal)", exc_info=True)

            try:
                app_cfg = get_app_config()
                if app_cfg.memory.enabled:
                    from deerflow.agents.memory import get_memory_manager

                    flush_timeout = app_cfg.memory.shutdown_flush_timeout_seconds
                    manager = await asyncio.to_thread(get_memory_manager)
                    completed = await asyncio.to_thread(manager.shutdown_flush, flush_timeout)
                    if completed:
                        logger.info("Memory queue flush completed within %.1fs", flush_timeout)
                    else:
                        logger.warning(
                            "Memory queue flush did not finish within %.1fs; remaining updates may be lost",
                            flush_timeout,
                        )
            except Exception:
                logger.exception("Failed to flush memory queue on shutdown")
            finally:
                close = getattr(manager, "close", None)
                if callable(close) and retrieval_warm_finished:
                    try:
                        await asyncio.to_thread(close)
                    except Exception:
                        logger.exception("Failed to close memory backend on shutdown")

    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    config = get_gateway_config()
    docs_url = "/docs" if config.enable_docs else None
    redoc_url = "/redoc" if config.enable_docs else None
    openapi_url = "/openapi.json" if config.enable_docs else None

    app = FastAPI(
        title="EAIFlow API Gateway",
        description="""
## EAIFlow API Gateway

API Gateway for EAIFlow - A LangGraph-based AI agent backend with sandbox execution capabilities.

### Features

- **Models Management**: Query and retrieve available AI models
- **MCP Configuration**: Manage Model Context Protocol (MCP) server configurations
- **Memory Management**: Access and manage global memory data for personalized conversations
- **Skills Management**: Query and manage skills and their enabled status
- **Artifacts**: Access thread artifacts and generated files
- **Health Monitoring**: System health check endpoints

### Architecture

LangGraph-compatible requests are routed through nginx to this gateway.
This gateway provides runtime endpoints for agent runs plus custom endpoints for models, MCP configuration, skills, and artifacts.
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        openapi_tags=[
            {
                "name": "models",
                "description": "Operations for querying available AI models and their configurations",
            },
            {
                "name": "mcp",
                "description": "Manage Model Context Protocol (MCP) server configurations",
            },
            {
                "name": "memory",
                "description": "Access and manage global memory data for personalized conversations",
            },
            {
                "name": "skills",
                "description": "Manage skills and their configurations",
            },
            {
                "name": "artifacts",
                "description": "Access and download thread artifacts and generated files",
            },
            {
                "name": "uploads",
                "description": "Upload and manage user files for threads",
            },
            {
                "name": "threads",
                "description": "Manage DeerFlow thread-local filesystem data",
            },
            {
                "name": "agents",
                "description": "Create and manage custom agents with per-agent config and prompts",
            },
            {
                "name": "suggestions",
                "description": "Generate follow-up question suggestions for conversations",
            },
            {
                "name": "channels",
                "description": "Manage IM channel integrations (Feishu, Slack, Telegram)",
            },
            {
                "name": "assistants-compat",
                "description": "LangGraph Platform-compatible assistants API (stub)",
            },
            {
                "name": "runs",
                "description": "LangGraph Platform-compatible runs lifecycle (create, stream, cancel)",
            },
            {
                "name": "health",
                "description": "Health check and system status endpoints",
            },
        ],
    )

    # Auth: reject unauthenticated requests to non-public paths (fail-closed safety net)
    app.add_middleware(AuthMiddleware)

    # Give contributed routers a neutral way to ask "is this caller an admin"
    # without importing app.gateway.deps, which would pin them to an
    # unpublished internal layer and defeat independent distribution. The
    # resolver mirrors require_admin_user's primary path (deps.py): it reads
    # request.state.user, which AuthMiddleware stamps before any router runs,
    # rather than the async get_current_user_from_request/get_optional_user_from_request
    # accessors that exist for tests and alternative ASGI compositions. Staying
    # synchronous keeps resolve_principal/require_admin usable from both sync
    # and async route handlers.
    def _resolve_extension_principal(request):
        """Project the host's auth context into the neutral extension shape.

        Deliberately a projection, not a handle: an extension gets the
        questions it may ask (who, is that an admin, and what role they
        hold), not the host's AuthContext, which would pin every extension to
        its internals.
        """
        user = getattr(request.state, "user", None)
        if user is None:
            return None
        system_role = getattr(user, "system_role", None)
        # PAT credentials never carry admin capability (#5041): suppress every
        # admin signal — both ``is_admin`` and the ``admin`` role — so an
        # admin-owned PAT cannot regain admin through extension-side
        # require_admin, mirroring deps.is_admin_user's PAT guard.
        auth_source = getattr(request.state, "auth_source", None)
        is_pat = auth_source == AUTH_SOURCE_PAT
        is_admin = system_role == "admin" and not is_pat
        roles = () if is_pat and system_role == "admin" else (system_role,) if isinstance(system_role, str) and system_role else ()
        return ExtensionPrincipal(
            user_id=str(user.id),
            is_admin=is_admin,
            is_internal=auth_source == AUTH_SOURCE_INTERNAL,
            # The host's only role concept is the single system_role column
            # (e.g. "admin", "user") — there is no multi-role system to
            # project, so a set role becomes the one-element tuple rather
            # than reading a "roles" attribute the user model never had.
            roles=roles,
        )

    setattr(app.state, EXTENSION_PRINCIPAL_RESOLVER_KEY, _resolve_extension_principal)

    # CSRF: Double Submit Cookie pattern for state-changing requests
    app.add_middleware(CSRFMiddleware)

    # CORS: the unified nginx endpoint is same-origin by default. Split-origin
    # browser clients must opt in with this explicit Gateway allowlist so CORS
    # and CSRF origin checks share the same source of truth.
    cors_origins = sorted(get_configured_cors_origins())
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=list(CORS_EXPOSED_HEADERS),
        )

    # Python extensions load once while the Gateway app is constructed. Agent
    # middleware builders consume the same immutable set through the process
    # singleton; app.state exposes it to the Gateway runtime. (Upstream #4780)
    from deerflow.extensions import (
        EMPTY_EXTENSIONS,
        ExtensionLoadError,
        initialize_runtime_diagnostics,
        load_extensions,
        record_runtime_diagnostics,
        set_loaded_extensions,
    )

    # Resolving the configured plugin list is deliberately outside the
    # fail-open guard below: a config.yaml that exists but cannot be parsed or
    # validated is a configuration failure, not an extension failure. Reporting
    # it as the latter would silently drop a `required: true` extension instead
    # of failing the boot. Only an absent config.yaml is tolerated, mirroring
    # _resolve_trace_enabled_for_app_construction() — create_app() runs at
    # import time, and lifespan still performs strict config loading before
    # serving.
    try:
        configured_plugins = get_app_config().plugins
    except FileNotFoundError:
        logger.debug("config.yaml not found while constructing Gateway app; loading no extensions for this app instance")
        configured_plugins = []

    try:
        loaded_extensions, extension_diagnostics = load_extensions(configured_plugins)
    except ExtensionLoadError:
        # `required: true` makes the extension part of the startup contract.
        # Booting without it would silently change configured behaviour.
        raise
    except Exception:
        logger.exception("Extension loading failed; continuing with no extensions")
        loaded_extensions, extension_diagnostics = EMPTY_EXTENSIONS, []
    set_loaded_extensions(loaded_extensions)
    app.state.extensions = loaded_extensions
    app.state.extension_diagnostics = initialize_runtime_diagnostics(extension_diagnostics)

    # Include routers
    # Models API is mounted at /api/models
    app.include_router(models.router)
    app.include_router(features.router)
    app.include_router(scheduled_tasks.router)

    # MCP API is mounted at /api/mcp
    app.include_router(mcp.router)

    # Durable MCP tasks are scoped to their owning thread.
    app.include_router(mcp_tasks.router)
    app.include_router(subagent_batches.router)

    # Memory API is mounted at /api/memory
    app.include_router(memory.router)

    # Skills API is mounted at /api/skills
    app.include_router(skills.router)

    # Artifacts API is mounted at /api/threads/{thread_id}/artifacts
    app.include_router(artifacts.router)

    # Uploads API is mounted at /api/threads/{thread_id}/uploads
    app.include_router(uploads.router)

    # Thread cleanup API is mounted at /api/threads/{thread_id}
    app.include_router(threads.router)

    # Agents API is mounted at /api/agents
    app.include_router(agents.router)

    # Deployment-level subagent catalog and admin management.
    app.include_router(subagents.router)

    # Suggestions API is mounted at /api/threads/{thread_id}/suggestions
    app.include_router(suggestions.router)

    # UI config API is mounted at /api/ui/config (frontend UI behavior toggles)
    app.include_router(ui.router)

    # Channels API is mounted at /api/channels
    app.include_router(channels.router)
    app.include_router(channel_connections.router)

    # Assistants compatibility API (LangGraph Platform stub)
    app.include_router(assistants_compat.router)

    # Auth API is mounted at /api/v1/auth
    app.include_router(auth.router)

    # Input polish API is mounted at /api/input-polish
    app.include_router(input_polish.router)

    # Feedback API is mounted at /api/threads/{thread_id}/runs/{run_id}/feedback
    app.include_router(feedback.router)

    # Thread Runs API (LangGraph Platform-compatible runs lifecycle)
    app.include_router(thread_runs.router)

    # Stateless Runs API (stream/wait without a pre-existing thread)
    app.include_router(runs.router)

    # Extension APIs
    # Authentication API is mounted at /api/extensions/auth
    app.include_router(auth_router)

    # ABAC Policies API is mounted at /api/policies
    app.include_router(policy_router)

    # Permissions API is mounted at /api/permissions
    app.include_router(permissions_router)

    # Users API is mounted at /api/extensions/users
    app.include_router(user_router)

    # Roles API is mounted at /api/extensions/roles
    app.include_router(role_router)

    # Departments API is mounted at /api/extensions/departments
    app.include_router(dept_router)

    # Doc Mgr API is mounted at /api/extensions/docmgr
    app.include_router(docmgr_router)

    # Collab API (comments + versions) is mounted at /api/extensions/docmgr
    app.include_router(collab_router)

    # Collab AI Chat — proxied through nginx, uses default_model from Settings
    app.include_router(collab_ai_chat_router)

    # Knowledge Bases API is mounted at /knowledge
    app.include_router(knowledge_router)

    # Web Scraper API is mounted at /scraper
    app.include_router(web_scraper_router)

    # Law API is mounted at /api/kf/laws (router has prefix="/kf/laws")
    app.include_router(law_router)

    # Knowledge Factory API is mounted at /api/kf (router has prefix="/kf")
    app.include_router(knowledge_factory_router)

    # Contract price analysis management API (/api/extensions/contract-price/*)
    app.include_router(contract_price_router)

    # Geo sample bank management API (/api/extensions/geo-samples/*)  [EAI-CUSTOM]
    app.include_router(geo_samples_router)

    # Spare-parts price analysis management API (/api/extensions/spare-parts/*)  [EAI-CUSTOM]
    app.include_router(spare_parts_router)

    # Ontology semantic layer read API (/api/extensions/ontology/*)  [EAI-CUSTOM]
    app.include_router(ontology_router)

    # Settings API is mounted at /api/extensions
    app.include_router(settings_router)

    # Project management API is mounted at /api/extensions/project
    app.include_router(project_router)
    app.include_router(workspace_router)  # EAI-CUSTOM: Collab Workspace

    # Approval workflow API is mounted at /api/extensions/approval
    app.include_router(approval_router)

    # Data source management API (stub)
    app.include_router(data_source_router)

    # App-center API is mounted at /api/extensions/app-center
    app.include_router(app_center_router)

    # Workflow definition API is mounted at /api/extensions/workflow
    app.include_router(workflow_router)

    # Project timeline API is mounted at /api/extensions/workflow/projects/{project_id}/timeline
    app.include_router(timeline_router)

    # Dashboard (task console, stats, calendar, notifications)
    app.include_router(dashboard_router)

    # Layout template management for report output
    app.include_router(output_router)

    # License management API is mounted at /api/license
    app.include_router(license_router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Service health status information.
        """
        return {"status": "healthy", "service": "deer-flow-gateway"}

    # Extension routes are deliberately last: FastAPI/Starlette dispatches in
    # registration order, so every host route (including conditional routes
    # and /health) keeps precedence. Definite shadows are rejected with an
    # attributed diagnostic while unrelated extension routers still mount.
    # (Upstream #4780)
    from deerflow.extensions.gateway import include_contributed_routers

    record_runtime_diagnostics(include_contributed_routers(app, loaded_extensions))

    return app


# Create app instance for uvicorn
app = create_app()
