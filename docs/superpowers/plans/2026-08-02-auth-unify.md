# EAI 统一认证门面（工号+密码 / 邮箱+验证码）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 登录页双轨（工号+密码 / 邮箱+验证码）全部收敛到 EAI 登录门面，零上游 deerflow 代码改动。

**Architecture:** 重写 `app/extensions/auth/routers.py` 的 `/login` 为门面（username→email→gateway argon2 验证→签发 gateway 会话 cookie），新增 `app/extensions/auth/otp.py` 实现邮箱验证码（bcrypt 存储 + 企业 SMTP），两个登录方式共用 `_issue_gateway_session` 尾部例程。extensions PostgreSQL 是组织目录真源，gateway 是会话层（admin 建号时由现有 `sync.py` 自动镜像）。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy(asyncpg) + bcrypt + smtplib；前端 Next.js 16 + React 19 + Tailwind 4。

**Spec:** `docs/superpowers/specs/2026-08-02-auth-unify-design.md`

---

## 硬性约束

- **零上游改动**：不得修改 `packages/harness/deerflow/*`、`backend/app/gateway/auth/*`、`backend/app/gateway/routers/auth.py`。只 **import 复用**（`get_local_provider`、`create_access_token`、`get_auth_config`、`is_secure_request`）。凡改到上游同步的前端文件（`login/page.tsx`）须加 EAI-CUSTOM 注释。
- **测试运行方式**：`cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py -v`。测试不依赖 live PostgreSQL（用 fake session + monkeypatch）。
- **提交**：本分支 `main-dev-fork`；每个任务单独 commit。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/extensions/config.py` | Modify | 新增 `SmtpConfig`、`OtpConfig` |
| `backend/app/extensions/models/__init__.py` | Modify | 新增 `OtpCode` 模型 |
| `backend/app/extensions/auth/otp.py` | Create | OTP 生成/存储/校验/SMTP 发送 |
| `backend/app/extensions/auth/routers.py` | Modify | 重写 `login`、新增 `otp/send` + `login/otp`、禁用 `register` |
| `backend/app/extensions/schemas.py` | Modify | 新增 `FacadeLoginResponse`/`OtpSendRequest`/`OtpSendResponse`/`OtpLoginRequest` |
| `backend/tests/test_extensions_auth_facade.py` | Create | 全部门面测试 |
| `frontend/src/app/(auth)/login/page.tsx` | Modify | 双 tab 登录页（EAI-CUSTOM） |

---

## Task 1: SMTP + OTP 配置

**Files:**
- Modify: `backend/app/extensions/config.py`
- Test: `backend/tests/test_extensions_auth_facade.py`（本任务追加 `TestAuthConfig`）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_extensions_auth_facade.py` 顶部写入：

```python
"""Tests for the EAI auth facade (username+password / email+OTP login)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.config import ExtensionsConfig


@pytest.fixture(autouse=True)
def _ensure_gateway_auth_config():
    """Ensure the Gateway AuthConfig singleton is set so token issuance works in tests
    (otherwise get_auth_config() would auto-generate/persist a real .jwt_secret)."""
    from app.gateway.auth.config import AuthConfig, set_auth_config

    set_auth_config(AuthConfig(jwt_secret="test-secret"))
    yield


class TestAuthConfig:
    def test_smtp_defaults_disabled(self):
        cfg = ExtensionsConfig()
        assert cfg.smtp.enabled is False
        assert cfg.smtp.usable is False

    def test_smtp_usable_when_enabled_and_host(self):
        cfg = ExtensionsConfig()
        cfg.smtp.host = "smtp.example.com"
        cfg.smtp.enabled = True
        assert cfg.smtp.usable is True

    def test_otp_defaults(self):
        cfg = ExtensionsConfig()
        assert cfg.otp.length == 6
        assert cfg.otp.ttl_seconds == 300
        assert cfg.otp.send_cooldown_seconds == 60
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestAuthConfig -v`
Expected: FAIL（`ExtensionsConfig` 没有 `smtp`/`otp` 属性 → AttributeError）

- [ ] **Step 3: 实现配置**

在 `backend/app/extensions/config.py` 的 `JWTConfig` 之后插入两个类，并在 `ExtensionsConfig` 中挂接：

