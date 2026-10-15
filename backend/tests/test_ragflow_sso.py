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
