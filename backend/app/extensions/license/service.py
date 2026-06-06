"""License verification and management service.

Handles offline JWT+RSA license verification, grace period, dev mode bypass.
"""

import hashlib
import logging
import os
import platform
import time
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jwt import PyJWTError, decode as jwt_decode, encode as jwt_encode
from sqlalchemy import func as sql_func, select, update
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


class LicenseError(Exception):
    """License-related errors with machine-readable codes."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class LicensePayload:
    """Decoded and validated license data from JWT."""

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
        candidates = [DEFAULT_LICENSE_PATH]
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
            LicenseService._record_start_timestamp()
            return True, GRACE_PERIOD_DAYS

        elapsed = time.time() - start_ts
        remaining = GRACE_PERIOD_DAYS - (elapsed / 86400)
        if remaining > 0:
            return True, int(remaining)
        return False, 0

    @staticmethod
    def _generate_machine_id() -> str:
        """Generate a stable machine identifier."""
        raw = platform.node() + str(uuid_mod.getnode())
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

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
            raise LicenseError(
                "LICENSE_MISSING",
                "No license file found and grace period expired",
            )

        try:
            public_key = LicenseService._load_public_key()
            claims = jwt_decode(jwt_raw, public_key, algorithms=[ALGORITHM])
        except PyJWTError as e:
            logger.error(f"License JWT verification failed: {e}")
            raise LicenseError(
                "LICENSE_INVALID", f"License verification failed: {e}"
            ) from e

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
        """Build full status response for the frontend."""
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
            }

        # Handle grace period payload
        if payload.type == "grace":
            _, remaining = LicenseService._compute_grace_period()
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
                "in_grace_period": True,
                "grace_period_remaining_days": remaining,
                "warnings": ["grace_period_active"],
                "is_dev_mode": False,
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
        public_key = LicenseService._load_public_key()
        try:
            claims = jwt_decode(jwt_raw, public_key, algorithms=[ALGORITHM])
        except PyJWTError as e:
            raise LicenseError("LICENSE_INVALID", f"Invalid license: {e}") from e

        # Check machine_id
        current_machine_id = LicenseService._generate_machine_id()
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
            raise LicenseError(
                "DUPLICATE_LICENSE", "This license has already been imported"
            )

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
        query = (
            select(License)
            .order_by(License.imported_at.desc())
            .offset(skip)
            .limit(limit)
        )
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
