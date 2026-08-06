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


# ---------------------------------------------------------------------------
# M5: visibility matrix (replaces the deleted test_kb_access_visibility.py).
# SQL-level composition only — no DB rows needed. Mirrors the real registry
# scope templates so a regression in any one clause (owner / public / dept
# overlap) surfaces as a failed assertion here.
#
# We assert BOTH (a) the FilterRule structure (operator/field/value), which
# pins semantics precisely, and (b) the compiled SQL structure (column names
# and operators), which pins the column_map wiring. Values are checked on the
# rule object rather than in compiled SQL because the default test dialect
# cannot render UUID literals and identity bakes values in at build time.
# ---------------------------------------------------------------------------

_KNOWLEDGE_COLMAP = {
    "owner_id": KnowledgeBase.owner_id,
    "access_type": KnowledgeBase.access_type,
    "allowed_depts": KnowledgeBase.allowed_depts,
}


def _compile_sql(rule: FilterRule) -> str:
    return str(rule.to_sqlalchemy(KnowledgeBase, _KNOWLEDGE_COLMAP).compile(compile_kwargs={"literal_binds": False})).lower()


def test_knowledge_owner_scope_matches_owner_id():
    """knowledge_owner → owner_id = <user> (sees own, incl. own private)."""
    reg = get_permission_registry()
    ds = reg.get_data_scope("knowledge_owner")
    assert ds is not None
    user_id = uuid.uuid4()
    idn = AttributeSet(user_id=str(user_id), username="u", role_code="user")
    rule = FilterRule.from_template(ds.rule_template, idn)
    # structure: eq on owner_id with the identity's user_id
    assert rule.operator == "eq" and rule.field == "owner_id"
    assert rule.value == str(user_id)
    # SQL: owner column present; access_type is NOT constrained (own private visible)
    sql = _compile_sql(rule)
    assert "owner_id" in sql
    assert "access_type" not in sql


def test_knowledge_public_scope_matches_access_type_public():
    """knowledge_public → access_type = 'public' (sees public)."""
    reg = get_permission_registry()
    ds = reg.get_data_scope("knowledge_public")
    assert ds is not None
    idn = AttributeSet(user_id="u1", username="u", role_code="user")
    rule = FilterRule.from_template(ds.rule_template, idn)
    # structure: eq on access_type with literal 'public'
    assert rule.operator == "eq" and rule.field == "access_type"
    assert rule.value == "public"
    sql = _compile_sql(rule)
    assert "access_type" in sql


def test_knowledge_dept_scope_matches_owner_or_dept_overlap():
    """knowledge_dept → owner_id = <user> OR (access_type='dept' AND allowed_depts && <depts>)."""
    reg = get_permission_registry()
    ds = reg.get_data_scope("knowledge_dept")
    assert ds is not None
    dept = uuid.uuid4()
    user_id = uuid.uuid4()
    idn = AttributeSet(user_id=str(user_id), username="u", role_code="user", dept_ids=[str(dept)])
    rule = FilterRule.from_template(ds.rule_template, idn)
    # structure: OR of [owner-eq, AND(access_type=dept, overlap)]
    assert rule.operator == "or"
    assert len(rule.children) == 2
    owner_branch, dept_branch = rule.children
    assert owner_branch.operator == "eq" and owner_branch.field == "owner_id"
    assert owner_branch.value == str(user_id)
    assert dept_branch.operator == "and" and len(dept_branch.children) == 2
    access_clause, overlap_clause = dept_branch.children
    assert access_clause.operator == "eq" and access_clause.field == "access_type" and access_clause.value == "dept"
    assert overlap_clause.operator == "overlap" and overlap_clause.field == "allowed_depts"
    assert all(isinstance(x, uuid.UUID) for x in overlap_clause.value)  # str → UUID coercion happened
    # SQL: all three clauses + the PG overlap operator appear
    sql = _compile_sql(rule)
    assert "owner_id" in sql and "access_type" in sql and "allowed_depts" in sql and "&&" in sql


def test_knowledge_owner_plus_public_plus_dept_or_union():
    """A role bound to owner+public+dept → OR-union of all three (the realistic case).

    Mirrors how ``with_data_scope("knowledge")`` combines the role's granted
    data_scopes via ``DataScopeEngine.build_scope_union``.
    """
    from app.extensions.auth.datascope import DataScopeEngine

    user_id = uuid.uuid4()
    dept = uuid.uuid4()
    idn = AttributeSet(user_id=str(user_id), username="u", role_code="user", dept_ids=[str(dept)])
    engine = DataScopeEngine.from_registry()
    rule = engine.build_scope_union(idn, "knowledge", ["knowledge_owner", "knowledge_public", "knowledge_dept"])
    # structure: OR of 3 distinct scope rules
    assert rule.operator == "or"
    assert len(rule.children) == 3
    fields = {(c.operator, c.field) for c in rule.children}
    # owner (eq, owner_id) + public (eq, access_type) + dept (or-composite)
    assert ("eq", "owner_id") in fields
    assert ("eq", "access_type") in fields
    assert any(c.operator == "or" for c in rule.children)  # knowledge_dept composite
    # SQL: OR-union of owner + access_type + allowed_depts overlap
    sql = _compile_sql(rule)
    assert " or " in sql
    assert "owner_id" in sql and "access_type" in sql and "allowed_depts" in sql and "&&" in sql


