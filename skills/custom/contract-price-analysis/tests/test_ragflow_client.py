"""Tests for the RAGFlow client (HTTP mocked — no live server needed)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from scripts.ragflow_client import RagflowClient, RagflowError


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    request = httpx.Request("GET", "http://x")
    return httpx.Response(status_code, json=json_data, request=request)


@pytest.mark.asyncio
async def test_list_documents_returns_docs():
    payload = {
        "code": 0,
        "data": [
            {"id": "doc-a", "name": "合同1.pdf", "hash": "h1", "run": "DONE"},
            {"id": "doc-b", "name": "合同2.pdf", "hash": "h2", "run": "DONE"},
        ],
    }
    client = RagflowClient(base_url="http://x", api_key="k", kb_id="kb")
    with patch.object(
        client._http, "get", new=AsyncMock(return_value=_mock_response(200, payload))
    ):
        docs = await client.list_documents()
    assert [d["id"] for d in docs] == ["doc-a", "doc-b"]


@pytest.mark.asyncio
async def test_list_documents_raises_on_nonzero_code():
    client = RagflowClient(base_url="http://x", api_key="k", kb_id="kb")
    with patch.object(
        client._http, "get",
        new=AsyncMock(return_value=_mock_response(200, {"code": 1, "message": "bad"})),
    ):
        with pytest.raises(RagflowError):
            await client.list_documents()


@pytest.mark.asyncio
async def test_get_document_chunks_returns_data():
    payload = {"code": 0, "data": [{"content": "row1"}, {"content": "row2"}]}
    client = RagflowClient(base_url="http://x", api_key="k", kb_id="kb")
    with patch.object(
        client._http, "get", new=AsyncMock(return_value=_mock_response(200, payload))
    ):
        chunks = await client.get_document_chunks("doc-a")
    assert len(chunks) == 2


def test_filter_changed_returns_new_and_stale():
    docs = [
        {"id": "doc-a", "name": "c1", "hash": "h1"},
        {"id": "doc-b", "name": "c2", "hash": "h2"},
        {"id": "doc-c", "name": "c3", "hash": "h3"},
    ]
    # doc-a unchanged (same hash), doc-b stale (hash differs), doc-c brand new
    cached = {"doc-a": "h1", "doc-b": "h-old"}
    changed = RagflowClient.filter_changed(docs, cached)
    assert [d["id"] for d in changed] == ["doc-b", "doc-c"]


def test_filter_changed_empty_cache_returns_all():
    docs = [{"id": "a", "hash": "1"}, {"id": "b", "hash": "2"}]
    assert [d["id"] for d in RagflowClient.filter_changed(docs, {})] == ["a", "b"]
