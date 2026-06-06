# License 控制系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 DeerFlow 构建离线许可证控制系统，支持机器绑定 + 用户数 + 功能模块 + 有效期的多维度授权，包含厂商 CLI 工具和管理后台。

**Architecture:** JWT+RSA-2048 离线签名验证方案。后端 LicenseService 读取 `license.lic` 文件验证 JWT 签名并解析 Payload，DB 存储元数据镜像供管理页面查询。前端通过 `GET /api/license/status`（无需认证）获取许可证状态，路由守卫控制模块可见性。`DEER_FLOW_DEV_MODE=true` 开发后门跳过验证。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy (async) + python-jose (JWT) + cryptography (RSA) + TypeScript + React 19 + TanStack Query + Tailwind CSS 4

---

## 文件结构

### 创建

| 文件 | 职责 |
|------|------|
| `tools/license/generate_keys.py` | RSA-2048 密钥对生成 |
| `tools/license/license_generator.py` | 许可证 JWT 签发 CLI |
| `tools/license/license_request.json` | 示例请求文件 |
| `tools/license/README.md` | 厂商工具使用说明 |
| `backend/app/extensions/license/__init__.py` | 模块导出 |
| `backend/app/extensions/license/schemas.py` | Pydantic 请求/响应模型 |
| `backend/app/extensions/license/models.py` | SQLAlchemy License DB 模型 |
| `backend/app/extensions/license/service.py` | LicenseService 核心逻辑 |
| `backend/app/extensions/license/routers.py` | FastAPI 路由 |
| `backend/app/extensions/license/public_key.pem` | RSA 公钥（嵌入） |
| `frontend/src/extensions/license/api.ts` | 前端 API 调用 |
| `frontend/src/extensions/license/useLicense.ts` | React hook（路由守卫） |
| `frontend/src/extensions/license/DevModeBanner.tsx` | 开发模式水印 |
| `frontend/src/extensions/license/GracePeriodBanner.tsx` | 宽限期倒计时 Banner |
| `frontend/src/extensions/license/SystemLockedPage.tsx` | 系统锁定页面 |
| `frontend/src/extensions/license/ModuleLockedPage.tsx` | 未授权模块页面 |
| `frontend/src/extensions/license/LicensePage.tsx` | 管理后台许可证页面 |

### 修改

| 文件 | 变更 |
|------|------|
| `backend/app/extensions/models.py` | 添加 License 模型导入 |
| `backend/app/extensions/schemas.py` | 添加 License Pydantic schemas |
| `backend/app/extensions/database.py` | 注册 License 模型确保表创建 |
| `backend/app/extensions/__init__.py` | 注册 license router |
| `config.yaml` | 添加 license 配置项 |
| `docker-compose.yml` | 添加 deerflow_data volume |

---

### Task 1: 厂商 CLI 工具 — RSA 密钥生成

**Files:**
- Create: `tools/license/generate_keys.py`
- Create: `tools/license/README.md`

- [ ] **Step 1: 创建 generate_keys.py**

```python
"""Generate RSA-2048 key pair for license signing/verification.

Usage:
    python generate_keys.py

Outputs:
    tools/license/private_key.pem  — Keep secret, used by license_generator.py
    tools/license/public_key.pem   — Embed in product for verification
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os


def generate_keys(output_dir: str = ".") -> tuple[str, str]:
    """Generate RSA-2048 key pair. Returns (private_key_path, public_key_path)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_path = os.path.join(output_dir, "private_key.pem")
    with open(private_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    public_key = private_key.public_key()
    public_path = os.path.join(output_dir, "public_key.pem")
    with open(public_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    return private_path, public_path


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    priv, pub = generate_keys(script_dir)
    print(f"Private key: {priv}")
    print(f"Public key:  {pub}")
    print("\nKeep private_key.pem SECRET. Embed public_key.pem in the product.")
```

- [ ] **Step 2: 运行验证**

```bash
cd tools/license && python generate_keys.py
```

Expected: 生成 `private_key.pem` (约 1704 bytes) 和 `public_key.pem` (约 451 bytes)

- [ ] **Step 3: 创建 README.md**

```markdown
# DeerFlow License Tools

## 首次使用

1. 生成密钥对（仅需一次）：
   ```bash
   python generate_keys.py
   ```

2. 将 `public_key.pem` 复制到产品 `backend/app/extensions/license/` 目录
3. 将 `private_key.pem` 安全保管，**切勿**入库或随产品分发

## 生成许可证

客户提交 `license_request.json`（包含 machine_id），然后：

```bash
# 30 天试用
python license_generator.py license_request.json --days 30

# 永久全模块
python license_generator.py license_request.json --permanent --all-modules --customer "XX公司" --max-users 50
```
```

- [ ] **Step 4: Commit**

```bash
git add tools/license/generate_keys.py tools/license/README.md
git commit -m "feat(license): add RSA key generation tool"
```

---

### Task 2: 厂商 CLI 工具 — 许可证生成器

**Files:**
- Create: `tools/license/license_generator.py`
- Create: `tools/license/license_request.json`

- [ ] **Step 1: 创建 license_request.json 示例**

```json
{
  "machine_id": "F1B9DE46-2BFA-47C5-BA39-7CD18D7ACDB7",
  "generated_at": "2026-06-06T10:00:00Z",
  "system_info": {
    "hostname": "prod-server-01",
    "platform": "linux"
  }
}
```

- [ ] **Step 2: 创建 license_generator.py**

