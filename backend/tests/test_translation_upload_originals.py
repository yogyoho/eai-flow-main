"""upload_assets 原文即刻入库（B1）——失败降级不挡上传。容器真库跑。

夹具残留防护：upload_assets 缺省时拣「恰一 translation_enabled KB」（多库改 400 引导选择），
任务可能落在本测试自建的 KB 之外——清理一律按夹具内容 sha（测试专用 stub，无业务碰撞）；
red run 在 monkeypatch 处中断会漏 try/finally，故 setup 亦先清扫一轮自愈。
"""

import hashlib
import io
import uuid
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select

import app.extensions.translation.routers as routers
from app.extensions.config import get_extensions_config
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
            result = await routers.upload_assets(files=[f], folder_id=None, kb_id=None, current_user=SimpleNamespace(id=owner), db=db)
            assert result["count"] == 1
            assert result["items"][0]["reused"] is False
            task = await db.get(TranslationTask, uuid.UUID(result["items"][0]["task_id"]))
            assert task.ragflow_source_doc_id == "doc-original-1"
        finally:
            with suppress(Exception):
                await _cleanup_stale(db)


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_duplicate_reuses_existing_without_orphan_file(_engine, monkeypatch):
    """同 KB 同 sha 重复上传：复用现有任务、返回 existing_file，且不落盘孤儿文件。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        await _cleanup_stale(db)
        monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
        kb = KnowledgeBase(name=f"kb-b1dup-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-b1", translation_enabled=True)
        db.add(kb)
        await db.commit()
        dup_name = f"t1-dup-{uuid.uuid4().hex[:8]}.docx"
        try:
            f1 = UploadFile(filename="t1.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            r1 = await routers.upload_assets(files=[f1], folder_id=None, kb_id=kb.id, current_user=SimpleNamespace(id=owner), db=db)
            assert r1["items"][0]["reused"] is False

            f2 = UploadFile(filename=dup_name, file=io.BytesIO(b"PK\x03\x04stub-content"))
            r2 = await routers.upload_assets(files=[f2], folder_id=None, kb_id=kb.id, current_user=SimpleNamespace(id=owner), db=db)
            item = r2["items"][0]
            assert item["reused"] is True
            assert item["task_id"] == r1["items"][0]["task_id"]
            assert item["existing_file"] == "t1.docx"

            storage = Path(get_extensions_config().storage.base_path) / "translation"
            assert not list(storage.rglob(dup_name)), "重复上传不应落盘孤儿文件"
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_after_archive_creates_next_version(_engine, monkeypatch):
    """归档后重传同内容：应新建 task_version=2，而不是撞唯一键 500。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        await _cleanup_stale(db)
        monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
        kb = KnowledgeBase(name=f"kb-b1ver-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-b1", translation_enabled=True)
        db.add(kb)
        await db.commit()
        try:
            f1 = UploadFile(filename="v1.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            r1 = await routers.upload_assets(files=[f1], folder_id=None, kb_id=kb.id, current_user=SimpleNamespace(id=owner), db=db)
            t1 = await db.get(TranslationTask, uuid.UUID(r1["items"][0]["task_id"]))
            assert t1 is not None and t1.task_version == 1
            t1.state = "archived"
            await db.commit()

            f2 = UploadFile(filename="v2.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            r2 = await routers.upload_assets(files=[f2], folder_id=None, kb_id=kb.id, current_user=SimpleNamespace(id=owner), db=db)
            item = r2["items"][0]
            assert item["reused"] is False
            t2 = await db.get(TranslationTask, uuid.UUID(item["task_id"]))
            assert t2 is not None and t2.id != t1.id
            assert t2.task_version == 2
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


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
            result = await routers.upload_assets(files=[f], folder_id=None, kb_id=None, current_user=SimpleNamespace(id=owner), db=db)
            assert result["count"] == 1  # 上传未被打断
            task = await db.get(TranslationTask, uuid.UUID(result["items"][0]["task_id"]))
            assert result["items"][0]["reused"] is False  # 同 sha 残留已在 setup 清扫
            assert task.ragflow_source_doc_id is None
        finally:
            with suppress(Exception):
                await _cleanup_stale(db)


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_multiple_kbs_requires_choice(_engine, monkeypatch):
    """缺省 + 多 enabled 库 → 400 引导选择（不再静默取第一个）。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb1 = KnowledgeBase(name=f"kb-rt1-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-x", translation_enabled=True)
        kb2 = KnowledgeBase(name=f"kb-rt2-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-y", translation_enabled=True)
        db.add_all([kb1, kb2])
        await db.commit()
        monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
        try:
            f = UploadFile(filename="t3.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            with pytest.raises(HTTPException) as ei:
                await routers.upload_assets(files=[f], folder_id=None, kb_id=None,
                                            current_user=SimpleNamespace(id=owner), db=db)
            assert "选择目标知识库" in ei.value.detail
        finally:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_([kb1.id, kb2.id])))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_upload_explicit_kb_id_routes(_engine, monkeypatch):
    """显式 kb_id：非 enabled 库 400；enabled 库正常建任务。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb_off = KnowledgeBase(name=f"kb-rt3-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-off", translation_enabled=False)
        kb_on = KnowledgeBase(name=f"kb-rt4-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-on", translation_enabled=True)
        db.add_all([kb_off, kb_on])
        await db.commit()
        monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
        try:
            f1 = UploadFile(filename="t4.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            with pytest.raises(HTTPException) as ei:
                await routers.upload_assets(files=[f1], folder_id=None, kb_id=kb_off.id,
                                            current_user=SimpleNamespace(id=owner), db=db)
            assert "未加入翻译体系" in ei.value.detail
            f2 = UploadFile(filename="t5.docx", file=io.BytesIO(b"PK\x03\x04stub-content"))
            result = await routers.upload_assets(files=[f2], folder_id=None, kb_id=kb_on.id,
                                                 current_user=SimpleNamespace(id=owner), db=db)
            task = await db.get(TranslationTask, uuid.UUID(result["items"][0]["task_id"]))
            assert task is not None and task.ragflow_source_doc_id == "doc-original-1"
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_on.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_([kb_off.id, kb_on.id])))
            await db.commit()
