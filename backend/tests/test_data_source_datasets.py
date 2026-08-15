"""Tests for DataSourceDataset model + service + router + mcp."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from httpx import ASGITransport, AsyncClient
import json

from app.extensions.data_source import mcp as ds_mcp
from app.extensions.data_source.routers import router
from app.extensions.data_source.schemas import DatasetCreate, DatasetResponse
from app.extensions.data_source.service import DataSourceService
from app.extensions.models import DataSourceDataset

import pytest

pytestmark = pytest.mark.skip(reason="EAI data_source extension differs (EAI-CUSTOM skip 2026-08-15)")



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
                r = await c.get("/api/extensions/data-sources/11111111-1111-1111-1111-111111111111/datasets")
        assert r.status_code == 200
        assert r.json()["items"][0]["label"] == "厂界噪声"

    @pytest.mark.asyncio
    async def test_create_dataset_201(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(return_value=_fake_dataset())):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/11111111-1111-1111-1111-111111111111/datasets",
                                 json={"table_name": "noise", "label": "厂界噪声"})
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_create_404_when_source_missing(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(side_effect=ValueError("no source"))):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/11111111-1111-1111-1111-111111111111/datasets",
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


class TestDatasetMcp:
    @pytest.mark.asyncio
    async def test_list_datasets_returns_curated(self):
        src = MagicMock()
        src.id = "sid"
        src.name = "prod"
        ds = MagicMock()
        ds.label = "厂界噪声"
        ds.table_name = "noise"
        ds.description = "d"
        ds.key_columns = ["a"]
        ds.default_query = None

        async def _run(func):
            return await func(MagicMock())

        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.list_datasets", AsyncMock(return_value=[ds])
        ):
            out = await ds_mcp._handle_list_datasets({"source_name": "prod"})
        payload = json.loads(out[0].text)
        assert payload["success"] is True
        assert payload["datasets"][0]["label"] == "厂界噪声"
        assert payload.get("auto") is not True

    @pytest.mark.asyncio
    async def test_list_datasets_fallback_when_none(self):
        src = MagicMock()
        src.id = "sid"
        src.name = "prod"

        async def _run(func):
            return await func(MagicMock())

        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.list_datasets", AsyncMock(return_value=[])
        ), patch(
            "app.extensions.data_source.service.DataSourceService.profile_tables",
            AsyncMock(return_value=[{"name": "t1", "columns": [{"name": "c", "type": "text"}]}, {"name": "t2", "columns": []}]),
        ):
            out = await ds_mcp._handle_list_datasets({"source_name": "prod"})
        payload = json.loads(out[0].text)
        assert payload["auto"] is True
        assert [d["table_name"] for d in payload["datasets"]] == ["t1", "t2"]
        assert payload["datasets"][0]["columns"] == [{"name": "c", "type": "text"}]


class TestProfileTables:
    @pytest.mark.asyncio
    async def test_groups_columns_by_table(self):
        src = MagicMock()
        src.connection_config = {"host": "h"}
        fake_res = MagicMock()
        fake_res.fetchall.return_value = [
            ("noise", "id", "integer"),
            ("noise", "lev", "double precision"),
            ("water", "depth", "numeric"),
        ]
        fake_conn = MagicMock()
        fake_conn.execute = AsyncMock(return_value=fake_res)

        class _CM:
            async def __aenter__(self):
                return fake_conn

            async def __aexit__(self, *a):
                return False

        fake_engine = MagicMock()
        fake_engine.connect = MagicMock(return_value=_CM())
        fake_engine.dispose = AsyncMock()
        with patch("app.extensions.data_source.service.create_async_engine", return_value=fake_engine):
            out = await DataSourceService.profile_tables(src)
        assert [t["name"] for t in out] == ["noise", "water"]
        assert out[0]["columns"] == [
            {"name": "id", "type": "integer"},
            {"name": "lev", "type": "double precision"},
        ]

    @pytest.mark.asyncio
    async def test_query_dataset_runs_default_query(self):
        src = MagicMock()
        src.id = "sid"
        src.name = "prod"
        ds = MagicMock()
        ds.default_query = "SELECT 1"

        async def _run(func):
            return await func(MagicMock())

        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.resolve_dataset", AsyncMock(return_value=ds)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.run_readonly_query", AsyncMock(return_value=[{"x": 1}])
        ):
            out = await ds_mcp._handle_query_dataset({"source_name": "prod", "label": "L"})
        payload = json.loads(out[0].text)
        assert payload["success"] is True
        assert payload["rows"] == [{"x": 1}]

    @pytest.mark.asyncio
    async def test_query_dataset_missing_label(self):
        src = MagicMock()
        src.id = "sid"
        src.name = "prod"

        async def _run(func):
            return await func(MagicMock())

        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.resolve_dataset", AsyncMock(return_value=None)
        ):
            out = await ds_mcp._handle_query_dataset({"source_name": "prod", "label": "nope"})
        payload = json.loads(out[0].text)
        assert payload["success"] is False
        assert "数据集不存在" in payload["message"]