```python
class SmtpConfig(BaseModel):
    """SMTP configuration for OTP email sending (EAI-CUSTOM auth facade)."""

    host: str = Field(default="")
    port: int = Field(default=465)
    user: str = Field(default="")
    password: str = Field(default="")
    from_addr: str = Field(default="no-reply@eai-flow.com")
    use_tls: bool = Field(default=True)
    enabled: bool = Field(default=False)

    @property
    def usable(self) -> bool:
        return self.enabled and bool(self.host)

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        return cls(
            host=os.getenv("EAI_SMTP_HOST", ""),
            port=int(os.getenv("EAI_SMTP_PORT", "465")),
            user=os.getenv("EAI_SMTP_USER", ""),
            password=os.getenv("EAI_SMTP_PASSWORD", ""),
            from_addr=os.getenv("EAI_SMTP_FROM", "no-reply@eai-flow.com"),
            use_tls=os.getenv("EAI_SMTP_TLS", "true").lower() == "true",
            enabled=os.getenv("EAI_SMTP_ENABLED", "false").lower() == "true",
        )


class OtpConfig(BaseModel):
    """OTP login configuration (EAI-CUSTOM auth facade)."""

    length: int = Field(default=6, ge=4, le=10)
    ttl_seconds: int = Field(default=300, ge=60)
    send_cooldown_seconds: int = Field(default=60, ge=10)
    max_per_ip_per_hour: int = Field(default=20)

    @classmethod
    def from_env(cls) -> "OtpConfig":
        return cls(
            length=int(os.getenv("EAI_OTP_LENGTH", "6")),
            ttl_seconds=int(os.getenv("EAI_OTP_TTL_SECONDS", "300")),
            send_cooldown_seconds=int(os.getenv("EAI_OTP_SEND_COOLDOWN_SECONDS", "60")),
            max_per_ip_per_hour=int(os.getenv("EAI_OTP_MAX_PER_IP_HOUR", "20")),
        )
```

修改 `ExtensionsConfig`：

```python
class ExtensionsConfig(BaseModel):
    """Extensions module configuration."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    law: LawConfig = Field(default_factory=LawConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    otp: OtpConfig = Field(default_factory=OtpConfig)

    @classmethod
    def from_env(cls) -> "ExtensionsConfig":
        """Create config from environment variables."""
        return cls(
            database=DatabaseConfig.from_env(),
            jwt=JWTConfig.from_env(),
            ragflow=RAGFlowConfig.from_env(),
            storage=StorageConfig.from_env(),
            law=LawConfig.from_env(),
            smtp=SmtpConfig.from_env(),
            otp=OtpConfig.from_env(),
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestAuthConfig -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/config.py backend/tests/test_extensions_auth_facade.py
git commit -m "feat(auth): SMTP + OTP 配置（EAI 登录门面地基）"
```

---

## Task 2: OtpCode 模型

**Files:**
- Modify: `backend/app/extensions/models/__init__.py`
- Test: `backend/tests/test_extensions_auth_facade.py`（追加 `TestOtpModel`）

- [ ] **Step 1: 写失败测试**

```python
class TestOtpModel:
    def test_otp_codes_registered_on_shared_base(self):
        import app.extensions.auth  # noqa: F401  # ensure facade imported
        from app.extensions.database import Base

        assert "otp_codes" in Base.metadata.tables

    def test_otp_code_columns(self):
        from app.extensions.models import OtpCode

        row = OtpCode(email="a@b.com", code_hash="x", expires_at=datetime.now(UTC))
        assert row.email == "a@b.com"
        assert row.used_at is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpModel -v`
Expected: FAIL（`ImportError: cannot import name 'OtpCode'`）

- [ ] **Step 3: 实现模型**

在 `backend/app/extensions/models/__init__.py` 的 `SystemConfigEntry` 之后追加：

```python
class OtpCode(Base):
    """One-time password for email OTP login (EAI-CUSTOM auth facade)."""

    __tablename__ = "otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpModel -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_extensions_auth_facade.py
git commit -m "feat(auth): OtpCode 模型（otp_codes 表）"
```

---

## Task 3: OTP 核心逻辑（otp.py）

