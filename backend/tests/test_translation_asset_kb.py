"""tlt 检索知识库/原文入库 IO 回归（B1/B2/B3/C2）——容器真库跑。"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

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