```python
"""Generate signed license files for DeerFlow deployments.

Usage:
    # 30-day trial
    python license_generator.py license_request.json --days 30

    # Permanent, all modules
    python license_generator.py license_request.json --permanent --all-modules \\
        --customer "XX科技" --max-users 50 --output license.lic

    # Specify modules
    python license_generator.py license_request.json --permanent \\
        --modules project,docmgr,knowledge --max-users 100
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH = os.path.join(SCRIPT_DIR, "private_key.pem")
ALGORITHM = "RS256"

ALL_MODULES = [
    "project", "docmgr", "knowledge", "collab",
    "report", "approval", "workflow", "dashboard",
]


def load_private_key() -> bytes:
    if not os.path.exists(PRIVATE_KEY_PATH):
        print(f"Error: Private key not found at {PRIVATE_KEY_PATH}")
        print("Run generate_keys.py first.")
        exit(1)
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return f.read()


def generate_license(
    request_file: str,
    days: int | None = None,
    permanent: bool = False,
    all_modules: bool = False,
    modules: str | None = None,
    customer: str = "",
    max_users: int | None = None,
    features: str | None = None,
    output: str = "license.lic",
) -> None:
    # Load request
    with open(request_file) as f:
        request_data = json.load(f)

    machine_id = request_data.get("machine_id")
    if not machine_id:
        print("Error: missing machine_id in request file")
        return

    print(f"Generating license for Machine ID: {machine_id}")

    # Build modules dict
    if all_modules:
        modules_dict = {m: True for m in ALL_MODULES}
    elif modules:
        enabled = set(modules.split(","))
        modules_dict = {m: (m in enabled) for m in ALL_MODULES}
    else:
        modules_dict = {"project": True, "docmgr": True}

    # Build features dict
    features_dict = {}
    if features:
        for pair in features.split(","):
            k, v = pair.split("=")
            features_dict[k.strip()] = int(v) if v.isdigit() else v

    # Build JWT payload
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "DeerFlow",
        "iat": int(now.timestamp()),
        "jti": f"LIC-{uuid.uuid4().hex[:8].upper()}",
        "sub": machine_id,
        "type": "permanent" if permanent else "trial",
        "customer": customer,
        "max_users": max_users,
        "modules": modules_dict,
        "features": features_dict,
        "meta": {
            "contact": "support@deerflow.com",
            "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}",
        },
    }

    if not permanent:
        actual_days = days or 30
        expiry = now + timedelta(days=actual_days)
        payload["exp"] = int(expiry.timestamp())
        print(f"Type: trial ({actual_days} days), Expires: {expiry.isoformat()}")
    else:
        print("Type: permanent")

    # Sign
    private_key = load_private_key()
    encoded_jwt = jwt.encode(payload, private_key, algorithm=ALGORITHM)

    # Save
    with open(output, "w") as f:
        f.write(encoded_jwt)

    print(f"Success! License saved to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeerFlow License Generator")
    parser.add_argument("request_file", help="Path to license_request.json")
    parser.add_argument("--days", type=int, help="Days until expiry (trial)")
    parser.add_argument("--permanent", action="store_true", help="Generate permanent license")
    parser.add_argument("--all-modules", action="store_true", help="Enable all modules")
    parser.add_argument("--modules", help="Comma-separated module names")
    parser.add_argument("--customer", default="", help="Customer name")
    parser.add_argument("--max-users", type=int, help="Max active users")
    parser.add_argument("--features", help="Features as key=value pairs, comma-separated")
    parser.add_argument("--output", default="license.lic", help="Output file path")

    args = parser.parse_args()
    generate_license(
        request_file=args.request_file,
        days=args.days,
        permanent=args.permanent,
        all_modules=args.all_modules,
        modules=args.modules,
        customer=args.customer,
        max_users=args.max_users,
        features=args.features,
        output=args.output,
    )
```

- [ ] **Step 3: 验证生成器**

```bash
cd tools/license && python license_generator.py license_request.json --permanent --all-modules --customer "Test" --output test.lic
```

Expected: 生成 `test.lic` 包含 JWT 字符串。用 `python -c "import jwt; print(jwt.decode(open('test.lic').read(), open('public_key.pem').read(), algorithms=['RS256']))"` 验证解码。

- [ ] **Step 4: 清理测试文件并 commit**

```bash
rm tools/license/test.lic
git add tools/license/license_generator.py tools/license/license_request.json
git commit -m "feat(license): add license generator CLI tool"
```

---

### Task 3: 后端 — Pydantic Schemas

**Files:**
- Create: `backend/app/extensions/license/schemas.py`

- [ ] **Step 1: 创建 schemas.py**

