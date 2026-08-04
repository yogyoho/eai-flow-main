import uuid

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet


def test_overlap_template_parses():
    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[uuid.uuid4(), uuid.uuid4()])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    assert rule.operator == "overlap"
    assert rule.field == "allowed_depts"
    assert all(isinstance(x, uuid.UUID) for x in rule.value)  # str -> UUID coercion


def test_overlap_to_sqlalchemy_uses_array_overlap():
    from app.extensions.models import KnowledgeBase

    idn = AttributeSet(user_id="u1", username="u1", dept_ids=[uuid.uuid4()])
    rule = FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, idn)
    expr = rule.to_sqlalchemy(KnowledgeBase, {"allowed_depts": KnowledgeBase.allowed_depts})
    compiled = str(expr.compile(compile_kwargs={"literal_binds": False}))
    assert "allowed_depts" in compiled and "&&" in compiled
