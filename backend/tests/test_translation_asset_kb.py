"""tlt 检索知识库/原文入库 IO 回归（B1/B2/C2 + rag-kbs 多库配置）——容器真库跑。"""

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy import update as sql_update
from test_translation_upload_originals import _FakeUploadClient  # 复用 B1 上传测试的 upload fake（get_dataset/list_documents/upload_document/update_document_metadata）

import app.extensions.translation.routers as routers
from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


@pytest.mark.asyncio(loop_scope="session")
async def test_ragflow_source_doc_id_column_exists(_engine):
    """B1 前置：migrate_db 后 tlt_translation_tasks 具备 ragflow_source_doc_id 列。"""
    async with get_session_factory()() as db:
        rows = (await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='tlt_translation_tasks'"))).scalars().all()
        assert "ragflow_source_doc_id" in rows


@pytest.mark.asyncio(loop_scope="session")
async def test_translation_enabled_coexists(_engine):
    """C2 拆除回归：多库可同时加入翻译体系，update_kb 互不干扰。"""
    from app.extensions.knowledge.service import KnowledgeBaseService
    from app.extensions.schemas import KnowledgeBaseUpdate

    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb_a = KnowledgeBase(name=f"kb-mut-a-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", translation_enabled=True)
        db.add(kb_a)
        await db.commit()
        try:
            kb_b = KnowledgeBase(name=f"kb-mut-b-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow")
            db.add(kb_b)
            await db.commit()
            await KnowledgeBaseService.update_kb(db, kb_b, KnowledgeBaseUpdate(translation_enabled=True))
            await db.refresh(kb_a)
            assert kb_b.translation_enabled is True
            assert kb_a.translation_enabled is True  # 不再互斥
        finally:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_([kb_a.id, kb_b.id])))
            await db.commit()


