"""App-center extension — DB-persisted app & domain definitions."""

from app.extensions.app_center.models import AppDefinition, AppDomain  # noqa: F401
from app.extensions.app_center.routers import router

__all__ = ["router", "AppDefinition", "AppDomain"]
