"""共享测试装置（S1 Task 2 新增）: JWT 测试 secret + 测试 token 签发工具.

EAI-CUSTOM: Task 2 实装 JWT 鉴权（app/auth.py）后, REST 集成测试需带合法 token 访问
受保护端点。session 级 autouse 装置固定 ONTOSTUDIO_JWT_SECRET（auth 逐请求读 env, 故
装置时机晚于模块 import 也安全）; ``auth_headers``/``make_token`` 供各测试文件复用,
``make_token(roles=...)`` 可签非管理员/expired/带外 secret token 供负路径断言。
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest

TEST_JWT_SECRET = "ontostudio-test-secret-0123456789abcdef"  # ≥32 bytes（PyJWT HMAC-SHA256 建议长度, 免 InsecureKeyLength 警告）


@pytest.fixture(scope="session", autouse=True)
def _jwt_test_secret():
    """Pin the shared JWT secret for the whole test session (fail-closed auth needs it)."""
    saved = os.environ.get("ONTOSTUDIO_JWT_SECRET")
    os.environ["ONTOSTUDIO_JWT_SECRET"] = TEST_JWT_SECRET
    yield
    if saved is None:
        os.environ.pop("ONTOSTUDIO_JWT_SECRET", None)
    else:
        os.environ["ONTOSTUDIO_JWT_SECRET"] = saved


def make_test_token(
    *,
    roles: list[str] | tuple[str, ...] = ("superadmin",),
    secret: str = TEST_JWT_SECRET,
    expires_delta: timedelta | None = None,
    **extra: object,
) -> str:
    """Sign an HS256 access token shaped like the issuers ontostudio accepts (sub + roles)."""
    now = datetime.now(UTC)
    payload: dict = {
        "sub": str(uuid.uuid4()),
        "username": "test-admin",
        "email": "test-admin@local",
        "roles": list(roles),
        "iat": now,
        "exp": now + (expires_delta or timedelta(hours=1)),
        "type": "access",
    }
    payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture()
def jwt_test_secret() -> str:
    """测试共享 secret 原文（伪造 header/签名的负路径测试用）。"""
    return TEST_JWT_SECRET


@pytest.fixture()
def make_token() -> Callable[..., str]:
    """Token factory fixture（可自定义 roles/secret/exp 与任意额外 claims）。"""
    return make_test_token


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """默认 superadmin 测试 token 的 Authorization 头（REST 集成测试 client 装置用）。"""
    return {"Authorization": f"Bearer {make_test_token()}"}