**Files:**
- Create: `backend/app/extensions/auth/otp.py`
- Test: `backend/tests/test_extensions_auth_facade.py`（追加 `TestOtpCore`）

- [ ] **Step 1: 写失败测试**

```python
class TestOtpCore:
    def test_generate_code_is_numeric_length(self):
        from app.extensions.auth.otp import generate_code

        code = generate_code(6)
        assert len(code) == 6
        assert code.isdigit()

    def test_code_is_valid_rejects_wrong_and_expired(self):
        from app.extensions.auth.jwt import hash_password
        from app.extensions.auth.otp import code_is_valid
        from app.extensions.models import OtpCode

        row = OtpCode(email="a@b.com", code_hash=hash_password("123456"), expires_at=datetime.now(UTC) + timedelta(minutes=5))
        assert code_is_valid(row, "123456", datetime.now(UTC)) is True
        assert code_is_valid(row, "000000", datetime.now(UTC)) is False

        expired = OtpCode(email="a@b.com", code_hash=hash_password("123456"), expires_at=datetime.now(UTC) - timedelta(minutes=1))
        assert code_is_valid(expired, "123456", datetime.now(UTC)) is False

    @pytest.mark.asyncio
    async def test_send_otp_echoes_when_smtp_disabled(self, monkeypatch):
        from app.extensions.auth import otp
        from app.extensions.config import ExtensionsConfig

        # Force SMTP-disabled config for the module singleton (auto-restored by monkeypatch).
        monkeypatch.setattr("app.extensions.config._extensions_config", ExtensionsConfig())

        code = await otp.send_otp_email("a@b.com", "123456")
        assert code == "123456"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpCore -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.extensions.auth.otp'`）

- [ ] **Step 3: 实现 otp.py**

```python
"""OTP login core — generate, store (bcrypt), verify, and email one-time passwords.

EAI-CUSTOM auth facade: pure EAI-owned code; reuses app.extensions.auth.jwt hashing.
"""

import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import hash_password, verify_password
from app.extensions.config import get_extensions_config
from app.extensions.models import OtpCode

logger = logging.getLogger(__name__)


def generate_code(length: int = 6) -> str:
    """Generate a cryptographically random numeric OTP."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def code_is_valid(row: OtpCode | None, code: str, now: datetime) -> bool:
    """Pure check: row exists, not expired, code hash matches."""
    if row is None:
        return False
    if row.expires_at < now:
        return False
    return verify_password(code, row.code_hash)


async def send_otp_email(email: str, code: str) -> str | None:
    """Send the OTP via enterprise SMTP.

    Returns the code when SMTP is disabled (dev/placeholder echo) — production
    must set EAI_SMTP_ENABLED=true. Returns None when the email was sent.
    """
    cfg = get_extensions_config().smtp
    if not cfg.usable:
        logger.warning("SMTP disabled; OTP for %s would have been sent (dev echo)", email)
        return code

    msg = EmailMessage()
    msg["Subject"] = "登录验证码"
    msg["From"] = cfg.from_addr
    msg["To"] = email
    msg.set_content(f"您的登录验证码是：{code}，{get_extensions_config().otp.ttl_seconds // 60} 分钟内有效。")

    if cfg.use_tls:
        with smtplib.SMTP_SSL(cfg.host, cfg.port) as s:
            if cfg.user:
                s.login(cfg.user, cfg.password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port) as s:
            s.starttls()
            if cfg.user:
                s.login(cfg.user, cfg.password)
            s.send_message(msg)
    return None


async def create_otp(db: AsyncSession, email: str) -> str | None:
    """Generate, store (bcrypt-hashed), and send an OTP for `email`. Returns dev-echo code or None."""
    cfg = get_extensions_config().otp
    code = generate_code(cfg.length)
    expires_at = datetime.now(UTC) + timedelta(seconds=cfg.ttl_seconds)
    db.add(OtpCode(email=email, code_hash=hash_password(code), expires_at=expires_at))
    await db.commit()
    return await send_otp_email(email, code)


async def verify_otp(db: AsyncSession, email: str, code: str) -> bool:
    """Verify the latest unused, unexpired OTP for `email`; mark it used on success."""
    stmt = (
        select(OtpCode)
        .where(OtpCode.email == email, OtpCode.used_at.is_(None))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if not code_is_valid(row, code, datetime.now(UTC)):
        return False
    row.used_at = datetime.now(UTC)
    await db.commit()
    return True
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpCore -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/otp.py backend/tests/test_extensions_auth_facade.py
git commit -m "feat(auth): OTP 生成/校验/SMTP 发送核心"
```