```python
"""Pydantic schemas for license module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LicenseModules(BaseModel):
    """Feature module switches."""

    project: bool = False
    docmgr: bool = False
    knowledge: bool = False
    collab: bool = False
    report: bool = False
    approval: bool = False
    workflow: bool = False
    dashboard: bool = False


class LicenseFeatures(BaseModel):
    """Extended capability quotas."""

    agent_count: int = Field(default=3, ge=1)
    sandbox_type: str = "local"


class LicenseStatusResponse(BaseModel):
    """GET /api/license/status response."""

    valid: bool
    machine_id: str | None = None
    type: str | None = None  # permanent | trial | subscription
    customer: str | None = None
    max_users: int | None = None
    current_users: int = 0
    modules: dict[str, bool] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    days_remaining: int | None = None
    in_grace_period: bool = False
    grace_period_remaining_days: int | None = None
    warnings: list[str] = Field(default_factory=list)
    is_dev_mode: bool = False


class LicenseImportResponse(BaseModel):
    """POST /api/license/import response."""

    success: bool
    machine_id: str | None = None
    type: str | None = None
    customer: str | None = None
    message: str


class LicenseHistoryItem(BaseModel):
    """Single history record."""

    id: str  # UUID as string
    jwt_jti: str
    machine_id: str
    type: str
    customer: str | None = None
    max_users: int | None = None
    modules: dict[str, bool] = Field(default_factory=dict)
    issued_at: datetime
    expires_at: datetime | None = None
    imported_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class LicenseHistoryResponse(BaseModel):
    """GET /api/license/history response."""

    items: list[LicenseHistoryItem]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/license/schemas.py
git commit -m "feat(license): add Pydantic schemas for license module"
```

---

### Task 4: 后端 — DB Model

**Files:**
- Create: `backend/app/extensions/license/models.py`
- Create: `backend/app/extensions/license/__init__.py`

- [ ] **Step 1: 创建 models.py**

```python
"""SQLAlchemy model for licenses table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class License(Base):
    """License metadata mirror — NOT used for authorization decisions."""

    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jwt_jti: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="JWT unique ID"
    )
    machine_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Bound machine ID"
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="permanent | trial | subscription"
    )
    customer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    jwt_raw: Mapped[str] = mapped_column(Text, nullable=False, comment="Raw JWT string")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<License(id={self.id}, jti={self.jwt_jti}, active={self.is_active})>"
```

- [ ] **Step 2: 创建 __init__.py**

```python
"""License control extension module."""

from app.extensions.license.service import LicenseService
from app.extensions.license.routers import router as license_router

__all__ = ["LicenseService", "license_router"]
```

- [ ] **Step 3: 注册 Model 到 database.py**

在 `backend/app/extensions/database.py` 中，找到 `Base` 的 model 导入区域，添加：

```python
# 在 database.py 末尾的 model 导入部分添加：
from app.extensions.license.models import License  # noqa: F401
```

实际上检查 `database.py` 如何注册 models——查找现有模式：

```bash
grep -n "import.*models\|from.*models" backend/app/extensions/database.py | tail -5
```

