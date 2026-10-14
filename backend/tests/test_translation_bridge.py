"""RAGFlow bridge tests (T6) — fake client/storage, no real RAGFlow needed.

IO 流程测试在容器内跑（任务行落库断言）；markdown 构造为纯函数。
"""

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask
from app.extensions.translation.ragflow_bridge import (
    _zh_filename,
    build_markdown,
    index_translation,
)


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


def _task_like(sha: str = "a" * 64) -> TranslationTask:
    return TranslationTask(
        kb_id=uuid.uuid4(),
        doc_sha=sha,
        source_uri="/data/annual-report-2025.docx",
        source_lang="fr",
        state="indexed",
    )


class TestBuildMarkdown:
    def test_lineage_header_present(self):
        md = build_markdown(_task_like(), [])
        assert "tlt:translated-document" in md
        assert "source_sha256: " + "a" * 64 in md
        assert "source_lang: fr" in md

    def test_blocks_rendered(self):
        task = _task_like()
        zh_blocks = [
            {"id": "b0001", "type": "heading", "text": "经营概况", "meta": {}},
            {"id": "b0002", "type": "paragraph", "text": "产量增长。", "meta": {}},
            {"id": "b0003", "type": "table", "text": "年份\t产量", "meta": {"cells": [["年份", "产量"], ["2024", "3200"]]}},
        ]
        md = build_markdown(task, zh_blocks)
        assert "## 经营概况" in md
        assert "产量增长。" in md
        assert "| 年份 | 产量 |" in md
        assert "| 2024 | 3200 |" in md

    def test_zh_filename_encodes_lineage(self):
        name = _zh_filename(_task_like(sha="abcdef1234" + "0" * 54))
        assert name == "annual-report-2025.zh.abcdef12.md"


class FakeClient:
    def __init__(self, existing_doc_id: str | None = None):
        self.existing = existing_doc_id
        self.uploads: list[dict] = []
        self.metadata_calls: list[dict] = []
        self.parse_calls: list[str] = []

    async def list_documents(self, dataset_id, metadata_condition=None, **kw):
        if self.existing:
            return {"data": {"docs": [{"id": self.existing}]}}
        return {"data": {"docs": []}}

    async def get_dataset(self, dataset_id: str) -> dict:
        return {"code": 0, "data": {"id": dataset_id}}

    async def upload_document(self, dataset_id, file_path, file_name=None, parser_id=None, parser_config=None):
        self.uploads.append({"file_name": file_name, "parser_id": parser_id})
        return {"data": {"id": "rf-doc-123"}}

    async def update_document_metadata(self, dataset_id, document_id, metadata):
        self.metadata_calls.append({"document_id": document_id, **metadata})

    async def parse_document(self, dataset_id, document_id):
        self.parse_calls.append(document_id)


class FakeStorage:
    def __init__(self):
        self.uploads: list[dict] = []

    async def upload_local_file(self, local_path, owner_id, kb_id, filename, content_type=None):
        self.uploads.append({"filename": filename, "owner_id": owner_id, "kb_id": kb_id})
        return SimpleNamespace(uri=f"s3://tlt-bucket/{filename}", bucket="tlt-bucket", key=filename)


class _HealingFakeClient(FakeClient):
    """dataset 缺失场景的 fake：探活返回不存在，create 返回新 id。"""

    def __init__(self, new_dataset_id: str = "ds-healed"):
        super().__init__()
        self._new_dataset_id = new_dataset_id
        self.created_with: dict | None = None

    async def get_dataset(self, dataset_id: str) -> dict:
        return {"code": 102, "message": "Can't find the dataset"}

    async def list_available_embedding_models(self) -> list[str]:
        return ["bge-m3"]

    async def create_dataset(self, **kw) -> dict:
        self.created_with = kw
        return {"data": {"id": self._new_dataset_id}}


