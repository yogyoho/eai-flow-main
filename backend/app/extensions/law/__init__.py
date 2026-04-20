"""Law management module for regulations and standards."""

from app.extensions.models import Law, LawTemplateRelation
from .service import LawService
from .routers import router

__all__ = ["Law", "LawTemplateRelation", "LawService", "router"]