根据结果在适当位置添加导入。

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/license/__init__.py backend/app/extensions/license/models.py
git commit -m "feat(license): add License DB model"
```

---

### Task 5: 后端 — LicenseService 核心逻辑

**Files:**
- Create: `backend/app/extensions/license/service.py`
- Create: `backend/app/extensions/license/public_key.pem` (复制 tools/license/public_key.pem)

- [ ] **Step 1: 复制公钥**

```bash
cp tools/license/public_key.pem backend/app/extensions/license/public_key.pem
```

- [ ] **Step 2: 创建 service.py**

```python
"""License verification and management service."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jose import jwt, JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.license.models import License

logger = logging.getLogger(__name__)

PUBLIC_KEY_PATH = Path(__file__).parent / "public_key.pem"
DEERFLOW_DIR = Path("backend/.deer-flow")
GRACE_PERIOD_DAYS = int(os.getenv("GRACE_PERIOD_DAYS", "7"))
DEFAULT_LICENSE_PATH = Path(os.getenv("LICENSE_FILE_PATH", "/etc/deerflow/license.lic"))
ALGORITHM = "RS256"
ALL_MODULES = [
    "project", "docmgr", "knowledge", "collab",
    "report", "approval", "workflow", "dashboard",
]


class LicensePayload:
    """Decoded and validated license data."""

    def __init__(
        self,
        machine_id: str,
        type: str,
        customer: str,
        max_users: int | None,
        modules: dict[str, bool],
        features: dict[str, Any],
        expires_at: datetime | None,
        meta: dict[str, Any],
        jti: str,
    ):
        self.machine_id = machine_id
        self.type = type
        self.customer = customer
        self.max_users = max_users
        self.modules = modules
        self.features = features
        self.expires_at = expires_at
        self.meta = meta
        self.jti = jti

    @classmethod
    def dev_mode(cls) -> "LicensePayload":
        return cls(
            machine_id="DEV-MODE",
            type="permanent",
            customer="DEVELOPMENT",
            max_users=9999,
            modules={m: True for m in ALL_MODULES},
            features={"agent_count": 99, "sandbox_type": "docker"},
            expires_at=None,
            meta={"contact": "dev@localhost", "order_id": "DEV-SKIP"},
            jti="DEV-MODE",
        )


class LicenseService:
    """Offline license verification using JWT + RSA-2048."""

    @staticmethod
    def _load_public_key() -> bytes:
        with open(PUBLIC_KEY_PATH, "rb") as f:
            return f.read()

    @staticmethod
    def _is_dev_mode() -> bool:
        """Check if developer bypass is active and safe."""
        dev_mode = os.getenv("DEER_FLOW_DEV_MODE", "").lower() in ("1", "true", "yes")
        if not dev_mode:
            return False
        env = os.getenv("DEER_FLOW_ENV", "")
        if env == "production":
            raise RuntimeError(
                "DEER_FLOW_DEV_MODE is not allowed in production environment"
            )
        return True

    @staticmethod
    def _get_license_file_paths() -> list[Path]:
        """Return candidate paths for license.lic, in search order."""
        candidates = [DEFAULT_LICENSE_PATH]
        # Also check project root
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        candidates.append(project_root / "license.lic")
        candidates.append(project_root / "backend" / "license.lic")
        return candidates

    @staticmethod
    def _read_license_file() -> str | None:
        for path in LicenseService._get_license_file_paths():
            if path.exists():
                with open(path) as f:
                    return f.read().strip()
        return None

    @staticmethod
    def _ensure_deerflow_dir() -> None:
        DEERFLOW_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_start_timestamp() -> float | None:
        """Read first-run timestamp for grace period calculation."""
        stamp_file = DEERFLOW_DIR / "license_start.log"
        if stamp_file.exists():
            return float(stamp_file.read_text().strip())
        return None

    @staticmethod
    def _record_start_timestamp() -> None:
        LicenseService._ensure_deerflow_dir()
        stamp_file = DEERFLOW_DIR / "license_start.log"
        if not stamp_file.exists():
            stamp_file.write_text(str(time.time()))

    @staticmethod
    def _compute_grace_period() -> tuple[bool, int | None]:
        """Returns (in_grace_period, remaining_days)."""
        start_ts = LicenseService._get_start_timestamp()
        if start_ts is None:
            # First run without license: record timestamp, start grace period
            LicenseService._record_start_timestamp()
            return True, GRACE_PERIOD_DAYS

        elapsed = time.time() - start_ts
        remaining = GRACE_PERIOD_DAYS - (elapsed / 86400)
        if remaining > 0:
            return True, int(remaining)
        return False, 0

    @staticmethod
    def verify() -> LicensePayload:
        """Verify license and return payload.

        Priority:
        1. DEV_MODE → dev payload
        2. Valid license.lic → payload from JWT
        3. Missing/invalid license → check grace period
        """
        if LicenseService._is_dev_mode():
            logger.info("DEV_MODE active — license check bypassed")
            return LicensePayload.dev_mode()

        jwt_raw = LicenseService._read_license_file()

        if not jwt_raw:
            logger.warning("No license file found")
            in_grace, remaining = LicenseService._compute_grace_period()
            if in_grace:
                logger.info(f"Grace period active: {remaining} days remaining")
                # Return a minimal payload; frontend uses in_grace_period flag
                return LicensePayload(
                    machine_id="",
                    type="grace",
                    customer="",
                    max_users=None,
                    modules={},
                    features={},
                    expires_at=None,
                    meta={},
                    jti="",
                )
            raise LicenseError("LICENSE_MISSING", "No license file found and grace period expired")

        try:
            public_key = LicenseService._load_public_key()
            claims = jwt.decode(jwt_raw, public_key, algorithms=[ALGORITHM])
        except JWTError as e:
            logger.error(f"License JWT verification failed: {e}")
            raise LicenseError("LICENSE_INVALID", f"License verification failed: {e}") from e

        # Check expiry
        expires_at = None
        exp_ts = claims.get("exp")
        if exp_ts:
            expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise LicenseError("LICENSE_EXPIRED", "License has expired")

        return LicensePayload(
            machine_id=claims.get("sub", ""),
            type=claims.get("type", "unknown"),
            customer=claims.get("customer", ""),
            max_users=claims.get("max_users"),
            modules=claims.get("modules", {}),
            features=claims.get("features", {}),
            expires_at=expires_at,
            meta=claims.get("meta", {}),
            jti=claims.get("jti", ""),
        )

    @staticmethod
    def get_status(
        payload: LicensePayload | None = None,
        current_user_count: int = 0,
    ) -> dict[str, Any]:
        """Build the full status response for the frontend."""
        try:
            if payload is None:
                payload = LicenseService.verify()
        except LicenseError as e:
            in_grace, remaining = LicenseService._compute_grace_period()
            return {
                "valid": False,
                "machine_id": None,
                "type": None,
                "customer": None,
                "max_users": None,
                "current_users": current_user_count,
                "modules": {},
                "features": {},
                "expires_at": None,
                "days_remaining": None,
                "in_grace_period": in_grace,
                "grace_period_remaining_days": remaining if in_grace else None,
                "warnings": [],
                "is_dev_mode": False,
                "error": e.code if not in_grace else None,
            }

        # Compute warnings
        warnings = []
        if payload.expires_at:
            days_left = (payload.expires_at - datetime.now(timezone.utc)).days
            if payload.type == "trial" and days_left <= 7:
                warnings.append("trial_ending")
            if days_left <= 30:
                warnings.append("license_expiring_soon")
            days_remaining = max(0, days_left)
        else:
            days_remaining = None

        if payload.max_users and current_user_count >= payload.max_users * 0.9:
            warnings.append("user_limit_nearing")

        return {
            "valid": True,
            "machine_id": payload.machine_id,
            "type": payload.type,
            "customer": payload.customer,
            "max_users": payload.max_users,
            "current_users": current_user_count,
            "modules": payload.modules,
            "features": payload.features,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            "days_remaining": days_remaining,
            "in_grace_period": False,
            "grace_period_remaining_days": None,
            "warnings": warnings,
            "is_dev_mode": payload.machine_id == "DEV-MODE",
        }

    @staticmethod
    async def import_license(db: AsyncSession, jwt_raw: str) -> License:
        """Validate and import a license file. Stores metadata in DB."""
        # Verify JWT
        public_key = LicenseService._load_public_key()
        try:
            claims = jwt.decode(jwt_raw, public_key, algorithms=[ALGORITHM])
        except JWTError as e:
            raise LicenseError("LICENSE_INVALID", f"Invalid license: {e}")

        # Check machine_id
        import hashlib
        import platform
        import uuid as uuid_mod

        # Generate current machine_id
        raw = platform.node() + str(uuid_mod.getnode())
        current_machine_id = hashlib.sha256(raw.encode()).hexdigest()[:32]

        license_machine_id = claims.get("sub", "")
        if license_machine_id != current_machine_id:
            raise LicenseError(
                "MACHINE_MISMATCH",
                f"License machine_id {license_machine_id} does not match current machine {current_machine_id}",
            )

        # Check duplicate jti
        jti = claims.get("jti", "")
        existing = await db.execute(select(License).where(License.jwt_jti == jti))
        if existing.scalar_one_or_none():
            raise LicenseError("DUPLICATE_LICENSE", "This license has already been imported")

        # Deactivate current active license
        await db.execute(
            update(License).where(License.is_active == True).values(is_active=False)
        )

        # Create new record
        exp_ts = claims.get("exp")
        expires_at = None
        if exp_ts:
            expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

        license_record = License(
            jwt_jti=jti,
            machine_id=license_machine_id,
            type=claims.get("type", "unknown"),
            customer=claims.get("customer", ""),
            max_users=claims.get("max_users"),
            modules=claims.get("modules", {}),
            features=claims.get("features", {}),
            issued_at=datetime.fromtimestamp(claims.get("iat", 0), tz=timezone.utc),
            expires_at=expires_at,
            meta=claims.get("meta", {}),
            jwt_raw=jwt_raw,
            is_active=True,
        )
        db.add(license_record)
        await db.commit()

        # Clear grace period on successful import
        stamp_file = DEERFLOW_DIR / "license_start.log"
        if stamp_file.exists():
            stamp_file.unlink()

        return license_record

    @staticmethod
    async def get_history(
        db: AsyncSession, skip: int = 0, limit: int = 20
    ) -> tuple[list[License], int]:
        """Get license import history."""
        from sqlalchemy import func as sql_func

        query = select(License).order_by(License.imported_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        items = result.scalars().all()

        count_query = select(sql_func.count(License.id))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(items), total

    @staticmethod
    async def export_license(db: AsyncSession) -> str | None:
        """Get raw JWT of the currently active license."""
        result = await db.execute(
            select(License).where(License.is_active == True)
        )
        record = result.scalar_one_or_none()
        return record.jwt_raw if record else None


class LicenseError(Exception):
    """License-related errors with machine-readable codes."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/license/service.py backend/app/extensions/license/public_key.pem
