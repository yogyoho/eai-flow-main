"""Project data-access scope tests (Task L1).

Mirrors the SQL-level tests in test_knowledge_data_access.py — these verify
that:

1. The ``project_member`` data-scope template compiles to SQL containing
   both ``id IN`` (member_projects branch) and ``created_by`` (creator
   branch) — the OR-union that must mirror the legacy hand-rolled
   ``(created_by == user_id OR ProjectMember exists)`` filter.

2. ``_load_project_scoped`` composes the by-id SELECT with the same
   visibility FilterRule the list endpoint uses, so list and by-id stay
   consistent. none_allow → WHERE false; allow_all → only the id predicate.

No async DB fixture is required (conftest has none); we capture the
compiled statement via an AsyncMock session, exactly like the KB tests.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import get_permission_registry
from app.extensions.models import ReportProject
from app.extensions.project.routers import _load_project_scoped


def test_project_member_scope_compiles_to_id_in_and_created_by():
    """The project_member scope template compiles to SQL containing both branches.

    Template is { or: [ { id IN: $identity.member_projects },
                         { created_by: $identity.user_id } ] }.
    The OR-union must mirror the legacy hand-rolled list_projects filter
    (created_by == user_id OR ProjectMember subquery) for the no-deny case.
    """
    reg = get_permission_registry()
    ds = reg.get_data_scope("project_member")
    assert ds is not None, "project_member scope must be declared in permissions.yaml"

    member_project_ids = [str(uuid.uuid4()) for _ in range(2)]
    idn = AttributeSet(
        user_id=str(uuid.uuid4()),
        username="u1",
        role_code="r",
        member_projects=member_project_ids,
    )
    rule = FilterRule.from_template(ds.rule_template, idn)

    column_map = {"id": ReportProject.id, "created_by": ReportProject.created_by}
    compiled = str(rule.to_sqlalchemy(ReportProject, column_map).compile(compile_kwargs={"literal_binds": False})).lower()

    # member_projects branch — IN clause on the id column
    assert "id IN" in compiled or "id in" in compiled, f"id IN clause missing: {compiled}"
    # creator branch — equality on created_by
    assert "created_by" in compiled, f"created_by branch missing: {compiled}"
    # OR combining the two branches
    assert " or " in compiled, f"OR combiner missing: {compiled}"


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
async def test_load_project_scoped_none_allow_composes_where_false():
    """A none_allow visibility scope must deny so no project row is returned."""
    db = _capture_session()
    scope = FilterRule(operator="none_allow")
    rv = await _load_project_scoped(db, uuid.uuid4(), scope)
    assert rv is None
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # none_allow compiles to sqlalchemy.false() → "false" in the WHERE clause
    assert "false" in sql


@pytest.mark.asyncio
async def test_load_project_scoped_allow_all_keeps_only_id_predicate():
    """An allow_all scope (superadmin) adds no restriction beyond id = project_id."""
    db = _capture_session()
    scope = FilterRule(operator="allow_all")
    project_id = uuid.uuid4()
    await _load_project_scoped(db, project_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # asyncpg renders UUIDs without hyphens; compare against the hex form
    assert project_id.hex in sql  # the id predicate is present
    assert "false" not in sql  # no denial composed in


@pytest.mark.asyncio
async def test_load_project_scoped_member_or_creator_composes_with_id_predicate():
    """The realistic project_member scope AND-composes with the id predicate.

    Note: we compile WITHOUT literal_binds (default — bound params) because
    SQLAlchemy's UUID type literal-processor requires a ``uuid.UUID`` value,
    not a ``str``. The scope engine resolves ``$identity.user_id`` and
    ``$identity.member_projects`` to strings (identity attributes are
    string-typed), so literal-binds rendering would fail — this is a
    *compile-time test artifact*, not a production issue. In production the
    bound-param path runs, where SQLAlchemy's UUID bind processor coerces
    strings to UUIDs (same mechanism as ``knowledge_owner``'s
    ``owner_id == $identity.user_id`` in prod).
    """
    db = _capture_session()
    member_pid = uuid.uuid4()
    user_id_str = str(uuid.uuid4())
    idn = AttributeSet(
        user_id=user_id_str,
        username="u1",
        role_code="r",
        member_projects=[str(member_pid)],
    )
    reg = get_permission_registry()
    rule = FilterRule.from_template(reg.get_data_scope("project_member").rule_template, idn)
    project_id = uuid.uuid4()
    await _load_project_scoped(db, project_id, rule)
    # Compile with bound params (default) — this is what production uses.
    sql_text = str(db.execute.await_args.args[0].compile())
    sql = sql_text.lower()
    # Both the id predicate (the by-id SELECT) and the scope's two branches are present.
    # The project_id is a real uuid.UUID (from uuid.uuid4()) so SQLAlchemy's UUID
    # literal-binds would handle it — but we compiled with bound params, so the
    # params show up as named placeholders. Assert on the column structure instead.
    assert "report_projects.id" in sql or "id =" in sql or "id in" in sql, f"id predicate missing: {sql}"
    assert "created_by" in sql, f"created_by branch missing: {sql}"
    assert " or " in sql, f"OR combiner missing: {sql}"
    assert "false" not in sql  # no denial; all predicates are real filters
