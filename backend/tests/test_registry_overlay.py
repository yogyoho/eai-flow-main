"""测试 PermissionRegistry 的 overlay 加载、project_roles 和双文件热重载功能。"""
from app.extensions.auth.registry import PermissionRegistry


def test_overlay_merges_roles(tmp_path):
    """验证 overlay 文件合并角色：覆盖内置角色、添加自定义角色、禁用角色。"""
    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles:
  builtin:
    display_name: "内置"
    level: 10
    permissions: ["kb:read"]
    data_scopes: ["knowledge_public"]
  shared:
    display_name: "共享"
    level: 20
    permissions: ["doc:read"]
    data_scopes: []
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
roles:
  builtin:
    permissions: ["kb:read", "kb:create"]
  custom:
    display_name: "自定义"
    level: 5
    permissions: ["#inherit:builtin", "doc:read"]
    nav: ["nav:knowledge"]
    data_scopes: ["knowledge_dept"]
disabled_roles: ["shared"]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))

    # overlay 覆盖内置角色的权限
    assert set(reg.resolve_role_permissions("builtin")) == {"kb:read", "kb:create"}
    # 自定义角色出现，且正确继承内置角色权限
    assert set(reg.resolve_role_permissions("custom")) == {"kb:read", "kb:create", "doc:read"}
    # 禁用的内置角色被隐藏
    assert reg.get_role_defaults("shared") is None
    assert "shared" not in reg.list_role_codes()
    # data_scopes 访问器
    assert reg.get_data_scopes_for_role("custom") == ["knowledge_dept"]


def test_project_roles_parsed(tmp_path):
    """验证 permissions.yaml 中的 project_roles 字段被正确解析。"""
    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles: {}
project_roles:
  owner: [project:edit, project:delete]
  writer: [chapter:write_own]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml))
    assert reg.get_project_roles()["owner"] == ["project:edit", "project:delete"]
    assert reg.get_project_roles()["writer"] == ["chapter:write_own"]


def test_disabled_roles_cleared_on_reload(tmp_path):
    """验证 reload 时 _disabled_roles 被正确清空。

    场景：首次加载 overlay 禁用了 A+B 两个角色，修改 overlay 只禁用 B，
    调用 reload() 后，A 不应再处于禁用状态。
    """
    main_yaml = tmp_path / "permissions.yaml"
    main_yaml.write_text("""
version: 3
modules: {}
roles:
  alpha:
    display_name: "Alpha"
    level: 10
    permissions: ["a:read"]
  beta:
    display_name: "Beta"
    level: 20
    permissions: ["b:read"]
""", encoding="utf-8")
    overlay_yaml = tmp_path / "roles_custom.yaml"
    overlay_yaml.write_text("""
disabled_roles: ["alpha", "beta"]
""", encoding="utf-8")
    reg = PermissionRegistry(str(main_yaml), overlay_path=str(overlay_yaml))

    # 首次加载：两个角色都被禁用
    assert reg.get_role_defaults("alpha") is None
    assert reg.get_role_defaults("beta") is None
    assert "alpha" not in reg.list_role_codes()
    assert "beta" not in reg.list_role_codes()

    # 修改 overlay：只禁用 beta，alpha 恢复
    overlay_yaml.write_text("""
disabled_roles: ["beta"]
""", encoding="utf-8")
    reg.reload()

    # alpha 应恢复可见
    assert reg.get_role_defaults("alpha") is not None
    assert "alpha" in reg.list_role_codes()
    # beta 仍被禁用
    assert reg.get_role_defaults("beta") is None
    assert "beta" not in reg.list_role_codes()
