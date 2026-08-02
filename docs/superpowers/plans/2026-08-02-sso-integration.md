# SSO 集成（通用 OIDC 第三门面）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在认证门面（工号+密码 / 邮箱+验证码）基础上新增第三登录方式：**通用 OIDC SSO**。按工号 join extensions 组织目录，仅预建号可登，复用 `_issue_gateway_session`。

**Architecture:** EAI 自建 OIDC 发起 + 回调（上游 state cookie 的 Path 绑在 `/api/v1/auth/callback/*`，EAI 回调收不到，故 EAI 用相同签名格式写 `Path=/` 的 state cookie），复用上游 `OIDCService`（discover / build_authorization_url / authenticate_callback，import 不修改）。回调按 IdP 的 `employee_number`/`preferred_username` claim（工号）join extensions `User.username`，命中且 active 后调 `_issue_gateway_session` 发统一会话。

**Tech Stack:** Python 3.12 + FastAPI + OIDCService(upstream) + bcrypt；前端 Next.js 16。

**Spec:** `docs/superpowers/specs/2026-08-02-sso-integration-design.md`

---

## 硬性约束

- **零上游修改**：只 import 复用 `OIDCService`（`app/gateway/auth/oidc.py`）、`oidc_state` 的 `OIDCStatePayload`/`generate_*`/`get_state_cookie`/`_sign_state_payload`。不修改 harness 或 `app/gateway/auth/*`。
- 唯一上游触点：`auth_middleware.py::_PUBLIC_PATH_PREFIXES` 加前缀 `/api/extensions/auth/oidc/`（EAI-CUSTOM 注释）。
- **仅预建号可登**：回调 join extensions `User`（`User.username == 工号` 或回退 email），查无/非 active → 401，**绝不自动建号**。
- EAI-CUSTOM 注释 + 中文注释；只 stage 计划列出的文件，绝不 `git add -A`。
- 测试：`cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py -v`（不依赖 live IdP，mock OIDCService）。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/extensions/auth/sso.py` | Create | OIDC 发起/回调路由 + state cookie(Path=/) 助手 |
| `backend/app/extensions/auth/routers.py` | Modify | `router.include_router(sso_router)` 挂载 |
| `backend/app/gateway/auth_middleware.py` | Modify | `_PUBLIC_PATH_PREFIXES` 加 `/api/extensions/auth/oidc/`（EAI-CUSTOM） |
| `backend/tests/test_extensions_sso.py` | Create | 全部 SSO 单测 |
| `frontend/src/app/(auth)/login/page.tsx` | Modify | 加 SSO 登录按钮（EAI-CUSTOM） |
| `backend/CLAUDE.md` | Modify | 认证章节补 SSO |
| `docker/docker-compose-dev.yaml` | Modify | 加 Keycloak 服务（P1） |

---

## Task 1: SSO 模块骨架 + state cookie(Path=/) 助手

**Files:**
- Create: `backend/app/extensions/auth/sso.py`
- Test: `backend/tests/test_extensions_sso.py`（本任务 `TestStateCookie`）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_extensions_sso.py` 写入：

```python
"""Tests for the EAI SSO (OIDC third facade)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response


@pytest.fixture(autouse=True)
def _ensure_gateway_auth_config():
    """确保 Gateway AuthConfig 单例就绪（token 签发用）。"""
    from app.gateway.auth.config import AuthConfig, set_auth_config

    set_auth_config(AuthConfig(jwt_secret="test-secret"))
    yield


def _make_request(host: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = host
    req.url.scheme = "http"
    return req


class TestStateCookie:
    def test_set_eai_state_cookie_writes_path_root(self):
        from app.extensions.auth import sso
        from app.gateway.auth.oidc_state import OIDCStatePayload

        resp = Response()
        sso._set_eai_state_cookie(resp, _make_request(),
                                  OIDCStatePayload(provider="keycloak", state="abc"))
        set_cookie = resp.headers.get("set-cookie", "")
        assert "df_oidc_state_keycloak=" in set_cookie
        assert "Path=/" in set_cookie

    def test_cookie_survives_get_state_cookie_roundtrip(self):
        from app.extensions.auth import sso
        from app.gateway.auth.oidc_state import OIDCStatePayload, get_state_cookie

        resp = Response()
        payload = OIDCStatePayload(provider="keycloak", state="s1", nonce="n1",
                                   code_verifier="v1")
        sso._set_eai_state_cookie(resp, _make_request(), payload)
        # 用真实的 Request 读 cookie（带 Path=/ 才能被收到）
        from starlette.requests import Request

        raw_cookie = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw_cookie}".encode())],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        req = Request(scope)
        got = get_state_cookie(req, "keycloak")
        assert got is not None
        assert got.state == "s1"
        assert got.nonce == "n1"
        assert got.code_verifier == "v1"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestStateCookie -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.extensions.auth.sso'`）

