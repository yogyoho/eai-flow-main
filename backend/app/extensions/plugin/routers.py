"""Plugin API router — registry + instances + API keys (metadata only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from jsonschema import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.database import get_db
from app.extensions.plugin.schemas import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    PluginInstanceCreate,
    PluginInstanceListResponse,
    PluginInstanceResponse,
    PluginInstanceUpdate,
    PluginListResponse,
    PluginResponse,
)
from app.extensions.plugin.service import PluginService
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/plugins", tags=["plugins"])


# ── registry ──


@router.get("/registry", response_model=PluginListResponse)
async def list_registry(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:read")),  # EAI-CUSTOM: Add permission check
):
    items = await PluginService.list_plugins(db)
    return PluginListResponse(items=[PluginResponse.model_validate(i) for i in items])


@router.get("/registry/{plugin_id}", response_model=PluginResponse)
async def get_plugin(
    plugin_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:read")),  # EAI-CUSTOM: Add permission check
):
    p = await PluginService.get_plugin(db, plugin_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    return PluginResponse.model_validate(p)


# ── instances ──


@router.get("/instances", response_model=PluginInstanceListResponse)
async def list_instances(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:read")),  # EAI-CUSTOM: Add permission check
):
    items = await PluginService.list_instances(db, project_id=project_id)
    return PluginInstanceListResponse(items=[PluginInstanceResponse.model_validate(i) for i in items])


@router.post("/instances", response_model=PluginInstanceResponse, status_code=status.HTTP_201_CREATED)
async def install_instance(
    data: PluginInstanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:install")),  # EAI-CUSTOM: Add permission check
):
    try:
        inst = await PluginService.create_instance(db, data, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    await db.commit()
    await db.refresh(inst)
    return PluginInstanceResponse.model_validate(inst)


@router.patch("/instances/{instance_id}", response_model=PluginInstanceResponse)
async def update_instance(
    instance_id: UUID,
    data: PluginInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:install")),  # EAI-CUSTOM: Add permission check
):
    try:
        inst = await PluginService.update_instance(db, instance_id, data)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件实例不存在")
    await db.commit()
    await db.refresh(inst)
    return PluginInstanceResponse.model_validate(inst)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:uninstall")),  # EAI-CUSTOM: Add permission check
):
    ok = await PluginService.delete_instance(db, instance_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件实例不存在")
    await db.commit()


# ── API keys ──


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:read")),  # EAI-CUSTOM: Add permission check
):
    items = await PluginService.list_api_keys(db)
    return ApiKeyListResponse(items=[ApiKeyResponse.model_validate(i) for i in items])


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:install")),  # EAI-CUSTOM: Add permission check
):
    rec, raw = await PluginService.create_api_key(db, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(rec)
    return ApiKeyCreateResponse(id=rec.id, key=raw)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("skill:install")),  # EAI-CUSTOM: Add permission check
):
    ok = await PluginService.delete_api_key(db, key_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    await db.commit()
