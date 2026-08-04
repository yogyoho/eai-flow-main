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
        # EAI-CUSTOM: dept_ids are UUIDs in production (UserDepartment.dept_id);
        # the overlap-based knowledge_dept scope coerces str→UUID at parse time.
        import uuid as _uuid
        idn = AttributeSet(user_id="u1", username="test",
                           role_code="writer", dept_ids=[str(_uuid.uuid4())])
        rule = engine.get_data_scope(idn, "knowledge")
        # writer has knowledge_dept scope
        assert rule is not None
        # Should not be none_allow if permissions.yaml has writer with knowledge_dept
        assert rule.operator != "none_allow"


def test_get_data_scope_from_overlay_role(tmp_path):
    """角色 data_scopes 经 registry（含 overlay）解析，不再硬编码 yaml 默认。"""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules:
  contract_price:
    display_name: "合同价格"
    nav_id: "nav:contract-price"
    pages: []
    operations:
      - { id: "cpa:read", display_name: "查看" }
    data_scopes:
      - { id: "cpa_all", display_name: "全部", rule_template: {} }
      - { id: "cpa_dept", display_name: "本部门", rule_template: { dept_id IN: "$identity.dept_ids" } }
roles: {}
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
roles:
  buyer:
    display_name: "采购员"
    permissions: ["cpa:read"]
    data_scopes: ["cpa_dept"]
disabled_roles: []
""", encoding="utf-8")

    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))
    engine = DataScopeEngine.from_registry_with(reg)
    identity = AttributeSet(user_id="1", username="u", role_code="buyer", dept_ids=["d1"])
    rule = engine.get_data_scope(identity, "contract_price")
    assert rule.operator == "in"
    assert rule.field == "dept_id"


def test_empty_template_means_allow_all(tmp_path):
    """空 rule_template {} 应解析为 allow_all（全量），而非 none_allow（拒绝全部）。"""
    from app.extensions.auth.registry import PermissionRegistry

    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules:
  projects:
    display_name: "项目"
    nav_id: "nav:projects"
    pages: []
    operations: []
    data_scopes:
      - { id: "project_all", display_name: "全部", rule_template: {} }
roles:
  manager:
    display_name: "经理"
    permissions: ["project:read"]
    data_scopes: ["project_all"]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    engine = DataScopeEngine.from_registry_with(reg)
    identity = AttributeSet(user_id="1", username="u", role_code="manager")
    rule = engine.get_data_scope(identity, "projects")
    assert rule.operator == "allow_all"


def test_get_data_scope_with_deny_composes_and_not():
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.identity import AttributeSet
    from app.extensions.auth.registry import DataScope
    scopes = {"knowledge": [
        DataScope(id="knowledge_owner", display_name="o", rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
        DataScope(id="knowledge_public", display_name="p", rule_template={"access_type": "public"}, module="knowledge"),
    ]}
    idn = AttributeSet(user_id="u1", username="u1")
    eng = DataScopeEngine(scopes, role_data_scopes={"r": ["knowledge_owner", "knowledge_public"]})
    rule = eng.get_data_scope(idn, "knowledge", deny_scope_ids={"knowledge_public"})
    assert rule.operator == "and"
    assert rule.children[1].operator == "not"   # AND NOT public


def test_get_data_scope_no_deny_returns_allow_unchanged():
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.identity import AttributeSet
    from app.extensions.auth.registry import DataScope
    scopes = {"knowledge": [DataScope(id="knowledge_owner", display_name="o", rule_template={"owner_id": "$identity.user_id"}, module="knowledge")]}
    idn = AttributeSet(user_id="u1", username="u1")
    eng = DataScopeEngine(scopes, role_data_scopes={"r": ["knowledge_owner"]})
    rule = eng.get_data_scope(idn, "knowledge")                      # no deny
    rule2 = eng.get_data_scope(idn, "knowledge", deny_scope_ids=set())  # empty deny
    # both equal the plain allow union (owner eq rule); NOT an 'and' wrapper
    assert rule.operator != "and" and rule2.operator != "and"
