"""Translation MCP server tests (T5) — handler-level, in-container DB."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


def _docx(path, text="Quarterly output reached 42,000 tonnes per the report."):
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(path))
    return str(path)


async def _mk_kb(db, enabled: bool):
    from sqlalchemy import select as _select

    owner = (await db.execute(_select(User.id).limit(1))).scalar()
    if owner is None:
        pytest.skip("no users row")
    kb = KnowledgeBase(
        name=f"tlt-mcp-{uuid.uuid4().hex[:8]}",
        owner_id=owner,
        kb_type="ragflow",
        translation_enabled=enabled,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def _cleanup(db, kb_id):
    await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_id))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_translate_document_disabled_kb_rejected(_engine, tmp_path):
    from app.extensions.translation.mcp import _handle_translate

    p = _docx(tmp_path / "a.docx")
    async with get_session_factory()() as db:
        kb = await _mk_kb(db, enabled=False)
        kb_id = str(kb.id)
        try:
            out = await _handle_translate({"kb_id": kb_id, "file_path": p})
            assert "translation is not enabled" in out[0].text
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_translate_document_enqueues_and_status_reports(_engine, tmp_path):
    from app.extensions.translation.mcp import _handle_status, _handle_translate

    p = _docx(tmp_path / "b.docx")
    async with get_session_factory()() as db:
        kb = await _mk_kb(db, enabled=True)
        kb_id = str(kb.id)
        try:
            out = await _handle_translate({"kb_id": kb_id, "file_path": p})
            import json

            payload = json.loads(out[0].text)
            assert payload.get("error") is None
            assert payload["state"] == "pending"
            assert payload["source_lang"] == "en"

            # 幂等：同文件重复提交 → 复用同一任务
            out2 = await _handle_translate({"kb_id": kb_id, "file_path": p})
            payload2 = json.loads(out2[0].text)
            assert payload2["task_id"] == payload["task_id"]

            # status：单查
            st = json.loads((await _handle_status({"task_id": payload["task_id"]}))[0].text)
            assert st["task_id"] == payload["task_id"]
            # status：按 kb 列表
            lst = json.loads((await _handle_status({"kb_id": kb_id}))[0].text)
            assert any(i["task_id"] == payload["task_id"] for i in lst["items"])
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_status_unknown_task_is_clean_error(_engine):
    from app.extensions.translation.mcp import _handle_status

    st = await _handle_status({"task_id": str(uuid.uuid4())})
    assert "not found" in st[0].text