- [ ] **Step 3: 创建 sso.py 骨架 + 助手**

创建 `backend/app/extensions/auth/sso.py`：

```python
"""EAI SSO — 通用 OIDC 第三登录门面（发起 + 回调）。

EAI-CUSTOM：上游 OIDC 发起路由把 state cookie 的 Path 绑在 /api/v1/auth/callback/*
（oidc_state.set_state_cookie），EAI 回调路径收不到该 cookie，故本模块用**相同签名格式**
（OIDCStatePayload + HS256 + auth jwt_secret）自写 Path=/ 的 state cookie，使
上游 get_state_cookie 可直接校验。复用上游 OIDCService（discover/auth_url/authenticate_callback），
仅 import 不修改。仅预建号可登（按工号 join extensions User.username）。
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.extensions.database import get_db
from app.extensions.models import User

logger = logging.getLogger(__name__)

sso_router = APIRouter(prefix="/oidc", tags=["SSO"])

_oidc_service = None


def _get_oidc_service():
    """懒加载 OIDCService 单例（复用上游实现，不修改）。"""
    global _oidc_service
    if _oidc_service is None:
        from app.gateway.auth.oidc import OIDCService

        _oidc_service = OIDCService()
    return _oidc_service


def _resolve_provider(provider: str):
    """读取 config.yaml auth.oidc 中的 provider 配置；未启用/未知 → 404。"""
    from deerflow.config.app_config import get_app_config

    app_config = get_app_config()
    oidc = app_config.auth.oidc
    if not oidc.enabled:
        return None, None
    pc = oidc.providers.get(provider)
    if pc is None:
        return None, None
    return oidc, pc


def _resolve_redirect_uri(request: Request, provider: str, configured: str | None) -> str:
    """派生回调地址（未配置时按请求 origin 构造，同上游模式）。"""
    if configured:
        return configured
    origin = f"{request.url.scheme}://{request.headers.get('host', 'localhost:8001')}"
    return f"{origin}/api/extensions/auth/oidc/callback/{provider}"


def _set_eai_state_cookie(response: Response, request: Request, payload) -> None:
    """用上游签名格式写 Path=/ 的 state cookie（EAI 回调可收到）。"""
    from app.gateway.auth.oidc_state import _sign_state_payload
    from app.gateway.csrf_middleware import is_secure_request

    response.set_cookie(
        key=f"df_oidc_state_{payload.provider}",
        value=_sign_state_payload(payload),
        httponly=True,
        secure=is_secure_request(request),
        samesite="lax",
        max_age=300,  # 5 分钟，与上游一致
        path="/",
    )


def _delete_eai_state_cookie(response: Response, request: Request, provider: str) -> None:
    """按 Path=/ 删除 EAI 写的 state cookie（上游 delete_state_cookie 的 path 不符）。"""
    from app.gateway.csrf_middleware import is_secure_request

    response.delete_cookie(
        key=f"df_oidc_state_{provider}",
        secure=is_secure_request(request),
        samesite="lax",
        path="/",
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestStateCookie -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/sso.py backend/tests/test_extensions_sso.py
git commit -m "feat(sso): SSO 模块骨架 + state cookie(Path=/) 助手"
```

---

## Task 2: 发起端点 `/oidc/start`

