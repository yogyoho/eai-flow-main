"""Tests for the data_source MCP server (tool wiring + read-only enforcement)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.data_source import mcp as ds_mcp


def _db_src(type_="database", **kw):
    m = MagicMock()
    m.name = kw.get("name", "prod")
    m.type = type_
    m.connection_config = kw.get("connection_config", {})
    return m


@pytest.mark.asyncio
async def test_list_tools_returns_six():
    names = {t.name for t in ds_mcp.TOOLS}
    assert names == {
        "list_data_sources",
        "get_data_source_schema",
        "query_data_source",
        "test_data_source",
        "list_datasets",
        "query_dataset",
    }


@pytest.mark.asyncio
async def test_list_data_sources_handler():
    fake = MagicMock()
    fake.id = "id1"
    fake.name = "prod"
    fake.type = "database"
    fake.status = "connected"
    fake.last_sync_at = None
    fake.description = "厂界噪声2024"

    async def _run(func):
        return await func(MagicMock())

    with patch("app.extensions.data_source.mcp._run_in_db", _run), patch("app.extensions.data_source.service.DataSourceService.list", AsyncMock(return_value=[fake])):
        out = await ds_mcp._handle_list_data_sources({})
    payload = json.loads(out[0].text)
    assert payload["success"] is True
    assert payload["data_sources"][0]["name"] == "prod"
    assert payload["data_sources"][0]["description"] == "厂界噪声2024"


@pytest.mark.asyncio
async def test_query_rejects_write_sql():
    async def _run(func):
        return await func(MagicMock())

    with patch("app.extensions.data_source.mcp._run_in_db", _run), patch("app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=_db_src())):
        out = await ds_mcp._handle_query_data_source({"name": "prod", "params": {"sql": "DELETE FROM users"}})
    payload = json.loads(out[0].text)
    assert payload["success"] is False
    assert payload["message"]


@pytest.mark.asyncio
async def test_query_executes_readonly_sql():
    async def _run(func):
        return await func(MagicMock())  # lookup session

    with (
        patch("app.extensions.data_source.mcp._run_in_db", _run),
        patch("app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=_db_src())),
        patch(
            # the handler now queries the SOURCE's own DB via this service method
            "app.extensions.data_source.service.DataSourceService.run_readonly_query",
            AsyncMock(return_value=[{"id": 1, "name": "x"}]),
        ),
    ):
        out = await ds_mcp._handle_query_data_source({"name": "prod", "params": {"sql": "SELECT id, name FROM users"}})
    payload = json.loads(out[0].text)
    assert payload["success"] is True
    assert payload["rows"] == [{"id": 1, "name": "x"}]
    assert "LIMIT" in payload["sql"].upper()


@pytest.mark.asyncio
async def test_query_404_when_source_missing():
    async def _run(func):
        return await func(MagicMock())

    with patch("app.extensions.data_source.mcp._run_in_db", _run), patch("app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=None)):
        out = await ds_mcp._handle_query_data_source({"name": "nope", "params": {"sql": "SELECT 1"}})
    payload = json.loads(out[0].text)
    assert payload["success"] is False
    assert "不存在" in payload["message"]
