"""tlt 检索知识库/原文入库 IO 回归（B1/B2/B3/C2）——容器真库跑。"""

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy import update as sql_update

import app.extensions.translation.routers as routers
from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User


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
async def test_translation_enabled_exclusive(_engine):
    """C2：置 B 为 translation_enabled 时，A 自动被关（全局至多一个）。"""
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
            await KnowledgeBaseService.update_kb(
                db, kb_b, KnowledgeBaseUpdate(translation_enabled=True)
            )
            await db.refresh(kb_a)
            assert kb_b.translation_enabled is True
            assert kb_a.translation_enabled is False  # 互斥生效
        finally:
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_([kb_a.id, kb_b.id])))
            await db.commit()


class _StatusClient:
    """dataset 探活 fake：exists 可切换。"""

    exists = True

    async def get_dataset(self, dataset_id: str) -> dict:
        if not self.exists:
            return {"code": 102, "message": "gone"}
        return {"code": 0, "data": {"id": dataset_id}}

    async def list_available_embedding_models(self) -> list[str]:
        return ["bge-m3"]

    async def create_dataset(self, **kw) -> dict:
        type(self).exists = True  # 建完即存在（对齐真实 RAGFlow）：initialize 修复后 re-probe 才可能 ready
        return {"data": {"id": f"ds-init-{uuid.uuid4().hex[:6]}"}}


@pytest.mark.asyncio(loop_scope="session")
async def test_asset_kb_status_three_states(_engine, monkeypatch):
    from app.extensions.translation.routers import asset_kb_status

    monkeypatch.setattr(routers, "RAGFlowClient", _StatusClient)
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        user = SimpleNamespace(id=owner)
        # unbound：无 translation_enabled 库
        await db.execute(sql_update(KnowledgeBase).values(translation_enabled=False))
        await db.commit()
        assert (await asset_kb_status(current_user=user, db=db))["state"] == "unbound"
        # dangling：库开着但 dataset 没了
        kb = KnowledgeBase(name=f"kb-st-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow",
                           ragflow_dataset_id="ds-gone", translation_enabled=True)
        db.add(kb)
        await db.commit()
        _StatusClient.exists = False
        st = await asset_kb_status(current_user=user, db=db)
        assert st["state"] == "dangling" and st["kb_name"] == kb.name
        # ready：dataset 探活通过 + 计数
        _StatusClient.exists = True
        st = await asset_kb_status(current_user=user, db=db)
        assert st["state"] == "ready" and st["source_count"] == 0 and st["zh_count"] == 0
        await db.execute(sql_update(KnowledgeBase).where(KnowledgeBase.id == kb.id).values(translation_enabled=False))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_asset_kb_initialize_dangling_repairs(_engine, monkeypatch):
    from app.extensions.translation.routers import asset_kb_initialize

    monkeypatch.setattr(routers, "RAGFlowClient", _StatusClient)
    _StatusClient.exists = False
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        kb = KnowledgeBase(name=f"kb-init-{uuid.uuid4().hex[:6]}", owner_id=owner, kb_type="ragflow",
                           ragflow_dataset_id="ds-gone", translation_enabled=True)
        db.add(kb)
        await db.commit()
        try:
            st = await asset_kb_initialize(current_user=SimpleNamespace(id=owner), db=db)
            assert st["state"] == "ready"
            await db.refresh(kb)
            assert kb.ragflow_dataset_id.startswith("ds-init-")  # 自愈回写落库
        finally:
            await db.execute(sql_update(KnowledgeBase).where(KnowledgeBase.id == kb.id).values(translation_enabled=False))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()
