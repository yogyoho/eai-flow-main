"""Docmgr data-access scope tests (Task 13).

Verifies that the doc_owner + doc_project_member scope templates — bound in
permissions.yaml to every role carrying doc:read — compile to the SAME
visibility predicate the prior hand-rolled list_docs clause used:
    (user_id == caller) OR (project_id IN member_projects)

SQL-level tests only (no DB fixture required), mirroring the layout of
test_knowledge_data_access.py.
"""

import uuid

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import get_permission_registry
from app.extensions.models import AIDocument


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
