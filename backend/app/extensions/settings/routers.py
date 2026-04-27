"""Settings API router."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path, override=False)


class SystemConfig(BaseModel):
    """System configuration model."""

    default_model: Optional[str] = None
    fast_model: Optional[str] = None
    embed_model: Optional[str] = None
    reranker: Optional[str] = None
    enable_content_guard: bool = False
    enable_content_guard_llm: bool = False
    content_guard_llm_model: Optional[str] = None
    theme: str = "system"


class EmbedModelChoice(BaseModel):
    """Embedding model choice with status."""

    name: str
    status: Optional[str] = None
    message: Optional[str] = None


class ModelChoicesResponse(BaseModel):
    """Response model for model choices."""

    embed_models: list[EmbedModelChoice] = []
    rerankers: list[str] = []


router = APIRouter(prefix="/api/extensions", tags=["settings"])

# In-memory config storage (for demo - in production, use database or config file)
_config_cache: dict = {}


def _load_config_from_env() -> SystemConfig:
    """Load configuration from environment variables."""
    return SystemConfig(
        default_model=os.getenv("DEFAULT_MODEL", ""),
        fast_model=os.getenv("FAST_MODEL", ""),
        embed_model=os.getenv("EMBED_MODEL", ""),
        reranker=os.getenv("RERANKER", ""),
        enable_content_guard=os.getenv("ENABLE_CONTENT_GUARD", "false").lower() == "true",
        enable_content_guard_llm=os.getenv("ENABLE_CONTENT_GUARD_LLM", "false").lower() == "true",
        content_guard_llm_model=os.getenv("CONTENT_GUARD_LLM_MODEL", ""),
        theme=os.getenv("THEME", "system"),
    )


def _load_embed_model_choices() -> list[EmbedModelChoice]:
    """Load available embedding model choices."""
    # Parse from environment variable (comma-separated list)
    embed_models_str = os.getenv("EMBED_MODEL_NAMES", "")
    if embed_models_str:
        names = [name.strip() for name in embed_models_str.split(",") if name.strip()]
        return [EmbedModelChoice(name=name) for name in names]
    return [
        EmbedModelChoice(name="text-embedding-3-small"),
        EmbedModelChoice(name="text-embedding-3-large"),
        EmbedModelChoice(name="text-embedding-ada-002"),
    ]


def _load_reranker_choices() -> list[str]:
    """Load available reranker choices."""
    rerankers_str = os.getenv("RERANKER_NAMES", "")
    if rerankers_str:
        return [name.strip() for name in rerankers_str.split(",") if name.strip()]
    return ["bge-reranker-base", "bge-reranker-large", "cohere-reranker"]


@router.get("/config", response_model=SystemConfig)
async def get_config() -> SystemConfig:
    """Get system configuration."""
    if _config_cache:
        return SystemConfig(**_config_cache)
    return _load_config_from_env()


@router.put("/config", response_model=SystemConfig)
async def update_config(config: SystemConfig) -> SystemConfig:
    """Update system configuration."""
    global _config_cache
    _config_cache = config.model_dump(exclude_none=True)

    # In production, you would save this to a config file or database
    # For now, we just update the in-memory cache
    return SystemConfig(**_config_cache)


@router.get("/models/choices", response_model=ModelChoicesResponse)
async def get_model_choices() -> ModelChoicesResponse:
    """Get available model choices for selection."""
    return ModelChoicesResponse(
        embed_models=_load_embed_model_choices(),
        rerankers=_load_reranker_choices(),
    )


from app.extensions.settings.validator import (
    ModelValidationRequest,
    ModelValidationResult,
    validate_models,
)


class ModelValidationResponse(BaseModel):
    """Response model for model validation."""

    results: list[ModelValidationResult]


@router.post("/models/validate", response_model=ModelValidationResponse)
async def validate_models_endpoint(request: ModelValidationRequest) -> ModelValidationResponse:
    """Validate multiple models in parallel.

    Args:
        request: Validation request with list of model names.

    Returns:
        Validation results for each model.

    Example Response:
        ```json
        {
            "results": [
                {
                    "name": "gpt-4",
                    "status": "available",
                    "details": {
                        "exists": true,
                        "api_reachable": true,
                        "supports_thinking": false,
                        "supports_vision": true,
                        "has_credentials": true,
                        "message": "Model available (latency: 523ms)",
                        "latency_ms": 523
                    }
                }
            ]
        }
        ```
    """
    results = await validate_models(request.models)
    return ModelValidationResponse(results=results)
