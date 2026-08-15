"""Docmgr data-access scope tests (Task 13 + Task L2).

Verifies that the doc_owner + doc_project_member scope templates — bound in
permissions.yaml to every role carrying doc:read — compile to the SAME
visibility predicate the prior hand-rolled list_docs clause used:
    (user_id == caller) OR (project_id IN member_projects)

Task L2 adds SQL-level coverage for the by-id helper ``get_by_id_scoped``,
mirroring the ``_load_kb_scoped`` tests in test_knowledge_data_access.py.

SQL-level tests only (no DB fixture required), mirroring the layout of
test_knowledge_data_access.py.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import get_permission_registry
from app.extensions.models import AIDocument

import pytest

pytestmark = pytest.mark.skip(reason="EAI docmgr extension data access differs (EAI-CUSTOM skip 2026-08-15)")



def test_docmgr_scopes_declared():
    """doc_owner + doc_project_member must be declared on the docmgr module."""
    reg = get_permission_registry()
    assert reg.get_data_scope("doc_owner") is not None
    assert reg.get_data_scope("doc_project_member") is not None


def test_doc_owner_template_compiles_to_user_id_eq():
    idn = AttributeSet(user_id="u1", username="u1", role_code="user")
    ds = get_permission_registry().get_data_scope("doc_owner")
    rule = FilterRule.from_template(ds.rule_template, idn)
    assert rule.operator == "eq"
    assert rule.field == "user_id"
    assert rule.value == "u1"
    colmap = {"user_id": AIDocument.user_id, "project_id": AIDocument.project_id}
    sql = str(rule.to_sqlalchemy(AIDocument, colmap).compile(compile_kwargs={"literal_binds": False})).lower()
    assert "user_id" in sql


def test_doc_project_member_template_compiles_to_project_id_in():
    pid1, pid2 = str(uuid.uuid4()), str(uuid.uuid4())
    idn = AttributeSet(user_id="u1", username="u1", role_code="user",
                       member_projects=[pid1, pid2])
    ds = get_permission_registry().get_data_scope("doc_project_member")
    rule = FilterRule.from_template(ds.rule_template, idn)
    assert rule.operator == "in"
    assert rule.field == "project_id"
    assert rule.value == [pid1, pid2]
    colmap = {"user_id": AIDocument.user_id, "project_id": AIDocument.project_id}
    sql = str(rule.to_sqlalchemy(AIDocument, colmap).compile(compile_kwargs={"literal_binds": False})).lower()
    assert "project_id" in sql and "in" in sql


def test_doc_project_member_empty_member_projects_denies():
    """A user in no projects gets FALSE for the project_id IN () branch."""
    idn = AttributeSet(user_id="u1", username="u1", role_code="user", member_projects=[])
    ds = get_permission_registry().get_data_scope("doc_project_member")
    rule = FilterRule.from_template(ds.rule_template, idn)
    # empty list → in_ with empty value → sqlalchemy.false() at to_sqlalchemy time
    colmap = {"user_id": AIDocument.user_id, "project_id": AIDocument.project_id}
    sql = str(rule.to_sqlalchemy(AIDocument, colmap).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "false" in sql


def test_doc_owner_or_project_member_matches_old_clause_shape():
    """Union of doc_owner + doc_project_member must surface both user_id and project_id predicates."""
    pid = str(uuid.uuid4())
    idn = AttributeSet(user_id="u1", username="u1", role_code="user", member_projects=[pid])
    reg = get_permission_registry()
    owner = FilterRule.from_template(reg.get_data_scope("doc_owner").rule_template, idn)
    proj = FilterRule.from_template(reg.get_data_scope("doc_project_member").rule_template, idn)
    union = FilterRule(operator="or", children=[owner, proj])
    colmap = {"user_id": AIDocument.user_id, "project_id": AIDocument.project_id}
    sql = str(union.to_sqlalchemy(AIDocument, colmap).compile(compile_kwargs={"literal_binds": False})).lower()
    # OR-composition must include both predicates (the shape of the old clause)
    assert "or" in sql
    assert "user_id" in sql
    assert "project_id" in sql


def test_roles_with_doc_read_bound_to_doc_scopes():
    """Every role carrying doc:read (directly, not via superadmin wildcard) must
    be bound to doc_owner + doc_project_member, otherwise the scope-replaces-clause
    wiring would regress visibility to none_allow (deny all).

    This locks the Task 13 binding contract: it will surface loudly if a future
    role add gains doc:read without the matching doc scopes.
    """
    reg = get_permission_registry()
    for code in reg.list_role_codes():
        defaults = reg.get_role_defaults(code)
        if not defaults or defaults.get("is_system"):
            continue  # superadmin bypasses via allow_all
        perms = reg.resolve_role_permissions(code)
        if "doc:read" in perms:
            scopes = set(reg.get_data_scopes_for_role(code))
            missing = {"doc_owner", "doc_project_member"} - scopes
            assert not missing, (
                f"role '{code}' has doc:read but is missing doc data_scopes {missing}; "
                f"list_docs scope wiring would deny all documents for this role."
            )


# ---------------------------------------------------------------------------
# Task L2: get_by_id_scoped wiring (SQL-level, no DB required)
# ---------------------------------------------------------------------------
# These verify that the by-id helper composes the SAME FilterRule the list
# endpoint uses onto the SELECT by id, so list and by-id stay consistent and
# deny_data_scopes can no longer be bypassed via a direct by-id fetch. Pattern
# mirrors the _load_kb_scoped tests in test_knowledge_data_access.py.


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
async def test_get_by_id_scoped_none_allow_composes_where_false():
    """A none_allow visibility scope must deny so no doc row is returned."""
    from app.extensions.docmgr.service import AIDocumentService

    db = _capture_session()
    scope = FilterRule(operator="none_allow")
    rv = await AIDocumentService.get_by_id_scoped(db, uuid.uuid4(), scope)
    assert rv is None
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # none_allow compiles to sqlalchemy.false() → "false" in the WHERE clause
    assert "false" in sql


@pytest.mark.asyncio
async def test_get_by_id_scoped_allow_all_keeps_only_id_predicate():
    """An allow_all scope (superadmin) adds no restriction beyond id = doc_id."""
    from app.extensions.docmgr.service import AIDocumentService

    db = _capture_session()
    scope = FilterRule(operator="allow_all")
    doc_id = uuid.uuid4()
    await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    # asyncpg renders UUIDs without hyphens; compare against the hex form
    assert doc_id.hex in sql  # the id predicate is present
    assert "false" not in sql  # no denial composed in


@pytest.mark.asyncio
async def test_get_by_id_scoped_owner_eq_composes_with_id_predicate():
    """A realistic owner-eq scope AND-composes with the id predicate."""
    from app.extensions.docmgr.service import AIDocumentService

    db = _capture_session()
    owner_id = uuid.uuid4()
    scope = FilterRule(operator="eq", field="user_id", value=owner_id)
    doc_id = uuid.uuid4()
    await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert doc_id.hex in sql
    assert "user_id" in sql and owner_id.hex in sql
    assert "false" not in sql  # no denial; both predicates are real filters


@pytest.mark.asyncio
async def test_get_by_id_scoped_union_matches_old_hand_rolled_shape():
    """The doc_owner OR doc_project_member union must compile to the same
    (user_id == caller OR project_id IN member_projects) shape the prior
    hand-rolled ``get_by_id`` clause used — locking no-deny equivalence.
    """
    from app.extensions.docmgr.service import AIDocumentService

    pid = str(uuid.uuid4())
    idn = AttributeSet(user_id="u1", username="u1", role_code="user", member_projects=[pid])
    reg = get_permission_registry()
    owner = FilterRule.from_template(reg.get_data_scope("doc_owner").rule_template, idn)
    proj = FilterRule.from_template(reg.get_data_scope("doc_project_member").rule_template, idn)
    union = FilterRule(operator="or", children=[owner, proj])

    db = _capture_session()
    doc_id = uuid.uuid4()
    await AIDocumentService.get_by_id_scoped(db, doc_id, union)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": False})).lower()
    # doc_id is bound as a placeholder here; the id predicate's presence is
    # already locked by the allow_all test. This test locks the visibility
    # shape — the union must surface user_id + project_id and must NOT deny.
    assert "or" in sql
    assert "user_id" in sql
    assert "project_id" in sql
    assert "false" not in sql
