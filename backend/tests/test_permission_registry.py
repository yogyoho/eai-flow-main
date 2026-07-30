import pytest
from app.extensions.auth.registry import PermissionRegistry


class TestPermissionRegistry:
    def test_loads_all_modules_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
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
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        assert "knowledge" in registry.modules
        assert registry.modules["knowledge"].display_name == "知识库"
        assert len(registry.modules["knowledge"].permissions) == 2
        assert registry.modules["knowledge"].permissions[0].id == "kb:read"

    def test_get_permission_by_id(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  knowledge:
    display_name: "知识库"
    permissions:
      - { id: "kb:read", display_name: "查看知识库" }
      - { id: "kb:create", display_name: "创建知识库" }
    data_scopes: []
roles: {}
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        perm = registry.get_permission("kb:read")
        assert perm is not None
        assert perm.id == "kb:read"
        assert perm.module == "knowledge"
        assert registry.get_permission("nonexistent") is None

    def test_list_all_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
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
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        all_perms = registry.list_all_permissions()
        assert len(all_perms) == 2
        ids = {p.id for p in all_perms}
        assert ids == {"kb:read", "user:read"}

    def test_role_defaults_loaded(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules: {}
roles:
  dept_head:
    display_name: "部门负责人"
    is_system: false
    level: 50
    permissions: ["kb:read", "system:access"]
    data_scopes: ["knowledge_dept"]
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        role = registry.get_role_defaults("dept_head")
        assert role is not None
        assert role["display_name"] == "部门负责人"
        assert role["permissions"] == ["kb:read", "system:access"]
        assert registry.get_role_defaults("nonexistent") is None

    def test_admin_only_permissions(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
version: 1
modules:
  license:
    display_name: "许可证管理"
    permissions:
      - { id: "license:manage", display_name: "管理许可证", admin_only: true }
      - { id: "license:view", display_name: "查看许可证" }
    data_scopes: []
roles: {}
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        perms = registry.list_admin_only_permissions()
        assert len(perms) == 1
        assert perms[0].id == "license:manage"

    def test_inherit_resolution(self, tmp_path):
        yaml_file = tmp_path / "permissions.yaml"
        yaml_file.write_text("""
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
""", encoding="utf-8")
        registry = PermissionRegistry(str(yaml_file))
        resolved = registry.resolve_role_permissions("derived")
        assert "kb:read" in resolved
        assert "kb:create" in resolved
        assert "system:access" in resolved
