"""AI Document routers for extensions module."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.docmgr.service import AIDocumentService
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentListResponse,
    AIDocumentResponse,
    AIDocumentUpdate,
    CurrentUser,
    FolderListResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["AI Documents"])


@router.get("/documents", response_model=AIDocumentListResponse)
async def list_documents(
    folder: str | None = Query(None, description="Filter by folder name"),
    starred: bool | None = Query(None, description="Filter by starred status"),
    shared: bool | None = Query(None, description="Filter by shared status"),
    q: str | None = Query(None, description="Search query for title"),
    skip: int = Query(0, ge=0),
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all documents for the current user."""
    documents, total = await AIDocumentService.list_docs(
        db,
        user_id=current_user.id,
        folder=folder,
        starred=starred,
        shared=shared,
        q=q,
        skip=skip,
        limit=limit,
    )
    return AIDocumentListResponse(
        documents=[await AIDocumentService.to_response(doc) for doc in documents],
        total=total,
    )


@router.get("/documents/{doc_id}", response_model=AIDocumentResponse)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific document by ID."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return await AIDocumentService.to_detail_response(document)


@router.post("/documents", response_model=AIDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: AIDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new document."""
    document = await AIDocumentService.create(db, current_user.id, data)
    return await AIDocumentService.to_response(document)


@router.put("/documents/{doc_id}", response_model=AIDocumentResponse)
async def update_document(
    doc_id: UUID,
    data: AIDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a document."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    document = await AIDocumentService.update(db, document, data)
    return await AIDocumentService.to_response(document)


@router.delete("/documents/{doc_id}", response_model=MessageResponse)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a document."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await AIDocumentService.delete(db, document)
    return MessageResponse(message="Document deleted successfully")


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all folders for the current user."""
    folders = await AIDocumentService.list_folders(db, current_user.id)
    return FolderListResponse(folders=folders)


# ─── AI Operations ────────────────────────────────────────────────────────────

class AIEditRequest(BaseModel):
    """AI edit request schema (inline, mirrors source code)."""

    text: str = Field(..., min_length=1, description="The text to process")
    operation: str = Field(..., description="polish | expand | condense | brainstorm")
    model_name: str | None = Field(None, description="Optional model override")


class AIEditResponse(BaseModel):
    """AI edit response schema."""

    result: str


OPERATION_PROMPTS: dict[str, str] = {
    "polish": (
        "你是一位专业的文字编辑。请对以下文本进行润色，使其更加流畅、专业，保持原意不变。"
        "只输出润色后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"
    ),
    "expand": (
        "你是一位专业的写作助手。请对以下文本进行扩写，增加更多细节、论据或说明，使内容更加丰富详实。"
        "只输出扩写后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"
    ),
    "condense": (
        "你是一位专业的文字编辑。请对以下文本进行精简，去除冗余内容，保留核心信息，使表达更加简洁有力。"
        "只输出精简后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"
    ),
    "brainstorm": (
        "你是一位创意写作助手。请基于以下文本进行头脑风暴，提供3-5个相关的扩展思路或角度，每条思路用「- 」开头。"
        "只输出思路列表，不要添加任何解释或前缀。\n\n文本：\n{text}"
    ),
}

# Timeout for AI edit operations (seconds)
AI_EDIT_TIMEOUT_SECONDS = 120

# Default model for AI edit operations (faster than glm-4.7-cloud)
DEFAULT_AI_EDIT_MODEL = "siliconflow-deepseek"


def _extract_ai_response_text(content: object) -> str:
    """Extract text from AI model response content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else ""
    if content is None:
        return ""
    return str(content)


@router.post("/documents/ai-edit", response_model=AIEditResponse)
async def ai_edit_text(
    request: AIEditRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Apply AI operation (polish/expand/condense/brainstorm) to a text snippet."""
    prompt_template = OPERATION_PROMPTS.get(request.operation)
    if not prompt_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation: {request.operation}. Must be one of: {list(OPERATION_PROMPTS.keys())}",
        )

    prompt = prompt_template.format(text=request.text)
    model_name = request.model_name or DEFAULT_AI_EDIT_MODEL

    try:
        from deerflow.models import create_chat_model

        model = create_chat_model(name=model_name, thinking_enabled=False)
        response = await asyncio.wait_for(
            model.ainvoke(prompt),
            timeout=AI_EDIT_TIMEOUT_SECONDS,
        )
        result = _extract_ai_response_text(response.content).strip()
        return AIEditResponse(result=result)
    except asyncio.TimeoutError:
        logger.warning("AI edit timed out: operation=%s model=%s", request.operation, model_name)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI processing timed out, please try a shorter text or select a faster model",
        )
    except Exception as exc:
        logger.exception("AI edit failed: operation=%s model=%s err=%s", request.operation, model_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI processing failed, please try again",
        )
