"""Data source API router — CRUD + connection test + manual sync."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.data_source.schemas import (
    DatasetCreate,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdate,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    SyncResponse,
    TestConnectionResult,
)
from app.extensions.data_source.service import DataSourceService
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/data-sources", tags=["data-sources"])


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await DataSourceService.list(db)
    return DataSourceListResponse(items=[DataSourceResponse.model_validate(i) for i in items])


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = await DataSourceService.get_by_name(db, data.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据源名称已存在")
    ds = await DataSourceService.create(db, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse.model_validate(ds)


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    return DataSourceResponse.model_validate(ds)


@router.patch("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    source_id: UUID,
    data: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.update(db, source_id, data)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse.model_validate(ds)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await DataSourceService.delete(db, source_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    await db.commit()


@router.post("/{source_id}/test", response_model=TestConnectionResult)
async def test_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    ds.status = "testing"
    await db.flush()
    result = await DataSourceService.test_connection(ds)
    ds.status = "connected" if result.success else "error"
    await db.commit()
    return result


@router.post("/{source_id}/sync", response_model=SyncResponse)
async def sync_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    out = await DataSourceService.sync(ds)
    ds.status = out["status"]
    ds.last_sync_at = out["last_sync_at"]
    await db.commit()
    await db.refresh(ds)
    return SyncResponse(
        id=ds.id, status=ds.status, last_sync_at=ds.last_sync_at, metadata=out["metadata"]
    )


# ── datasets (curated business tables within a source) ──


@router.get("/{source_id}/datasets", response_model=DatasetListResponse)
async def list_datasets(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await DataSourceService.list_datasets(db, source_id)
    return DatasetListResponse(items=[DatasetResponse.model_validate(i) for i in items])


@router.post("/{source_id}/datasets", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    source_id: UUID,
    data: DatasetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ds = await DataSourceService.create_dataset(db, source_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    await db.commit()
    await db.refresh(ds)
    return DatasetResponse.model_validate(ds)


@router.patch("/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: UUID,
    data: DatasetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.update_dataset(db, dataset_id, data)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    await db.commit()
    await db.refresh(ds)
    return DatasetResponse.model_validate(ds)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await DataSourceService.delete_dataset(db, dataset_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    await db.commit()
