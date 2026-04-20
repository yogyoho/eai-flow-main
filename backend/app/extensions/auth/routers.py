"""Authentication routers for extensions module."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import (
    generate_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.extensions.auth.middleware import ACCESS_TOKEN_COOKIE, get_current_user
from app.extensions.database import get_db
from app.extensions.models import Department, Role, User
from app.extensions.schemas import (
    CurrentUser,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshTokenRequest,
    UserCreate,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return tokens."""
    stmt = select(User).where(User.username == request.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
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

    access_token, expires_in = generate_access_token(
        str(user.id), user.username, role_code, permissions
    )
    refresh_token, _ = generate_refresh_token(str(user.id))

    user.last_login_at = datetime.utcnow()
    await db.commit()

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=expires_in,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


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

    access_token, expires_in = generate_access_token(
        str(user.id), user.username, role_code, permissions
    )
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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    stmt = select(User).where(User.username == request.username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        dept_id=request.dept_id,
        role_id=request.role_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    role_name = None
    if user.role_id:
        stmt_role = select(Role).where(Role.id == user.role_id)
        result_role = await db.execute(stmt_role)
        role = result_role.scalar_one_or_none()
        if role:
            role_name = role.name

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        dept_id=user.dept_id,
        dept_name=None,
        role_id=user.role_id,
        role_name=role_name,
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
