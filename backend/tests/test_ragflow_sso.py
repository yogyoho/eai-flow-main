# EAI-CUSTOM: RAGFlow SSO integration tests — 本地定制,非上游.

import time
import uuid
from types import SimpleNamespace

import pytest

# EAI-CUSTOM: 测试用共享密钥(≥32 字符),仅用于本地单测,非生产值.
SECRET = "shared-secret-for-tests-only-32+chars"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def _fresh_config(monkeypatch):
    """get_extensions_config() caches a singleton at first use; reset it so each
    test's EAI_SSO_SHARED_SECRET / RAGFLOW_API_KEY monkeypatching is actually
    read (same mechanism as test_extensions_auth_facade.py's singleton patch)."""
    monkeypatch.setattr("app.extensions.config._extensions_config", None)
    yield


@pytest.fixture
async def sso_db(tmp_path):
    """In-SQLite async session over the ragflow_credentials table only.

    The users table cannot be created on SQLite (its tags column is a PG ARRAY
    that the SQLite compiler rejects), and the service only reads
    user.id/user.username off a namespace, so the FK target is left absent
    (SQLite does not enforce FKs without the pragma). Importing
    app.extensions.models registers users into the shared metadata so the FK
    resolves; the table-subset create_all mirrors test_auth.py's
    ``tables=[...]`` pattern.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.extensions.models  # noqa: F401  — 注册 users 表进共享 metadata 供 FK 解析（只 import，不建表）
    from app.extensions.ragflow_sso.models import RagflowCredential

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ragflow_sso.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(RagflowCredential.metadata.create_all, tables=[RagflowCredential.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_ragflow_config_reads_sso_secret(monkeypatch):
    from app.extensions.config import RAGFlowConfig

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", "abc123")
    cfg = RAGFlowConfig.from_env()
    assert cfg.sso_secret == "abc123"


def test_ragflow_config_sso_secret_default_empty(monkeypatch):
    from app.extensions.config import RAGFlowConfig

    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    cfg = RAGFlowConfig.from_env()
    assert cfg.sso_secret == ""


def test_credential_model_registered_in_metadata():
    import subprocess
    import sys
    from pathlib import Path

    # EAI-CUSTOM: guards the models/__init__ aggregation import — if it is
    # removed/reordered, create_all silently drops the table and the first
    # SSO exchange dies on a missing relation. Runs in a fresh interpreter so
    # pytest-session imports cannot make this self-fulfilling.
    probe = "import app.extensions.models; from app.extensions.database import Base; assert 'ragflow_credentials' in Base.metadata.tables"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


# ── service: mint + exchange + per-user credential store ──


def test_mint_ragflow_jwt_claims(_fresh_config, monkeypatch):
    import jwt as pyjwt

    from app.extensions.ragflow_sso.service import mint_ragflow_jwt

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    token = mint_ragflow_jwt(user_id="11111111-1111-1111-1111-111111111111", username="admin")
    claims = pyjwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],
        audience="ragflow-sso",
    )
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["username"] == "admin"
    assert claims["role"] == "user"
    assert claims["type"] == "access"
    assert 590 <= claims["exp"] - time.time() < 700  # ~10 min TTL


def test_mint_requires_secret(_fresh_config, monkeypatch):
    from app.extensions.ragflow_sso.service import mint_ragflow_jwt

    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        mint_ragflow_jwt(user_id="x", username="x")


@pytest.mark.anyio
async def test_exchange_mode_web(_fresh_config, monkeypatch):
    """web mode → POST to RAGFlow exchange, return access_token from data."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.ragflow_sso import service

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    captured = {}

    async def fake_request(method, url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["auth_header"] = kwargs.get("headers", {}).get("Authorization", "")
        return httpx.Response(200, json={"code": 0, "data": {"access_token": "sess-abc"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), username="admin")
    result = await service.exchange_mode_web(user=user)
    assert result == "sess-abc"
    assert captured["url"].endswith("/api/v1/auth/sso/exchange")
    assert captured["json"] == {"mode": "web"}
    assert captured["auth_header"].startswith("Bearer ")


@pytest.mark.anyio
async def test_exchange_mode_web_http_failure(_fresh_config, monkeypatch):
    """web mode non-200 → RuntimeError."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.ragflow_sso import service

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)

    async def fake_request(method, url, **kwargs):
        return httpx.Response(401, json={"code": 401, "message": "invalid token"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), username="admin")
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await service.exchange_mode_web(user=user)


@pytest.mark.anyio
async def test_exchange_mode_web_missing_token(_fresh_config, monkeypatch):
    """web mode 200 without access_token in data → RuntimeError (no silent empty token)."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.ragflow_sso import service

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)

    async def fake_request(method, url, **kwargs):
        return httpx.Response(200, json={"code": 0, "data": {}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), username="admin")
    with pytest.raises(RuntimeError, match="no access_token"):
        await service.exchange_mode_web(user=user)


@pytest.mark.anyio
async def test_get_or_issue_api_token_persists(_fresh_config, monkeypatch, sso_db):
    """api mode → token cached in RagflowCredential; second call reads cache (no HTTP)."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.ragflow_sso import service

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    calls = {"n": 0}
    captured = {}

    async def fake_request(method, url, **kwargs):
        calls["n"] += 1
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"code": 0, "data": {"api_token": "ragflow-xyz"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    # EAI-CUSTOM: 走库的 user id 必须含 a-f 十六进制字母——SQLite 对裸 UUID 声明的列给
    # NUMERIC 亲和性，纯数字 hex(如 2222...2222)落库被转成 REAL，读回时 Uuid 结果处理崩;
    # PG 无此强转，生产不受影响。
    user = SimpleNamespace(id=uuid.UUID("aaa22222-2222-4222-8222-a2222222eeee"), username="ops")
    t1 = await service.get_or_issue_api_token(sso_db, user)
    t2 = await service.get_or_issue_api_token(sso_db, user)
    assert t1 == t2 == "ragflow-xyz"
    assert calls["n"] == 1  # second call served from cache
    assert captured["json"] == {"mode": "api"}


@pytest.mark.anyio
async def test_get_or_issue_api_token_http_failure_persists_nothing(_fresh_config, monkeypatch, sso_db):
    """Non-200 exchange → RuntimeError; no credential row is persisted."""
    from unittest.mock import AsyncMock

    import httpx
    from sqlalchemy import select

    from app.extensions.ragflow_sso import service
    from app.extensions.ragflow_sso.models import RagflowCredential

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    calls = {"n": 0}

    async def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return httpx.Response(401, json={"code": 401, "message": "invalid token"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uuid.UUID("bbb33333-3333-4333-8333-b3333333eeee"), username="ops")
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await service.get_or_issue_api_token(sso_db, user)
    assert calls["n"] == 1
    rows = (await sso_db.execute(select(RagflowCredential))).scalars().all()
    assert rows == []


@pytest.mark.anyio
async def test_get_client_for_user_falls_back_without_secret(_fresh_config, monkeypatch):
    """SSO unconfigured → shared-key RAGFlowClient, no exchange HTTP call."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.knowledge.client import RAGFlowClient
    from app.extensions.ragflow_sso import service

    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)
    calls = {"n": 0}

    async def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return httpx.Response(200, json={"code": 0, "data": {"api_token": "should-not-be-used"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uuid.UUID("44444444-4444-4444-4444-444444444444"), username="any")
    client = await service.get_client_for_user(db=None, user=user)
    assert isinstance(client, RAGFlowClient)
    assert client.api_key == ""  # shared key default in tests
    assert calls["n"] == 0


@pytest.mark.anyio
async def test_get_client_for_user_uses_cached_token(_fresh_config, monkeypatch, sso_db):
    """SSO configured + cached credential → client bound to the per-user token, no HTTP."""
    from unittest.mock import AsyncMock

    import httpx

    from app.extensions.ragflow_sso import service
    from app.extensions.ragflow_sso.models import RagflowCredential

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)
    uid = uuid.UUID("ccc55555-5555-4555-8555-c5555555eeee")
    sso_db.add(RagflowCredential(eai_user_id=uid, api_token="cached-token"))
    await sso_db.commit()
    calls = {"n": 0}

    async def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return httpx.Response(200, json={"code": 0, "data": {"api_token": "should-not-be-used"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = SimpleNamespace(id=uid, username="ops")
    client = await service.get_client_for_user(sso_db, user)
    assert client.api_key == "cached-token"
    assert calls["n"] == 0


@pytest.mark.anyio
async def test_get_client_for_user_rollback_keeps_session_usable(_fresh_config, monkeypatch, sso_db):
    """Fallback on exchange failure rolls the session back so the caller's request
    survives (no PendingRollbackError poisoning subsequent queries on the same session)."""
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from app.extensions.knowledge.client import RAGFlowClient
    from app.extensions.ragflow_sso import service

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)

    async def boom(db, user):
        raise RuntimeError("exchange failed")

    monkeypatch.setattr(service, "get_or_issue_api_token", AsyncMock(side_effect=boom))
    user = SimpleNamespace(id=uuid.UUID("ddd66666-6666-4666-8666-d6666666eeee"), username="ops")
    client = await service.get_client_for_user(sso_db, user)
    assert isinstance(client, RAGFlowClient)
    assert client.api_key == ""  # shared-key fallback
    assert (await sso_db.execute(select(1))).scalar() == 1  # same session still usable


# ── routers: /ragflow-sso/login 302 + /token per-user ──

LOGIN_URL = "/api/extensions/auth/ragflow-sso/login"
TOKEN_URL = "/api/extensions/auth/ragflow-sso/token"


def _sso_app(*, user=None, db):
    """挂**真实 auth router** 的最小 app（ragflow-sso 子路由经 router.include_router
    注册在 /api/extensions/auth 前缀下——测试因此同时钉住挂载路径）。

    - get_db → 夹具 session（sqlite 真库语义）；
    - user 给定时才 override get_current_user；None → 真依赖走 Gateway cookie
      校验 → 401（守卫即被测行为）。
    - httpx ASGITransport 而非 TestClient：async sqlite 夹具 session 不能被
      TestClient 的 portal 线程拽进另一个事件循环（test_bid_materials.py 先例）。
    """
    from fastapi import FastAPI

    from app.extensions.auth.middleware import get_current_user
    from app.extensions.auth.routers import router as auth_router
    from app.extensions.database import get_db

    app = FastAPI()
    app.include_router(auth_router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    if user is not None:

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return app


@pytest.mark.anyio
async def test_login_endpoint_auth_gated(sso_db):
    """无 Gateway 会话（不 override get_current_user）→ 401。

    401 而非 404 同时证明两件事：路由已注册进 auth router **且** get_current_user
    守卫生效。/token 同验（同一依赖,一次钉住两个端点的守卫）。"""
    from httpx import ASGITransport, AsyncClient

    app = _sso_app(user=None, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(LOGIN_URL)).status_code == 401
        assert (await client.post(TOKEN_URL)).status_code == 401


@pytest.mark.anyio
async def test_login_redirects_with_auth_param(_fresh_config, monkeypatch, sso_db):
    """登录态 GET /login → 302 到 {RAGFLOW_BASE_URL}/?auth=<会话 token>
    （上游 root loader 落地 localStorage 并去参，前端零改动——RAGFlow spec §4）。"""
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient

    from app.extensions.ragflow_sso import routers
    from app.extensions.schemas import CurrentUser

    monkeypatch.setenv("RAGFLOW_BASE_URL", "http://ragflow.test:9380")  # 服务间地址,不用于跳转
    monkeypatch.setenv("RAGFLOW_WEB_URL", "http://localhost.test:9381")  # 浏览器可达 Web UI
    exchange = AsyncMock(return_value="sess-token")
    monkeypatch.setattr(routers, "exchange_mode_web", exchange)

    user = CurrentUser(
        id=uuid.UUID("aaa11111-1111-4111-8111-a1111111eeee"),
        username="admin",
        email="admin@eai-flow.com",
        status="active",
    )
    app = _sso_app(user=user, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(LOGIN_URL)  # httpx 默认不跟随重定向——Location 原样断言
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost.test:9381/?auth=sess-token"
    exchange.assert_awaited_once_with(user)


@pytest.mark.anyio
async def test_token_endpoint_returns_cached_token(_fresh_config, monkeypatch, sso_db):
    """/token 返回 per-user token——本测钉缓存命中路径（RagflowCredential 已落库,
    直接回读,不发 HTTP）；首签路径由 service 层 get_or_issue_api_token_* 覆盖。
    端点只走 get_or_issue_api_token（失败即 503）,共享 key 永不外发——由
    test_token_endpoint_never_returns_shared_key / _exchange_failure_503 钉住。"""
    from httpx import ASGITransport, AsyncClient

    from app.extensions.ragflow_sso.models import RagflowCredential
    from app.extensions.schemas import CurrentUser

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)  # 配置态（缓存命中其实不发 mint）
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)
    # EAI-CUSTOM: 走库的 user id 必须含 a-f 十六进制字母——SQLite NUMERIC 亲和性陷阱（见上文）
    uid = uuid.UUID("aaa88888-8888-4888-8888-a8888888eeee")
    sso_db.add(RagflowCredential(eai_user_id=uid, api_token="cached-token"))
    await sso_db.commit()

    user = CurrentUser(id=uid, username="ops", email="ops@eai-flow.com", status="active")
    app = _sso_app(user=user, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(TOKEN_URL)
    assert resp.status_code == 200
    assert resp.json() == {"api_token": "cached-token"}


@pytest.mark.anyio
async def test_token_endpoint_never_returns_shared_key(_fresh_config, monkeypatch, sso_db):
    """SSO 未配置（无共享 secret）→ 503 "RAGFlow SSO unavailable"。

    安全边界:共享 key 绝不经由此端点外发——否则任何登录用户可取回共享 key,
    绕过 per-user 审计与数据集可见性（spec §5/§6）。get_client_for_user 的
    共享 key 回退只存在于 KB 操作路径,不进 /token。"""
    from httpx import ASGITransport, AsyncClient

    from app.extensions.schemas import CurrentUser

    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)

    user = CurrentUser(
        id=uuid.UUID("bbb99999-9999-4999-8999-b9999999eeee"),
        username="ops",
        email="ops@eai-flow.com",
        status="active",
    )
    app = _sso_app(user=user, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(TOKEN_URL)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "RAGFlow SSO unavailable"


@pytest.mark.anyio
async def test_token_endpoint_exchange_failure_503(_fresh_config, monkeypatch, sso_db):
    """SSO 已配置但 RAGFlow 交换失败（401）→ 503——端点不降级到共享 key。"""
    from unittest.mock import AsyncMock

    import httpx
    from httpx import ASGITransport, AsyncClient

    from app.extensions.ragflow_sso import service
    from app.extensions.schemas import CurrentUser

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", SECRET)
    monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)

    async def fake_request(method, url, **kwargs):
        return httpx.Response(401, json={"code": 401, "message": "invalid token"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(service, "_exchange_request", AsyncMock(side_effect=fake_request))
    user = CurrentUser(
        id=uuid.UUID("ccc00000-0000-4000-8000-c0000000eeee"),
        username="ops",
        email="ops@eai-flow.com",
        status="active",
    )
    app = _sso_app(user=user, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(TOKEN_URL)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "RAGFlow SSO unavailable"


@pytest.mark.anyio
async def test_login_exchange_failure_500(_fresh_config, monkeypatch, sso_db):
    """/login 交换失败 → 未捕获 RuntimeError → HTTP 500（失败 UX 显式钉住:
    不伪 302、不静默回退）。ASGITransport raise_app_exceptions=False 使未处理
    异常呈 500 响应而非冒泡进测试。"""
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient

    from app.extensions.ragflow_sso import routers
    from app.extensions.schemas import CurrentUser

    monkeypatch.setattr(routers, "exchange_mode_web", AsyncMock(side_effect=RuntimeError("RAGFlow SSO exchange failed")))
    user = CurrentUser(
        id=uuid.UUID("ddd12345-1234-4123-8123-d1234567eeee"),
        username="admin",
        email="admin@eai-flow.com",
        status="active",
    )
    app = _sso_app(user=user, db=sso_db)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        resp = await client.get(LOGIN_URL)
    assert resp.status_code == 500
