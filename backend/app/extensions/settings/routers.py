"""Settings API router."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.settings.service import SystemConfigService
from app.extensions.settings.validator import (
    ModelValidationRequest,
    ModelValidationResult,
    validate_models,
)
from deerflow.config import get_app_config

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path, override=False)


class SystemConfig(BaseModel):
    """System configuration model."""

    default_model: str | None = None
    fast_model: str | None = None
    embed_model: str | None = None
    reranker: str | None = None
    enable_content_guard: bool = False
    enable_content_guard_llm: bool = False
    content_guard_llm_model: str | None = None
    theme: str = "system"


class EmbedModelChoice(BaseModel):
    """Embedding model choice with status."""

    name: str
    status: str | None = None
    message: str | None = None


class ChatModelChoice(BaseModel):
    """A single chat model for selection."""

    name: str
    display_name: str


class ChatModelGroup(BaseModel):
    """Group of chat models from the same provider."""

    provider: str
    models: list[ChatModelChoice]


class ModelChoicesResponse(BaseModel):
    """Response model for model choices."""

    embed_models: list[EmbedModelChoice] = []
    rerankers: list[str] = []
    chat_models: list[ChatModelGroup] = []


router = APIRouter(prefix="/api/extensions", tags=["settings"])

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


def _pydantic_to_flat_dict(config: SystemConfig) -> dict[str, str]:
    """Convert SystemConfig to flat dict for DB storage, skipping None."""
    flat: dict[str, str] = {}
    for field_name, value in config.model_dump().items():
        if value is None:
            continue
        if isinstance(value, bool):
            flat[field_name] = "true" if value else "false"
        else:
            flat[field_name] = str(value)
    return flat


def _dict_to_system_config(data: dict[str, str]) -> SystemConfig:
    """Convert a flat dict back to a SystemConfig Pydantic model."""
    return SystemConfig(
        default_model=data.get("default_model") or None,
        fast_model=data.get("fast_model") or None,
        embed_model=data.get("embed_model") or None,
        reranker=data.get("reranker") or None,
        enable_content_guard=data.get("enable_content_guard", "false").lower() == "true",
        enable_content_guard_llm=data.get("enable_content_guard_llm", "false").lower() == "true",
        content_guard_llm_model=data.get("content_guard_llm_model") or None,
        theme=data.get("theme", "system"),
    )


@router.get("/config", response_model=SystemConfig)
async def get_config(db: AsyncSession = Depends(get_db)) -> SystemConfig:
    """Get system configuration from database."""
    data = await SystemConfigService.get_all(db)
    if not data:
        env_config = _load_config_from_env()
        env_dict = _pydantic_to_flat_dict(env_config)
        if env_dict:
            await SystemConfigService.upsert_many(db, env_dict)
            await db.commit()
            data = env_dict
    return _dict_to_system_config(data)


@router.put("/config", response_model=SystemConfig)
async def update_config(
    config: SystemConfig,
    db: AsyncSession = Depends(get_db),
) -> SystemConfig:
    """Update system configuration."""
    flat = _pydantic_to_flat_dict(config)
    await SystemConfigService.upsert_many(db, flat)
    await db.commit()
    data = await SystemConfigService.get_all(db)
    return _dict_to_system_config(data)


def _get_provider(name: str) -> str:
    """Extract provider from model name."""
    known_prefixes = ["siliconflow", "ollama", "openai", "anthropic", "google", "deepseek", "glm"]
    for prefix in known_prefixes:
        if name.startswith(f"{prefix}-") or name == prefix:
            return prefix
    return "other"


_PROVIDER_NAMES: dict[str, str] = {
    "siliconflow": "SiliconFlow",
    "ollama": "Ollama",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "deepseek": "DeepSeek",
    "glm": "GLM / 本地",
    "other": "其他",
}


def _load_chat_model_choices() -> list[ChatModelGroup]:
    """Load available chat models grouped by provider."""
    try:
        app_config = get_app_config()
    except Exception:
        return []

    groups: dict[str, list[ChatModelChoice]] = {}
    for model in app_config.models:
        provider = _get_provider(model.name)
        choice = ChatModelChoice(
            name=model.name,
            display_name=model.display_name or model.name,
        )
        groups.setdefault(provider, []).append(choice)

    return [
        ChatModelGroup(
            provider=_PROVIDER_NAMES.get(key, key),
            models=value,
        )
        for key, value in groups.items()
    ]


@router.get("/models/choices", response_model=ModelChoicesResponse)
async def get_model_choices() -> ModelChoicesResponse:
    """Get available model choices for selection."""
    return ModelChoicesResponse(
        embed_models=_load_embed_model_choices(),
        rerankers=_load_reranker_choices(),
        chat_models=_load_chat_model_choices(),
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