---

## Task 4: 密码登录门面（重写 /login + 会话签发）

**Files:**
- Modify: `backend/app/extensions/schemas.py`
- Modify: `backend/app/extensions/auth/routers.py`
- Test: `backend/tests/test_extensions_auth_facade.py`（追加 `TestPasswordLogin` + `TestIssueSession`）

- [ ] **Step 1: 写失败测试**

```python
def _make_request(host: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = host
    req.url.scheme = "http"
    return req


class TestPasswordLogin:
    @pytest.mark.asyncio
    async def test_login_success_issues_cookie(self, monkeypatch):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        gw_user = MagicMock()
        gw_user.id = uuid.uuid4()
        gw_user.token_version = 0

        async def fake_authenticate(creds):
            assert creds["email"] == "zhangsan@eai-flow.com"
            return gw_user

        provider = MagicMock()
        provider.authenticate = fake_authenticate
        # _issue_gateway_session 会 await provider.get_user_by_email()，必须是 AsyncMock，
        # 且 gw_user 要带真实 token_version=0 才可被 jwt.encode 序列化。
        provider.get_user_by_email = AsyncMock(return_value=gw_user)
        # login 与 _issue_gateway_session 体内都是 `from app.gateway.deps import get_local_provider`
        #（惰性导入），所以必须 patch app.gateway.deps 上的名字，而不是 routers 模块属性。
        monkeypatch.setattr("app.gateway.deps.get_local_provider", lambda: provider)

        from fastapi import Response
        from app.extensions.auth.routers import LoginRequest  # reuse existing schema

        resp = Response()
        from app.extensions.auth.routers import login
        result = await login(_make_request(), resp, LoginRequest(username="zhangsan", password="secret123"), db)
        assert result.expires_in > 0
        assert resp.headers["set-cookie"].startswith("access_token=")

    @pytest.mark.asyncio
    async def test_login_wrong_password_401(self, monkeypatch):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        async def fake_authenticate(creds):
            return None

        provider = MagicMock()
        provider.authenticate = fake_authenticate
        monkeypatch.setattr("app.gateway.deps.get_local_provider", lambda: provider)
        # Keep the self-heal resync a fast no-op (avoids a real argon2 hash in tests).
        monkeypatch.setattr("app.extensions.user.sync.sync_user_created", AsyncMock())

        from fastapi import Response
        from fastapi import HTTPException
        from app.extensions.auth.routers import LoginRequest, login

        resp = Response()
        with pytest.raises(HTTPException) as exc:
            await login(_make_request(), resp, LoginRequest(username="zhangsan", password="bad"), db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user_401(self):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="disabled")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)

        from fastapi import Response
        from fastapi import HTTPException
        from app.extensions.auth.routers import LoginRequest, login

        with pytest.raises(HTTPException) as exc:
            await login(_make_request(), Response(), LoginRequest(username="zhangsan", password="x"), db)
        assert exc.value.status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestPasswordLogin -v`
Expected: FAIL（`ImportError` / 登录端点仍是旧的 extensions JWT 流程，响应不含 `expires_in` cookie）

- [ ] **Step 3: 在 schemas.py 追加门面响应模型**

在 `backend/app/extensions/schemas.py` 的 `LoginResponse` 之后追加：

```python
class FacadeLoginResponse(BaseModel):
    """EAI login facade response — Gateway-style session (cookie carries the token)."""

    expires_in: int
    needs_setup: bool = False


class OtpSendRequest(BaseModel):
    """OTP send request."""

    email: EmailStr


class OtpSendResponse(BaseModel):
    """OTP send response."""

    sent: bool = True
    # EAI-CUSTOM: dev/placeholder echo when SMTP disabled — production MUST be None.
    debug_code: str | None = None


class OtpLoginRequest(BaseModel):
    """OTP login request."""

    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)
```