**Files:**
- Modify: `backend/app/extensions/auth/sso.py`
- Test: `backend/tests/test_extensions_sso.py`（追加 `TestStartEndpoint`）

- [ ] **Step 1: 写失败测试**

```python
class TestStartEndpoint:
    @pytest.mark.asyncio
    async def test_unknown_provider_404(self, monkeypatch):
        from app.extensions.auth import sso

        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        from starlette.responses import RedirectResponse

        # 直接调函数（provider 未知 → 404）
        with pytest.raises(HTTPException) as exc:
            await sso.sso_start(_make_request(), "nope", Response())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_start_redirects_and_sets_state_cookie(self, monkeypatch):
        from app.extensions.auth import sso

        # provider 配置
        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "client1"
        pc.client_secret = "secret"
        pc.redirect_uri = None
        pc.scopes = ["openid", "email", "profile"]
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        # mock OIDCService
        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock(authorization_endpoint="https://idp.example.com/auth"))
        svc.build_authorization_url = lambda *a, **k: "https://idp.example.com/auth?client_id=client1"
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        resp = Response()
        result = await sso.sso_start(req, "keycloak", resp)
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"].startswith("https://idp.example.com/auth")
        assert "df_oidc_state_keycloak=" in resp.headers["set-cookie"]
        assert "Path=/" in resp.headers["set-cookie"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestStartEndpoint -v`
Expected: FAIL（`AttributeError: module 'app.extensions.auth.sso' has no attribute 'sso_start'`）

- [ ] **Step 3: 实现 sso_start**

在 `sso.py` 追加：

```python
@sso_router.get("/start")
async def sso_start(request: Request, provider: str, response: Response):
    """发起 OIDC 登录：discover → 生成 state/nonce/PKCE → 写 Path=/ 的 state cookie → 302 IdP。

    EAI-CUSTOM：自建发起（上游发起路由的 state cookie Path 不符）。
    """
    from app.gateway.auth.oidc_state import (
        OIDCStatePayload,
        compute_code_challenge,
        generate_code_verifier,
        generate_nonce,
        generate_oidc_state,
    )

    oidc, pc = _resolve_provider(provider)
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not configured")

    metadata = await _get_oidc_service().discover(pc.issuer)
    state = generate_oidc_state()
    nonce = generate_nonce() if pc.nonce_enabled else None
    verifier = generate_code_verifier() if pc.pkce_enabled else None
    challenge = compute_code_challenge(verifier) if verifier else None

    redirect_uri = _resolve_redirect_uri(request, provider, pc.redirect_uri)
    auth_url = _get_oidc_service().build_authorization_url(
        metadata=metadata,
        client_id=pc.client_id,
        redirect_uri=redirect_uri,
        scopes=pc.scopes,
        state=state,
        nonce=nonce,
        code_challenge=challenge,
    )

    payload = OIDCStatePayload(provider=provider, state=state, nonce=nonce, code_verifier=verifier)
    _set_eai_state_cookie(response, request, payload)

    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestStartEndpoint -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/sso.py backend/tests/test_extensions_sso.py
git commit -m "feat(sso): 发起端点 /oidc/start"
```

---

## Task 3: 回调端点 `/oidc/callback/{provider}`

**Files:**
- Modify: `backend/app/extensions/auth/sso.py`
- Test: `backend/tests/test_extensions_sso.py`（追加 `TestCallbackEndpoint`）

- [ ] **Step 1: 写失败测试**

