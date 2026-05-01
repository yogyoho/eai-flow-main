"""Law management module for regulations and standards."""

from app.extensions.models import Law, LawTemplateRelation

from .routers import router
from .service import LawService

__all__ = ["Law", "LawTemplateRelation", "LawService", "router"]
