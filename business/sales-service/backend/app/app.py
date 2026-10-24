"""FastAPI application for the QW2 sales service."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import close_db, get_session_maker, init_db
from app.errors import SalesError, error_response
from app.jobs.scheduler import scheduler_loop
from app.routers import approvals, attachments, health, master_data, opportunities, rules, todos, workbench
from app.seed import seed_all
from app.storage import ensure_bucket
from app.workflows.client import close_client

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    await init_db()
    if settings.minio_enabled:
        try:
            await ensure_bucket()
        except Exception:  # noqa: BLE001
            logger.warning("MinIO bucket initialization failed; attachments will degrade", exc_info=True)
    if settings.seed_demo:
        try:
            async with get_session_maker()() as db:
                await seed_all(db)
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("sales demo seed failed; continuing with empty database")
    tasks: list[asyncio.Task] = []
    # The API only writes the outbox. Outbox dispatch and Temporal
    # reconciliation are owned by the worker (or by the embedded worker in
    # local development) so multiple API replicas cannot double-dispatch.
    if settings.scheduler_enabled:
        tasks.append(asyncio.create_task(scheduler_loop(), name="sales-scheduler"))
    if settings.sales_embedded_worker and settings.temporal_enabled:
        from app.worker import run_worker

        tasks.append(asyncio.create_task(run_worker(), name="sales-embedded-worker"))
    app.state.background_tasks = tasks
    logger.info("sales service started (auth=%s, temporal=%s)", settings.auth_mode, settings.temporal_enabled)
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await close_client()
        await close_db()


app = FastAPI(
    title="EAI Sales QW2 Service",
    version="0.1.0",
    description="商机漏斗、统一待办、我的工作台与 Temporal 审批",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.add_exception_handler(SalesError, error_response)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "参数校验失败", "code": "SALES-422-VALIDATION", "context": {"errors": exc.errors()}},
    )


for router in [workbench.router, opportunities.router, todos.router, approvals.router, master_data.router, rules.router, attachments.router]:
    app.include_router(router, prefix=settings.api_prefix)
app.include_router(health.router)
app.include_router(health.router, prefix=settings.api_prefix, include_in_schema=False)


@app.get("/")
async def root():
    return {
        "service": "sales-service",
        "version": "0.1.0",
        "scope": "QW2",
        "docs": f"{settings.api_prefix}/docs",
    }