- [ ] **Step 4: 重写 routers.py 的 login + 新增 _issue_gateway_session**

修改 `backend/app/extensions/auth/routers.py`：

把头部导入改为（追加到现有导入中）：

```python
from app.extensions.schemas import (
    FacadeLoginResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    OtpLoginRequest,
    OtpSendRequest,
    OtpSendResponse,
    RefreshTokenRequest,
    UserCreate,
    UserResponse,
)
```

在 `logger = logging.getLogger(__name__)` 之后、`router = ...` 之前，插入会话签发与限流助手：

```python
# EAI-CUSTOM: Gateway session issuance + per-IP rate limiting for the auth facade.
# Reuses upstream building blocks (get_local_provider / create_access_token /
# get_auth_config / is_secure_request) — no upstream code is modified.
async def _issue_gateway_session(email: str, request: Request, response: Response) -> FacadeLoginResponse:
    from app.gateway.auth import create_access_token
    from app.gateway.auth.config import get_auth_config
    from app.gateway.csrf_middleware import is_secure_request
    from app.gateway.deps import get_local_provider

    provider = get_local_provider()
    gw_user = await provider.get_user_by_email(email)
    if gw_user is None:
        gw_user = await provider.create_user(email=email, password=None, system_role="user", needs_setup=False)

    token = create_access_token(str(gw_user.id), token_version=gw_user.token_version)
    config = get_auth_config()
    is_https = is_secure_request(request)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=config.token_expiry_days * 24 * 3600 if is_https else None,
    )
    return FacadeLoginResponse(expires_in=config.token_expiry_days * 24 * 3600)


_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300
_login_attempts: dict[str, tuple[int, float]] = {}


def _check_login_rate_limit(ip: str) -> None:
    import time

    record = _login_attempts.get(ip)
    if record and record[0] >= _MAX_LOGIN_ATTEMPTS and time.time() < record[1]:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.")


def _record_login_failure(ip: str) -> None:
    import time

    count, until = _login_attempts.get(ip, (0, 0.0))
    count += 1
    until = time.time() + _LOCKOUT_SECONDS if count >= _MAX_LOGIN_ATTEMPTS else until
    _login_attempts[ip] = (count, until)
```

**替换整个旧的 `login` 端点**（现在是 35-84 行的那个，返回 extensions JWT）：

```python
@router.post("/login", response_model=FacadeLoginResponse)
async def login(request: Request, response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """EAI login facade — username (or email) + password.

    EAI-CUSTOM: extensions is the org directory (username→email); Gateway verifies
    the password (argon2, mirrored by user/sync.py on admin create/change) and owns
    the session cookie. Falls back to best-effort resync once if the Gateway row is missing.
    """
    from app.gateway.deps import get_local_provider

    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)

    identifier = body.username.strip()
    stmt = select(User).where(User.is_deleted == False)  # noqa: E712
    if "@" in identifier:
        stmt = stmt.where(User.email == identifier)
    else:
        stmt = stmt.where(User.username == identifier)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or user.status != "active":
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    provider = get_local_provider()
    gw_user = await provider.authenticate({"email": user.email, "password": body.password})
    if gw_user is None:
        # Self-heal: gateway mirror row may be missing/stale (admin sync failure). Best-effort resync then retry once.
        from app.extensions.user import sync as user_sync

        await user_sync.sync_user_created(db, user.email, body.password, user.role_id)
        gw_user = await provider.authenticate({"email": user.email, "password": body.password})
    if gw_user is None:
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    return await _issue_gateway_session(user.email, request, response)
```

**将旧的 `register` 端点改为禁用**（企业无自注册，安全加固；原实现删除）：

```python
@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_403_FORBIDDEN)
async def register(request: UserCreate, db: AsyncSession = Depends(get_db)):
    """EAI-CUSTOM: self-registration disabled — users are created by admins."""
    return MessageResponse(message="Registration is disabled; contact an administrator to create an account.", success=False)
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestPasswordLogin -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/schemas.py backend/app/extensions/auth/routers.py backend/tests/test_extensions_auth_facade.py
git commit -m "feat(auth): 密码登录门面（username→email→gateway 验证→会话 cookie）"
```

