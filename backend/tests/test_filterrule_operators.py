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