git commit -m "feat(license): add LicenseService with JWT verification, dev mode, grace period"
```

---

### Task 6: 后端 — FastAPI 路由

**Files:**
- Create: `backend/app/extensions/license/routers.py`

- [ ] **Step 1: 创建 routers.py**

```python
"""License API routers."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.database import get_db
from app.extensions.license.schemas import (
    LicenseHistoryItem,
    LicenseHistoryResponse,
    LicenseImportResponse,
    LicenseStatusResponse,
)
from app.extensions.license.service import LicenseError, LicenseService
from app.extensions.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/license", tags=["License"])


@router.get("/status", response_model=LicenseStatusResponse)
async def get_license_status(
    db: AsyncSession = Depends(get_db),
):
    """Get current license status. No auth required — used by frontend route guards."""
    # Count current active users
    count_result = await db.execute(
        select(func.count(User.id)).where(
            User.is_deleted == False,
            User.status == "active",
        )
    )
    user_count = count_result.scalar() or 0

    status_data = LicenseService.get_status(current_user_count=user_count)
    # Include dev mode check if not already in payload
    if status_data.get("machine_id") == "DEV-MODE":
        status_data["is_dev_mode"] = True
    return LicenseStatusResponse(**status_data)


@router.post("/import", response_model=LicenseImportResponse)
async def import_license(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Import a new license file. Requires admin permission."""
    if not file.filename or not file.filename.endswith(".lic"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Expected .lic file.",
        )

    jwt_raw = (await file.read()).decode("utf-8").strip()
    if not jwt_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty license file.",
        )

    try:
        record = await LicenseService.import_license(db, jwt_raw)
    except LicenseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )

    return LicenseImportResponse(
        success=True,
        machine_id=record.machine_id,
        type=record.type,
        customer=record.customer,
        message="License imported successfully",
    )


@router.get("/history", response_model=LicenseHistoryResponse)
async def get_license_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Get license import history. Requires admin permission."""
    items, total = await LicenseService.get_history(db, skip=skip, limit=limit)
    return LicenseHistoryResponse(
        items=[LicenseHistoryItem.model_validate(item) for item in items],
        total=total,
    )


@router.get("/export")
async def export_license(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Download current active license file. Requires admin permission."""
    jwt_raw = await LicenseService.export_license(db)
    if not jwt_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active license found",
        )
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=jwt_raw,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=license.lic"},
    )
```

- [ ] **Step 2: 注册路由到 extensions 模块**

在 `backend/app/extensions/__init__.py` 添加：

```python
from app.extensions.license.routers import router as license_router  # noqa: F401
```

（检查现有 __init__.py 中其他 router 的注册方式，保持一致）

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/license/routers.py
git commit -m "feat(license): add license API routes (status, import, history, export)"
```

---

### Task 7: 前端 — API Client

**Files:**
- Create: `frontend/src/extensions/license/api.ts`