# ---------------------------------------------------------------------------
# Task 1: KnowledgeBaseGrant 模型注册（每-KB 显式授权）
# ---------------------------------------------------------------------------


def test_knowledge_base_grant_model_registered():
    from app.extensions.models import KnowledgeBaseGrant

    assert KnowledgeBaseGrant.__tablename__ == "knowledge_base_grants"
    cols = {c.name for c in KnowledgeBaseGrant.__table__.columns}
    assert {"kb_id", "grantee_type", "grantee_id", "permission", "expires_at", "created_by", "created_at"} <= cols


# ---------------------------------------------------------------------------
# Task 2: kb_grant_visible_clause — 授权可见性 EXISTS 子句
# ---------------------------------------------------------------------------


def test_kb_grant_visible_clause_sql_contains_grant_table_and_matches():
    from app.extensions.knowledge.access import kb_grant_visible_clause

    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    sql = str(kb_grant_visible_clause(idn).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "knowledge_base_grants" in sql
    assert "user" in sql and "u1" in sql
    assert "dept" in sql and "d1" in sql
    assert "dept_head" in sql
    assert "expires_at" in sql


# ---------------------------------------------------------------------------
# Task 3: has_kb_grant — 命中/未命中 + permission 过滤
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_kb_grant_matches_and_permission_filter():
    from app.extensions.knowledge.access import has_kb_grant

    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    kb_id = uuid.uuid4()

    # grant 命中（write）
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute.return_value = res
    assert await has_kb_grant(db, kb_id, idn, "write") is True

    # 未命中
    db2 = AsyncMock()
    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = None
    db2.execute.return_value = res2
    assert await has_kb_grant(db2, kb_id, idn, "write") is False


# ---------------------------------------------------------------------------
# Task 4: _load_kb_scoped / list / federated 可见性 OR 组合
# ---------------------------------------------------------------------------
# 可见性 = 角色 scope OR 显式授权 EXISTS。显式授权仅当 identity 传入且 scope
# 非 allow_all（超管全量）时 OR 进去。


@pytest.mark.asyncio
async def test_load_kb_scoped_identity_ors_grant_clause():
    """传入 identity 且 scope 非 allow_all 时，OR 上 knowledge_base_grants EXISTS。"""
    db = _capture_session()
    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    scope = FilterRule(operator="eq", field="owner_id", value=uuid.uuid4())
    await _load_kb_scoped(db, uuid.uuid4(), scope, identity=idn)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "knowledge_base_grants" in sql  # 显式授权 EXISTS 已 OR 进 WHERE
    assert "u1" in sql  # grantee 匹配条件带上了 identity


@pytest.mark.asyncio
async def test_load_kb_scoped_identity_allow_all_skips_grant_clause():
    """超管 allow_all 时不追加 grant 子查询（纯 scope 路径）。"""
    db = _capture_session()
    idn = AttributeSet(user_id="u1", username="u1", role_code="admin", dept_ids=["d1"])
    scope = FilterRule(operator="allow_all")
    kb_id = uuid.uuid4()
    await _load_kb_scoped(db, kb_id, scope, identity=idn)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert kb_id.hex in sql
    assert "knowledge_base_grants" not in sql  # allow_all 无例外子查询
    assert "false" not in sql


@pytest.mark.asyncio
async def test_load_kb_scoped_no_identity_keeps_pure_scope():
    """无 identity（向后兼容）时仍是纯 scope，无 grant 子查询。"""
    db = _capture_session()
    owner_id = uuid.uuid4()
    scope = FilterRule(operator="eq", field="owner_id", value=owner_id)
    kb_id = uuid.uuid4()
    await _load_kb_scoped(db, kb_id, scope)
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert kb_id.hex in sql and owner_id.hex in sql
    assert "knowledge_base_grants" not in sql


def test_list_scope_clause_ors_grant_for_non_allow_all():
    """list 端点组合：scope 非 allow_all 时，最终子句 = scope OR 授权 EXISTS。"""
    from sqlalchemy import or_ as sa_or

    from app.extensions.knowledge.access import kb_grant_visible_clause

    idn = AttributeSet(user_id="u1", username="u1", role_code="dept_head", dept_ids=["d1"])
    scope = FilterRule(operator="eq", field="owner_id", value=uuid.uuid4())
    scope_clause = scope.to_sqlalchemy(KnowledgeBase, _KNOWLEDGE_COLMAP)
    if scope.operator != "allow_all":
        scope_clause = sa_or(scope_clause, kb_grant_visible_clause(idn))
    sql = str(scope_clause.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "owner_id" in sql
    assert "knowledge_base_grants" in sql  # 授权 EXISTS 已 OR 进来


def test_list_scope_clause_allow_all_keeps_pure_scope():
    """list 端点组合：allow_all 时不追加授权子查询。"""
    scope = FilterRule(operator="allow_all")
    scope_clause = scope.to_sqlalchemy(KnowledgeBase, _KNOWLEDGE_COLMAP)
    assert scope.operator == "allow_all"  # 触发跳过分支，保持纯 scope
    sql = str(scope_clause.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "knowledge_base_grants" not in sql
