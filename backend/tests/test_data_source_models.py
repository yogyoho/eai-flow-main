"""Tests for the DataSource model."""

from app.extensions.models import DataSource


class TestDataSourceModel:
    def test_defaults(self):
        ds = DataSource(
            name="生产数据库",
            type="database",
            connection_config={"host": "db", "port": "5432"},
        )
        assert ds.name == "生产数据库"
        assert ds.type == "database"
        assert ds.auth_type == "none"
        assert ds.sync_mode == "manual"
        assert ds.status == "disconnected"
        assert ds.last_sync_at is None
        assert ds.sync_config is None

    def test_connection_config_accepts_arbitrary_json(self):
        ds = DataSource(name="api1", type="api", connection_config={"url": "https://x"})
        assert ds.connection_config["url"] == "https://x"

    def test_tablename(self):
        assert DataSource.__tablename__ == "data_sources"

    def test_type_field_is_plain_string(self):
        ds = DataSource(name="f", type="gis", connection_config={})
        assert ds.type == "gis"
