"""Knowledge base routers for extensions module."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.config import get_extensions_config
from app.extensions.database import get_db
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.service import DocumentService, KnowledgeBaseService
from app.extensions.models import KnowledgeBase
from app.extensions.schemas import (
    CurrentUser,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    MessageResponse,
    RAGChatRequest,
    RAGFederatedSearchRequest,
    RAGFederatedSearchResponse,
    to_doc_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/knowledge-bases", tags=["Knowledge Bases"])


def _can_access_kb(kb: KnowledgeBase, current_user: CurrentUser) -> bool:
    if kb.owner_id == current_user.id:
        return True
    if kb.access_type == "public":
        return True
    if kb.access_type == "dept":
        return bool(current_user.dept_id and kb.allowed_depts and current_user.dept_id in kb.allowed_depts)
    return False


def _extract_score(chunk: dict) -> float | None:
    for key in ("score", "similarity", "relevance"):
        value = chunk.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    distance = chunk.get("distance")
    if isinstance(distance, (int, float)):
        return 1.0 - float(distance)
    return None


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    kbs, total = await KnowledgeBaseService.list_kbs(db, current_user.id, skip=skip, limit=limit)
    return KnowledgeBaseListResponse(knowledge_bases=[KnowledgeBaseService.to_response(kb) for kb in kbs], total=total)


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:create")),
):
    kb = await KnowledgeBaseService.create_kb(db, current_user.id, data)
    return KnowledgeBaseService.to_response(kb)


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return KnowledgeBaseService.to_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: UUID,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
):
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    if kb.owner_id != current_user.id and current_user.role_name not in ["超级管理员", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    kb = await KnowledgeBaseService.update_kb(db, kb, data)
    return KnowledgeBaseService.to_response(kb)


@router.delete("/{kb_id}", response_model=MessageResponse)
async def delete_knowledge_base(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:delete")),
):
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    if kb.owner_id != current_user.id and current_user.role_name not in ["超级管理员", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    await KnowledgeBaseService.delete_kb(db, kb)
    return MessageResponse(message="Knowledge base deleted successfully")


@router.post("/{kb_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:upload")),
):
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    config = get_extensions_config()
    upload_dir = Path(config.storage.base_path) / str(current_user.id) / "knowledge" / str(kb.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    doc = await DocumentService.create_doc(
        db,
        kb,
        file.filename,
        str(file_path),
        file.size,
        content_type=file.content_type,
    )
    return DocumentService.to_response(doc)


@router.get("/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    kb_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    docs, total = await DocumentService.list_docs(db, kb_id, skip=skip, limit=limit)

    processing_docs = [d for d in docs if d.status in ("uploading", "processing") and d.ragflow_document_id]
    if processing_docs:
        kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
        if kb and kb.ragflow_dataset_id:
            rf_client = DocumentService._get_ragflow_client()
            if rf_client:
                for doc in processing_docs:
                    try:
                        status_info = await DocumentService.sync_doc_status(doc, kb)
                        rf_status = status_info.get("status")
                        if rf_status and rf_status != doc.status:
                            doc.status = to_doc_status(rf_status)
                    except Exception:
                        pass
                await db.commit()

    return DocumentListResponse(documents=[DocumentService.to_response(d) for d in docs], total=total)


@router.delete("/{kb_id}/documents/{doc_id}", response_model=MessageResponse)
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:upload")),
):
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    doc = await DocumentService.get_doc_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await DocumentService.delete_doc(db, doc)
    return MessageResponse(message="Document deleted successfully")


@router.get("/{kb_id}/documents/{doc_id}/chunks")
async def list_document_chunks(
    kb_id: UUID,
    doc_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    """List chunks of a document (from RAGFlow)."""
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    doc = await DocumentService.get_doc_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb.ragflow_dataset_id or not doc.ragflow_document_id:
        return {"total": 0, "chunks": [], "message": "Document not synced to RAGFlow or not yet parsed"}
    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")
    try:
        rf_client = RAGFlowClient()
        result = await rf_client.list_chunks(
            dataset_id=kb.ragflow_dataset_id,
            document_id=doc.ragflow_document_id,
            page=page,
            size=size,
        )
        data = result.get("data", {})
        if isinstance(data, dict):
            return {"total": data.get("total", 0), "chunks": data.get("chunks", [])}
        return {"total": 0, "chunks": []}
    except Exception as e:
        logger.error(f"RAGFlow list_chunks error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{kb_id}/chat")
async def chat_with_knowledge_base(
    kb_id: UUID,
    request: RAGChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    """Chat with a knowledge base using RAGFlow."""
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    if not kb.ragflow_dataset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base not synced to RAGFlow")

    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")

    try:
        rf_client = RAGFlowClient()
        result = await rf_client.chat(
            dataset_id=kb.ragflow_dataset_id,
            query=request.query,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            vector_similarity_weight=request.vector_similarity_weight,
        )

        data = result.get("data", {})
        return {
            "answer": data.get("answer", ""),
            "sources": data.get("chunks", []),
        }
    except Exception as e:
        logger.error(f"RAGFlow chat error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/search", response_model=RAGFederatedSearchResponse)
async def federated_search(
    request: RAGFederatedSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    """Federated search across multiple knowledge bases."""
    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")

    from sqlalchemy import select

    stmt = select(KnowledgeBase).where(KnowledgeBase.id.in_(request.kb_ids))
    result = await db.execute(stmt)
    kbs = {kb.id: kb for kb in result.scalars().all()}

    missing = [kb_id for kb_id in request.kb_ids if kb_id not in kbs]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    kb_list = [kbs[kb_id] for kb_id in request.kb_ids]

    for kb in kb_list:
        if not _can_access_kb(kb, current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        if not kb.ragflow_dataset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base not synced to RAGFlow")

    rf_client = RAGFlowClient()
    tasks = [
        rf_client.chat(
            dataset_id=kb.ragflow_dataset_id,
            query=request.query,
            top_k=request.per_kb_k,
        )
        for kb in kb_list
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    chunks: list[dict] = []
    failures = 0
    for kb, res in zip(kb_list, results):
        if isinstance(res, Exception):
            failures += 1
            logger.warning(f"Federated search failed for kb={kb.id}: {res}")
            continue
        data = res.get("data", {})
        for chunk in data.get("chunks", []) or []:
            item = dict(chunk)
            item["kb_id"] = str(kb.id)
            item["kb_name"] = kb.name
            item["ragflow_dataset_id"] = kb.ragflow_dataset_id
            score = _extract_score(item)
            if score is not None:
                item["_score"] = score
            chunks.append(item)

    if failures == len(results):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="RAGFlow search failed")

    scored = [c for c in chunks if "_score" in c]
    if scored:
        scores = [c["_score"] for c in scored]
        min_s, max_s = min(scores), max(scores)
        for c in scored:
            if max_s > min_s:
                c["score"] = (c["_score"] - min_s) / (max_s - min_s)
            else:
                c["score"] = 1.0
            c.pop("_score", None)
        chunks.sort(key=lambda x: x.get("score", 0), reverse=True)

    return RAGFederatedSearchResponse(sources=chunks[: request.top_k])


@router.get("/{kb_id}/status")
async def get_knowledge_base_status(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
):
    """Get knowledge base sync status from RAGFlow."""
    kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    status_info = await KnowledgeBaseService.sync_kb_status(kb)
    return status_info