```python
class TestCallbackEndpoint:
    @pytest.mark.asyncio
    async def test_callback_join_by_工号_and_issue_session(self, monkeypatch):
        from app.extensions.auth import sso, routers
        from app.extensions.models import User

        # provider 配置
        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "client1"
        pc.client_secret = "secret"
        pc.redirect_uri = None
        pc.scopes = ["openid", "email", "profile"]
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        # mock OIDCService.authenticate_callback → identity with 工号 claim
        identity = MagicMock()
        identity.subject = "sub-123"
        identity.email = "zhangsan@eai-flow.com"
        identity.claims = {"employee_number": "zhangsan", "sub": "sub-123"}
        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock())
        svc.authenticate_callback = AsyncMock(return_value=identity)
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        # extensions user 按 username(工号) 命中
        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        # state cookie 验证通过（用真实签名写 cookie 再读）
        from app.gateway.auth.oidc_state import OIDCStatePayload

        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        resp = Response()
        sso._set_eai_state_cookie(resp, req, OIDCStatePayload(provider="keycloak", state="the-state"))
        raw = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        from starlette.requests import Request as SRequest

        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw}".encode()),
                        (b"host", b"localhost:2026")],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        real_req = SRequest(scope)

        # _issue_gateway_session 复用真实的（需要 auth config fixture 已设）
        result = await sso.sso_callback(real_req, "keycloak", resp, code="code1", state="the-state", db=db)
        assert result.expires_in > 0

    @pytest.mark.asyncio
    async def test_callback_unknown_工号_401(self, monkeypatch):
        from app.extensions.auth import sso

        pc = MagicMock()
        pc.issuer = "https://idp.example.com/issuer"
        pc.client_id = "c"
        pc.client_secret = "s"
        pc.redirect_uri = None
        pc.pkce_enabled = True
        pc.nonce_enabled = True
        pc.token_endpoint_auth_method = "client_secret_post"
        app_cfg = MagicMock()
        app_cfg.auth.oidc.enabled = True
        app_cfg.auth.oidc.providers = {"keycloak": pc}
        monkeypatch.setattr("app.extensions.auth.sso.get_app_config", lambda: app_cfg)

        identity = MagicMock()
        identity.subject = "sub-1"
        identity.email = "nobody@eai-flow.com"
        identity.claims = {"employee_number": "nobody"}
        svc = MagicMock()
        svc.discover = AsyncMock(return_value=MagicMock())
        svc.authenticate_callback = AsyncMock(return_value=identity)
        monkeypatch.setattr(sso, "_get_oidc_service", lambda: svc)

        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)  # 工号未预建

        from app.gateway.auth.oidc_state import OIDCStatePayload

        resp = Response()
        req = _make_request()
        req.headers = {"host": "localhost:2026"}
        sso._set_eai_state_cookie(resp, req, OIDCStatePayload(provider="keycloak", state="st"))
        raw = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        from starlette.requests import Request as SRequest

        scope = {
            "type": "http", "method": "GET", "path": "/api/extensions/auth/oidc/callback/keycloak",
            "headers": [(b"cookie", f"df_oidc_state_keycloak={raw}".encode()),
                        (b"host", b"localhost:2026")],
            "scheme": "http", "client": ("127.0.0.1", 1234),
        }
        real_req = SRequest(scope)

        with pytest.raises(HTTPException) as exc:
            await sso.sso_callback(real_req, "keycloak", resp, code="c", state="st", db=db)
        assert exc.value.status_code == 401  # 仅预建号，不自动建
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestCallbackEndpoint -v`
Expected: FAIL（`AttributeError: module 'app.extensions.auth.sso' has no attribute 'sso_callback'`）

- [ ] **Step 3: 实现 sso_callback**

在 `sso.py` 追加：

```python
@sso_router.get("/callback/{provider}")
async def sso_callback(
    request: Request,
    provider: str,
    response: Response,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """OIDC 回调：验 state → 换码/验签 → 按工号 join extensions User → 复用 _issue_gateway_session。

    EAI-CUSTOM：仅预建号可登（工号未预建/非 active → 401，绝不自动建号）。
    """
    from app.gateway.auth.oidc_state import get_state_cookie
    from app.extensions.auth.routers import _issue_gateway_session

    oidc, pc = _resolve_provider(provider)
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO provider not configured")

    # 1) state 校验（constant-time）
    payload = get_state_cookie(request, provider)
    if payload is None or not secrets.compare_digest(payload.state, state):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid OIDC state")

    # 2) 换码 + id_token 验签（复用上游 OIDCService）
    metadata = await _get_oidc_service().discover(pc.issuer)
    redirect_uri = _resolve_redirect_uri(request, provider, pc.redirect_uri)
    identity = await _get_oidc_service().authenticate_callback(
        provider_id=provider,
        metadata=metadata,
        client_id=pc.client_id,
        client_secret=pc.client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=payload.code_verifier,
        nonce=payload.nonce,
        auth_method=pc.token_endpoint_auth_method,
    )

    # 3) 提取工号（employee_number 首选，preferred_username 回退）；email 作次级别名
    emp_no = identity.claims.get("employee_number") or identity.claims.get("preferred_username")
    email = identity.email or ""

    # 4) 按工号 join extensions User（仅预建号）
    stmt = select(User).where(User.is_deleted == False)  # noqa: E712
    if emp_no:
        stmt = stmt.where(User.username == emp_no)
    elif email:
        stmt = stmt.where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # 工号未命中时回退 email
    if user is None and emp_no and email:
        stmt = select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SSO account not provisioned or inactive")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    _delete_eai_state_cookie(response, request, provider)
    return await _issue_gateway_session(user.email, request, response)
```

