"""Knowledge data-access scope tests (overlap-based dept sharing)."""
import uuid
from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import get_permission_registry
from app.extensions.models import KnowledgeBase


def test_knowledge_dept_scope_uses_allowed_depts_overlap():
    reg = get_permission_registry()
    # sanity: the scope is declared
    assert reg.get_data_scope("knowledge_dept") is not None
    engine = DataScopeEngine.from_registry_with(reg)
    idn = AttributeSet(user_id="u1", username="u1", role_code="r", dept_ids=[str(uuid.uuid4())])
    # Build the rule as the middleware would for a role whose data_scopes include knowledge_dept.
    # DataScopeEngine.get_data_scope uses role_data_scopes built from registry role defaults;
    # instead, directly compose via the registry's scope template to test the template itself:
    from app.extensions.auth.engine import FilterRule
    ds = reg.get_data_scope("knowledge_dept")
    rule = FilterRule.from_template(ds.rule_template, idn)
    colmap = {"access_type": KnowledgeBase.access_type, "allowed_depts": KnowledgeBase.allowed_depts, "owner_id": KnowledgeBase.owner_id}
    sql = str(rule.to_sqlalchemy(KnowledgeBase, colmap).compile(compile_kwargs={"literal_binds": False})).lower()
    assert "access_type" in sql and "dept" in sql
    assert "allowed_depts" in sql and "&&" in sql   # the overlap operator is present


def test_knowledge_owner_and_public_scopes_still_present():
    reg = get_permission_registry()
    assert reg.get_data_scope("knowledge_owner") is not None
    assert reg.get_data_scope("knowledge_public") is not None
