"""Tests for DataSourceDataset model + service + router + mcp."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.data_source.schemas import DatasetCreate, DatasetResponse
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
