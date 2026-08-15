"""deny_permissions 策略 → 真实 HTTP 端点 403（Y 被拒 / Z 放行 / 超管豁免 / 空条件全员）。"""

import pytest
from fastapi import APIRouter, Depends
from rbac_helpers import build_app, fake_identity, make_user, patch_identity, policy_row, policy_rows_db

from app.extensions.auth.middleware import require_permission

probe = APIRouter()


@probe.get("/ping-kb")
async def ping_kb(_u=Depends(require_permission("kb:read"))):
    return {"ok": True}


@pytest.mark.parametrize(
    "role,rows,expected",
    [
        ("user", [policy_row("d", grants={"deny_permissions": ["kb:read"]})], 403),  # 精确点 deny
        ("user", [policy_row("d", grants={"deny_permissions": ["kb:*"]})], 403),  # 模块通配 deny
        ("user", [policy_row("d", grants={"deny_permissions": ["doc:read"]})], 200),  # 无关 deny → 放行
        ("user", [policy_row("d", conditions={"attr": "user_id", "op": "eq", "value": "someone-else"})], 200),  # 条件不匹配
        ("superadmin", [policy_row("d", grants={"deny_permissions": ["kb:read"]})], 200),  # 超管豁免
        ("user", [policy_row("d", conditions={}, grants={"deny_permissions": ["kb:read"]})], 403),  # 空条件=全员
    ],
)
def test_deny_to_endpoint(monkeypatch, role, rows, expected):
    patch_identity(monkeypatch, fake_identity(role_code=role))
    tc = build_app(probe, user=make_user(), db=policy_rows_db(rows))
    assert tc.get("/ping-kb").status_code == expected
