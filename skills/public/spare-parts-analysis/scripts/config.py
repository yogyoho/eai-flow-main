# EAI-CUSTOM: forked from contract-price-analysis/scripts/config.py(备件价格体系分析)。
"""Configuration for the spare-parts-analysis pipeline (MinIO + OCR service)。

复用 eai-flow-ocr HTTP 服务 + 独立 MinIO bucket(csp-parts)。与 contract_price
的差异:env 前缀 CSP_、bucket csp-parts、输出目录 spare-parts。全部走环境变量。
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
    minio_bucket: str              # 独立 bucket, e.g. csp-parts
    minio_secure: bool


def get_config() -> Config:
    return Config(
        database_url=os.environ.get(
            "CSP_DATABASE_URL",
            "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow",
        ),
        output_dir=os.environ.get("CSP_OUTPUT_DIR", "/mnt/user-data/outputs/spare-parts/"),
        ocr_service_url=os.environ.get("OCR_SERVICE_URL", "http://eai-flow-ocr:8010"),
        minio_endpoint=os.environ.get("CSP_MINIO_ENDPOINT", "ragflow-minio:9000"),
        minio_access_key=os.environ.get(
            "CSP_MINIO_ACCESS_KEY", os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        ),
        minio_secret_key=os.environ.get(
            "CSP_MINIO_SECRET_KEY", os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        ),
        minio_bucket=os.environ.get("CSP_MINIO_BUCKET", "csp-parts"),
        minio_secure=os.environ.get("CSP_MINIO_SECURE", "false").lower() == "true",
    )
