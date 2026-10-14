"""upload_assets 原文即刻入库（B1）——失败降级不挡上传。容器真库跑。

夹具残留防护：upload_assets 拣「第一个 translation_enabled KB」（created_at asc），
任务可能落在本测试自建的 KB 之外——清理一律按夹具内容 sha（测试专用 stub，无业务碰撞）；
red run 在 monkeypatch 处中断会漏 try/finally，故 setup 亦先清扫一轮自愈。
"""

import hashlib
import io
import uuid
from contextlib import suppress
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy import delete, select

import app.extensions.translation.routers as routers
from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask

_SHA = hashlib.sha256(b"PK\x03\x04stub-content").hexdigest()


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


async def _cleanup_stale(db) -> None:
    await db.execute(delete(TranslationTask).where(TranslationTask.doc_sha == _SHA))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.name.like("kb-b1-%")))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.name.like("kb-b1dead-%")))
    await db.commit()


class _FakeUploadClient:
    """dataset 就绪 + upload 成功的最小 fake。"""

    async def get_dataset(self, dataset_id: str) -> dict:
        return {"code": 0, "data": {"id": dataset_id}}

    async def list_documents(self, dataset_id: str, metadata_condition: dict | None = None, **kw) -> dict:
        return {"data": {"docs": []}}

    async def upload_document(self, dataset_id: str, file_path: str, file_name: str = None, **kw) -> dict:
        return {"data": {"id": "doc-original-1"}}

    async def update_document_metadata(self, dataset_id: str, doc_id: str, metadata: dict) -> dict:
        return {}

    async def parse_document(self, dataset_id: str, doc_id: str) -> dict:
        return {}


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_indexes_original_and_fails_open(_engine, monkeypatch):
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        await _cleanup_stale(db)
        monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
        kb = KnowledgeBase(name=f"kb-b1-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-b1", translation_enabled=True)
        db.add(kb)
        await db.commit()
        try:
            f = UploadFile(filename="t1.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            result = await routers.upload_assets(files=[f], folder_id=None, current_user=SimpleNamespace(id=owner), db=db)
            assert result["count"] == 1
            assert result["items"][0]["reused"] is False
            task = await db.get(TranslationTask, uuid.UUID(result["items"][0]["task_id"]))
            assert task.ragflow_source_doc_id == "doc-original-1"
        finally:
            with suppress(Exception):
                await _cleanup_stale(db)


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_survives_ragflow_outage(_engine, monkeypatch):
    """RAGFlow 全挂：任务照建，ragflow_source_doc_id 留 NULL（D2 失败不阻断）。"""

    class _DeadClient:
        async def get_dataset(self, dataset_id: str) -> dict:
            raise RuntimeError("ragflow down")

    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        await _cleanup_stale(db)
        monkeypatch.setattr(routers, "RAGFlowClient", _DeadClient)
        kb = KnowledgeBase(name=f"kb-b1dead-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-b1", translation_enabled=True)
        db.add(kb)
        await db.commit()
        try:
            f = UploadFile(filename="t2.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            result = await routers.upload_assets(files=[f], folder_id=None, current_user=SimpleNamespace(id=owner), db=db)
            assert result["count"] == 1  # 上传未被打断
            task = await db.get(TranslationTask, uuid.UUID(result["items"][0]["task_id"]))
            assert result["items"][0]["reused"] is False  # 同 sha 残留已在 setup 清扫
            assert task.ragflow_source_doc_id is None
        finally:
            with suppress(Exception):
                await _cleanup_stale(db)
