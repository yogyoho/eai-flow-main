"""Runtime configuration for the standalone workflow subsystem.

Environment variables (all optional):

* ``WORKFLOW_DATABASE_URL`` – SQLAlchemy async URL. Defaults to a local SQLite
  database next to the backend package so the demo runs with zero setup.
  PostgreSQL is supported out of the box, e.g.
  ``postgresql+asyncpg://user:pass@localhost:5432/workflow``.
* ``WORKFLOW_CORS_ORIGINS`` – comma separated origins.
* ``WORKFLOW_TENANT_ID`` – default tenant for requests without ``X-Tenant-Id``.
* ``WORKFLOW_SEED_DEMO`` – ``1``/``0`` to seed the demo definitions and users.
* ``WORKFLOW_AUTO_CREATE_SCHEMA`` – create tables at startup. Keep ``1`` for
  local SQLite/demo use; production runs ``alembic upgrade head`` and sets ``0``.
* ``WORKFLOW_AUTH_MODE`` – ``local`` trusts ``X-User-*`` headers (tests/demo),
  ``eai`` validates the shared EAI JWT and resolves permissions via Gateway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _default_database_url() -> str:
    db_path = (BACKEND_DIR / "workflow.db").as_posix()
    return f"sqlite+aiosqlite:///{db_path}"


def _split(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


@dataclass(slots=True)
class Settings:
    app_name: str = "EAI Workflow"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/workflow"
    database_url: str = field(default_factory=lambda: os.getenv("WORKFLOW_DATABASE_URL") or _default_database_url())
    cors_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("WORKFLOW_CORS_ORIGINS"),
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3020",
                "http://127.0.0.1:3020",
                "http://localhost:2026",
                "http://127.0.0.1:2026",
            ],
        )
    )
    default_tenant: str = os.getenv("WORKFLOW_TENANT_ID", "000000")
    seed_demo: bool = os.getenv("WORKFLOW_SEED_DEMO", "1") != "0"
    seed_sales_approvals: bool = _env_flag("WORKFLOW_SEED_SALES_APPROVALS", True)
    auto_create_schema: bool = _env_flag("WORKFLOW_AUTO_CREATE_SCHEMA", True)
    sql_echo: bool = os.getenv("WORKFLOW_SQL_ECHO", "0") == "1"
    log_level: str = os.getenv("WORKFLOW_LOG_LEVEL", "INFO")
    max_page_size: int = 200
    db_health_timeout_seconds: float = float(os.getenv("WORKFLOW_DB_HEALTH_TIMEOUT_SECONDS", "2"))

    # Authentication. ``local`` keeps the standalone header identity used by
    # the demo and tests; ``eai`` validates EAI's shared JWT and resolves the
    # user + permissions through the Gateway.
    auth_mode: str = os.getenv("WORKFLOW_AUTH_MODE", "local").strip().lower()
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    eai_base_url: str = os.getenv("EAI_BASE_URL", "http://gateway:8001")
    eai_timeout_seconds: float = float(os.getenv("EAI_TIMEOUT_SECONDS", "4"))
    permission_cache_ttl_seconds: int = int(os.getenv("PERMISSION_CACHE_TTL_SECONDS", "60"))
    access_token_cookie: str = os.getenv("ACCESS_TOKEN_COOKIE", "access_token")
    # Trusted BFF/service calls (e.g. sales-service) may pass X-User-* headers
    # when this shared secret matches. Keep empty to disable impersonation.
    internal_token: str = os.getenv("WORKFLOW_INTERNAL_TOKEN", "").strip()

    # Temporal execution engine. Disabled by default so the standalone demo
    # and the unit-test suite keep working without a running Temporal server.
    temporal_enabled: bool = _env_flag("TEMPORAL_ENABLED")
    temporal_url: str = os.getenv("TEMPORAL_URL", "127.0.0.1:7233")
    temporal_namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    temporal_task_queue: str = os.getenv("TEMPORAL_TASK_QUEUE", "workflow-engine-queue")
    temporal_rpc_timeout_seconds: float = float(os.getenv("TEMPORAL_RPC_TIMEOUT_SECONDS", "5"))
    temporal_probe_timeout_seconds: float = float(os.getenv("TEMPORAL_PROBE_TIMEOUT_SECONDS", "1.5"))
    temporal_max_concurrent_activities: int = int(os.getenv("TEMPORAL_MAX_CONCURRENT_ACTIVITIES", "20"))
    temporal_max_concurrent_workflow_tasks: int = int(os.getenv("TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS", "20"))
    temporal_workflow_id_prefix: str = os.getenv("WORKFLOW_INSTANCE_WORKFLOW_ID_PREFIX", "flow-instance")

    # Durable command inbox and Temporal signalling.
    command_wait_timeout_seconds: float = float(os.getenv("WORKFLOW_COMMAND_WAIT_TIMEOUT_SECONDS", "5"))
    command_dispatch_interval_seconds: float = float(os.getenv("WORKFLOW_COMMAND_DISPATCH_INTERVAL_SECONDS", "2"))
    command_max_attempts: int = int(os.getenv("WORKFLOW_COMMAND_MAX_ATTEMPTS", "10"))
    command_stale_seconds: int = int(os.getenv("WORKFLOW_COMMAND_STALE_SECONDS", "120"))
    command_activity_timeout_seconds: int = int(os.getenv("WORKFLOW_COMMAND_ACTIVITY_TIMEOUT_SECONDS", "30"))
    command_activity_max_attempts: int = int(os.getenv("WORKFLOW_COMMAND_ACTIVITY_MAX_ATTEMPTS", "10"))
    command_backoff_base_seconds: int = int(os.getenv("WORKFLOW_COMMAND_BACKOFF_BASE_SECONDS", "2"))

    # Outbox delivery to the marketing BFF.
    event_webhook_url: str = os.getenv("WORKFLOW_EVENT_WEBHOOK_URL", "").strip()
    event_webhook_secret: str = os.getenv("WORKFLOW_EVENT_WEBHOOK_SECRET", "")
    event_webhook_timeout_seconds: float = float(os.getenv("WORKFLOW_EVENT_WEBHOOK_TIMEOUT_SECONDS", "5"))
    outbox_dispatch_interval_seconds: float = float(os.getenv("WORKFLOW_OUTBOX_DISPATCH_INTERVAL_SECONDS", "3"))
    outbox_max_attempts: int = int(os.getenv("WORKFLOW_OUTBOX_MAX_ATTEMPTS", "10"))
    outbox_stale_seconds: int = int(os.getenv("WORKFLOW_OUTBOX_STALE_SECONDS", "120"))
    outbox_backoff_base_seconds: int = int(os.getenv("WORKFLOW_OUTBOX_BACKOFF_BASE_SECONDS", "5"))

    # Scheduled reconciliation.
    reconcile_interval_seconds: int = int(os.getenv("WORKFLOW_RECONCILE_INTERVAL_SECONDS", "300"))
    reconcile_stale_seconds: int = int(os.getenv("WORKFLOW_RECONCILE_STALE_SECONDS", "120"))
    reconcile_batch_size: int = int(os.getenv("WORKFLOW_RECONCILE_BATCH_SIZE", "50"))

    workflow_public_base_url: str = os.getenv("WORKFLOW_PUBLIC_BASE_URL", "http://localhost:3020/workflow")


settings = Settings()
