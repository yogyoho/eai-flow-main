"""Tests for data_source schemas + service logic."""

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.extensions.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    TestConnectionResult,
)
from app.extensions.data_source.service import (
    DataSourceService,
    assert_readonly_select,
)


def _src(type_, cfg):
    """Build a fake DataSource ORM-like object for tests."""
    m = MagicMock()
    m.type = type_
    m.connection_config = cfg
    return m


class TestSchemas:
    def test_create_minimal(self):
        ds = DataSourceCreate(
            name="prod",
            type="database",
            connection_config={"host": "h", "port": "5432"},
        )
        assert ds.auth_type == "none"
        assert ds.sync_mode == "manual"
        assert ds.sync_config is None

    def test_create_requires_name(self):
        with pytest.raises(ValidationError):
            DataSourceCreate(name="", type="api", connection_config={})

    def test_test_connection_result_defaults(self):
        r = TestConnectionResult(success=True, message="ok")
        assert r.metadata is None

    def test_response_from_attributes(self):
        # Simulate an ORM-like object via a simple namespace
        class _Fake:
            id = "abc"
            name = "n"
            type = "api"
            connection_config = {}
            auth_type = "none"
            sync_mode = "manual"
            sync_config = None
            status = "disconnected"
            last_sync_at = None
            created_by = None
            created_at = None
            updated_at = None

        resp = DataSourceResponse.model_validate(_Fake())
        assert resp.name == "n"
        assert resp.id == "abc"


class TestAssertReadonlySelect:
    def test_select_appends_limit(self):
        out = assert_readonly_select("SELECT * FROM users")
        assert out.endswith("LIMIT 200")

    def test_with_cte_allowed(self):
        out = assert_readonly_select("WITH x AS (SELECT 1) SELECT * FROM x")
        assert out.startswith("WITH")

    def test_existing_limit_kept(self):
        out = assert_readonly_select("SELECT * FROM users LIMIT 5")
        assert "LIMIT 5" in out
        # must not double-append
        assert out.count("LIMIT") == 1

    def test_lowercase_select_allowed(self):
        out = assert_readonly_select("select * from t")
        assert "LIMIT 200" in out

    def test_insert_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("INSERT INTO t VALUES (1)")

    def test_update_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("UPDATE t SET a=1")

    def test_delete_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("DELETE FROM t")

    def test_drop_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("DROP TABLE t")

    def test_multi_statement_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("SELECT 1; DROP TABLE t;")

    def test_select_into_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("SELECT * INTO newt FROM t")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("   ")

    def test_trailing_semicolon_stripped(self):
        out = assert_readonly_select("SELECT 1;")
        assert ";" not in out
        assert "LIMIT 200" in out

    def test_cte_with_delete_rejected(self):
        # PostgreSQL data-modifying CTE — must be blocked (the bypass this guards against)
        with pytest.raises(ValueError):
            assert_readonly_select("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d")

    def test_cte_with_insert_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("WITH i AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM i")

    def test_column_named_update_time_passes(self):
        # underscore is a word char, so \bUPDATE\b must NOT match "update_time"
        out = assert_readonly_select("SELECT update_time FROM events")
        assert "LIMIT 200" in out

    def test_table_named_deleted_logs_passes(self):
        out = assert_readonly_select("SELECT * FROM deleted_logs")
        assert "LIMIT 200" in out

    def test_string_literal_with_delete_word_rejected(self):
        # fail-closed: a write verb inside a string literal is rejected (safe over-blocking)
        with pytest.raises(ValueError):
            assert_readonly_select("SELECT * FROM t WHERE note = 'please delete this'")


