"""delete_kb 子表级联回归（bug-1791807358242）— 扩展子表 FK 必须 ON DELETE CASCADE。

根因：KnowledgeBaseService.delete_kb 只先删 documents；tlt_translation_tasks /
scrap_drafts 的 FK 缺省 NO ACTION 且无人清理 → 删 KB 撞 IntegrityError 500
（tlt-bridge-* 测试残留删不掉即此因）。IO 测试在容器内跑（真库断言）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.extensions.database import get_session_factory, init_engine
from app.extensions.knowledge.service import KnowledgeBaseService
from app.extensions.models import KnowledgeBase, ScrapDraft, User
from app.extensions.translation.models import TranslationTask


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_kb_cascades_extension_children(_engine):
    """删 KB：翻译任务行与爬取草稿随库级联清除，不再撞子表 FK。"""
    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        kb = KnowledgeBase(name=f"kb-cascade-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow")
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        db.add_all(
            [
                TranslationTask(kb_id=kb.id, doc_sha="e" * 64, source_uri="/data/x.docx", source_lang="en", state="indexed"),
                ScrapDraft(
                    user_id=owner,
                    source_url="https://example.com/x",
                    schema_name="demo",
                    title="t",
                    knowledge_base_id=kb.id,
                ),
            ]
        )
        await db.commit()
        kb_id = kb.id
        try:
            await KnowledgeBaseService.delete_kb(db, kb)
            assert (await db.execute(select(TranslationTask.id).where(TranslationTask.kb_id == kb_id))).scalars().all() == []
            assert (await db.execute(select(ScrapDraft.id).where(ScrapDraft.knowledge_base_id == kb_id))).scalars().all() == []
            assert (await db.execute(select(KnowledgeBase.id).where(KnowledgeBase.id == kb_id))).scalar() is None
        finally:
            # 断言失败时的兜底清理（旧 NO ACTION 库需先删子表再删库）
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_id))
            await db.execute(delete(ScrapDraft).where(ScrapDraft.knowledge_base_id == kb_id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            await db.commit()
