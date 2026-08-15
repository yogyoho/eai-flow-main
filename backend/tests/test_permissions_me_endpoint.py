"""/api/permissions/me 端点 HTTP 测试（修复前 0 覆盖）。

真实 registry + canned identity + mock policy 行；验证超管全集、策略 grant/deny、
以及 /me 与 require_permission 的一致性（deny 时端点 403）。
"""

from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_row, policy_rows_db

from app.extensions.auth.permission_routers import router


def test_me_superadmin_full_set_and_is_admin(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    tc = build_app(router, user=make_user(role_name="超级管理员"), db=policy_rows_db([]))
    r = tc.get("/api/permissions/me")
    assert r.status_code == 200
    data = r.json()
    assert data["is_admin"] is True
    assert data["permissions"], "超管应展开为具体权限点全集"
    assert "*" not in data["permissions"], "list_permissions 输出具体点，不含裸通配"


def test_me_policy_grant_appears_and_deny_overrides(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = policy_rows_db(
        [
            policy_row("grant_plus", grants={"permissions": ["kb:create", "kb:update", "kb:delete"]}),
            policy_row("deny_delete", grants={"deny_permissions": ["kb:delete"]}),
        ]
    )
    tc = build_app(router, user=make_user(role_name="普通用户"), db=db)
    data = tc.get("/api/permissions/me").json()
    perms = set(data["permissions"])
    assert "kb:read" in perms  # user base
    assert "kb:create" in perms  # 策略授予
    assert "kb:update" in perms  # 策略授予、未被 deny
    assert "kb:delete" not in perms  # deny-overrides 压过策略授予


def test_me_deny_consistent_with_endpoint_403(monkeypatch):
    from fastapi import APIRouter, Depends

    from app.extensions.auth.middleware import require_permission

    # 最小 gate 端点：与 /me 用同一 require_permission + 同一 policy 集
    probe = APIRouter()

    @probe.get("/ping-kb")
    async def ping_kb(_u=Depends(require_permission("kb:read"))):
        return {"ok": True}

    identity = fake_identity(role_code="user")
    patch_identity(monkeypatch, identity)
    rows = [policy_row("deny_read", grants={"deny_permissions": ["kb:read"]})]
    db = policy_rows_db(rows)

    # /me：kb:read 被 deny
    me_data = build_app(router, db=db).get("/api/permissions/me").json()
    assert "kb:read" not in set(me_data["permissions"])

    # 同一 policy 集下 gate 端点 403
    assert build_app(probe, db=db).get("/ping-kb").status_code == 403