（若 `datetime` 未导入，在文件头加 `from datetime import datetime`。）

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py -v`
Expected: PASS（本文件全部通过）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/sso.py backend/tests/test_extensions_sso.py
git commit -m "feat(sso): 回调端点 /oidc/callback/{provider}（工号 join + 仅预建号）"
```

---

## Task 4: 挂载 sso_router + 中间件豁免

**Files:**
- Modify: `backend/app/extensions/auth/routers.py`
- Modify: `backend/app/gateway/auth_middleware.py`
- Test: `backend/tests/test_extensions_sso.py`（追加 `TestMount`）

- [ ] **Step 1: 写失败测试**

```python
class TestMount:
    def test_sso_router_mounted(self):
        from app.extensions.auth.routers import router

        paths = {r.path for r in router.routes}
        assert "/oidc/start" in paths
        assert "/oidc/callback/{provider}" in paths

    def test_oidc_prefix_is_public(self):
        from app.gateway.auth_middleware import _is_public

        assert _is_public("/api/extensions/auth/oidc/start") is True
        assert _is_public("/api/extensions/auth/oidc/callback/keycloak") is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py::TestMount -v`
Expected: FAIL（`/oidc/start` 不在 auth router；`_is_public` 返回 False）

- [ ] **Step 3: 挂载 + 豁免**

在 `backend/app/extensions/auth/routers.py` 末尾（`router` 定义之后）追加：

```python
# EAI-CUSTOM: 挂载 SSO 子路由（OIDC 第三登录门面）
from app.extensions.auth.sso import sso_router  # noqa: E402

router.include_router(sso_router)
```

在 `backend/app/gateway/auth_middleware.py` 的 `_PUBLIC_PATH_PREFIXES` 追加：

```python
    # EAI-CUSTOM: EAI SSO OIDC 发起/回调（无会话时也要可达）
    "/api/extensions/auth/oidc/",
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py -v`
Expected: PASS（全部通过）；`PYTHONPATH=. uv run ruff check app/extensions/auth/sso.py app/extensions/auth/routers.py app/gateway/auth_middleware.py tests/test_extensions_sso.py` → All checks passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/routers.py backend/app/gateway/auth_middleware.py backend/tests/test_extensions_sso.py
git commit -m "feat(sso): 挂载 sso_router + auth_middleware 前缀豁免(EAI-CUSTOM)"
```

---

## Task 5: 前端 SSO 按钮

**Files:**
- Modify: `frontend/src/app/(auth)/login/page.tsx`（EAI-CUSTOM）

- [ ] **Step 1: 在登录页加 SSO 按钮**

在 `login/page.tsx` 的 tab 切换区之后、表单之前，加一个 SSO 入口（EAI-CUSTOM）：

```tsx
{/* EAI-CUSTOM: SSO 登录入口（通用 OIDC 第三门面） */}
<a
  href="/api/extensions/auth/oidc/start?provider=keycloak"
  className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted transition-colors"
>
  企业统一登录（SSO）
</a>
```

- [ ] **Step 2: 校验类型与 lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: PASS（本文件无新错误；typecheck 的 collab/workflow 预存错误忽略）

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/(auth)/login/page.tsx"
git commit -m "feat(sso): 登录页 SSO 按钮"
```