class TestTestConnection:
    """Per-type connection testing for DataSourceService."""

    @pytest.mark.asyncio
    async def test_database_success(self):
        # Build a fake async engine whose .connect() is an async context manager
        # yielding a connection whose .execute is an AsyncMock.
        fake_conn = MagicMock()
        fake_conn.execute = AsyncMock(return_value=MagicMock())

        fake_engine = MagicMock()
        fake_engine.dispose = AsyncMock()

        # engine.connect() must return an async context manager
        class _ConnectCM:
            async def __aenter__(self_inner):
                return fake_conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        fake_engine.connect = MagicMock(return_value=_ConnectCM())

        with patch(
            "app.extensions.data_source.service.create_async_engine",
            return_value=fake_engine,
        ):
            result = await DataSourceService.test_connection(_src("database", {"host": "h", "port": 5432, "database": "d"}))
        assert result.success is True
        fake_conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_database_failure(self):
        with patch(
            "app.extensions.data_source.service.create_async_engine",
            side_effect=RuntimeError("no host"),
        ):
            result = await DataSourceService.test_connection(_src("database", {"host": "h"}))
        assert result.success is False
        assert "no host" in result.message

    @pytest.mark.asyncio
    async def test_api_success(self):
        fake_response = MagicMock()
        fake_response.status_code = 200

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=fake_response)

        # httpx.AsyncClient(...) returns an async context manager
        class _ClientCM:
            async def __aenter__(self_inner):
                return fake_client

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        with patch(
            "app.extensions.data_source.service.httpx.AsyncClient",
            return_value=_ClientCM(),
        ):
            result = await DataSourceService.test_connection(_src("api", {"url": "https://example.com"}))
        assert result.success is True
        fake_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_api_http_error(self):
        fake_response = MagicMock()
        fake_response.status_code = 500

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=fake_response)

        class _ClientCM:
            async def __aenter__(self_inner):
                return fake_client

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        with patch(
            "app.extensions.data_source.service.httpx.AsyncClient",
            return_value=_ClientCM(),
        ):
            result = await DataSourceService.test_connection(_src("api", {"url": "https://example.com"}))
        assert result.success is False

    def test_file_exists(self):
        with tempfile.NamedTemporaryFile() as tmp:
            result = DataSourceService.test_connection_sync(_src("file", {"path": tmp.name}))
        assert result.success is True

    def test_file_missing(self):
        result = DataSourceService.test_connection_sync(_src("file", {"path": "/no/such/xyz"}))
        assert result.success is False

    def test_gis_configured(self):
        result = DataSourceService.test_connection_sync(_src("gis", {"file_name": "a.shp"}))
        assert result.success is True

    def test_unknown_type_fails_closed(self):
        result = DataSourceService.test_connection_sync(_src("weird", {}))
        assert result.success is False


class TestSync:
    @pytest.mark.asyncio
    async def test_sync_connected_when_test_ok(self):
        src = _src("api", {"url": "https://x"})
        with patch.object(
            DataSourceService,
            "test_connection",
            AsyncMock(return_value=TestConnectionResult(success=True, message="ok", metadata={"k": 1})),
        ):
            out = await DataSourceService.sync(src)
        assert out["status"] == "connected"
        assert out["last_sync_at"] is not None
        # Regression: last_sync_at must be tz-naive — DataSource.last_sync_at is
        # TIMESTAMP WITHOUT TIME ZONE; asyncpg rejects tz-aware (DataError → 500).
        assert out["last_sync_at"].tzinfo is None
        assert out["metadata"] == {"k": 1}

    @pytest.mark.asyncio
    async def test_sync_error_when_test_fails(self):
        src = _src("api", {"url": "https://x"})
        with patch.object(
            DataSourceService,
            "test_connection",
            AsyncMock(return_value=TestConnectionResult(success=False, message="boom")),
        ):
            out = await DataSourceService.sync(src)
        assert out["status"] == "error"


class TestCRUD:
    @pytest.mark.asyncio
    async def test_create_persists_and_returns(self):
        db = AsyncMock()
        added = []

        def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "new-id"

        db.add = MagicMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        db.commit = AsyncMock()

        req = DataSourceCreate(name="n", type="api", connection_config={"url": "u"})
        out = await DataSourceService.create(db, req, user_id=None)
        assert added, "row should be added to session"
        assert out.name == "n"

    @pytest.mark.asyncio
    async def test_list_returns_scalars(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ["a", "b"]
        db.execute = AsyncMock(return_value=result_mock)
        items = await DataSourceService.list(db)
        assert items == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_by_name(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = "FOUND"
        db.execute = AsyncMock(return_value=result_mock)
        out = await DataSourceService.get_by_name(db, "prod")
        assert out == "FOUND"


class TestRunReadonlyQuery:
    @pytest.mark.asyncio
    async def test_engine_url_built_from_source_config(self):
        # Regression: query must connect to the SOURCE's configured DB, NOT the
        # extensions DB. Found by /qa verification — query was hitting agentflow.
        src = MagicMock()
        src.connection_config = {
            "host": "src-host",
            "port": 5432,
            "database": "THE_SOURCE_DB",
            "username": "u",
            "password": "p",
        }
        captured = {}
        fake_res = MagicMock()
        fake_res.mappings.return_value.all.return_value = [{"db": "THE_SOURCE_DB"}]
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

        def _capture(url, **kw):
            captured["url"] = str(url)
            return fake_engine

        with patch("app.extensions.data_source.service.create_async_engine", side_effect=_capture):
            rows = await DataSourceService.run_readonly_query(src, "SELECT current_database() AS db LIMIT 200")
        assert "THE_SOURCE_DB" in captured["url"], f"engine should target source DB, got {captured['url']}"
        assert "src-host" in captured["url"]
        assert rows == [{"db": "THE_SOURCE_DB"}]
