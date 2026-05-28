"""招标采购微服务 FastAPI 应用入口"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db
from app.routers import (
    bids,
    bidders,
    complaints,
    contracts,
    dashboard,
    evaluations,
    experts,
    plans,
    projects,
    venue_spaces,
    winning_bids,
    witness_records,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(f"Starting Procurement Service on {settings.host}:{settings.port}")

    await init_db()
    logger.info("Database initialized successfully")

    yield

    await close_db()
    logger.info("Shutting down Procurement Service")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="招标采购微服务 API",
        description="招标采购业务微服务，提供专家管理、投标管理、评标管理等完整功能",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = settings.api_prefix
    app.include_router(experts.router, prefix=api_prefix)
    app.include_router(bidders.router, prefix=api_prefix)
    app.include_router(plans.router, prefix=api_prefix)
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(bids.router, prefix=api_prefix)
    app.include_router(evaluations.router, prefix=api_prefix)
    app.include_router(winning_bids.router, prefix=api_prefix)
    app.include_router(contracts.router, prefix=api_prefix)
    app.include_router(complaints.router, prefix=api_prefix)
    app.include_router(witness_records.router, prefix=api_prefix)
    app.include_router(venue_spaces.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "service": "procurement-service"}

    return app


app = create_app()
