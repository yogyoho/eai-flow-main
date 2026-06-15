"""FastAPI application for the contract-price-analysis management API.

All routes are mounted under ``/api/cpa``. The app stays decoupled from the main
backend extensions — it reuses Plan 1's ``scripts.db`` engine and ``cpa_`` models
but runs as its own service (see ``main.py``).

CORS is open by default so the Next.js frontend (different origin/port) can call
it during development; tighten ``allow_origins`` for production.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Contract Price Analysis API",
        version="0.1.0",
        docs_url="/api/cpa/docs",
        openapi_url="/api/cpa/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/cpa/health")
    async def health() -> dict:
        return {"status": "ok"}

    # Routers are registered lazily to avoid import errors when a router's
    # optional deps are missing during partial development.
    from scripts.server.routers import (  # noqa: E402
        clusters,
        config,
        dashboard,
        documents,
        items,
        pipeline,
        tasks,
    )

    for router in (documents, clusters, items, tasks, config, dashboard, pipeline):
        app.include_router(router.router, prefix="/api/cpa")

    return app


app = create_app()
