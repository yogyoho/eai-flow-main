"""项目管理微服务 FastAPI 应用入口"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db
from app.routers import (
    dashboard,
    documents,
    milestones,
    projects,
    resources,
    risks,
    tasks,
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
    logger.info(f"Starting Project Service on {settings.host}:{settings.port}")

    await init_db()
    logger.info("Database initialized successfully")

    yield

    await close_db()
    logger.info("Shutting down Project Service")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="项目管理微服务 API",
        description="项目管理业务微服务，提供项目立项、任务管理、里程碑跟踪、风险管理等完整功能",
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
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(milestones.router, prefix=api_prefix)
    app.include_router(resources.router, prefix=api_prefix)
    app.include_router(risks.router, prefix=api_prefix)
    app.include_router(documents.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "service": "project-service"}

    return app


app = create_app()
