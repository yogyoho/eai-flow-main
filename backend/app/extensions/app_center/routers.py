"""App-center API router — DB-persisted app catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.app_center.schemas import (
    AppDefinitionCreate,
    AppDefinitionListResponse,
    AppDefinitionResponse,
    AppDefinitionUpdate,
    AppDomainCreate,
    AppDomainListResponse,
    AppDomainResponse,
    AppDomainUpdate,
)
from app.extensions.app_center.service import AppCenterService
from app.extensions.auth.middleware import get_current_user, require_permission, require_super_admin
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/app-center", tags=["app-center"])

# ── Domains (public read, admin write) ──


@router.get("/domains", response_model=AppDomainListResponse)
async def list_domains(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: read access for all users
):
    items = await AppCenterService.list_domains(db)
    return AppDomainListResponse(
        items=[AppDomainResponse.model_validate(i) for i in items]
    )


@router.post(
    "/domains", response_model=AppDomainResponse, status_code=status.HTTP_201_CREATED
)
async def create_domain(
    data: AppDomainCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    domain = await AppCenterService.create_domain(db, data)
    await db.commit()
    await db.refresh(domain)
    return AppDomainResponse.model_validate(domain)


@router.put("/domains/{key}", response_model=AppDomainResponse)
async def update_domain(
    key: str,
    data: AppDomainUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    domain = await AppCenterService.update_domain(db, key, data)
    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found"
        )
    await db.commit()
    await db.refresh(domain)
    return AppDomainResponse.model_validate(domain)


@router.delete("/domains/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    key: str,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    ok = await AppCenterService.delete_domain(db, key)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found"
        )
    await db.commit()


# ── Apps (public read, admin write) ──


@router.get("/apps", response_model=AppDefinitionListResponse)
async def list_apps(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: read access for all users
):
    items = await AppCenterService.list_apps(db)
    return AppDefinitionListResponse(
        items=[AppDefinitionResponse.model_validate(i) for i in items]
    )


@router.get("/apps/all", response_model=AppDefinitionListResponse)
async def list_all_apps(
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    """Admin-only: returns all apps including disabled ones."""
    items = await AppCenterService.list_all_apps(db)
    return AppDefinitionListResponse(
        items=[AppDefinitionResponse.model_validate(i) for i in items]
    )


@router.post(
    "/apps", response_model=AppDefinitionResponse, status_code=status.HTTP_201_CREATED
)
async def create_app(
    data: AppDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    app = await AppCenterService.create_app(db, data)
    await db.commit()
    await db.refresh(app)
    return AppDefinitionResponse.model_validate(app)


@router.put("/apps/{app_id}", response_model=AppDefinitionResponse)
async def update_app(
    app_id: str,
    data: AppDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    app = await AppCenterService.update_app(db, app_id, data)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )
    await db.commit()
    await db.refresh(app)
    return AppDefinitionResponse.model_validate(app)


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: Annotated[CurrentUser, Depends(require_super_admin())] = None,
):
    ok = await AppCenterService.delete_app(db, app_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )
    await db.commit()
