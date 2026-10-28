"""ASGI entry point for the standalone workflow subsystem.

Run with::

    uvicorn app.main:app --reload --port 8020

The application is deliberately self-contained.  It can also be mounted on the
eai-flow gateway with ``app.mount("/api/workflow-app", workflow_app)`` once the
host's authentication middleware is wired in.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import definitions, designer, forms, meta, runtime
from .config import settings
from .database import (
    database_health,
    dispose_engine,
    init_db,
    redacted_database_url,
    session_scope,
)
from .deps import get_context
from .engine.errors import WorkflowError
from .temporal.client import close_client, temporal_health

logger = logging.getLogger("workflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.seed_sales_approvals:
        try:
            from .seed_sales_approvals import seed_sales_approvals

            async with session_scope() as session:
                await seed_sales_approvals(session)
        except Exception:  # noqa: BLE001 - seeding must not block API startup
            logger.exception("sales approval seed failed")
    logger.info("workflow database ready: %s", redacted_database_url())
    logger.info(
        "workflow Temporal config: enabled=%s url=%s namespace=%s queue=%s",
        settings.temporal_enabled,
        settings.temporal_url,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    if settings.auth_mode == "eai" and settings.jwt_secret_key == "change-me-in-production":
        logger.warning("WORKFLOW_AUTH_MODE=eai but JWT_SECRET_KEY is still the default value")
    try:
        yield
    finally:
        await close_client()
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="warm-flow compatible definition designer and approval runtime",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.exception_handler(WorkflowError)
    async def _workflow_error(_: Request, exc: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    prefix = settings.api_prefix
    # Authenticate every workflow route, including read-only metadata. The
    # dependency is cached per request, so endpoints that already declare Ctx
    # do not trigger a second EAI permission lookup.
    dependencies = [Depends(get_context)]
    app.include_router(definitions.router, prefix=prefix, dependencies=dependencies)
    app.include_router(designer.router, prefix=prefix, dependencies=dependencies)
    app.include_router(runtime.router, prefix=prefix, dependencies=dependencies)
    app.include_router(forms.router, prefix=prefix, dependencies=dependencies)
    app.include_router(meta.router, prefix=prefix, dependencies=dependencies)

    async def _health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "database": await database_health(),
            "temporal": await temporal_health(),
        }

    @app.get(f"{prefix}/health", tags=["workflow-meta"])
    async def health() -> dict[str, Any]:
        return await _health()

    @app.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, Any]:
        return await _health()

    return app


app = create_app()