@pytest.mark.asyncio(loop_scope="session")
async def test_index_translation_happy_path(_engine, tmp_path):
    """上传→元数据→解析→交付物落账，parser 走 SC-1 映射。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        kb = KnowledgeBase(
            name=f"tlt-bridge-{uuid.uuid4().hex[:8]}",
            owner_id=owner,
            kb_type="ragflow",
            ragflow_dataset_id="ds-001",
            chunk_method="naive",
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        task = TranslationTask(
            kb_id=kb.id,
            doc_sha="b" * 64,
            source_uri="/data/report.docx",
            source_lang="fr",
            state="indexed",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id, kb_id = task.id, kb.id
        try:
            zh_blocks = [{"id": "b0001", "type": "paragraph", "text": "译文内容", "meta": {}}]
            client = FakeClient()
            storage = FakeStorage()
            await index_translation(task, zh_blocks, [], client=client, storage=storage)
            # SC-1: parser 经映射表（naive→naive）
            assert client.uploads and client.uploads[0]["parser_id"] == "naive"
            assert client.uploads[0]["file_name"].startswith("report.zh.")
            assert client.metadata_calls[0]["tlt_task_id"] == str(task_id)
            assert client.parse_calls == ["rf-doc-123"]
            await db.refresh(task)
            assert task.deliverable_uri == "s3://tlt-bucket/report.zh." + "b" * 8 + ".md"
            assert task.ragflow_zh_doc_id == "rf-doc-123"
        finally:
            await _cleanup(db, kb_id)


@pytest.mark.asyncio(loop_scope="session")
async def test_index_translation_idempotent_rerun(_engine, tmp_path):
    """重跑（退避重试场景）：tlt_task_id 元数据命中 → 不重复上传，仍补解析与交付账。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(
            name=f"tlt-bridge-{uuid.uuid4().hex[:8]}",
            owner_id=owner,
            kb_type="ragflow",
            ragflow_dataset_id="ds-002",
            chunk_method="naive",
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        task = TranslationTask(
            kb_id=kb.id,
            doc_sha="c" * 64,
            source_uri="/data/doc.docx",
            source_lang="en",
            state="indexed",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        kb_id = kb.id
        try:
            client = FakeClient(existing_doc_id="rf-existing")
            storage = FakeStorage()
            await index_translation(task, [{"id": "b0001", "type": "paragraph", "text": "x", "meta": {}}], [], client=client, storage=storage)
            assert client.uploads == []  # 不重复建文档
            assert client.parse_calls == ["rf-existing"]
            await db.refresh(task)
            assert task.ragflow_zh_doc_id == "rf-existing"
        finally:
            await _cleanup(db, kb_id)


@pytest.mark.asyncio(loop_scope="session")
async def test_index_translation_self_heals_missing_dataset(_engine, tmp_path):
    """C1: KB 无 ragflow_dataset_id → ensure_dataset 自动重建并回写落库（原硬报错已废除）。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(
            name=f"tlt-bridge-{uuid.uuid4().hex[:8]}",
            owner_id=owner,
            kb_type="ragflow",
            embedding_model="bge-m3",
            chunk_method="naive",
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        task = TranslationTask(kb_id=kb.id, doc_sha="d" * 64, source_uri="/data/x.docx", source_lang="en", state="indexed")
        db.add(task)
        await db.commit()
        await db.refresh(task)
        kb_id = kb.id
        try:
            client = _HealingFakeClient(new_dataset_id="ds-healed")
            await index_translation(task, [{"id": "b0001", "type": "paragraph", "text": "x", "meta": {}}], [], client=client, storage=FakeStorage())
            assert client.created_with["name"] == kb.name
            await db.refresh(kb)
            assert kb.ragflow_dataset_id == "ds-healed"  # 回写落库
        finally:
            await _cleanup(db, kb_id)


async def _cleanup(db, kb_id):
    await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_id))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()


class _FakeClientForEnsure:
    """ensure_dataset 的最小 fake：可控 dataset 是否存在/创建结果。"""

    def __init__(self, exists: bool, new_id: str = "new-ds-1"):
        self._exists = exists
        self._new_id = new_id
        self.created_with: dict | None = None

    async def get_dataset(self, dataset_id: str) -> dict:
        if not self._exists:
            return {"code": 102, "message": "Can't find the dataset"}
        return {"code": 0, "data": {"id": dataset_id}}

    async def list_available_embedding_models(self) -> list[str]:
        return ["bge-m3"]

    async def create_dataset(self, **kw) -> dict:
        self.created_with = kw
        return {"data": {"id": self._new_id}}


class TestDatasetEnsure:
    def _kb(self, dataset_id: str | None) -> KnowledgeBase:
        return KnowledgeBase(
            name="tlt-ensure-kb",
            owner_id=uuid.uuid4(),
            kb_type="ragflow",
            embedding_model="bge-m3",
            chunk_method="naive",
            ragflow_dataset_id=dataset_id,
        )

    @pytest.mark.asyncio
    async def test_ready_dataset_passthrough(self):
        from app.extensions.translation.ragflow_bridge import ensure_dataset

        client = _FakeClientForEnsure(exists=True)
        kb = self._kb("ds-live")
        assert await ensure_dataset(kb, client=client) == "ds-live"
        assert client.created_with is None  # 未触发重建

    @pytest.mark.asyncio
    async def test_dangling_dataset_rebuilt_and_written_back(self):
        from app.extensions.translation.ragflow_bridge import ensure_dataset

        client = _FakeClientForEnsure(exists=False, new_id="ds-new")
        kb = self._kb("ds-dead")
        assert await ensure_dataset(kb, client=client) == "ds-new"
        assert kb.ragflow_dataset_id == "ds-new"  # 回写
        assert client.created_with["name"] == "tlt-ensure-kb"
        assert client.created_with["embedding_model"] == "bge-m3"

    @pytest.mark.asyncio
    async def test_missing_dataset_id_creates_one(self):
        from app.extensions.translation.ragflow_bridge import ensure_dataset

        client = _FakeClientForEnsure(exists=False, new_id="ds-fresh")
        kb = self._kb(None)
        assert await ensure_dataset(kb, client=client) == "ds-fresh"

    @pytest.mark.asyncio
    async def test_embed_model_autoselected_when_kb_has_none(self):
        from app.extensions.translation.ragflow_bridge import ensure_dataset

        client = _FakeClientForEnsure(exists=False, new_id="ds-auto")
        kb = self._kb("ds-dead")
        kb.embedding_model = None
        await ensure_dataset(kb, client=client)
        assert client.created_with["embedding_model"] == "bge-m3"


class _FakeClientForOriginal:
    """index_original 的最小 fake。"""

    def __init__(self, existing_docs: list[dict] | None = None):
        self._existing = existing_docs or []
        self.uploaded: list[tuple[str, str]] = []
        self.metadatas: list[dict] = []

    async def list_documents(self, dataset_id: str, metadata_condition: dict | None = None, **kw) -> dict:
        name = metadata_condition["conditions"][0]["value"]
        docs = [d for d in self._existing if d.get("tlt_source_sha256") == name]
        return {"data": {"docs": [{"id": d["id"]} for d in docs]}}

    async def upload_document(self, dataset_id: str, file_path: str, file_name: str = None, parser_id: str = None, **kw) -> dict:
        self.uploaded.append((file_name, parser_id or ""))
        return {"data": {"id": f"doc-{len(self.uploaded)}"}}

    async def update_document_metadata(self, dataset_id: str, doc_id: str, metadata: dict) -> dict:
        self.metadatas.append(metadata)
        return {}

    async def parse_document(self, dataset_id: str, doc_id: str) -> dict:
        self.parsed: list[str] = getattr(self, "parsed", [])
        self.parsed.append(doc_id)
        return {}

    async def get_dataset(self, dataset_id: str) -> dict:
        return {"code": 0, "data": {"id": dataset_id}}


class TestIndexOriginal:
    def _task(self) -> TranslationTask:
        return TranslationTask(
            kb_id=uuid.uuid4(),
            doc_sha="b" * 64,
            source_uri="/data/report.docx",
            source_lang="mixed",
            state="stored",
        )

    @pytest.mark.asyncio
    async def test_uploads_original_with_sha_metadata(self, tmp_path):
        from app.extensions.translation.ragflow_bridge import index_original

        dest = tmp_path / "report.docx"
        dest.write_bytes(b"PK\x03\x04stub")
        client = _FakeClientForOriginal()
        kb = KnowledgeBase(id=uuid.uuid4(), name="kb", owner_id=uuid.uuid4(), kb_type="ragflow", embedding_model="bge-m3", chunk_method="naive", ragflow_dataset_id="ds-1")
        task = self._task()
        doc_id = await index_original(task, dest, kb=kb, client=client)
        assert doc_id == "doc-1"
        assert client.uploaded[0][0] == "report.docx"
        assert client.metadatas[0] == {"tlt_source_sha256": "b" * 64, "tlt_source_lang": "mixed"}
        assert client.parsed == ["doc-1"]  # C-1: 原文必须触发 parse，否则永不被检索

    @pytest.mark.asyncio
    async def test_sha_idempotent_skip(self, tmp_path):
        from app.extensions.translation.ragflow_bridge import index_original

        dest = tmp_path / "report.docx"
        dest.write_bytes(b"PK\x03\x04stub")
        client = _FakeClientForOriginal(existing_docs=[{"id": "doc-exists", "tlt_source_sha256": "b" * 64}])
        kb = KnowledgeBase(id=uuid.uuid4(), name="kb", owner_id=uuid.uuid4(), kb_type="ragflow", embedding_model="bge-m3", chunk_method="naive", ragflow_dataset_id="ds-1")
        doc_id = await index_original(self._task(), dest, kb=kb, client=client)
        assert doc_id == "doc-exists"
        assert client.uploaded == []  # 未重复上传
