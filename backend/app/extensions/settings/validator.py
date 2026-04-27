"""Model validation logic."""

from typing import Literal
from pydantic import BaseModel

from deerflow.config import get_app_config


class ModelValidationDetails(BaseModel):
    """Validation details for a single model."""

    exists: bool
    api_reachable: bool | None
    supports_thinking: bool
    supports_vision: bool
    has_credentials: bool
    message: str | None
    latency_ms: float | None


class ModelValidationResult(BaseModel):
    """Validation result for a single model."""

    name: str
    status: Literal["available", "unavailable", "error"]
    details: ModelValidationDetails


class ModelValidationRequest(BaseModel):
    """Request to validate models."""

    models: list[str]


def check_model_exists(model_name: str) -> bool:
    """Check if model exists in configuration."""
    config = get_app_config()
    return any(m.name == model_name for m in config.models)


import time
import asyncio
from deerflow.models import create_chat_model


async def test_api_reachable(model_name: str) -> tuple[bool, float | None]:
    """Test if model API is reachable with a lightweight request.

    Returns:
        (reachable, latency_ms)
    """
    try:
        start = time.time()
        model = create_chat_model(model_name, thinking_enabled=False)
        # Send minimal test message
        response = await model.ainvoke([("human", "Hi")])
        latency = (time.time() - start) * 1000
        return True, latency
    except Exception as e:
        return False, None


def get_model_features(model_name: str) -> tuple[bool, bool]:
    """Get model features (thinking, vision support).

    Returns:
        (supports_thinking, supports_vision)
    """
    config = get_app_config()
    model = config.get_model_config(model_name)
    if not model:
        return False, False
    return model.supports_thinking, model.supports_vision


import os


def check_model_credentials(model_name: str) -> bool:
    """Check if model has required API credentials."""
    config = get_app_config()
    model = config.get_model_config(model_name)
    if not model:
        return False

    # Check if provider-specific env vars are set
    # This is a basic check - real implementation depends on provider
    if "openai" in model.use.lower():
        return bool(os.getenv("OPENAI_API_KEY"))
    elif "anthropic" in model.use.lower() or "claude" in model.use.lower():
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    # Add other providers as needed
    return True  # Default to True for unknown providers


async def validate_model(model_name: str) -> ModelValidationResult:
    """Validate a single model and return detailed result.

    Args:
        model_name: Name of the model to validate.

    Returns:
        ModelValidationResult with status and details.
    """
    exists = check_model_exists(model_name)

    if not exists:
        return ModelValidationResult(
            name=model_name,
            status="unavailable",
            details=ModelValidationDetails(
                exists=False,
                api_reachable=None,
                supports_thinking=False,
                supports_vision=False,
                has_credentials=False,
                message=f"Model '{model_name}' not found in configuration",
                latency_ms=None,
            ),
        )

    # Run validations in parallel
    has_creds = check_model_credentials(model_name)
    supports_thinking, supports_vision = get_model_features(model_name)
    api_reachable, latency = await test_api_reachable(model_name)

    if api_reachable and has_creds:
        status = "available"
        message = f"Model available (latency: {latency:.0f}ms)"
    else:
        status = "unavailable"
        reasons = []
        if not has_creds:
            reasons.append("missing credentials")
        if not api_reachable:
            reasons.append("API unreachable")
        message = f"Validation failed: {', '.join(reasons)}"

    return ModelValidationResult(
        name=model_name,
        status=status,
        details=ModelValidationDetails(
            exists=True,
            api_reachable=api_reachable,
            supports_thinking=supports_thinking,
            supports_vision=supports_vision,
            has_credentials=has_creds,
            message=message,
            latency_ms=latency,
        ),
    )


async def validate_models(model_names: list[str]) -> list[ModelValidationResult]:
    """Validate multiple models in parallel.

    Args:
        model_names: List of model names to validate.

    Returns:
        List of ModelValidationResult.
    """
    tasks = [validate_model(name) for name in model_names]
    return await asyncio.gather(*tasks)