- [ ] **Step 1: 创建 api.ts**

```typescript
// frontend/src/extensions/license/api.ts

export interface LicenseStatus {
  valid: boolean;
  machine_id: string | null;
  type: "permanent" | "trial" | "subscription" | null;
  customer: string | null;
  max_users: number | null;
  current_users: number;
  modules: Record<string, boolean>;
  features: Record<string, unknown>;
  expires_at: string | null;
  days_remaining: number | null;
  in_grace_period: boolean;
  grace_period_remaining_days: number | null;
  warnings: string[];
  is_dev_mode: boolean;
}

export interface LicenseImportResult {
  success: boolean;
  machine_id: string | null;
  type: string | null;
  customer: string | null;
  message: string;
}

export interface LicenseHistoryItem {
  id: string;
  jwt_jti: string;
  machine_id: string;
  type: string;
  customer: string | null;
  max_users: number | null;
  modules: Record<string, boolean>;
  issued_at: string;
  expires_at: string | null;
  imported_at: string;
  is_active: boolean;
}

const BASE = "/api/license";

export async function getLicenseStatus(): Promise<LicenseStatus> {
  const res = await fetch(`${BASE}/status`);
  if (!res.ok) throw new Error(`License status failed: ${res.status}`);
  return res.json();
}

export async function importLicense(file: File): Promise<LicenseImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Import failed" }));
    throw new Error(err.detail ?? "Import failed");
  }
  return res.json();
}

export async function getLicenseHistory(
  skip = 0,
  limit = 20
): Promise<{ items: LicenseHistoryItem[]; total: number }> {
  const res = await fetch(`${BASE}/history?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  return res.json();
}

