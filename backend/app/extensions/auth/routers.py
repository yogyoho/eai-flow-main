"""Authentication routers for extensions module."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import (
    generate_access_token,
    generate_refresh_token,
    hash_password,
    verify_token,
)
from app.extensions.auth.middleware import ACCESS_TOKEN_COOKIE, get_current_user
from app.extensions.database import get_db
from app.extensions.models import Department, Role, User
from app.extensions.schemas import (
    CurrentUser,
    FacadeLoginResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    OtpLoginRequest,  # EAI-CUSTOM: Task 5 OTP 端点使用
    OtpSendRequest,  # EAI-CUSTOM: Task 5 OTP 端点使用
    OtpSendResponse,  # EAI-CUSTOM: Task 5 OTP 端点使用
    RefreshTokenRequest,
    UserCreate,
    UserResponse,
)

logger = logging.getLogger(__name__)

# EAI-CUSTOM: Gateway session issuance + per-IP rate limiting for the auth facade.
# 复用上游构建块（get_local_provider / create_access_token / get_auth_config /
# is_secure_request）——不修改任何上游代码。
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


router = APIRouter(prefix="/api/extensions/auth", tags=["Authentication"])


@router.post("/login", response_model=FacadeLoginResponse)
async def login(request: Request, response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """EAI 登录门面 —— 工号（或 email）+ 密码.

    EAI-CUSTOM: extensions 是组织目录（工号→email）；Gateway 验证密码（argon2，
    由 user/sync.py 在 admin 建号/改密时镜像）并持有会话 cookie。Gateway 行缺失时
    best-effort 重同步一次再验证。
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

    # EAI-CUSTOM 安全修正：extensions 哈希是密码真源，用 gateway 的 verify_password_async
    # 验证（自动识别 $dfv2$/$dfv1$/裸 bcrypt 三种格式，fail-closed 返回 False）。
    # ① 有哈希 → 本地验证；② 空哈希/无效哈希（facade 上线前的 bridge 老用户）→ 回退
    # gateway 认证并一次性迁移成裸 bcrypt。任何分支密码错误都直接 401，
    # **绝不** 用未验证的密码去 sync_user_created（否则攻击者用错误密码覆盖 gateway 哈希）。
    provider = get_local_provider()
    verified = False
    if user.password_hash:
        from app.gateway.auth.password import verify_password_async

        verified = await verify_password_async(body.password, user.password_hash)
    if not verified:
        gw = await provider.authenticate({"email": user.email, "password": body.password})
        if gw is not None:
            verified = True
            user.password_hash = hash_password(body.password)  # 一次性 bcrypt 迁移
            await db.commit()

    if not verified:
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    # 密码已通过验证，此时才允许补建缺失的 gateway 镜像行（best-effort）。
    gw_user = await provider.get_user_by_email(user.email)
    if gw_user is None:
        from app.extensions.user import sync as user_sync

        await user_sync.sync_user_created(db, user.email, body.password, user.role_id)
        gw_user = await provider.get_user_by_email(user.email)

    if gw_user is None:
        _record_login_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    return await _issue_gateway_session(user.email, request, response)


@router.post("/otp/send", response_model=OtpSendResponse)
async def otp_send(request: Request, body: OtpSendRequest, db: AsyncSession = Depends(get_db)):
    """发送登录验证码到指定邮箱（EAI-CUSTOM）.

    防枚举：无论邮箱是否存在都返回统一响应。
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
    """校验验证码并签发 Gateway 会话（EAI-CUSTOM）."""
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


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """Logout current user."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return MessageResponse(message="Logged out successfully")


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = verify_token(request.refresh_token, "refresh")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    stmt = select(User).where(User.id == payload.sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active",
        )

    role_code = None
    permissions = []
    if user.role_id:
        stmt_role = select(Role).where(Role.id == user.role_id)
        result_role = await db.execute(stmt_role)
        role = result_role.scalar_one_or_none()
        if role:
            role_code = role.code
            permissions = role.permissions or []

    access_token, expires_in = generate_access_token(str(user.id), user.username, role_code, permissions)
    new_refresh_token, _ = generate_refresh_token(str(user.id))

    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current authenticated user info."""
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    role_name = None
    if user.role_id:
        stmt_role = select(Role).where(Role.id == user.role_id)
        result_role = await db.execute(stmt_role)
        role = result_role.scalar_one_or_none()
        if role:
            role_name = role.name

    dept_name = None
    if user.dept_id:
        stmt_dept = select(Department).where(Department.id == user.dept_id)
        result_dept = await db.execute(stmt_dept)
        dept = result_dept.scalar_one_or_none()
        if dept:
            dept_name = dept.name

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        dept_id=user.dept_id,
        dept_name=dept_name,
        role_id=user.role_id,
        role_name=role_name,
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_403_FORBIDDEN)
async def register(request: UserCreate, db: AsyncSession = Depends(get_db)):
    """EAI-CUSTOM: 企业无自注册 —— 用户由管理员统一创建."""
    return MessageResponse(message="Registration is disabled; contact an administrator to create an account.", success=False)


# EAI-CUSTOM: 挂载 SSO 子路由（OIDC 第三登录门面）
from app.extensions.auth.sso import sso_router  # noqa: E402

router.include_router(sso_router)
