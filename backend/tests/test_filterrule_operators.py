import uuid

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet


def test_overlap_template_parses():
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[str(uuid.uuid4()), str(uuid.uuid4())])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    assert rule.operator == "overlap"
    assert rule.field == "allowed_depts"
    assert all(isinstance(x, uuid.UUID) for x in rule.value)  # str -> UUID coercion


def test_overlap_empty_identity_attr_denies():
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    assert rule.operator == "none_allow"


def test_overlap_malformed_dept_id_denies():
    # EAI-CUSTOM (M3): a malformed (non-UUID) dept_id string must NOT raise —
    # it should yield none_allow (deny, safe default) instead of a 500.
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=["not-a-valid-uuid"])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    assert rule.operator == "none_allow"


def test_overlap_to_sqlalchemy_uses_array_overlap():
    from app.extensions.models import KnowledgeBase

    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[uuid.uuid4()])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    expr = rule.to_sqlalchemy(KnowledgeBase, {"allowed_depts": KnowledgeBase.allowed_depts})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": False}))
    assert "allowed_depts" in compiled and "&&" in compiled


def test_not_template_and_sqlalchemy():
    from app.extensions.models import KnowledgeBase

    idn = AttributeSet(user_id="u1", username="u1")
    inner = FilterRule.from_template({"access_type": "public"}, idn)  # eq
    rule = FilterRule(operator="not", children=[inner])
    expr = rule.to_sqlalchemy(KnowledgeBase, {"access_type": KnowledgeBase.access_type})
    # NOTE: SQLAlchemy's not_(col == v) algebraically simplifies to (col != v),
    # so the literal "NOT" keyword does not appear in compiled SQL. Assert the
    # negation of the inner eq materialized (pre-fix this branch returned FALSE).
    compiled = str(expr.compile(compile_kwargs={"literal_binds": False})).upper()
    assert "ACCESS_TYPE" in compiled and "!=" in compiled


def test_or_composite_compiles():
    from app.extensions.models import KnowledgeBase

    idn = AttributeSet(user_id="u1", username="u1")
    owner = FilterRule.from_template({"owner_id": "$identity.user_id"}, idn)
    public = FilterRule.from_template({"access_type": "public"}, idn)
    rule = FilterRule(operator="or", children=[owner, public])
    s = str(rule.to_sqlalchemy(KnowledgeBase, {"owner_id": KnowledgeBase.owner_id, "access_type": KnowledgeBase.access_type}).compile(compile_kwargs={"literal_binds": False})).upper()
    assert " OR " in s and "OWNER_ID" in s and "ACCESS_TYPE" in s


def test_evaluate_policy_conditions_module_function():
    from app.extensions.auth.engine import evaluate_policy_conditions
    idn = AttributeSet(user_id="u1", username="u1", role_level=50)
    assert evaluate_policy_conditions({"attr": "role_level", "op": "gte", "value": 40}, idn) is True
    assert evaluate_policy_conditions({"attr": "role_level", "op": "gte", "value": 60}, idn) is False
    assert evaluate_policy_conditions({}, idn) is True   # empty conditions = match all


def _engine_with(deny=None, allow_role=None, role="r", role_perms=None, all_ids=None):
    from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
    return UnifiedPermissionEngine(
        role_permissions={role: role_perms or set()},
        all_permission_ids=all_ids or set(),
        policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": deny or []})],
    )


def test_check_deny_overrides_role_grant():
    from app.extensions.auth.identity import AttributeSet
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    eng = _engine_with(deny=["kb:delete"], role_perms={"kb:delete"})
    assert eng.check(idn, "kb:delete") is False   # role grants it, but deny wins


def test_check_deny_module_wildcard():
    from app.extensions.auth.identity import AttributeSet
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    eng = _engine_with(deny=["kb:*"], role_perms={"kb:read", "kb:create"})
    assert eng.check(idn, "kb:read") is False and eng.check(idn, "kb:create") is False


def test_check_superadmin_immune_to_deny():
    from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
    from app.extensions.auth.identity import AttributeSet
    eng = UnifiedPermissionEngine(role_permissions={"super": {"*"}},
                                  policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:read"]})])
    sup = AttributeSet(user_id="s", username="s", role_code="super")
    assert eng.check(sup, "kb:read") is True


def test_check_allow_still_works_no_deny():
    from app.extensions.auth.identity import AttributeSet
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    eng = _engine_with(deny=[], role_perms={"kb:read"})
    assert eng.check(idn, "kb:read") is True
    assert eng.check(idn, "kb:write") is False


def test_list_permissions_expands_and_subtracts_deny():
    from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
    from app.extensions.auth.identity import AttributeSet
    eng = UnifiedPermissionEngine(
        role_permissions={"r": {"kb:*"}},
        all_permission_ids={"kb:read", "kb:create", "kb:delete"},
        policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:delete"]})],
    )
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    perms = eng.list_permissions(idn)
    assert "kb:read" in perms and "kb:create" in perms and "kb:delete" not in perms


def test_list_permissions_superadmin_returns_all_and_ignores_deny():
    from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
    from app.extensions.auth.identity import AttributeSet
    eng = UnifiedPermissionEngine(
        role_permissions={"super": {"*"}},
        all_permission_ids={"kb:read", "kb:create"},
        policies=[Policy(name="d", priority=0, conditions={}, grants={"deny_permissions": ["kb:read"]})],
    )
    sup = AttributeSet(user_id="s", username="s", role_code="super")
    perms = eng.list_permissions(sup)
    assert perms == {"kb:read", "kb:create"}   # superadmin immune


def test_find_deny_policy_name():
    from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
    from app.extensions.auth.identity import AttributeSet
    eng = UnifiedPermissionEngine(role_permissions={"r": {"kb:read"}},
        policies=[Policy(name="block_delete", priority=0, conditions={}, grants={"deny_permissions": ["kb:delete"]})])
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    assert eng.find_deny_policy_name(idn, "kb:delete") == "block_delete"
    assert eng.find_deny_policy_name(idn, "kb:read") is None
