"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    ragflow_api_key: str
    ragflow_base_url: str
    ragflow_kb_id: str
    database_url: str
    output_dir: str


def get_config() -> Config:
    return Config(
        ragflow_api_key=os.environ["RAGFLOW_API_KEY"],
        ragflow_base_url=os.environ.get(
            "RAGFLOW_BASE_URL", "http://localhost:9380/api/v1"
        ),
        ragflow_kb_id=os.environ.get(
            "RAGFLOW_KB_ID", "a8e8f3dc660d11f1ad61e1631bd6f152"
        ),
        database_url=os.environ.get(
            "CPA_DATABASE_URL",
            "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow",
        ),
        output_dir=os.environ.get(
            "CPA_OUTPUT_DIR", "/mnt/user-data/outputs/contract-price/"
        ),
    )
