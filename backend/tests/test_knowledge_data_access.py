"""Knowledge data-access scope tests (overlap-based dept sharing)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import get_permission_registry
from app.extensions.knowledge.routers import _load_kb_scoped
from app.extensions.models import KnowledgeBase


def test_knowledge_dept_scope_uses_allowed_depts_overlap():
    reg = get_permission_registry()
    # sanity: the scope is declared
    assert reg.get_data_scope("knowledge_dept") is not None
    idn = AttributeSet(user_id="u1", username="u1", role_code="r", dept_ids=[str(uuid.uuid4())])
    # Build the rule as the middleware would for a role whose data_scopes include knowledge_dept.
    # Directly compose via the registry's scope template to test the template itself:
    ds = reg.get_data_scope("knowledge_dept")
    rule = FilterRule.from_template(ds.rule_template, idn)
    colmap = {"access_type": KnowledgeBase.access_type, "allowed_depts": KnowledgeBase.allowed_depts, "owner_id": KnowledgeBase.owner_id}
    sql = str(rule.to_sqlalchemy(KnowledgeBase, colmap).compile(compile_kwargs={"literal_binds": False})).lower()
    # knowledge_dept = owner OR (dept-shared): must contain owner_id, the access_type='dept' check, AND the overlap
    assert "owner_id" in sql
    assert "access_type" in sql and "dept" in sql
    assert "allowed_depts" in sql and "&&" in sql  # the overlap operator is present


def test_knowledge_owner_and_public_scopes_still_present():
    reg = get_permission_registry()
    assert reg.get_data_scope("knowledge_owner") is not None
    assert reg.get_data_scope("knowledge_public") is not None


# ---------------------------------------------------------------------------
# Task 11: _load_kb_scoped wiring (SQL-level, no DB required)
# ---------------------------------------------------------------------------
# These verify that the by-id helper composes the SAME FilterRule the list
# endpoint uses onto the SELECT by id, so list and by-id stay consistent.
# There is no async DB fixture in conftest, so we capture the statement built
# by the helper via an AsyncMock session and inspect the compiled SQL.


def _capture_session():
    """Build a mock AsyncSession whose ``execute`` captures the statement.

    ``db.execute`` is async; awaiting it returns ``result_mock`` whose
    ``scalar_one_or_none()`` is rigged to return None. The captured statement
    is then available as ``db.execute.await_args.args[0]``.
    """
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock
    return db


@pytest.mark.asyncio
async def test_load_kb_scoped_none_allow_composes_where_false():
    """A none_allow visibility scope must deny so no KB row is returned."""
    db = _capture_session()
    scope = FilterRule(operator="none_allow")
    rv = await _load_kb_scoped(db, uuid.uuid4(), scope)
    assert rv is None
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # none_allow compiles to sqlalchemy.false() → "false" in the WHERE clause
    assert "false" in sql


@pytest.mark.asyncio
async def test_load_kb_scoped_allow_all_keeps_only_id_predicate():
    """An allow_all scope (superadmin) adds no restriction beyond id = kb_id."""
    db = _capture_session()
    scope = FilterRule(operator="allow_all")
    kb_id = uuid.uuid4()
    await _load_kb_scoped(db, kb_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # asyncpg renders UUIDs without hyphens; compare against the hex form
    assert kb_id.hex in sql  # the id predicate is present
    assert "false" not in sql  # no denial composed in


@pytest.mark.asyncio
async def test_load_kb_scoped_owner_eq_composes_with_id_predicate():
    """A realistic owner-eq scope AND-composes with the id predicate."""
    db = _capture_session()
    owner_id = uuid.uuid4()
    scope = FilterRule(operator="eq", field="owner_id", value=owner_id)
    kb_id = uuid.uuid4()
    await _load_kb_scoped(db, kb_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert kb_id.hex in sql
    assert "owner_id" in sql and owner_id.hex in sql
    assert "false" not in sql  # no denial; both predicates are real filters
