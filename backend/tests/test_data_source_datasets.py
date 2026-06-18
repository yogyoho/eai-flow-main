"""Tests for DataSourceDataset model + service + router + mcp."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from httpx import ASGITransport, AsyncClient

from app.extensions.data_source.routers import router
from app.extensions.data_source.schemas import DatasetCreate, DatasetResponse
from app.extensions.data_source.service import DataSourceService
from app.extensions.models import DataSourceDataset


class TestDatasetModel:
    def test_defaults(self):
        d = DataSourceDataset(source_id="sid", table_name="noise_monitor", label="厂界噪声")
        assert d.table_name == "noise_monitor"
        assert d.label == "厂界噪声"
        assert d.description is None
        assert d.key_columns is None
        assert d.default_query is None

    def test_tablename(self):
        assert DataSourceDataset.__tablename__ == "data_source_datasets"


class TestDatasetSchemas:
    def test_create_minimal(self):
        d = DatasetCreate(table_name="t", label="L")
        assert d.description is None
        assert d.key_columns is None
        assert d.default_query is None

    def test_create_requires_label(self):
        with pytest.raises(ValidationError):
            DatasetCreate(table_name="t", label="")

    def test_response_from_attributes(self):
        class _Fake:
            id = "d1"
            source_id = "s1"
            table_name = "t"
            label = "L"
            description = None
            key_columns = None
            default_query = None
            created_at = None
            updated_at = None

        r = DatasetResponse.model_validate(_Fake())
        assert r.label == "L"


def _src():
    m = MagicMock()
    m.id = "sid"
    return m


class TestDatasetService:
    @pytest.mark.asyncio
    async def test_create_checks_source_exists(self):
        db = AsyncMock()
        req = MagicMock()
        req.table_name = "t"
        req.label = "L"
        req.description = None
        req.key_columns = None
        req.default_query = None
        with patch.object(DataSourceService, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(ValueError):
                await DataSourceService.create_dataset(db, "sid", req)

    @pytest.mark.asyncio
    async def test_create_persists(self):
        db = AsyncMock()
        added = []

        def _add(o):
            added.append(o)

        db.add = MagicMock(side_effect=_add)
        db.flush = AsyncMock()
        req = MagicMock()
        req.table_name = "noise"
        req.label = "厂界噪声"
        req.description = "d"
        req.key_columns = ["a"]
        req.default_query = None
        with patch.object(DataSourceService, "get_by_id", AsyncMock(return_value=_src())):
            ds = await DataSourceService.create_dataset(db, "sid", req)
        assert added and ds.label == "厂界噪声"

    @pytest.mark.asyncio
    async def test_list_by_source(self):
        db = AsyncMock()
        rm = MagicMock()
        rm.scalars.return_value.all.return_value = ["x", "y"]
        db.execute = AsyncMock(return_value=rm)
        out = await DataSourceService.list_datasets(db, "sid")
        assert out == ["x", "y"]

    @pytest.mark.asyncio
    async def test_resolve_by_label(self):
        db = AsyncMock()
        rm = MagicMock()
        rm.scalars.return_value.first.return_value = "FOUND"
        db.execute = AsyncMock(return_value=rm)
        assert await DataSourceService.resolve_dataset(db, "sid", "厂界噪声") == "FOUND"


def _fake_dataset(**ov):
    base = {"id": str(uuid4()), "source_id": "sid", "table_name": "noise",
            "label": "厂界噪声", "description": None, "key_columns": None,
            "default_query": None, "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1)}
    base.update(ov)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


def _build_app():
    from fastapi import FastAPI
    from app.extensions.auth.middleware import get_current_user
    from app.extensions.database import get_db
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=uuid4())
    app.dependency_overrides[get_db] = _db
    return app


class TestDatasetRouter:
    @pytest.mark.asyncio
    async def test_list_datasets(self):
        with patch("app.extensions.data_source.routers.DataSourceService.list_datasets",
                   AsyncMock(return_value=[_fake_dataset()])):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get("/api/extensions/data-sources/sid/datasets")
        assert r.status_code == 200
        assert r.json()["items"][0]["label"] == "厂界噪声"

    @pytest.mark.asyncio
    async def test_create_dataset_201(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(return_value=_fake_dataset())):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/sid/datasets",
                                 json={"table_name": "noise", "label": "厂界噪声"})
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_create_404_when_source_missing(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(side_effect=ValueError("no source"))):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/sid/datasets",
                                 json={"table_name": "noise", "label": "L"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_dataset_204(self):
        with patch("app.extensions.data_source.routers.DataSourceService.delete_dataset",
                   AsyncMock(return_value=True)):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.delete("/api/extensions/data-sources/datasets/" + str(uuid4()))
        assert r.status_code == 204