class _RagKbClient:
    """rag-kbs 端点 fake：create/get_dataset/update 全 capture。"""

    created: dict | None = None
    updated: dict | None = None
    dataset: dict = {"parser_id": "laws", "language": "Chinese", "permission": "team", "parser_config": {"chunk_token_num": 256}, "pagerank": 3, "embedding_model": "bge-m3"}

    async def create_dataset(self, **kw) -> dict:
        type(self).created = kw
        return {"data": {"id": f"ds-new-{uuid.uuid4().hex[:6]}"}}

    async def update_dataset(self, dataset_id: str, **kw) -> dict:
        type(self).updated = {"dataset_id": dataset_id, **kw}
        return {"code": 0}

    async def get_dataset(self, dataset_id: str) -> dict:
        return {"code": 0, "data": dict(type(self).dataset, id=dataset_id)}

    async def list_available_embedding_models(self) -> list[str]:
        return ["bge-m3", "bge-large"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_rag_kb_full_params(_engine, monkeypatch):
    """POST /rag-kbs：RAGFlow create 收全参（不含 language）；language/pagerank 走 create 后 update。"""
    from app.extensions.translation.routers import create_rag_kb

    monkeypatch.setattr(routers, "RAGFlowClient", _RagKbClient)
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        body = routers.RagKbCreate(
            name=f"新建矿压库-{uuid.uuid4().hex[:4]}",
            description="test",
            language="Chinese",
            permission="team",
            embedding_model="bge-m3",
            chunk_method="laws",
            parser_config={"chunk_token_num": 256},
            pagerank=3,
        )
        try:
            resp = await create_rag_kb(body, SimpleNamespace(id=owner), db=db)
            assert resp["ragflow_dataset_id"].startswith("ds-new-")
            assert _RagKbClient.created["permission"] == "team"
            assert _RagKbClient.created["chunk_method"] == "laws"
            assert "language" not in _RagKbClient.created  # create 不收 language
            assert _RagKbClient.updated["language"] == "Chinese"
            assert _RagKbClient.updated["pagerank"] == 3
            kb = await db.get(KnowledgeBase, uuid.UUID(resp["id"]))
            assert kb.translation_enabled is True and kb.chunk_method == "laws"
        finally:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(resp["id"])))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_rag_kbs_aggregates(_engine, monkeypatch):
    """GET /rag-kbs：enabled 库 + RAGFlow 配置回读 + doc/pending 聚合。"""
    from app.extensions.translation.routers import list_rag_kbs

    monkeypatch.setattr(routers, "RAGFlowClient", _RagKbClient)
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(name=f"kb-lst-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-live", translation_enabled=True)
        db.add(kb)
        await db.flush()
        db.add(TranslationTask(kb_id=kb.id, doc_sha="1" * 64, source_uri="/data/x.docx", source_lang="en", state="pending"))
        db.add(TranslationTask(kb_id=kb.id, doc_sha="2" * 64, source_uri="/data/y.docx", source_lang="en", state="delivered"))
        await db.commit()
        try:
            resp = await list_rag_kbs(current_user=SimpleNamespace(id=owner), db=db)
            mine = [i for i in resp["items"] if i["id"] == str(kb.id)]
            assert mine, "enabled 库必须在列"
            row = mine[0]
            assert row["ragflow_linked"] is True
            assert row["pending_count"] >= 1
            assert row["parser_config"] == {"chunk_token_num": 256}  # RAGFlow 回读
            assert row["permission"] == "team"
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb.id))
            await db.execute(sql_update(KnowledgeBase).where(KnowledgeBase.id == kb.id).values(translation_enabled=False))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))  # 卫生：不留 kb-lst-* 残行
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_update_and_enable_rag_kb(_engine, monkeypatch):
    """PUT 配置走 update_dataset；enabled 开关无互斥（两库共存）。"""
    from app.extensions.translation.routers import set_rag_kb_enabled, update_rag_kb

    monkeypatch.setattr(routers, "RAGFlowClient", _RagKbClient)
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb1 = KnowledgeBase(name=f"kb-up1-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-up1", translation_enabled=True)
        kb2 = KnowledgeBase(name=f"kb-up2-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-up2", translation_enabled=False)
        db.add_all([kb1, kb2])
        await db.commit()
        try:
            await update_rag_kb(kb1.id, routers.RagKbUpdate(chunk_method="book", pagerank=5), SimpleNamespace(id=owner), db=db)
            assert _RagKbClient.updated["dataset_id"] == "ds-up1"
            assert _RagKbClient.updated["chunk_method"] == "book"
            await db.refresh(kb1)
            assert kb1.chunk_method == "book"  # PG 摘要同步
            await set_rag_kb_enabled(kb2.id, routers.RagKbEnabled(enabled=True), SimpleNamespace(id=owner), db=db)
            await db.refresh(kb1)
            await db.refresh(kb2)
            assert kb1.translation_enabled is True and kb2.translation_enabled is True  # 无互斥
        finally:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_([kb1.id, kb2.id])))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_backfill_indexes_missing_source(_engine, monkeypatch, tmp_path):
    """B2：ragflow_source_doc_id 为 NULL 的任务回填后落列。"""
    from app.extensions.translation.routers import backfill_sources

    monkeypatch.setattr(routers, "RAGFlowClient", _FakeUploadClient)
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(name=f"kb-bf-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow", ragflow_dataset_id="ds-bf", translation_enabled=True)
        db.add(kb)
        await db.commit()
        src = tmp_path / "bf.docx"
        src.write_bytes(b"PK\x03\x04stub")
        task = TranslationTask(kb_id=kb.id, doc_sha="c" * 64, source_uri=str(src), source_lang="en", state="stored")
        db.add(task)
        await db.commit()
        try:
            r1 = await backfill_sources(current_user=SimpleNamespace(id=owner), db=db)
            mine = [r for r in r1["results"] if r["task_id"] == str(task.id)]
            assert mine and mine[0]["action"] in ("source_indexed", "source_skipped")
            await db.refresh(task)
            assert task.ragflow_source_doc_id is not None
        finally:
            # I-1: 端点全表扫描会把 fake id 写到真实残行上——finally 精确回滚（该 id 仅 fake 会产生）
            await db.execute(text("UPDATE tlt_translation_tasks SET ragflow_source_doc_id=NULL WHERE ragflow_source_doc_id='doc-original-1'"))
            await db.execute(delete(TranslationTask).where(TranslationTask.id == task.id))
            await db.execute(sql_update(KnowledgeBase).where(KnowledgeBase.id == kb.id).values(translation_enabled=False))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()
