"""S1 Task 2 验收: /health 豁免 + JWT 鉴权 401/200/403 + MCP streamable-http 端点可达.

计划: docs/superpowers/plans/2026-09-17-ontostudio-s1-backend.md Task 2（Step 2.5/2.6）。
验证层级 = 路由挂载 + SDK 构造不抛 + 鉴权语义（真连容器轮在 Task 4）。MCP 端点对普通
GET 的预期拒绝形态: stateless streamable-http 对无 ``Accept: text/event-stream`` 的 GET
返回 406 Not Acceptable——能走到 406 即证明 路由存在 → guard 放行 → SDK transport 应答。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient

from app.main import app as ontostudio_app


def test_health_open_without_auth():
    client = TestClient(ontostudio_app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "ontostudio-backend"}


def test_protected_endpoint_401_without_token():
    client = TestClient(ontostudio_app)
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"
    assert r.json()["detail"] == "Not authenticated"


def test_protected_endpoint_401_with_garbage_token():
    client = TestClient(ontostudio_app, headers={"Authorization": "Bearer not-a-jwt"})
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 401


def test_protected_endpoint_401_with_expired_token(make_token: Callable[..., str]):
    expired = make_token(expires_delta=timedelta(seconds=-60))
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {expired}"})
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 401


def test_protected_endpoint_200_with_valid_token(auth_headers):
    # object-types 端点只读本地 registry（不触 extensions DB）——200 即鉴权放行证据
    client = TestClient(ontostudio_app, headers=auth_headers)
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200
    body = r.json()
    assert body["object_types"] and body["link_types"]


def test_protected_endpoint_403_with_non_admin_token(make_token: Callable[..., str]):
    # v1 superadmin-only 口径: roles 不含 superadmin/admin → 403
    token = make_token(roles=("user",))
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 403
    assert "system:access" in r.json()["detail"]


def test_cookie_channel_accepted(make_token: Callable[..., str]):
    # D1: nginx 同源浏览器 HttpOnly cookie 通道
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token())
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200


def test_wrong_secret_token_rejected(make_token: Callable[..., str]):
    token = make_token(secret="some-other-secret-that-is-long-enough-32b")
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {token}"})
    assert client.get("/api/extensions/ontology/object-types").status_code == 401


# ── MCP streamable-http 端点 ──────────────────────────────────────────


def test_mcp_endpoints_registered_in_routes():
    paths = {getattr(r, "path", "") for r in ontostudio_app.routes}
    assert "/mcp/ontology" in paths
    assert "/mcp/doc-graph" in paths


def test_mcp_endpoints_reach_transport_on_plain_get():
    # 406 = 路由存在 + guard 放行（无内部 token 配置） + SDK transport Accept 校验应答
    with TestClient(ontostudio_app) as client:
        for path in ("/mcp/ontology", "/mcp/doc-graph"):
            r = client.get(path)
            assert r.status_code == 406, (path, r.status_code, r.text)


def test_mcp_guard_401_when_internal_token_configured(monkeypatch, make_token: Callable[..., str]):
    monkeypatch.setenv("ONTOSTUDIO_INTERNAL_AUTH_TOKEN", "s3cret-internal")
    with TestClient(ontostudio_app) as client:
        missing = client.get("/mcp/ontology")
        assert missing.status_code == 401
        wrong = client.get("/mcp/ontology", headers={"X-Internal-Auth": "wrong"})
        assert wrong.status_code == 401
        matched = client.get("/mcp/ontology", headers={"X-Internal-Auth": "s3cret-internal"})
        assert matched.status_code == 406  # 过 guard, 到 transport 的 Accept 校验
        bearer = client.get("/mcp/doc-graph", headers={"Authorization": f"Bearer {make_token()}"})
        assert bearer.status_code == 406  # Bearer JWT 亦可过 guard


def test_mcp_unsupported_method_405():
    with TestClient(ontostudio_app) as client:
        r = client.put("/mcp/ontology")
        assert r.status_code == 405
