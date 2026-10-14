"""tlt 检索知识库/原文入库 IO 回归（B1/B2/B3/C2）——容器真库跑。"""

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.extensions.database import get_session_factory, init_engine


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
