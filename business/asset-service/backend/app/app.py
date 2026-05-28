"""资产管理微服务 FastAPI 应用入口"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db
from app.routers import (
    allocations,
    assets,
    checks,
    dashboard,
    depreciation,
    maintenance,
    scrapping,
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
    logger.info(f"Starting Asset Service on {settings.host}:{settings.port}")

    await init_db()
    logger.info("Database initialized successfully")

    yield

    await close_db()
    logger.info("Shutting down Asset Service")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="资产管理微服务 API",
        description="资产管理业务微服务，提供资产台账、维修保养、调拨管理、折旧计算、资产盘点等完整功能",
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
    app.include_router(assets.router, prefix=api_prefix)
    app.include_router(maintenance.router, prefix=api_prefix)
    app.include_router(allocations.router, prefix=api_prefix)
    app.include_router(depreciation.router, prefix=api_prefix)
    app.include_router(checks.router, prefix=api_prefix)
    app.include_router(scrapping.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "service": "asset-service"}

    return app


app = create_app()