---

## Task 5: OTP 登录端点（otp/send + login/otp）

**Files:**
- Modify: `backend/app/extensions/auth/routers.py`
- Test: `backend/tests/test_extensions_auth_facade.py`（追加 `TestOtpEndpoints`）

- [ ] **Step 1: 写失败测试**

```python
class TestOtpEndpoints:
    @pytest.mark.asyncio
    async def test_otp_send_known_email(self, monkeypatch):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)
        monkeypatch.setattr(routers, "create_otp", AsyncMock(return_value=None))

        from app.extensions.auth.routers import OtpSendRequest, otp_send
        result = await otp_send(_make_request(), OtpSendRequest(email="zhangsan@eai-flow.com"), db)
        assert result.sent is True
        routers.create_otp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_otp_send_unknown_email_uniform_response(self, monkeypatch):
        from app.extensions.auth import routers

        db = AsyncMock()
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        monkeypatch.setattr(routers, "create_otp", AsyncMock(return_value=None))

        from app.extensions.auth.routers import OtpSendRequest, otp_send
        result = await otp_send(_make_request(), OtpSendRequest(email="nobody@eai-flow.com"), db)
        assert result.sent is True  # anti-enumeration
        routers.create_otp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_otp_login_success(self, monkeypatch):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)
        monkeypatch.setattr(routers, "verify_otp", AsyncMock(return_value=True))
        monkeypatch.setattr(routers, "_issue_gateway_session", AsyncMock(
            return_value=routers.FacadeLoginResponse(expires_in=86400)))

        from fastapi import Response
        from app.extensions.auth.routers import OtpLoginRequest, login_otp
        result = await login_otp(_make_request(), Response(), OtpLoginRequest(email="zhangsan@eai-flow.com", code="123456"), db)
        assert result.expires_in == 86400

    @pytest.mark.asyncio
    async def test_otp_login_bad_code_401(self, monkeypatch):
        from app.extensions.auth import routers
        from app.extensions.models import User

        db = AsyncMock()
        user = User(id=uuid.uuid4(), username="zhangsan", email="zhangsan@eai-flow.com",
                    password_hash="", status="active")
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: user)
        monkeypatch.setattr(routers, "verify_otp", AsyncMock(return_value=False))

        from fastapi import HTTPException
        from app.extensions.auth.routers import OtpLoginRequest, login_otp
        with pytest.raises(HTTPException) as exc:
            await login_otp(_make_request(), Response(), OtpLoginRequest(email="zhangsan@eai-flow.com", code="000000"), db)
        assert exc.value.status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpEndpoints -v`
Expected: FAIL（`AttributeError`：router 没有 `otp_send`/`login_otp`/`create_otp`）

- [ ] **Step 3: 实现 OTP 端点**

在 `backend/app/extensions/auth/routers.py` 的 `login` 之后追加：

```python
@router.post("/otp/send", response_model=OtpSendResponse)
async def otp_send(request: Request, body: OtpSendRequest, db: AsyncSession = Depends(get_db)):
    """Send a login OTP to the given email (EAI-CUSTOM).

    Anti-enumeration: returns a uniform response whether or not the email exists.
    """
    from app.extensions.auth.otp import create_otp

    email = body.email.strip().lower()
    stmt = select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    debug_code = None
    if user is not None and user.status == "active":
        debug_code = await create_otp(db, email)
    return OtpSendResponse(sent=True, debug_code=debug_code)


@router.post("/login/otp", response_model=FacadeLoginResponse)
async def login_otp(request: Request, response: Response, body: OtpLoginRequest, db: AsyncSession = Depends(get_db)):
    """Verify an OTP and issue a Gateway session (EAI-CUSTOM)."""
    from app.extensions.auth.otp import verify_otp

    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)

    email = body.email.strip().lower()
    if not await verify_otp(db, email, body.code):
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码错误或已过期")

    stmt = select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码错误或已过期")

    user.last_login_at = datetime.utcnow()
    await db.commit()
    return await _issue_gateway_session(user.email, request, response)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py::TestOtpEndpoints -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/auth/routers.py backend/tests/test_extensions_auth_facade.py
git commit -m "feat(auth): 邮箱验证码登录端点（otp/send + login/otp）"
```

