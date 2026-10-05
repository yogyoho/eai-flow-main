"""Regression tests for bug-3307.

``create_kb`` silently degrades to a local-only KB (``ragflow_dataset_id IS NULL``)
when RAGFlow is unavailable, and no relink path existed — the orphans could never
self-heal (5 KBs stranded 2026-05~08, RAGFlow only became stable 2026-09-02).

``KnowledgeBaseService.relink_ragflow`` is the repair channel: idempotent dataset
creation + id write-back + best-effort re-upload of documents that never reached
RAGFlow.

Pure unit tests: the AsyncSession is mocked, RAGFlow is a stub (mirrors
test_kb_dept_fallback.py).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.knowledge.service import KnowledgeBaseService
from app.extensions.models import Document, KnowledgeBase


def _mock_db(docs=None):
    """AsyncSession mock; execute().scalars().all() yields the given documents."""
    db = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = docs or []
    result.scalars.return_value = scalars
    db.execute.return_value = result
    return db


def _stub_config(monkeypatch, base_path="."):
    monkeypatch.setattr(
        "app.extensions.knowledge.service.get_extensions_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(base_path=base_path)),
    )


def _stub_client(monkeypatch, client):
    monkeypatch.setattr(KnowledgeBaseService, "_get_ragflow_client", staticmethod(lambda: client))


def _client(*, available=True, dataset_id="ds-new", embedding_models=("embed-x",)):
    return SimpleNamespace(
        is_available=AsyncMock(return_value=available),
        list_available_embedding_models=AsyncMock(return_value=list(embedding_models)),
        create_dataset=AsyncMock(return_value={"data": {"id": dataset_id}}),
        upload_document=AsyncMock(return_value={"data": {"id": "rf-doc-1"}}),
        parse_document=AsyncMock(return_value={}),
    )


def _orphan_kb(**kwargs):
    # 显式 id: SQLAlchemy 列默认值要 flush 才生成, 单元测试不落库
    defaults = dict(id=uuid.uuid4(), name="消防报告样例库", owner_id=uuid.uuid4(), access_type="dept", kb_type="ragflow")
    defaults.update(kwargs)
    return KnowledgeBase(**defaults)


@pytest.mark.asyncio
async def test_relink_already_linked_never_recreates_dataset(monkeypatch, tmp_path):
    """已链接 KB 重跑 → 不重建 dataset, 但仍回填缺 ragflow_document_id 的漏网文档。"""
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch, base_path=str(tmp_path))
    kb = _orphan_kb(ragflow_dataset_id="ds-existing", chunk_method="naive")

    kb_dir = tmp_path / str(kb.id)
    kb_dir.mkdir()
    (kb_dir / "late.docx").write_bytes(b"late-bytes")
    late = Document(
        knowledge_base_id=kb.id,
        name="late.docx",
        file_path=str(kb_dir / "late.docx"),
        file_size=10,
        file_type="docx",
        status="success",
    )

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(docs=[late]), kb)

    assert result["status"] == "already_linked"
    assert result["ragflow_dataset_id"] == "ds-existing"
    client.create_dataset.assert_not_awaited()
    client.upload_document.assert_awaited_once_with(
        dataset_id="ds-existing",
        file_path=str(kb_dir / "late.docx"),
        file_name="late.docx",
        parser_id="naive",
        parser_config=None,
    )
    assert late.ragflow_document_id == "rf-doc-1"


@pytest.mark.asyncio
async def test_relink_without_client_reports_error(monkeypatch):
    _stub_client(monkeypatch, None)
    kb = _orphan_kb()

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(), kb)

    assert result["status"] == "error"
    assert kb.ragflow_dataset_id is None


@pytest.mark.asyncio
async def test_relink_when_ragflow_down_reports_error_without_linking(monkeypatch):
    """RAGFlow unavailable → explicit error, NULL id stays NULL (no silent residue)."""
    client = _client(available=False)
    _stub_client(monkeypatch, client)
    kb = _orphan_kb()

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(), kb)

    assert result["status"] == "error"
    assert "unavailable" in result["message"]
    client.create_dataset.assert_not_awaited()
    assert kb.ragflow_dataset_id is None


@pytest.mark.asyncio
async def test_relink_creates_dataset_and_writes_back_id(monkeypatch):
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch)
    kb = _orphan_kb()
    db = _mock_db()

    result = await KnowledgeBaseService.relink_ragflow(db, kb, include_documents=False)

    assert result["status"] == "linked"
    assert result["ragflow_dataset_id"] == "ds-new"
    assert kb.ragflow_dataset_id == "ds-new"
    assert kb.embedding_model == "embed-x"  # kb_type=ragflow → auto-selected
    client.create_dataset.assert_awaited_once_with(
        name="消防报告样例库",
        description="",
        embedding_model="embed-x",
        chunk_method=None,
        parser_config=None,
    )


@pytest.mark.asyncio
async def test_relink_reuploads_local_docs_and_marks_missing_skipped(monkeypatch, tmp_path):
    """Doc with an on-disk file → re-uploaded + parse triggered; missing file → skipped."""
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch, base_path=str(tmp_path))
    kb = _orphan_kb(chunk_method="naive")

    kb_dir = tmp_path / str(kb.id)
    kb_dir.mkdir()
    (kb_dir / "a.docx").write_bytes(b"docx-bytes")

    present = Document(
        knowledge_base_id=kb.id,
        name="a.docx",
        file_path=str(kb_dir / "a.docx"),
        file_size=10,
        file_type="docx",
        status="success",
    )
    missing = Document(
        knowledge_base_id=kb.id,
        name="gone.docx",
        file_path="data/users/xx/knowledge/kb/gone.docx",
        file_size=10,
        file_type="docx",
        status="success",
    )
    db = _mock_db(docs=[present, missing])

    result = await KnowledgeBaseService.relink_ragflow(db, kb)

    assert result["status"] == "linked"
    assert result["documents_uploaded"] == 1
    assert result["documents_skipped"] == 1
    assert result["documents_failed"] == []
    assert present.ragflow_document_id == "rf-doc-1"
    assert present.status == "uploading"
    assert missing.ragflow_document_id is None
    client.upload_document.assert_awaited_once()
    client.parse_document.assert_awaited_once_with("ds-new", "rf-doc-1")


@pytest.mark.asyncio
async def test_relink_counts_unsupported_file_type_as_failed(monkeypatch, tmp_path):
    """File type rejected by the parser → documents_failed, not a crash."""
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch, base_path=str(tmp_path))
    kb = _orphan_kb(chunk_method="naive")

    bad = Document(
        knowledge_base_id=kb.id,
        name="evil.exe",
        file_path=str(tmp_path / "evil.exe"),
        file_size=1,
        file_type="exe",
        status="success",
    )
    (tmp_path / "evil.exe").write_bytes(b"MZ")

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(docs=[bad]), kb)

    assert result["documents_uploaded"] == 0
    assert result["documents_failed"] == ["evil.exe"]
    client.upload_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_relink_maps_eai_report_chunk_method_to_ragflow_manual(monkeypatch):
    """bug-3307 根因: KB.chunk_method='report' 是 EAI 内部值, RAGFlow dataset 只认
    上游枚举 —— 必须走文档上传同源映射(report→manual), 否则建库 101 被拒后静默降级。"""
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch)
    kb = _orphan_kb(chunk_method="report")

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(), kb, include_documents=False)

    assert result["status"] == "linked"
    assert client.create_dataset.await_args.kwargs["chunk_method"] == "manual"


@pytest.mark.asyncio
async def test_relink_create_dataset_failure_returns_error_without_linking(monkeypatch):
    """建库被拒 → 显式 error(路由转 503), id 保持 NULL, 不留半链接状态。"""
    client = _client()
    client.create_dataset = AsyncMock(side_effect=RuntimeError("RAGFlow create_dataset failed (code=101): bad chunk_method"))
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch)
    kb = _orphan_kb(chunk_method="report")

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(), kb, include_documents=False)

    assert result["status"] == "error"
    assert "code=101" in result["message"]
    assert kb.ragflow_dataset_id is None


@pytest.mark.asyncio
async def test_relink_embedding_override_wins_and_persists(monkeypatch):
    """存量 embedding 模型在租户已失效(如 ZHIPU-AI 下线)→ 覆盖参数优先并回写 KB。"""
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch)
    kb = _orphan_kb(embedding_model="embedding-3@ZHIPU-AI")

    result = await KnowledgeBaseService.relink_ragflow(_mock_db(), kb, include_documents=False, embedding_model_override="bge-m3:latest@Ollama")

    assert result["status"] == "linked"
    assert kb.embedding_model == "bge-m3:latest@Ollama"
    assert client.create_dataset.await_args.kwargs["embedding_model"] == "bge-m3:latest@Ollama"


@pytest.mark.asyncio
async def test_relink_include_documents_false_never_touches_docs(monkeypatch):
    client = _client()
    _stub_client(monkeypatch, client)
    _stub_config(monkeypatch)
    kb = _orphan_kb()
    doc = Document(
        knowledge_base_id=kb.id,
        name="a.docx",
        file_path="whatever.docx",
        file_size=1,
        file_type="docx",
        status="success",
    )
    db = _mock_db(docs=[doc])

    result = await KnowledgeBaseService.relink_ragflow(db, kb, include_documents=False)

    assert result["documents_uploaded"] == 0
    client.upload_document.assert_not_awaited()
    assert doc.ragflow_document_id is None