export async function exportLicense(): Promise<Blob> {
  const res = await fetch(`${BASE}/export`);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return res.blob();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/license/api.ts
git commit -m "feat(license): add frontend license API client"
```

---

### Task 8: 前端 — useLicense Hook

**Files:**
- Create: `frontend/src/extensions/license/useLicense.ts`

- [ ] **Step 1: 创建 useLicense.ts**

```typescript
// frontend/src/extensions/license/useLicense.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { getLicenseStatus, type LicenseStatus } from "./api";

export function useLicense() {
  const { data, isLoading, error } = useQuery<LicenseStatus>({
    queryKey: ["license", "status"],
    queryFn: getLicenseStatus,
    refetchInterval: 5 * 60 * 1000, // poll every 5 minutes
    staleTime: 60 * 1000,
    retry: 2,
  });

  return {
    /** Raw license status data */
    status: data,
    /** Is license data still loading? */
    isLoading,
    /** Did the status fetch fail? */
    isError: !!error,
    /** Developer mode is active */
    isDevMode: data?.is_dev_mode ?? false,
    /** License is valid (or in grace period) */
    isValid: data?.valid ?? false,
    /** System is in grace period (no license yet, countdown active) */
    inGracePeriod: data?.in_grace_period ?? false,
    /** System is fully locked (grace period expired, no valid license) */
    isLocked: !data?.valid && !data?.in_grace_period,
    /** Check if a specific module is available */
    hasModule: (name: string): boolean => {
      if (!data) return false;
      // Grace period: all modules available
      if (data.in_grace_period) return true;
      // Valid license: check module map
      return data.valid && (data.modules[name] ?? false);
    },
    /** Active warnings */
    warnings: data?.warnings ?? [],
    /** Days remaining in grace period */
    gracePeriodDays: data?.grace_period_remaining_days ?? 0,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/license/useLicense.ts
git commit -m "feat(license): add useLicense React hook with route guard logic"
```

---

### Task 9: 前端 — Banner 组件

**Files:**
- Create: `frontend/src/extensions/license/DevModeBanner.tsx`
- Create: `frontend/src/extensions/license/GracePeriodBanner.tsx`

- [ ] **Step 1: 创建 DevModeBanner.tsx**

```tsx
// frontend/src/extensions/license/DevModeBanner.tsx
"use client";

export function DevModeBanner() {
  return (
    <div className="fixed bottom-2 right-2 z-50 select-none rounded bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-700 backdrop-blur-sm dark:bg-amber-500/10 dark:text-amber-400">
      DEV MODE — License Bypassed
    </div>
  );
}
```

- [ ] **Step 2: 创建 GracePeriodBanner.tsx**

```tsx
// frontend/src/extensions/license/GracePeriodBanner.tsx
"use client";

import { useLicense } from "./useLicense";

export function GracePeriodBanner() {
  const { inGracePeriod, gracePeriodDays } = useLicense();

  if (!inGracePeriod) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-yellow-50 px-4 py-2 text-sm text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300">
      <span className="i-lucide-clock size-4" />
      <span>
        许可证未激活，{" "}
        {gracePeriodDays > 0
          ? `${gracePeriodDays} 天后系统将锁定`
          : "请尽快导入许可证"}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/license/DevModeBanner.tsx frontend/src/extensions/license/GracePeriodBanner.tsx
git commit -m "feat(license): add DevModeBanner and GracePeriodBanner components"
```

---

### Task 10: 前端 — 锁定页面组件

**Files:**
- Create: `frontend/src/extensions/license/SystemLockedPage.tsx`
- Create: `frontend/src/extensions/license/ModuleLockedPage.tsx`

- [ ] **Step 1: 创建 SystemLockedPage.tsx**

```tsx
// frontend/src/extensions/license/SystemLockedPage.tsx
"use client";

export function SystemLockedPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="max-w-md text-center">
        <div className="mb-4 text-6xl">🔒</div>
        <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-white">
          系统未激活
        </h1>
        <p className="mb-6 text-gray-600 dark:text-gray-400">
          许可证宽限期已结束。请联系管理员导入有效的许可证文件以恢复系统访问。
        </p>
        <p className="text-sm text-gray-400">
          管理员请登录管理后台导入 license.lic 文件
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 ModuleLockedPage.tsx**

```tsx
// frontend/src/extensions/license/ModuleLockedPage.tsx
"use client";

interface ModuleLockedPageProps {
  module: string;
}

const MODULE_LABELS: Record<string, string> = {
  project: "项目管理",
  docmgr: "文档管理",
  knowledge: "知识库",
  collab: "协同编辑",
  report: "报告生成",
  approval: "审批流程",
  workflow: "工作流",
  dashboard: "仪表盘",
};

export function ModuleLockedPage({ module }: ModuleLockedPageProps) {
  const label = MODULE_LABELS[module] ?? module;

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md text-center">
        <div className="mb-4 text-5xl">🚫</div>
        <h2 className="mb-2 text-xl font-semibold text-gray-900 dark:text-white">
          {label} 模块未授权
        </h2>
        <p className="text-gray-600 dark:text-gray-400">
          当前许可证不包含"{label}"模块。如需使用，请联系管理员升级许可证。
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/license/SystemLockedPage.tsx frontend/src/extensions/license/ModuleLockedPage.tsx
git commit -m "feat(license): add SystemLockedPage and ModuleLockedPage"
```

---

### Task 11: 前端 — 管理页面

**Files:**
- Create: `frontend/src/extensions/license/LicensePage.tsx`

- [ ] **Step 1: 创建 LicensePage.tsx**

```tsx
// frontend/src/extensions/license/LicensePage.tsx
"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLicenseStatus, importLicense, getLicenseHistory, exportLicense } from "./api";
import type { LicenseHistoryItem } from "./api";

export default function LicensePage() {
  const queryClient = useQueryClient();
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);

  const { data: status } = useQuery({
    queryKey: ["license", "status"],
    queryFn: getLicenseStatus,
  });

  const { data: history } = useQuery({
    queryKey: ["license", "history"],
    queryFn: () => getLicenseHistory(0, 20),
  });

  const importMutation = useMutation({
    mutationFn: importLicense,
    onSuccess: (data) => {
      setImportSuccess(data.message);
      setImportError(null);
      queryClient.invalidateQueries({ queryKey: ["license"] });
    },
    onError: (err: Error) => {
      setImportError(err.message);
      setImportSuccess(null);
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportError(null);
      setImportSuccess(null);
      importMutation.mutate(file);
    }
  };

  const handleExport = async () => {
    try {
      const blob = await exportLicense();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "license.lic";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silently fail
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("zh-CN");
  };

  const typeLabel = (t: string | null | undefined) => {
    switch (t) {
      case "permanent": return "永久";
      case "trial": return "试用";
      case "subscription": return "订阅";
      default: return t ?? "—";
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">许可证管理</h1>

      {/* Current Status Card */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">当前许可证</h2>
        {status?.is_dev_mode && (
          <div className="mb-4 rounded bg-amber-100 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
            ⚠️ 开发模式 — 许可证验证已跳过
          </div>
        )}
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-gray-500">状态</dt>
            <dd>
              {status?.in_grace_period ? (
                <span className="text-yellow-600">宽限期 ({status.grace_period_remaining_days}天)</span>
              ) : status?.valid ? (
                <span className="text-green-600">有效</span>
              ) : (
                <span className="text-red-600">无效</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">类型</dt>
            <dd>{typeLabel(status?.type)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">客户</dt>
            <dd>{status?.customer ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">到期时间</dt>
            <dd>{formatDate(status?.expires_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">用户数</dt>
            <dd>{status?.current_users ?? 0} / {status?.max_users ?? "∞"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">剩余天数</dt>
            <dd>{status?.days_remaining ?? "—"}</dd>
          </div>
        </dl>

        {/* Modules */}
        {status?.modules && Object.keys(status.modules).length > 0 && (
          <div className="mt-4">
            <dt className="mb-2 text-sm text-gray-500">模块授权</dt>
            <dd className="flex flex-wrap gap-2">
              {Object.entries(status.modules).map(([name, enabled]) => (
                <span
                  key={name}
                  className={`rounded-full px-3 py-1 text-xs ${
                    enabled
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500"
                  }`}
                >
                  {name}
                </span>
              ))}
            </dd>
          </div>
        )}

        {/* Warnings */}
        {status?.warnings && status.warnings.length > 0 && (
          <div className="mt-4 space-y-1">
            {status.warnings.map((w) => (
              <div key={w} className="rounded bg-orange-50 px-3 py-2 text-sm text-orange-700 dark:bg-orange-900/20 dark:text-orange-400">
                ⚠ {w}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Import */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">导入许可证</h2>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          选择 .lic 文件
          <input
            type="file"
            accept=".lic"
            onChange={handleFileChange}
            className="hidden"
          />
        </label>
        {importMutation.isPending && (
          <span className="ml-3 text-sm text-gray-500">导入中...</span>
        )}
        {importError && (
          <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
            {importError}
          </div>
        )}
        {importSuccess && (
          <div className="mt-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
            {importSuccess}
          </div>
        )}
      </div>

      {/* Export */}
      {status?.valid && (
        <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
          <h2 className="mb-4 text-lg font-semibold">导出许可证</h2>
          <button
            onClick={handleExport}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700"
          >
            下载 license.lic
          </button>
        </div>
      )}

      {/* History */}
      <div className="rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">导入历史</h2>
        {history?.items.length === 0 ? (
          <p className="text-sm text-gray-400">暂无记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 pr-4">许可证 ID</th>
                  <th className="pb-2 pr-4">类型</th>
                  <th className="pb-2 pr-4">客户</th>
                  <th className="pb-2 pr-4">导入时间</th>
                  <th className="pb-2">状态</th>
                </tr>
              </thead>
              <tbody>
                {history?.items.map((item: LicenseHistoryItem) => (
                  <tr key={item.id} className="border-b dark:border-gray-800">
                    <td className="py-2 pr-4 font-mono text-xs">{item.jwt_jti}</td>
                    <td className="py-2 pr-4">{typeLabel(item.type)}</td>
                    <td className="py-2 pr-4">{item.customer ?? "—"}</td>
                    <td className="py-2 pr-4">{formatDate(item.imported_at)}</td>
                    <td className="py-2">
                      {item.is_active ? (
                        <span className="text-green-600">生效中</span>
                      ) : (
                        <span className="text-gray-400">已替换</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/license/LicensePage.tsx
git commit -m "feat(license): add LicensePage admin UI"
```

---

### Task 12: 前端 — 路由与布局集成

**Files:**
- Modify: `frontend/src/app/layout.tsx` (or equivalent root layout)
- Modify: 项目路由配置文件

- [ ] **Step 1: 在根布局添加 Banner 和水印**

在根布局组件中：

```tsx
// 在 layout.tsx 顶部添加 import
import { DevModeBanner } from "@/extensions/license/DevModeBanner";
import { GracePeriodBanner } from "@/extensions/license/GracePeriodBanner";
import { useLicense } from "@/extensions/license/useLicense";

// 在 Layout 组件内添加 LicenseProvider
function LicenseShell({ children }: { children: React.ReactNode }) {
  const { isDevMode, isLocked } = useLicense();

  return (
    <>
      <GracePeriodBanner />
      {isLocked ? <SystemLockedPage /> : children}
      {isDevMode && <DevModeBanner />}
    </>
  );
}
```

- [ ] **Step 2: 在管理后台路由注册许可证页面**

根据现有的 admin 路由结构，将 `LicensePage` 添加到管理后台导航中。

- [ ] **Step 3: 示例：为项目模块添加路由守卫**

在每个受保护路由中：

```tsx
// 示例: project 路由
import { useLicense } from "@/extensions/license/useLicense";
import { ModuleLockedPage } from "@/extensions/license/ModuleLockedPage";

function ProjectRoute() {
  const { hasModule } = useLicense();

  if (!hasModule("project")) {
    return <ModuleLockedPage module="project" />;
  }

  return <ProjectWorkspace />;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/
git commit -m "feat(license): integrate license banners and route guards into layout"
```

---

### Task 13: Docker 持久化 + 配置

**Files:**
- Modify: `docker-compose.yml`
- Modify: `config.yaml`

- [ ] **Step 1: docker-compose.yml 添加 volume**

```yaml
services:
  gateway:
    volumes:
      - deerflow_data:/app/backend/.deer-flow

volumes:
  deerflow_data:
```

- [ ] **Step 2: config.yaml 添加 license 配置**

```yaml
license:
  public_key_path: backend/app/extensions/license/public_key.pem
  license_file_path: /etc/deerflow/license.lic
  grace_period_days: 7
```

- [ ] **Step 3: .gitignore 确保 private key 不入库**

```bash
echo "tools/license/private_key.pem" >> .gitignore
echo "tools/license/*.lic" >> .gitignore
```

- [ ] **Step 4: 重建并验证**

```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker logs -f gateway | head -20
```

检查 Gateway 启动日志无 license 相关错误。

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml config.yaml .gitignore
git commit -m "feat(license): add Docker volume persistence and license config"
git add backend/app/extensions/__init__.py backend/app/extensions/database.py
git commit -m "feat(license): register license module in extensions"
```

---

### Task 14: 端到端验证

- [ ] **Step 1: 验证开发模式**

```bash
# 确认 DEV_MODE=true 时 status API 返回 dev payload
curl http://localhost:2026/api/license/status | jq .
```

Expected: `valid: true, is_dev_mode: true, machine_id: "DEV-MODE"`

- [ ] **Step 2: 验证正常模式（无 license）**

```bash
# 临时禁用 DEV_MODE 重启
# 检查宽限期状态
curl http://localhost:2026/api/license/status | jq .
```

Expected: `valid: false, in_grace_period: true, grace_period_remaining_days: 7`

- [ ] **Step 3: 用 CLI 工具生成 + 导入许可证**

```bash
cd tools/license
python generate_keys.py
python license_generator.py license_request.json --permanent --all-modules --customer "Test" --output test.lic
# 通过管理页面导入 test.lic
curl http://localhost:2026/api/license/status | jq .
```

Expected: `valid: true, type: "permanent"`

- [ ] **Step 4: 验证前端页面**

浏览器访问：
- `http://localhost:2026/license` — 管理页面正常渲染
- 开发模式水印显示在右下角

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(license): complete license control system implementation"
```
