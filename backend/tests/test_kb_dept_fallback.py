"""Regression tests for bug-1134.

A dept-visible KB created/updated without an explicit ``allowed_depts`` must be
backfilled from the owner's ``user_departments``. Otherwise the datascope rule
``allowed_depts OVERLAP $identity.dept_ids`` evaluates against NULL and, because
PG treats ``NULL && array`` as NULL (falsy), the KB is invisible to every
non-owner same-department user.

Pure unit tests: the AsyncSession is mocked, RAGFlow and storage are stubbed.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.knowledge.service import KnowledgeBaseService
from app.extensions.models import KnowledgeBase
from app.extensions.schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate


def _stub_config():
    """storage.type != 'local' and retain_local_copy False → skip mkdir in create_kb."""
    return SimpleNamespace(storage=SimpleNamespace(type="minio", retain_local_copy=False))


def _mock_db(dept_rows):
    """AsyncSession mock whose execute().all() yields the given (dept_id,) rows.

    AsyncMock propagates async-ness to children, so we pin the SYNC parts:
    ``AsyncSession.add`` is synchronous, and ``Result.all()`` must return the
    rows directly (not a coroutine). ``execute``/``commit``/``refresh`` stay async.
    """
    db = AsyncMock()
    db.add = MagicMock()
    result = MagicMock()
    result.all.return_value = dept_rows
    db.execute.return_value = result
    return db


def _stub_ragflow(monkeypatch):
    monkeypatch.setattr(KnowledgeBaseService, "_get_ragflow_client", staticmethod(lambda: None))


@pytest.mark.asyncio
async def test_create_dept_kb_backfills_allowed_depts_from_owner(monkeypatch):
    """access_type='dept' + no allowed_depts → backfill owner's department ids."""
    monkeypatch.setattr("app.extensions.knowledge.service.get_extensions_config", _stub_config)
    _stub_ragflow(monkeypatch)

    owner_id = uuid.uuid4()
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    db = _mock_db([(d1,), (d2,)])
    data = KnowledgeBaseCreate(name="dept-kb", access_type="dept")

    kb = await KnowledgeBaseService.create_kb(db, owner_id, data)

    assert kb.access_type == "dept"
    assert kb.allowed_depts == [d1, d2]


@pytest.mark.asyncio
async def test_create_dept_kb_keeps_explicit_allowed_depts(monkeypatch):
    """Explicit allowed_depts must win — owner departments are NOT consulted."""
    monkeypatch.setattr("app.extensions.knowledge.service.get_extensions_config", _stub_config)
    _stub_ragflow(monkeypatch)

    db = _mock_db([(uuid.uuid4(),)])  # would pollute if backfill ran
    explicit = [uuid.uuid4()]
    data = KnowledgeBaseCreate(name="dept-kb", access_type="dept", allowed_depts=explicit)

    kb = await KnowledgeBaseService.create_kb(db, uuid.uuid4(), data)

    assert kb.allowed_depts == explicit


@pytest.mark.asyncio
async def test_update_kb_to_dept_backfills_when_missing(monkeypatch):
    """Switching access_type to 'dept' without allowed_depts backfills from owner."""
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    db = _mock_db([(d1,), (d2,)])
    kb = KnowledgeBase(name="x", owner_id=uuid.uuid4(), access_type="private", allowed_depts=None)
    data = KnowledgeBaseUpdate(access_type="dept")  # allowed_depts omitted

    await KnowledgeBaseService.update_kb(db, kb, data)

    assert kb.access_type == "dept"
    assert kb.allowed_depts == [d1, d2]
