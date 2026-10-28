"""Sales service configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://business:business123@localhost:15433/sales"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 3004
    log_level: str = "INFO"

    # Identity is resolved through the existing EAI Gateway by default. The
    # local mode exists for component tests and offline development only.
    auth_mode: str = "eai"
    eai_base_url: str = "http://gateway:8001"
    eai_timeout_seconds: float = 4.0
    permission_cache_ttl_seconds: int = 60
    # Pilot bootstrap: EAI roles that have not yet been granted sales.* points
    # still get the role's default sales points. Set false after role mapping is
    # completed in EAI role management.
    sales_bootstrap_permissions: bool = True
    default_region_code: str = "DEFAULT"

    temporal_enabled: bool = True
    temporal_url: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "sales-approval-queue"
    temporal_workflow_id_prefix: str = "sales-approval"
    temporal_max_concurrent_activities: int = 20
    temporal_max_concurrent_workflow_tasks: int = 20
    temporal_probe_timeout_seconds: float = 1.5
    # Bound every Temporal RPC so an outage cannot pin a dispatcher/signal
    # request forever; the outbox then backs off and retries.
    temporal_rpc_timeout_seconds: float = 5.0
    temporal_reconcile_interval_seconds: int = 300
    temporal_reconcile_stale_seconds: int = 120
    outbox_dispatch_interval_seconds: int = 3
    outbox_max_attempts: int = 10
    sales_embedded_worker: bool = False

    # Workflow platform approval engine. When enabled, new sales approvals
    # start a workflow-platform instance and synchronize its tasks/history into
    # the sales read model. The sales Temporal workflow remains available for
    # existing requests and as a rollback path.
    workflow_platform_enabled: bool = False
    workflow_platform_base_url: str = "http://workflow-backend:8020/api/workflow"
    workflow_platform_internal_token: str = ""
    workflow_platform_timeout_seconds: float = 10.0
    workflow_platform_sync_limit: int = 30

    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 300
    seed_demo: bool = True
    demo_mode: bool = True

    # MinIO / S3-compatible object storage. The stack already runs MinIO as
    # ragflow-minio; QW2 stores attachments in a dedicated bucket.
    minio_enabled: bool = True
    minio_endpoint: str = "http://ragflow-minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "sales-attachments"
    minio_region: str = "us-east-1"
    minio_secure: bool = False
    attachment_max_mb: int = 25

    cors_origins: list[str] = [
        "http://localhost:2026",
        "http://localhost:3000",
        "http://localhost:5174",
        "http://sales-frontend:80",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