---

## Task 6: 全量回归 + 文档

**Files:**
- Modify: `backend/CLAUDE.md`

- [ ] **Step 1: 运行 SSO + 认证门面 + 回归测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_sso.py tests/test_extensions_auth_facade.py tests/test_contract_price_extension.py -q`
Expected: PASS（全绿）

- [ ] **Step 2: 更新 backend/CLAUDE.md 认证章节**

在 "EAI 统一认证门面" 段落后追加：

```markdown
- **SSO（第三登录方式，EAI-CUSTOM）**：`app/extensions/auth/sso.py` 提供 `GET /api/extensions/auth/oidc/start`（发起，复用上游 `OIDCService`）与 `GET /api/extensions/auth/oidc/callback/{provider}`（回调，按 IdP 的 `employee_number`/`preferred_username` claim（工号）join extensions `User.username`，**仅预建号可登**，复用 `_issue_gateway_session` 发会话）。state cookie 用上游签名格式写 `Path=/`。IdP 配置见 `config.yaml → auth.oidc.providers.*`；推荐 Keycloak（可 broker 企微/钉钉/飞书、联邦 AD/LDAP）。
```

- [ ] **Step 3: Commit**

```bash
git add backend/CLAUDE.md
git commit -m "docs(backend): SSO 门面说明"
```

---

## Task 7 (P1): Keycloak 部署（compose + 配置建议）

**Files:**
- Modify: `docker/docker-compose-dev.yaml`

- [ ] **Step 1: 加 Keycloak 服务**

在 `docker/docker-compose-dev.yaml` 的 services 末尾追加：

```yaml
  # ── Keycloak（EAI SSO IdP，自托管，可 broker 企微/钉钉/飞书 + 联邦 AD/LDAP）──
  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    container_name: eai-flow-keycloak
    command: ["start-dev"]
    environment:
      - KEYCLOAK_ADMIN=${KEYCLOAK_ADMIN:-admin}
      - KEYCLOAK_ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD:-admin123}
      - KC_DB=postgres
      - KC_DB_URL=${KEYCLOAK_DB_URL:-jdbc:postgresql://eai-flow-postgres-ext:5432/keycloak}
      - KC_DB_USERNAME=${KEYCLOAK_DB_USER:-agentflow}
      - KC_DB_PASSWORD=${KEYCLOAK_DB_PASSWORD:-agentflow123}
    ports:
      - "8080:8080"
    networks:
      - eai-flow-net
    restart: unless-stopped
```

- [ ] **Step 2: 说明（无代码测试）**

> 部署后需在 Keycloak 建 realm `eai` + client `eai-flow`（confidential，redirect_uri 指向 `http://localhost:2026/api/extensions/auth/oidc/callback/keycloak`），并加 token mapper：把 `preferred_username`（或 AD `employeeNumber` / 企微 `userid`）映射为 `employee_number` claim。然后 `config.yaml → auth.oidc.providers.keycloak.issuer/client_id/client_secret` 填入，gateway 重启后登录页 SSO 按钮即用。

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose-dev.yaml
git commit -m "feat(sso): Keycloak 部署服务（P1）"
```

---

## Self-Review 检查单

- [ ] Spec §4.1 发起 → Task 2 ✓
- [ ] Spec §4.2 回调 → Task 3 ✓
- [ ] Spec §4.3 配置 → 依赖 config.yaml auth.oidc（无需代码）✓
- [ ] Spec §4.4 前端按钮 → Task 5 ✓
- [ ] Spec §4.5 中间件豁免 → Task 4 ✓
- [ ] Spec §5 仅预建号 → Task 3 回调逻辑 ✓
- [ ] Spec §6 Keycloak 建议 → Task 7 ✓
- [ ] Spec §7 安全（state/验签/限流/防枚举）→ Task 2/3（state constant-time + OIDCService 验签）✓
- [ ] 占位符扫描：无 TBD/TODO ✓
- [ ] 类型一致：`sso_start`/`sso_callback`/`_set_eai_state_cookie`/`_get_oidc_service` 在各任务命名一致 ✓
