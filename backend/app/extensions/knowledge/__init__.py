"""Knowledge base module."""

from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.routers import router as kb_router
from app.extensions.knowledge.service import DocumentService, KnowledgeBaseService

__all__ = ["RAGFlowClient", "kb_router", "DocumentService", "KnowledgeBaseService"]
