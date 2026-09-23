"""S1 Task 2 验收: /health 豁免 + JWT 鉴权 401/200/403 + MCP streamable-http 端点可达.

计划: docs/superpowers/plans/2026-09-17-ontostudio-s1-backend.md Task 2（Step 2.5/2.6）。
验证层级 = 路由挂载 + SDK 构造不抛 + 鉴权语义（真连容器轮在 Task 4）。MCP 端点对普通
GET 的预期拒绝形态: stateless streamable-http 对无 ``Accept: text/event-stream`` 的 GET
返回 406 Not Acceptable——能走到 406 即证明 路由存在 → guard 放行 → SDK transport 应答。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app as ontostudio_app


def test_health_open_without_auth():
    client = TestClient(ontostudio_app)
    r = client.get("/health")
    assert r.status_code == 200
    # 逐字段断言（原先断言整个 body 相等）：/health 后续增长字段（如 Task 3 的 tables_ready）
    # 不该把这条「免鉴权可读」的用例打红——它守的是鉴权豁免与存活语义, 不是 body 的形状。
    assert r.json()["status"] == "ok"
    assert r.json()["service"] == "ontostudio-backend"


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


# ── alg 混淆/篡改回归钉（评审 Fix 4）────────────────────────────────────


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _forged_payload() -> dict:
    return {"sub": str(uuid.uuid4()), "username": "attacker", "exp": int(datetime.now(UTC).timestamp()) + 3600}


def test_alg_none_token_rejected():
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps(_forged_payload(), separators=(",", ":")).encode())
    token = f"{header}.{payload}."
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {token}"})
    assert client.get("/api/extensions/ontology/object-types").status_code == 401


def test_rs256_header_with_hs256_signature_rejected(jwt_test_secret: str):
    # 经典 alg 混淆: header 声称 RS256, 签名实为 HS256(secret)——algorithms=["HS256"] allowlist 必拒
    signing_input = f"{_b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())}.{_b64url(json.dumps(_forged_payload(), separators=(',', ':')).encode())}"
    sig = hmac.new(jwt_test_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{_b64url(sig)}"
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {token}"})
    assert client.get("/api/extensions/ontology/object-types").status_code == 401


def test_tampered_payload_rejected(make_token: Callable[..., str]):
    header_b64, _, sig_b64 = make_token().split(".")
    payload = _forged_payload()  # 换掉 sub/claims 但保留原签名
    forged = f"{header_b64}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}.{sig_b64}"
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {forged}"})
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


# ── v2 授权委托（S2 Task 3, EAI-CUSTOM）───────────────────────────────────────
# gateway upstream cookie 无角色 claims（claims 快路径必 miss）→ 携带原样 Cookie 反查
# gateway /api/permissions/me（UnifiedPermissionEngine）。is_admin / permissions 含目标点
# 即放行；TTL 缓存；gateway 不可达/非 200 fail-closed 403。

import httpx  # noqa: E402

import app.auth as ontostudio_auth  # noqa: E402  (与上方 app.main 同层, 置于用例区便于就近阅读)


class _FakeResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _FakeAsyncClient:
    """httpx.AsyncClient 替身：类属性 _behavior 下发给每次 get()；calls 记录调用轨迹."""

    behavior: tuple[int, object] | Exception = (200, {})
    calls: list[tuple[str, dict | None]] = []

    def __init__(self, **_kwargs: object):
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
        type(self).calls.append((url, headers))
        behavior = type(self).behavior
        if isinstance(behavior, Exception):
            raise behavior
        return _FakeResponse(*behavior)


def _install_fake_gateway(monkeypatch, behavior: tuple[int, object] | Exception) -> None:
    monkeypatch.setattr(ontostudio_auth.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.behavior = behavior
    _FakeAsyncClient.calls = []
    ontostudio_auth._authz_cache.clear()
    monkeypatch.setenv("ONTOSTUDIO_GATEWAY_URL", "http://gateway-test:9999")


def test_delegated_admin_cookie_allowed(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, (200, {"is_admin": True, "permissions": []}))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200
    # 委托确实发生：原样 Cookie 透传 + env 覆盖的 gateway 基址生效
    assert len(_FakeAsyncClient.calls) == 1
    url, headers = _FakeAsyncClient.calls[0]
    assert url.startswith("http://gateway-test:9999/api/permissions/me")
    assert "access_token=" in (headers or {}).get("Cookie", "")


def test_delegated_permission_member_allowed(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, (200, {"is_admin": False, "permissions": ["kb:read", "system:access"]}))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200


def test_delegated_denied_without_permission(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, (200, {"is_admin": False, "permissions": ["kb:read"]}))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 403
    assert "system:access" in r.json()["detail"]


def test_delegated_failclosed_on_gateway_unreachable(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, httpx.ConnectError("connection refused"))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 403


def test_delegated_failclosed_on_gateway_401(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, (401, {"detail": "Not authenticated"}))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 403


def test_delegated_result_cached_within_ttl(monkeypatch, make_token: Callable[..., str]):
    _install_fake_gateway(monkeypatch, (200, {"is_admin": True, "permissions": []}))
    client = TestClient(ontostudio_app)
    client.cookies.set("access_token", make_token(roles=()))
    assert client.get("/api/extensions/ontology/object-types").status_code == 200
    assert client.get("/api/extensions/ontology/object-types").status_code == 200
    # 第二次命中 TTL 缓存：gateway 只被反查一次
    assert len(_FakeAsyncClient.calls) == 1


def test_bearer_without_roles_and_no_cookie_denied_without_delegation(
    monkeypatch, make_token: Callable[..., str]
):
    # Bearer 通道无角色 claims 且无 Cookie 可透传 → 不打 gateway 直接 403（fail-closed 零网络）
    _install_fake_gateway(monkeypatch, (200, {"is_admin": True}))
    token = make_token(roles=())
    client = TestClient(ontostudio_app, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 403
    assert _FakeAsyncClient.calls == []


# ── 授权缓存键回归（EAI-CUSTOM 2026-09-22）────────────────────────────────
# _authz_cache 的键必须是 (user.id, permission)：历史实现只按 user.id 做键，而值的语义
# 是"某一次查询的那个权限是否放行"——只查 system:access 时未暴露；本体动作层引入
# ontology:action:review 后，同一用户在 TTL 内查两个权限会命中错误缓存。


class _SeqAsyncClient:
    """按调用顺序返回不同 payload 的 httpx.AsyncClient 替身（同用户两权限不串味用）."""

    payloads: list[object] = []
    calls: int = 0

    def __init__(self, **_kwargs: object):
        pass

    async def __aenter__(self) -> _SeqAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:  # noqa: ARG002
        idx = type(self).calls
        type(self).calls += 1
        return _FakeResponse(200, type(self).payloads[idx])


def _install_seq_gateway(monkeypatch, payloads: list[object]) -> None:
    """gateway 替身：第 n 次反查返回 payloads[n]——不同权限可得不同答案."""
    monkeypatch.setattr(ontostudio_auth.httpx, "AsyncClient", _SeqAsyncClient)
    _SeqAsyncClient.payloads = list(payloads)
    _SeqAsyncClient.calls = 0
    ontostudio_auth._authz_cache.clear()
    monkeypatch.setenv("ONTOSTUDIO_GATEWAY_URL", "http://gateway-test:9999")


class _FakeRequest:
    """_gateway_authorizes 只读 request.headers['cookie']，无需真 Request."""

    def __init__(self, cookie: str = "access_token=fake-cookie") -> None:
        self.headers = {"cookie": cookie}


@pytest.mark.asyncio
async def test_authz_cache_does_not_cross_contaminate_permissions(monkeypatch):
    """同一用户查两个权限不得串味——两个权限各反查 gateway 一次，答案各自独立.

    判别力（变异验证）：把缓存键改回 ``user.id`` 单键后，第二次调用命中第一次的缓存值
    （gateway 只被反查 1 次，且第二个断言拿到第一个权限的 True）→ 本用例红。
    """
    _install_seq_gateway(
        monkeypatch,
        [
            {"is_admin": False, "permissions": ["system:access"]},
            {"is_admin": False, "permissions": ["kb:read"]},
        ],
    )
    user = ontostudio_auth.CurrentUser(id=uuid.uuid4(), username="tester", email="tester@local")
    request = _FakeRequest()

    assert await ontostudio_auth._gateway_authorizes(request, user, "system:access") is True
    assert await ontostudio_auth._gateway_authorizes(request, user, "ontology:action:review") is False
    assert _SeqAsyncClient.calls == 2, "两个权限必须各反查一次 gateway（单键缓存会串味成 1 次）"
