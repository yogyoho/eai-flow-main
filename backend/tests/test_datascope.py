import pytest
from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import DataScope as RegDataScope
from app.extensions.auth.engine import FilterRule


class TestDataScopeEngine:
    def test_get_data_scope_returns_filter_rule(self):
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="dept_head", dept_ids=["d1", "d2"])
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_owner", display_name="only own",
                             rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
                RegDataScope(id="knowledge_dept", display_name="dept",
                             rule_template={"dept_id IN": "$identity.dept_ids"}, module="knowledge"),
            ]
        }
        engine = DataScopeEngine(scopes, role_data_scopes={"dept_head": ["knowledge_dept"]})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule is not None
        # dept_head gets knowledge_dept only, which is an IN rule
        assert rule.operator == "in"
        assert rule.field == "dept_id"
        assert rule.value == ["d1", "d2"]

    def test_unknown_resource_returns_none_allow(self):
        idn = AttributeSet(user_id="u1", username="test")
        engine = DataScopeEngine({}, {})
        rule = engine.get_data_scope(idn, "nonexistent")
        assert rule.operator == "none_allow"

    def test_role_without_data_scope_returns_none_allow(self):
        idn = AttributeSet(user_id="u1", username="test", role_code="no_scope")
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_public", display_name="public",
                             rule_template={"access_type": "public"}, module="knowledge"),
            ]
        }
        engine = DataScopeEngine(scopes, role_data_scopes={})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule.operator == "none_allow"

    def test_multiple_scopes_combined_with_or(self):
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="admin", dept_ids=["d1"])
        scopes = {
            "knowledge": [
                RegDataScope(id="knowledge_owner", display_name="only own",
                             rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
                RegDataScope(id="knowledge_dept", display_name="dept",
                             rule_template={"dept_id IN": "$identity.dept_ids"}, module="knowledge"),
            ]
        }
        engine = DataScopeEngine(scopes, role_data_scopes={"admin": ["knowledge_owner", "knowledge_dept"]})
        rule = engine.get_data_scope(idn, "knowledge")
        assert rule.operator == "or"
        assert len(rule.children) == 2

    def test_from_registry_builds_engine(self):
        # Uses the actual permissions.yaml in the project
        engine = DataScopeEngine.from_registry()
        # Should have at least knowledge, contract_price, project scopes
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="writer", dept_ids=["d1"])
        rule = engine.get_data_scope(idn, "knowledge")
        # writer has knowledge_dept scope
        assert rule is not None
        # Should not be none_allow if permissions.yaml has writer with knowledge_dept
        assert rule.operator != "none_allow"