---

## Task 6: 全量测试回归 + 文档

**Files:**
- Test: `backend/tests/test_extensions_auth_facade.py`

- [ ] **Step 1: 运行整个门面测试文件**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extensions_auth_facade.py -v`
Expected: PASS（全部，含 TestAuthConfig/TestOtpModel/TestOtpCore/TestPasswordLogin/TestOtpEndpoints）

- [ ] **Step 2: 运行既有 extensions 测试确认无回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_contract_price_extension.py -v`
Expected: PASS（既有测试不受影响）

- [ ] **Step 3: 更新 backend/CLAUDE.md 认证章节**

在 `backend/CLAUDE.md` 的 Gateway API 段落下方追加（简写）：

```markdown
### EAI 统一认证门面（EAI-CUSTOM）
- 登录入口收敛到 `app/extensions/auth/routers.py`：`POST /api/extensions/auth/login`（工号或 email+密码）与 `POST /api/extensions/auth/otp/send` + `POST /api/extensions/auth/login/otp`（邮箱验证码）。
- extensions PostgreSQL 是组织目录真源（工号/部门/角色/启停）；Gateway 是会话层。密码验证委托 `get_local_provider().authenticate()`（argon2，admin 建号/改密时由 `app/extensions/user/sync.py` 镜像），会话用上游 `create_access_token` 签发 HttpOnly cookie —— 零上游代码改动。
- 无自注册（`/register` 已禁用）；SMTP 配置见 `EAI_SMTP_*` 环境变量。
```

- [ ] **Step 4: Commit**

```bash
git add backend/CLAUDE.md
git commit -m "docs(backend): 认证门面说明"
```

---

## Task 7: 前端登录页双 tab

**Files:**
- Modify: `frontend/src/app/(auth)/login/page.tsx`（EAI-CUSTOM）

- [ ] **Step 1: 重写登录页**

整体替换 `frontend/src/app/(auth)/login/page.tsx` 的 `LoginPage` 组件为（保留左侧品牌面板与样式；这是 EAI 定制页，加注释）：

