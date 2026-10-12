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
async def test_index_translation_requires_dataset(_engine, tmp_path):
    """KB 无 ragflow_dataset_id → 明确报错（worker 落 failed，不静默假交付）。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(name=f"tlt-bridge-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow")
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        task = TranslationTask(kb_id=kb.id, doc_sha="d" * 64, source_uri="/data/x.docx", source_lang="en", state="indexed")
        db.add(task)
        await db.commit()
        await db.refresh(task)
        kb_id = kb.id
        try:
            with pytest.raises(RuntimeError, match="ragflow_dataset_id"):
                await index_translation(task, [], [], client=FakeClient(), storage=FakeStorage())
        finally:
            await _cleanup(db, kb_id)


async def _cleanup(db, kb_id):
    await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_id))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()
