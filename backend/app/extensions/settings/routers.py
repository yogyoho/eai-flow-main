"""Settings API router."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission, require_super_admin
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser
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
    enable_content_guard: bool = False
    enable_content_guard_llm: bool = False
    content_guard_llm_model: str | None = None
    theme: str = "system"
    # EAI-CUSTOM (cpa v3 M3): 专业 OCR 服务注册表,JSON 字符串
    # [{"name","base_url","api_key","model"}];GET 回显 api_key 掩码,写走专用 admin 端点。
    ocr_services: str | None = None


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
    chat_models: list[ChatModelGroup] = []


router = APIRouter(prefix="/api/extensions", tags=["settings"])


def _load_config_from_env() -> SystemConfig:
    """Load configuration from environment variables."""
    return SystemConfig(
        default_model=os.getenv("DEFAULT_MODEL", ""),
        fast_model=os.getenv("FAST_MODEL", ""),
        embed_model=os.getenv("EMBED_MODEL", ""),
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
        enable_content_guard=data.get("enable_content_guard", "false").lower() == "true",
        enable_content_guard_llm=data.get("enable_content_guard_llm", "false").lower() == "true",
        content_guard_llm_model=data.get("content_guard_llm_model") or None,
        theme=data.get("theme", "system"),
        ocr_services=data.get("ocr_services") or None,
    )


# ── OCR 服务注册表（cpa v3 M3,spec §3.2）────────────────────────────────
# EAI-CUSTOM: api_key write-only 掩码回显(镜像 contract_price LLM_KEY_MASK 模式);
# 读=登录用户(system:access),写=admin(require_super_admin)。
OCR_KEY_MASK = "********"


async def _load_ocr_services(db: AsyncSession) -> list[dict]:
    """system_config ocr_services KV → list[dict](空/坏 JSON → [])。"""
    data = await SystemConfigService.get_all(db)
    raw = (data or {}).get("ocr_services") or ""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _mask_ocr_services(services: list[dict]) -> list[dict]:
    """api_key → 掩码(非空才掩,保留「已配置/未配置」区分)。"""
    return [
        {**s, "api_key": OCR_KEY_MASK if (s.get("api_key") or "").strip() else ""}
        for s in services
    ]


def _resolve_ocr_services_mask(incoming: list[dict], stored: list[dict]) -> list[dict]:
    """入站 api_key==掩码 → 还原已存真值(「未修改」语义);新明文直接落。"""
    by_name = {s.get("name"): s for s in stored}
    out = []
    for s in incoming:
        key = (s.get("api_key") or "").strip()
        if key == OCR_KEY_MASK:
            prev = by_name.get(s.get("name"))
            key = (prev or {}).get("api_key", "")
        out.append({**s, "api_key": key})
    return out


@router.get("/config", response_model=SystemConfig)
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
) -> SystemConfig:
    """Get system configuration from database."""
    data = await SystemConfigService.get_all(db)
    if not data:
        env_config = _load_config_from_env()
        env_dict = _pydantic_to_flat_dict(env_config)
        if env_dict:
            await SystemConfigService.upsert_many(db, env_dict)
            await db.commit()
            data = env_dict
    cfg = _dict_to_system_config(data)
    # EAI-CUSTOM (cpa v3 M3): ocr_services 的 api_key 掩码回显(write-only);
    # cpa 设置 tab 只消费服务名列表,掩码不阻碍读方。
    if cfg.ocr_services:
        try:
            services = json.loads(cfg.ocr_services)
            if isinstance(services, list):
                cfg = cfg.model_copy(
                    update={"ocr_services": json.dumps(_mask_ocr_services(services), ensure_ascii=False)}
                )
        except (ValueError, TypeError):
            pass
    return cfg


@router.put("/config", response_model=SystemConfig)
async def update_config(
    config: SystemConfig,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
) -> SystemConfig:
    """Update system configuration."""
    flat = _pydantic_to_flat_dict(config)
    # EAI-CUSTOM (cpa v3 M3): 通用 PUT 不接 ocr_services——api_key 是掩码回显,
    # 原样回写会把真值冲成掩码;写走 PUT /ocr/services(admin,掩码还原)。
    # 入站含掩码哨兵 → 视为「未修改」整字段跳过;无掩码的明文同样忽略(越权防护)。
    flat.pop("ocr_services", None)
    await SystemConfigService.upsert_many(db, flat)
    await db.commit()
    data = await SystemConfigService.get_all(db)
    cfg = _dict_to_system_config(data)
    if cfg.ocr_services:
        try:
            services = json.loads(cfg.ocr_services)
            if isinstance(services, list):
                cfg = cfg.model_copy(
                    update={"ocr_services": json.dumps(_mask_ocr_services(services), ensure_ascii=False)}
                )
        except (ValueError, TypeError):
            pass
    return cfg


class OcrServiceEntry(BaseModel):
    """A single professional-OCR service registration (openai-vision protocol)."""

    name: str
    base_url: str
    api_key: str = ""
    model: str = ""


class OcrServicesPayload(BaseModel):
    services: list[OcrServiceEntry]


class OcrServicesResponse(BaseModel):
    services: list[OcrServiceEntry]


@router.get("/ocr/services", response_model=OcrServicesResponse)
async def get_ocr_services(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
) -> OcrServicesResponse:
    """List registered OCR services (api_key masked)."""
    services = await _load_ocr_services(db)
    return OcrServicesResponse(services=_mask_ocr_services(services))


@router.put("/ocr/services", response_model=OcrServicesResponse)
async def update_ocr_services(
    payload: OcrServicesPayload,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_super_admin()),  # EAI-CUSTOM: 注册表为管理员配置
) -> OcrServicesResponse:
    """Upsert the OCR service registry (admin only; masked keys keep stored truth)."""
    names = [s.name.strip() for s in payload.services]
    if any(not n for n in names):
        raise HTTPException(status_code=422, detail="服务名不能为空")
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="服务名重复")
    stored = await _load_ocr_services(db)
    resolved = _resolve_ocr_services_mask(
        [s.model_dump() for s in payload.services], stored
    )
    await SystemConfigService.upsert_many(
        db, {"ocr_services": json.dumps(resolved, ensure_ascii=False)}
    )
    await db.commit()
    return OcrServicesResponse(services=_mask_ocr_services(resolved))


class OcrValidateRequest(BaseModel):
    base_url: str
    api_key: str = ""
    model: str = ""


@router.post("/ocr/validate")
async def validate_ocr_service(
    request: OcrValidateRequest,
    _: CurrentUser = Depends(require_permission("system:access")),
) -> dict:
    """Ping an openai-vision OCR service with a 1x1 image (mirror models/validate)."""
    import base64 as _b64
    import time as _time

    import httpx

    base = (request.base_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=422, detail="base_url 不能为空")
    # 1x1 transparent PNG
    png_1px = _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    data_url = f"data:image/png;base64,{_b64.b64encode(png_1px).decode()}"
    body = {
        "model": request.model or "default",
        "max_tokens": 16,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "Reply with OK."},
                ],
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    if (request.api_key or "").strip():
        headers["Authorization"] = f"Bearer {request.api_key.strip()}"
    started = _time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base}/chat/completions", json=body, headers=headers)
        latency = int((_time.monotonic() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 — 网络错误归一化为不可用
        return {"ok": False, "message": f"连接失败：{exc}", "latency_ms": None}
    if resp.status_code >= 400:
        return {
            "ok": False,
            "message": f"HTTP {resp.status_code}：{resp.text[:200]}",
            "latency_ms": latency,
        }
    return {"ok": True, "message": f"可用（{latency}ms）", "latency_ms": latency}


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
async def get_model_choices(
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
) -> ModelChoicesResponse:
    """Get available model choices for selection."""
    return ModelChoicesResponse(
        embed_models=_load_embed_model_choices(),
        chat_models=_load_chat_model_choices(),
    )


class ModelValidationResponse(BaseModel):
    """Response model for model validation."""

    results: list[ModelValidationResult]


@router.post("/models/validate", response_model=ModelValidationResponse)
async def validate_models_endpoint(
    request: ModelValidationRequest,
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
) -> ModelValidationResponse:
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
