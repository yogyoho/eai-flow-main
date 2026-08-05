"""F1 回归：dept_head 权限被 overlay 清空后必须恢复（#inherit:user + 部门扩展）。

用真实 PermissionRegistry（读 config/permissions.yaml + config/roles_custom.yaml），
守护 shipped 数据——dept_head 用户因此持有 system:access，4 个在册用户不被锁死。
"""
from app.extensions.auth.registry import PermissionRegistry

REQUIRED_DEPT_HEAD = {
    "system:access", "kb:read", "doc:read", "model:read", "dashboard:view",  # 继承 user
    "department:create", "department:update", "department:delete",
    "kb:create", "kb:upload", "kb:update", "kb:delete",
    "doc:upload", "doc:delete", "project:create", "project:read",
    "approval:approve", "approval:submit", "approval:view",
    "chapter:review", "workflow:read",
}


def test_dept_head_resolves_nonempty_and_has_system_access():
    reg = PermissionRegistry()
    perms = reg.resolve_role_permissions("dept_head")
    assert len(perms) >= 21, f"dept_head 解析为 {len(perms)} 个权限（期望 >=21）"
    assert REQUIRED_DEPT_HEAD <= perms, f"dept_head 缺权限: {REQUIRED_DEPT_HEAD - perms}"
    assert "system:access" in perms


def test_project_manager_inherits_dept_head_chain():
    reg = PermissionRegistry()
    perms = reg.resolve_role_permissions("project_manager")
    assert "system:access" in perms  # #inherit:dept_head → #inherit:user → system:access
    assert "department:update" in perms  # 从 dept_head 继承的部门管理权限


def test_dept_head_data_scopes_present():
    reg = PermissionRegistry()
    scopes = reg.get_data_scopes_for_role("dept_head")
    assert {"project_member", "knowledge_dept", "doc_owner", "doc_project_member"} <= set(scopes)
