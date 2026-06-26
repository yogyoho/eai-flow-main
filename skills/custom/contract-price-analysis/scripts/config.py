"""Configuration for the contract-price-analysis pipeline (v2: MinIO + OCR service).

v2 replaces RAGFlow with: contract files in an independent MinIO bucket +
table extraction via the standalone eai-flow-ocr HTTP service. All from env.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    output_dir: str
    ocr_service_url: str           # eai-flow-ocr HTTP base, e.g. http://eai-flow-ocr:8010
    minio_endpoint: str            # e.g. ragflow-minio:9000 (inside eai-flow-net)
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str              # independent bucket, e.g. cpa-contracts
    minio_secure: bool


def get_config() -> Config:
    return Config(
        database_url=os.environ.get(
            "CPA_DATABASE_URL",
            "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow",
        ),
        output_dir=os.environ.get("CPA_OUTPUT_DIR", "/mnt/user-data/outputs/contract-price/"),
        ocr_service_url=os.environ.get("OCR_SERVICE_URL", "http://eai-flow-ocr:8010"),
        minio_endpoint=os.environ.get("CPA_MINIO_ENDPOINT", "ragflow-minio:9000"),
        minio_access_key=os.environ.get(
            "CPA_MINIO_ACCESS_KEY", os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        ),
        minio_secret_key=os.environ.get(
            "CPA_MINIO_SECRET_KEY", os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        ),
        minio_bucket=os.environ.get("CPA_MINIO_BUCKET", "cpa-contracts"),
        minio_secure=os.environ.get("CPA_MINIO_SECURE", "false").lower() == "true",
    )
