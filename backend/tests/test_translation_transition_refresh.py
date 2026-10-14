"""transition 端点 500 回归（MissingGreenlet）— commit 后序列化须 refresh。

根因：TranslationTask.updated_at 用 onupdate=func.now()（服务端生成），flush 后
该属性被 SQLAlchemy 标记过期；transition_task 在 commit 后直接
TaskOut.from_row(task) 读 t.updated_at → AsyncSession 同步懒加载 →
sqlalchemy.exc.MissingGreenlet。状态实际已落库（worker 会接单），但响应 500，
前端「再度翻译」表现为主流程失败。同 create_folder 的 commit+refresh 手法。
IO 测试在容器内跑（真库断言）。
"""

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import app.extensions.translation.routers as routers
from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask
from app.extensions.translation.routers import TransitionRequest, transition_task


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


@pytest.mark.asyncio(loop_scope="session")
async def test_transition_failed_to_pending_returns_serialized_task(_engine, monkeypatch):
    """failed → pending 人工重跑：commit 后响应序列化不再撞 MissingGreenlet。"""

    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = (await db.execute(select(User.id).limit(1))).scalar()
        if owner is None:
            pytest.skip("no users row")
        kb = KnowledgeBase(name=f"kb-transition-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow")
        db.add(kb)
        await db.flush()
        task = TranslationTask(
            kb_id=kb.id,
            doc_sha="f" * 64,
            source_uri="/data/transition-regression.docx",
            source_lang="en",
            state="failed",
            uncertainty=[],  # 第二层回归：worker 实写 list，TaskOut 曾误标 dict | None → pydantic 500
        )
        db.add(task)
        await db.commit()
        task_id, kb_id = task.id, kb.id
        try:
            resp = await transition_task(
                task_id, TransitionRequest(target="pending"), SimpleNamespace(id=owner), db
            )
            assert resp["state"] == "pending"
            # 修复点：服务端 onupdate 过期属性经 refresh 重载，序列化出非空时间戳
            assert resp["updated_at"] is not None
        finally:
            # 兜底清理：pending 先转 cancelled（worker 不接终态单），再删行
            row = await db.get(TranslationTask, task_id)
            if row is not None and row.state == "pending":
                row.state = "cancelled"
                await db.commit()
            await db.execute(delete(TranslationTask).where(TranslationTask.id == task_id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            await db.commit()
