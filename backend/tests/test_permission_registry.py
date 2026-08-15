import pytest

from app.extensions.auth.registry import PermissionRegistry

pytestmark = pytest.mark.skip(reason="EAI yaml-driven RBAC differs from upstream (EAI-CUSTOM skip 2026-08-15)")


class TestPermissionRegistry:
    def test_loads_all_modules_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes:
      - { id: "knowledge_owner", display_name: "仅自己的知识库", rule_template: { owner_id: "$identity.user_id" } }
  contract_price:
    display_name: "合同价格分析"
    permissions:
      - { id: "cpa:read", display_name: "查看合同价格" }
    data_scopes: []
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        assert "knowledge" in registry.modules
        assert registry.modules["knowledge"].display_name == "知识库"
        assert len(registry.modules["knowledge"].permissions) == 2
        assert registry.modules["knowledge"].permissions[0].id == "kb:read"

    def test_get_permission_by_id(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes: []
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        perm = registry.get_permission("kb:read")
        assert perm is not None
        assert perm.id == "kb:read"
        assert perm.module == "knowledge"
        assert registry.get_permission("nonexistent") is None

    def test_list_all_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
    data_scopes: []
  user_management:
    display_name: "用户管理"
    permissions:
      - { id: "user:read", display_name: "查看用户" }
    data_scopes: []
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        all_perms = registry.list_all_permissions()
        assert len(all_perms) == 2
        ids = {p.id for p in all_perms}
        assert ids == {"kb:read", "user:read"}

    def test_role_defaults_loaded(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules: {}
roles:
  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    permissions: ["kb:read", "system:access"]
    data_scopes: ["knowledge_dept"]
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        role = registry.get_role_defaults("dept_head")
        assert role is not None
        assert role["display_name"] == "部门负责人"
        assert role["permissions"] == ["kb:read", "system:access"]
        assert registry.get_role_defaults("nonexistent") is None

    def test_admin_only_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules:
  license:
    display_name: "许可证管理"
    permissions:
      - { id: "license:manage", display_name: "管理许可证", admin_only: true }
      - { id: "license:view", display_name: "查看许可证" }
    data_scopes: []
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        perms = registry.list_admin_only_permissions()
        assert len(perms) == 1
        assert perms[0].id == "license:manage"

    def test_inherit_resolution(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 1
modules: {}
roles:
  base:
    display_name: "基础角色"
    is_system: false
    level: 10
    permissions: ["kb:read", "system:access"]
    data_scopes: ["knowledge_public"]
  derived:
    display_name: "派生角色"
    is_system: false
    level: 20
    permissions: ["#inherit:base", "kb:create"]
    data_scopes: ["knowledge_dept"]
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        resolved = registry.resolve_role_permissions("derived")
        assert "kb:read" in resolved
        assert "kb:create" in resolved
        assert "system:access" in resolved

    # --- v2 format tests ---

    def test_parses_v2_nav_module(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 2
modules:
  knowledge:
    display_name: "知识库"
    nav_id: "nav:knowledge"
    pages:
      - { id: "knowledge:page:browse", display_name: "浏览知识库" }
      - { id: "knowledge:page:detail", display_name: "知识详情" }
    operations:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes:
      - { id: "knowledge_owner", display_name: "仅自己的知识库", rule_template: { owner_id: "$identity.user_id" } }
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        assert "knowledge" in registry.modules
        nm = registry.modules["knowledge"]
        assert nm.display_name == "知识库"
        assert nm.nav_id == "nav:knowledge"
        assert len(nm.pages) == 2
        assert nm.pages[0].id == "knowledge:page:browse"
        assert nm.pages[0].display_name == "浏览知识库"
        assert len(nm.operations) == 2
        assert nm.operations[0].id == "kb:read"
        assert len(nm.data_scopes) == 1
        assert nm.data_scopes[0].id == "knowledge_owner"

    def test_v2_modules_have_all_fields(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 2
modules:
  knowledge:
    display_name: "知识库"
    nav_id: "nav:knowledge"
    pages:
      - { id: "knowledge:page:browse", display_name: "浏览知识库" }
    operations:
      - { id: "kb:read", display_name: "查看知识库" }
    data_scopes: []
  contract_price:
    display_name: "合同价格分析"
    nav_id: "nav:contract_price"
    pages:
      - { id: "cpa:page:dashboard", display_name: "仪表盘" }
    operations:
      - { id: "cpa:read", display_name: "查看合同价格" }
    data_scopes:
      - { id: "cpa_dept", display_name: "本部门", rule_template: { dept_id: "$identity.dept_id" } }
roles: {}
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))
        assert len(registry.modules) == 2

        # Verify page IDs
        all_page_ids: set[str] = set()
        for nm in registry.modules.values():
            for p in nm.pages:
                all_page_ids.add(p.id)
        assert "knowledge:page:browse" in all_page_ids
        assert "cpa:page:dashboard" in all_page_ids

        # Verify operation IDs
        all_op_ids: set[str] = set()
        for nm in registry.modules.values():
            for op in nm.operations:
                all_op_ids.add(op.id)
        assert "kb:read" in all_op_ids
        assert "cpa:read" in all_op_ids

        # Verify nav modules
        nav_modules = registry.list_nav_modules()
        assert len(nav_modules) == 2
        nav_ids = {m.nav_id for m in nav_modules}
        assert nav_ids == {"nav:knowledge", "nav:contract_price"}

    def test_role_nav_defaults(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 2
modules: {}
roles:
  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    nav: ["nav:knowledge", "nav:contract_price"]
    pages: ["knowledge:page:browse", "cpa:page:dashboard"]
    permissions: ["kb:read", "cpa:read"]
    data_scopes: ["knowledge_dept"]
  viewer:
    display_name: "查看者"
    is_system: false
    level: 10
    nav: ["nav:knowledge"]
    pages: []
    permissions: ["kb:read"]
    data_scopes: []
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))

        # get_nav_ids_for_role
        dept_nav = registry.get_nav_ids_for_role("dept_head")
        assert dept_nav == ["nav:knowledge", "nav:contract_price"]

        viewer_nav = registry.get_nav_ids_for_role("viewer")
        assert viewer_nav == ["nav:knowledge"]

        non_role_nav = registry.get_nav_ids_for_role("nonexistent")
        assert non_role_nav == []

    def test_role_page_defaults(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text(
            """
version: 2
modules: {}
roles:
  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    nav: []
    pages: ["knowledge:page:browse", "knowledge:page:detail", "cpa:page:dashboard"]
    permissions: []
    data_scopes: []
""",
            encoding="utf-8",
        )
        registry = PermissionRegistry(str(yaml_file))

        page_ids = registry.get_page_ids_for_role("dept_head")
        assert page_ids == ["knowledge:page:browse", "knowledge:page:detail", "cpa:page:dashboard"]

        non_role_pages = registry.get_page_ids_for_role("nonexistent")
        assert non_role_pages == []
