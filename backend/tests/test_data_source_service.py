"""Tests for data_source schemas + service logic."""

import pytest
from pydantic import ValidationError

from app.extensions.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    TestConnectionResult,
)


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
