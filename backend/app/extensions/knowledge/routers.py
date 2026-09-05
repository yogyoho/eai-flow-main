"""Knowledge base routers for extensions module."""

import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.admin import is_superadmin
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.middleware import current_identity, require_permission, with_data_scope
from app.extensions.config import get_extensions_config
from app.extensions.database import get_db
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.service import (
    DocumentService,
    KnowledgeBaseService,
    build_metadata_condition,
    filter_doc_ids,
)
from app.extensions.models import KnowledgeBase, KnowledgeBaseGrant
from app.extensions.schemas import (
    CurrentUser,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseGrantCreate,
    KnowledgeBaseGrantResponse,
    KnowledgeBaseGrantUpdate,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    MessageResponse,
    RAGChatRequest,
    RAGFederatedSearchRequest,
    RAGFederatedSearchResponse,
    RetrievalConfig,
    to_doc_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/knowledge-bases", tags=["Knowledge Bases"])


@router.get("/ragflow/embedding-models")
async def list_ragflow_embedding_models(
    current_user: CurrentUser = Depends(require_permission("kb:create")),
):
    """List available embedding models from RAGFlow."""
    config = get_extensions_config()
    if not config.ragflow.api_key:
        return {"models": [], "error": "RAGFlow not configured"}
    try:
        rf_client = RAGFlowClient()
        models = await rf_client.list_available_embedding_models()
        return {"models": models}
    except Exception as e:
        logger.warning(f"Failed to list RAGFlow embedding models: {e}")
        return {"models": [], "error": str(e)}


async def _load_kb_scoped(db: AsyncSession, kb_id: UUID, scope: FilterRule, identity=None) -> KnowledgeBase | None:
    """Load a KB by id ONLY if the given visibility scope permits it.

    EAI-CUSTOM: unifies by-id access with the list endpoint's
    `with_data_scope("knowledge")` FilterRule so list and by-id enforce identical
    visibility (owner OR public OR dept-overlap, or allow_all for superadmin).
    When ``identity`` is provided and the scope is not ``allow_all``, an explicit
    per-KB grant (knowledge_base_grants) is OR'd in as a visibility exception.
    Returns None if the KB does not exist or is out of scope; callers raise 404
    to avoid existence leakage.
    """
    from sqlalchemy import or_ as sa_or
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import joinedload

    from app.extensions.knowledge.access import kb_grant_visible_clause

    column_map = {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }
    clause = scope.to_sqlalchemy(KnowledgeBase, column_map)
    # EAI-CUSTOM: 显式授权为可见性 OR 例外（超管 allow_all 时跳过子查询）
    if identity is not None and scope.operator != "allow_all":
        clause = sa_or(clause, kb_grant_visible_clause(identity))
    # EAI-CUSTOM (bug-3109): joinedload owner,同 list 端点(详情响应 owner_name 同理)
    q = (
        sa_select(KnowledgeBase)
        .options(joinedload(KnowledgeBase.owner))
        .where(KnowledgeBase.id == kb_id)
        .where(clause)
    )
    return (await db.execute(q)).scalar_one_or_none()


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
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    # EAI-CUSTOM: Use ABAC data scope engine instead of manual filtering.
    # EAI-CUSTOM (M2): the prior `is_superadmin` branch is redundant —
    # `with_data_scope("knowledge")` already returns `allow_all` for superadmin
    # (Task 5), and `allow_all.to_sqlalchemy()` renders `true()` (a no-op WHERE),
    # so a single scope-aware path covers both admin and non-admin cases.
    from sqlalchemy import func
    from sqlalchemy import or_ as sa_or
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import joinedload

    from app.extensions.knowledge.access import kb_grant_visible_clause
    from app.extensions.models import KnowledgeBase

    column_map = {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }
    scope_clause = scope.to_sqlalchemy(KnowledgeBase, column_map)
    # EAI-CUSTOM: 显式授权为可见性 OR 例外（超管 allow_all 时跳过子查询）
    if scope.operator != "allow_all":
        scope_clause = sa_or(scope_clause, kb_grant_visible_clause(identity))
    # EAI-CUSTOM (bug-3109): 必须 joinedload owner —— to_response 读 kb.owner.username,
    # 异步会话下未预加载的关系访问会抛错并被静默兜底为 None(所有卡片创建人显示"未知")
    query = sa_select(KnowledgeBase).options(joinedload(KnowledgeBase.owner)).where(scope_clause)

    # Count total before pagination
    count_query = sa_select(func.count(KnowledgeBase.id)).where(scope_clause)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    query = query.offset(skip).limit(limit).order_by(KnowledgeBase.created_at.desc())
    result = await db.execute(query)
    kbs = result.scalars().all()

    return KnowledgeBaseListResponse(
        knowledge_bases=[KnowledgeBaseService.to_response(kb) for kb in kbs],
        total=total,
    )


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
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return KnowledgeBaseService.to_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: UUID,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 写门 = owner | write-grantee | 超管
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    kb = await KnowledgeBaseService.update_kb(db, kb, data)
    return KnowledgeBaseService.to_response(kb)


@router.put("/{kb_id}/retrieval-config", response_model=KnowledgeBaseResponse)
async def update_knowledge_base_retrieval_config(
    kb_id: UUID,
    config: RetrievalConfig,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 写门 = owner | write-grantee | 超管 (verbatim 镜像 update_knowledge_base)
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return await KnowledgeBaseService.update_retrieval_config(db, kb, config)


@router.delete("/{kb_id}", response_model=MessageResponse)
async def delete_knowledge_base(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:delete")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 写门 = owner | write-grantee | 超管
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    await KnowledgeBaseService.delete_kb(db, kb)
    return MessageResponse(message="Knowledge base deleted successfully")


# ---------------------------------------------------------------------------
# Knowledge Base Grants CRUD (EAI-CUSTOM): 每-KB 显式授权管理（实例级 ACL）
# ---------------------------------------------------------------------------


async def _require_kb_owner(db, kb, current_user):
    """Grant 管理门：KB owner 或超管，才可管理该 KB 的授权。"""
    if kb.owner_id != current_user.id and not await is_superadmin(db, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


async def _validate_grantee(db: AsyncSession, grantee_type: str, grantee_id: str) -> None:
    """校验 grantee 存在：user/dept 查目录表；role 查权限注册表角色 code。"""
    if grantee_type in ("user", "dept"):
        from sqlalchemy import select as sa_select

        from app.extensions.models import Department, User

        # EAI-CUSTOM: 畸形 UUID 串会在 asyncpg 编码时报错→500，先解析成 UUID 使无效 id 返回 400
        try:
            parsed_id = UUID(grantee_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {grantee_type} id")
        model = User if grantee_type == "user" else Department
        stmt = sa_select(model.id).where(model.id == parsed_id)
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {grantee_type} id")
    else:  # role
        from app.extensions.auth.registry import get_permission_registry

        if grantee_id not in get_permission_registry().list_role_codes():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role code")


@router.get("/{kb_id}/grants", response_model=list[KnowledgeBaseGrantResponse])
async def list_kb_grants(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    from sqlalchemy import select

    stmt = select(KnowledgeBaseGrant).where(KnowledgeBaseGrant.kb_id == kb_id).order_by(KnowledgeBaseGrant.created_at)
    return (await db.execute(stmt)).scalars().all()


@router.post("/{kb_id}/grants", response_model=KnowledgeBaseGrantResponse, status_code=status.HTTP_201_CREATED)
async def add_kb_grant(
    kb_id: UUID,
    data: KnowledgeBaseGrantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    await _validate_grantee(db, data.grantee_type, data.grantee_id)
    grant = KnowledgeBaseGrant(
        kb_id=kb_id,
        grantee_type=data.grantee_type,
        grantee_id=data.grantee_id,
        permission=data.permission,
        expires_at=data.expires_at,
        created_by=current_user.id,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


@router.patch("/{kb_id}/grants/{grant_id}", response_model=KnowledgeBaseGrantResponse)
async def update_kb_grant(
    kb_id: UUID,
    grant_id: UUID,
    data: KnowledgeBaseGrantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    grant = await db.get(KnowledgeBaseGrant, grant_id)
    if grant is None or grant.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    if data.permission is not None:
        grant.permission = data.permission
    if data.expires_at is not None:
        grant.expires_at = data.expires_at
    await db.commit()
    await db.refresh(grant)
    return grant


@router.delete("/{kb_id}/grants/{grant_id}", response_model=MessageResponse)
async def delete_kb_grant(
    kb_id: UUID,
    grant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
):
    kb = await _load_kb_scoped(db, kb_id, scope)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    await _require_kb_owner(db, kb, current_user)
    grant = await db.get(KnowledgeBaseGrant, grant_id)
    if grant is None or grant.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await db.delete(grant)
    await db.commit()
    return MessageResponse(message="Grant revoked")


@router.post("/{kb_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: UUID,
    file: UploadFile = File(...),
    chunk_config: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:upload")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 上传内容 = owner | write-grantee | 超管（堵住"上传未 owner 门"缺口）
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    chunk_cfg = None
    if chunk_config:
        try:
            chunk_cfg = json.loads(chunk_config)
        except json.JSONDecodeError:
            logger.warning(f"Invalid chunk_config JSON: {chunk_config}")

    config = get_extensions_config()
    upload_dir = Path(config.storage.base_path) / str(current_user.id) / "knowledge" / str(kb.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    try:
        doc = await DocumentService.create_doc(
            db,
            kb,
            file.filename,
            str(file_path),
            file.size,
            content_type=file.content_type,
            chunk_config=chunk_cfg,
        )
    except ValueError as e:
        # File type validation error — clean up uploaded file and return 400
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return DocumentService.to_response(doc)


@router.get("/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    kb_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    # EAI-CUSTOM: 法规标准系统库无 documents 表记录(法规只写 laws 表),
    # 文件列表实时投影 laws(spec 2026-09-05);投影状态取自 is_synced,无需 RAGFlow 轮询。
    # 函数级导入规避循环依赖: law.service → knowledge.client → knowledge/__init__ → 本模块。
    from app.extensions.law.service import is_law_kb_name, project_laws_as_documents

    if is_law_kb_name(kb.name):
        documents, total = await project_laws_as_documents(db, kb, skip=skip, limit=limit)
        return DocumentListResponse(documents=documents, total=total)

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
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # EAI-CUSTOM: 删除文档 = owner | write-grantee | 超管
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
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
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    """List chunks of a document (from RAGFlow)."""
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    # EAI-CUSTOM: 法规标准系统库 doc_id 为 law.id(Law.id 为 String(36),须 str(doc_id) 绑定,
    # asyncpg 严格绑定下 UUID 绑 varchar 会抛错),投影到 RAGFlow chunk 查询(spec 2026-09-05)
    # 函数级导入规避循环依赖: law.service → knowledge.client → knowledge/__init__ → 本模块。
    from app.extensions.law.service import get_law_in_kb, is_law_kb_name

    if is_law_kb_name(kb.name):
        law = await get_law_in_kb(db, kb, str(doc_id))
        if law is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        ragflow_document_id = law.ragflow_document_id
    else:
        doc = await DocumentService.get_doc_by_id(db, doc_id)
        if not doc or doc.knowledge_base_id != kb.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        ragflow_document_id = doc.ragflow_document_id
    if not kb.ragflow_dataset_id or not ragflow_document_id:
        return {"total": 0, "chunks": [], "message": "Document not synced to RAGFlow or not yet parsed"}
    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")
    try:
        rf_client = RAGFlowClient()
        result = await rf_client.list_chunks(
            dataset_id=kb.ragflow_dataset_id,
            document_id=ragflow_document_id,
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
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    """Chat with a knowledge base using RAGFlow."""
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    if not kb.ragflow_dataset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base not synced to RAGFlow")

    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")

    try:
        rf_client = RAGFlowClient()
        params = KnowledgeBaseService.resolve_chat_params(request.top_k, request.similarity_threshold, request.vector_similarity_weight, kb.retrieval_config)

        condition = None
        try:
            condition = build_metadata_condition(request.filters)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        document_ids: list[str] | None = None
        filters_truncated = False
        if condition:
            document_ids, filters_truncated = await filter_doc_ids(rf_client, kb.ragflow_dataset_id, condition)
            if not document_ids:
                return {
                    "answer": "",
                    "sources": [],
                    "filters_applied": condition,
                    "filters_truncated": False,
                    "message": "过滤条件下无匹配文档",
                }

        result = await rf_client.chat(
            dataset_id=kb.ragflow_dataset_id,
            query=request.query,
            document_ids=document_ids,
            **params,
        )

        # RAGFlow returns code != 0 on error with data=null
        if result.get("code") != 0:
            msg = result.get("message", "RAGFlow retrieval failed")
            logger.error(f"RAGFlow chat error (code={result.get('code')}): {msg}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        data = result.get("data") or {}
        return {
            "answer": "",
            "sources": data.get("chunks", []),
            "filters_applied": condition,
            "filters_truncated": filters_truncated,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAGFlow chat error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/search", response_model=RAGFederatedSearchResponse)
async def federated_search(
    request: RAGFederatedSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    """Federated search across multiple knowledge bases."""
    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAGFlow not configured")

    from sqlalchemy import or_ as sa_or
    from sqlalchemy import select

    from app.extensions.knowledge.access import kb_grant_visible_clause

    # EAI-CUSTOM (I11): apply the SAME visibility scope the list endpoint uses.
    # A requested kb_id that is missing OR out of scope surfaces as 404 (no
    # existence leakage), replacing the prior per-kb 403 from _can_access_kb.
    column_map = {
        "owner_id": KnowledgeBase.owner_id,
        "access_type": KnowledgeBase.access_type,
        "allowed_depts": KnowledgeBase.allowed_depts,
    }
    scope_clause = scope.to_sqlalchemy(KnowledgeBase, column_map)
    # EAI-CUSTOM: 显式授权为可见性 OR 例外（超管 allow_all 时跳过子查询）
    if scope.operator != "allow_all":
        scope_clause = sa_or(scope_clause, kb_grant_visible_clause(identity))
    stmt = select(KnowledgeBase).where(KnowledgeBase.id.in_(request.kb_ids)).where(scope_clause)
    result = await db.execute(stmt)
    kbs = {kb.id: kb for kb in result.scalars().all()}

    missing = [kb_id for kb_id in request.kb_ids if kb_id not in kbs]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    kb_list = [kbs[kb_id] for kb_id in request.kb_ids]

    for kb in kb_list:
        if not kb.ragflow_dataset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base not synced to RAGFlow")

    rf_client = RAGFlowClient()

    condition = None
    try:
        condition = build_metadata_condition(request.filters)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 两段式:先按元数据条件收敛每库命中的 document_ids(失败库降级为整库检索)
    filters_truncated = False
    per_kb_ids: dict = {}
    if condition:
        for kb in kb_list:
            try:
                ids, trunc = await filter_doc_ids(rf_client, kb.ragflow_dataset_id, condition)
                per_kb_ids[kb.id] = ids
                filters_truncated = filters_truncated or trunc
            except Exception as e:
                logger.warning(f"metadata 过滤失败,降级整库检索 kb={kb.id}: {e}")
                per_kb_ids[kb.id] = None

    tasks = []
    kb_for_task = []
    for kb in kb_list:
        ids = per_kb_ids.get(kb.id)
        if condition and ids is not None and not ids:
            continue  # 该库零命中,跳过
        tasks.append(
            rf_client.chat(
                dataset_id=kb.ragflow_dataset_id,
                query=request.query,
                top_k=request.per_kb_k,
                document_ids=ids,
            )
        )
        kb_for_task.append(kb)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    kb_list = kb_for_task

    chunks: list[dict] = []
    failures = 0
    for kb, res in zip(kb_list, results):
        if isinstance(res, Exception):
            failures += 1
            logger.warning(f"Federated search failed for kb={kb.id}: {res}")
            continue
        data = res.get("data") or {}
        for chunk in data.get("chunks", []) or []:
            item = dict(chunk)
            item["kb_id"] = str(kb.id)
            item["kb_name"] = kb.name
            item["ragflow_dataset_id"] = kb.ragflow_dataset_id
            score = _extract_score(item)
            if score is not None:
                item["_score"] = score
            chunks.append(item)

    if results and failures == len(results):
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

    return RAGFederatedSearchResponse(
        sources=chunks[: request.top_k],
        filters_applied=condition,
        filters_truncated=filters_truncated,
    )


@router.get("/{kb_id}/status")
async def get_knowledge_base_status(
    kb_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:read")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    """Get knowledge base sync status from RAGFlow."""
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    status_info = await KnowledgeBaseService.sync_kb_status(kb)
    return status_info
