"""Tests for DataSourceDataset model + service + router + mcp."""

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
