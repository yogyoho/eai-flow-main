"""License control extension module."""

from app.extensions.license.routers import router as license_router
from app.extensions.license.service import LicenseService

__all__ = ["LicenseService", "license_router"]
