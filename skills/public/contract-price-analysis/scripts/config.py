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
    # 货物分组维度开关(设置页 checkbox, 2026-09-23): 名称恒开(UI 不可关);
    # 规格/分类对应聚类 AND 门限的启停(False → 该门限中性放行)。
    cluster_by_spec: bool
    cluster_by_category: bool
    # 聚类参数(设置页"高级:聚类参数", 2026-09-23 起真正接线——此前 UI 值
    # 从未到达 CLI,engine 一直用硬编码默认)。
    cluster_eps: float
    cluster_min_samples: int


def _env_flag(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no")


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
        cluster_by_spec=_env_flag("CPA_CLUSTER_BY_SPEC"),
        cluster_by_category=_env_flag("CPA_CLUSTER_BY_CATEGORY"),
        cluster_eps=float(os.environ.get("CPA_CLUSTER_EPS", "0.6")),
        cluster_min_samples=int(os.environ.get("CPA_CLUSTER_MIN_SAMPLES", "2")),
    )
