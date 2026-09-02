"""Wire-format tests for the extensions RAGFlow HTTP client.

Pins the request contract against the RAGFlow v0.27.1 server source:
- list pagination uses ``page``/``page_size`` (``limit``/``size`` are ignored
  upstream; ``page_size`` is capped at 100)
- embedding models come from ``GET /api/v1/models?type=embedding``
  (legacy ``/v1/llm/list`` was removed in v0.27.x)
- document metadata goes through PATCH with a ``meta_fields`` wrapper
- retrieval filters by ``document_ids`` (``doc_ids`` is not a known field)
- upload-time ``parser_id`` is applied via a follow-up document PATCH
"""

from types import SimpleNamespace

import httpx
import pytest

from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.service import DocumentService
from app.extensions.schemas import to_doc_status

BASE = "http://ragflow.test"


@pytest.fixture
def install_transport(monkeypatch):
    """Stub extensions config and route every httpx request through MockTransport."""

    def _install(handler):
        captured = SimpleNamespace(requests=[])

        def recording_handler(request):
            captured.requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(recording_handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(client, *args, **kwargs):
            kwargs.setdefault("transport", transport)
            original_init(client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        return captured

    stub_config = SimpleNamespace(ragflow=SimpleNamespace(api_key="test-key", base_url=BASE, timeout=5))
    monkeypatch.setattr("app.extensions.knowledge.client.get_extensions_config", lambda: stub_config)
    return _install


@pytest.mark.asyncio
async def test_embedding_models_use_api_v1_models_endpoint(install_transport):
    """Live v0.27.1 wire format: bare list in `data`, model_type is a LIST, no `enable` field."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": [
                    {"name": "bge-m3:latest", "provider_name": "Ollama", "model_type": ["embedding"], "rank": 500},
                    {"name": "agnes-2.0-flash", "provider_name": "OpenAI-API-Compatible", "model_type": ["chat"], "rank": 500},
                    {"name": "mxbai-embed-large:latest", "provider_name": "Ollama", "model_type": ["embedding"], "rank": 500},
                ],
            },
        )

    captured = install_transport(handler)
    models = await RAGFlowClient().list_available_embedding_models()

    assert models == ["bge-m3:latest@Ollama", "mxbai-embed-large:latest@Ollama"]
    req = captured.requests[0]
    assert req.url.path == "/api/v1/models"
    assert dict(req.url.params) == {"type": "embedding"}
    assert req.headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_embedding_models_empty_tenant_returns_bare_list(install_transport):
    """Empty tenant: upstream returns `data: []` (bare list), not the documented dict."""

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": []})

    install_transport(handler)
    assert await RAGFlowClient().list_available_embedding_models() == []


@pytest.mark.asyncio
async def test_embedding_models_documented_dict_shape(install_transport):
    """Tolerate the Swagger-documented {"models": [...]} shape too."""

    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"models": [{"model_name": "e", "model_provider": "P", "model_type": "embedding", "enable": True}]}})

    install_transport(handler)
    assert await RAGFlowClient().list_available_embedding_models() == ["e@P"]


@pytest.mark.asyncio
async def test_list_documents_sends_page_size_capped_at_100(install_transport):
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"total": 0, "docs": []}})

    captured = install_transport(handler)
    await RAGFlowClient().list_documents("ds1", page=2, size=250)

    params = dict(captured.requests[0].url.params)
    assert params == {"page": "2", "page_size": "100"}


@pytest.mark.asyncio
async def test_get_document_filters_by_id_param(install_transport):
    def handler(request):
        assert dict(request.url.params) == {"id": "doc-2"}
        return httpx.Response(
            200,
            json={"code": 0, "data": {"total": 1, "docs": [{"id": "doc-2", "run": "DONE", "chunk_count": 7}]}},
        )

    install_transport(handler)
    result = await RAGFlowClient().get_document("ds1", "doc-2")
    assert result["data"]["id"] == "doc-2"
    assert result["data"]["run"] == "DONE"


@pytest.mark.asyncio
async def test_get_document_unknown_id_returns_empty(install_transport):
    def handler(request):
        # upstream returns DATA_ERROR (HTTP 4xx) for ids not in the dataset
        return httpx.Response(400, json={"code": 102, "message": "You don't own the document"})

    install_transport(handler)
    result = await RAGFlowClient().get_document("ds1", "missing")
    assert result == {"data": {}}


@pytest.mark.asyncio
async def test_get_dataset_by_name_uses_name_filter(install_transport):
    def handler(request):
        params = dict(request.url.params)
        if params.get("name") == "ragflow-laws-legal":
            return httpx.Response(200, json={"code": 0, "data": [{"id": "ds-9", "name": "ragflow-laws-legal"}]})
        return httpx.Response(200, json={"code": 0, "data": []})

    install_transport(handler)
    found = await RAGFlowClient().get_dataset_by_name("ragflow-laws-legal")
    assert found == {"id": "ds-9", "name": "ragflow-laws-legal"}
    assert await RAGFlowClient().get_dataset_by_name("nope") is None


@pytest.mark.asyncio
async def test_update_document_metadata_patches_meta_fields(install_transport):
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": True})

    captured = install_transport(handler)
    metadata = {"law_number": "GB 50015-2019", "issuing_authority": "住建部"}
    await RAGFlowClient().update_document_metadata("ds1", "doc1", metadata)

    req = captured.requests[0]
    assert req.method == "PATCH"
    assert req.url.path == "/api/v1/datasets/ds1/documents/doc1"
    import json as _json

    body = _json.loads(req.read().decode())
    assert body == {"meta_fields": metadata}


@pytest.mark.asyncio
async def test_upload_document_applies_parser_via_patch(install_transport, tmp_path):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": [{"id": "doc-new", "name": "a.pdf"}]})
        assert request.method == "PATCH"
        assert request.url.path == "/api/v1/datasets/ds1/documents/doc-new"
        import json as _json

        assert _json.loads(request.read().decode()) == {
            "chunk_method": "laws",
            "parser_config": {"chunk_token_num": 512},
        }
        return httpx.Response(200, json={"code": 0, "data": True})

    captured = install_transport(handler)
    file = tmp_path / "a.pdf"
    file.write_bytes(b"%PDF-1.4 fake")

    result = await RAGFlowClient().upload_document("ds1", str(file), parser_id="laws", parser_config={"chunk_token_num": 512})
    assert result["data"]["id"] == "doc-new"
    assert len(captured.requests) == 2


@pytest.mark.asyncio
async def test_upload_document_without_parser_skips_patch(install_transport, tmp_path):
    def handler(request):
        assert request.method == "POST"
        return httpx.Response(200, json={"code": 0, "data": [{"id": "doc-new"}]})

    captured = install_transport(handler)
    file = tmp_path / "a.txt"
    file.write_text("hello")

    await RAGFlowClient().upload_document("ds1", str(file))
    assert len(captured.requests) == 1


@pytest.mark.asyncio
async def test_chat_sends_document_ids_filter(install_transport):
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"total": 0, "chunks": [], "doc_aggs": []}})

    captured = install_transport(handler)
    await RAGFlowClient().chat("ds1", "query", doc_ids=["doc-1", "doc-2"])

    import json as _json

    body = _json.loads(captured.requests[0].read().decode())
    assert body["dataset_ids"] == ["ds1"]
    assert body["document_ids"] == ["doc-1", "doc-2"]
    assert "doc_ids" not in body


def test_to_doc_status_maps_ragflow_run_values():
    assert to_doc_status("UNSTART") == "pending"
    assert to_doc_status("RUNNING") == "processing"
    assert to_doc_status("DONE") == "done"
    assert to_doc_status("FAIL") == "failed"
    assert to_doc_status("CANCEL") == "pending"
    assert to_doc_status(None) == "pending"


def test_build_parser_config_uses_upstream_keys():
    parser_id, parser_config = DocumentService._build_parser_config({"chunk_method": "report", "chunk_token_num": 512, "ocr_enabled": True})
    assert parser_id == "manual"
    assert parser_config == {"chunk_token_num": 512, "layout_recognize": "DeepDOC"}

    assert DocumentService._build_parser_config(None) == (None, None)
