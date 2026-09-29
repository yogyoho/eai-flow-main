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


# EAI-CUSTOM: 测试写库门禁（根治"跑一次集成测试污染一次 extensions 真库"）。
# 事故: executor('测试实体')/batch('批量实体')/e2e('E2E') 三文件无 skip 守卫直写 dg_entities,
# 宿主机 5432 恒可达, 积累 1254 行夹具（scripts/eia_purge_test_fixtures.py 存量清理）。
REAL_DB_GATE_ENV = "ONTOSTUDIO_TEST_ALLOW_REAL_DB"


def real_db_allowed() -> bool:
    """真库测试许可: 默认 False, 显式设 ONTOSTUDIO_TEST_ALLOW_REAL_DB=1 才放行（fail-closed）。"""
    return os.environ.get(REAL_DB_GATE_ENV) == "1"


@pytest.fixture(autouse=True)
def _gate_real_db_tests(request):
    """integration 标记的测试默认 skip——无显式许可一律不碰真库（EAI-CUSTOM）.

    语义分层: 本门禁管"许不许可"; 各文件既有的 _URL/_DB_READY 探针管"库可不可达"。
    许可打开后探针仍生效（无库/断连照旧 skip）, 两层叠加不冲突; 兼容既有空库 skip 逻辑。
    """
    if request.node.get_closest_marker("integration") and not real_db_allowed():
        pytest.skip(f"真库集成测试默认 skip——设 {REAL_DB_GATE_ENV}=1 显式放行（防测试污染 extensions 真库）")


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