```tsx
"use client";

// EAI-CUSTOM: dual-mode login (工号+密码 / 邮箱+验证码) → EAI auth facade.
// Upstream deer-flow's email+password /api/v1/auth/login/local remains intact.

import { Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type LoginMode = "password" | "otp";

export default function LoginPage() {
  const [mode, setMode] = useState<LoginMode>("password");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [otpSent, setOtpSent] = useState(false);

  useEffect(() => {
    const hasRedirect =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("redirect");
    if (!hasRedirect) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  }, []);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const redirectAfterLogin = () => {
    const redirectUrl =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("redirect")
        : null;
    window.location.href = redirectUrl ?? "/";
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const res = await fetch("/api/extensions/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "登录失败");
        return;
      }
      redirectAfterLogin();
    } catch {
      setError("网络错误");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    setError("");
    setOtpSent(false);
    try {
      const res = await fetch("/api/extensions/auth/otp/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "发送失败");
        return;
      }
      setOtpSent(true);
      setCountdown(60);
    } catch {
      setError("网络错误");
    }
  };

  const handleOtpLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const res = await fetch("/api/extensions/auth/login/otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "登录失败");
        return;
      }
      redirectAfterLogin();
    } catch {
      setError("网络错误");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex w-full bg-background">
      <div className="hidden lg:flex flex-col justify-between w-1/2 p-12 text-foreground relative overflow-hidden">
        <img
          src="/leftPanel.png?v=1"
          alt=""
          className="absolute inset-0 w-full h-full object-cover object-center"
          aria-hidden
        />
        <div className="absolute inset-0 bg-black/30" />
        <div className="relative z-10 mt-32">
          <h1 className="text-[56px] font-bold mb-8 tracking-wide text-white">
            吉林化工工程Agent
          </h1>
          <h2 className="text-3xl font-medium mb-6 text-white">
            企业智能体应用平台
          </h2>
          <p className="text-xl text-white/80">
            Harness驱动的多智能体协作、多模态交互、本地知识库
          </p>
        </div>
        <div className="relative z-10 text-sm text-white/60">
          &copy; 吉林化工工程有限公司 2026 v0.5
        </div>
      </div>

      <div className="flex-1 flex flex-col relative">
        <div className="absolute top-6 right-8">
          <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
            返回首页
          </Link>
        </div>

        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md bg-card rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-border p-10">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-foreground mb-2">欢迎回来</h2>
              <p className="text-muted-foreground text-sm">请输入您的账号信息登录</p>
            </div>

            <div className="grid grid-cols-2 gap-1 mb-6 p-1 bg-muted rounded-lg">
              {(["password", "otp"] as LoginMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setError("");
                  }}
                  className={`py-2 text-sm rounded-md transition-colors ${
                    mode === m ? "bg-background shadow-sm font-medium" : "text-muted-foreground"
                  }`}
                >
                  {m === "password" ? "工号+密码" : "邮箱验证码"}
                </button>
              ))}
            </div>

            {error && (
              <p className="text-destructive text-sm bg-destructive/10 rounded-lg px-3 py-2 mb-4">
                {error}
              </p>
            )}

            {mode === "password" ? (
              <form onSubmit={handlePasswordLogin} className="space-y-5">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">工号</label>
                  <Input
                    type="text"
                    placeholder="请输入工号或邮箱"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="h-11"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">密码</label>
                  <div className="relative">
                    <Input
                      type={showPassword ? "text" : "password"}
                      placeholder="请输入密码"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="h-11 pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <Button type="submit" disabled={isLoading} className="w-full h-11 text-base">
                  {isLoading ? "登录中..." : "登录"}
                </Button>
              </form>
            ) : (
              <form onSubmit={handleOtpLogin} className="space-y-5">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">邮箱</label>
                  <Input
                    type="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="h-11"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">验证码</label>
                  <div className="flex gap-2">
                    <Input
                      type="text"
                      inputMode="numeric"
                      maxLength={10}
                      placeholder="请输入验证码"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      required
                      className="h-11 flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={countdown > 0}
                      onClick={handleSendCode}
                      className="h-11 w-28 shrink-0"
                    >
                      {countdown > 0 ? `${countdown}s` : otpSent ? "重新发送" : "发送验证码"}
                    </Button>
                  </div>
                </div>
                <Button type="submit" disabled={isLoading} className="w-full h-11 text-base">
                  {isLoading ? "登录中..." : "登录"}
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 校验类型与 lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: PASS（无类型错误 / lint 错误）

- [ ] **Step 3: 更新 e2e mock 登录流（如存在）**

Run: `cd frontend && rg -l "api/v1/auth/login/local|api/extensions/auth" tests/e2e || echo "no-e2e-login-spec"`
- 若命中文件：把 mock 的 `/api/v1/auth/login/local` 替换为 `/api/extensions/auth/login`，响应体改为 `{"expires_in": 604800, "needs_setup": false}`，并重跑 `pnpm test:e2e`（仅登录相关 spec）。
- 若无命中：跳过（本任务无 e2e 依赖）。

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/app/(auth)/login/page.tsx"
git commit -m "feat(auth): 登录页双 tab（工号+密码 / 邮箱验证码）→ EAI 门面"
```

---

## Self-Review 检查单

- [ ] Spec §5.1（密码门面）→ Task 4 ✓
- [ ] Spec §5.2（OTP）→ Task 2/3/5 ✓
- [ ] Spec §5.3（会话签发共用例程）→ Task 4 `_issue_gateway_session` ✓
- [ ] Spec §5.4（前端双 tab）→ Task 7 ✓
- [ ] Spec §5.5（SMTP 配置）→ Task 1 ✓
- [ ] Spec §5.6（otp_codes 表）→ Task 2 ✓
- [ ] Spec §6（安全：bcrypt 存储/限流/防枚举）→ Task 3/4/5 ✓
- [ ] Spec §7（零迁移）→ 无需迁移任务 ✓
- [ ] Spec §8（无自注册）→ Task 4 register 禁用 ✓
- [ ] 占位符扫描：无 TBD/TODO ✓
- [ ] 类型一致性：`FacadeLoginResponse`、`OtpSendRequest/Response`、`OtpLoginRequest` 在 schemas/routers/tests 中命名一致 ✓
