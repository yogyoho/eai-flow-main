"""Knowledge base and document management service."""

import logging
import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.extensions.config import get_extensions_config
from app.extensions.database import AsyncSession
from app.extensions.models import Document, KnowledgeBase
from app.extensions.schemas import (
    DocumentResponse,
    DocumentStatus,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    to_doc_status,
)

from .client import RAGFlowClient
from .storage import get_storage_provider, is_remote_uri

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """Knowledge base service with RAGFlow integration."""

    @staticmethod
    def _get_ragflow_client() -> RAGFlowClient | None:
        """Get RAGFlow client if configured."""
        config = get_extensions_config()
        if not config.ragflow.api_key:
            logger.warning("RAGFlow API key not configured")
            return None
        return RAGFlowClient()

    @staticmethod
    async def get_kb_by_id(db: AsyncSession, kb_id: UUID) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).options(joinedload(KnowledgeBase.owner)).where(KnowledgeBase.id == kb_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_kbs(
        db: AsyncSession,
        owner_id: UUID,
        dept_id: UUID | None = None,
        *,
        is_admin: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[KnowledgeBase], int]:
        """List knowledge bases visible to the user.

        Visibility rules:
        - Admin users (is_admin=True): see all knowledge bases
        - private: only the owner can see it
        - dept: users whose dept_id is in allowed_depts can see it
        - public: everyone can see it
        """
        from sqlalchemy import and_, true

        # Super admin sees everything — no visibility filter
        if is_admin:
            query = (
                select(KnowledgeBase)
                .options(joinedload(KnowledgeBase.owner))
                .offset(skip)
                .limit(limit)
                .order_by(KnowledgeBase.created_at.desc())
            )
            result = await db.execute(query)
            kbs = result.scalars().all()
            count_result = await db.execute(select(func.count(KnowledgeBase.id)))
            total = count_result.scalar() or 0
            return list(kbs), total

        # Build visibility conditions for normal users
        own_filter = KnowledgeBase.owner_id == owner_id
        public_filter = KnowledgeBase.access_type == "public"

        conditions = [own_filter, public_filter]
        if dept_id is not None:
            conditions.append(
                and_(
                    KnowledgeBase.access_type == "dept",
                    KnowledgeBase.allowed_depts.contains([dept_id]),
                )
            )

        visibility = or_(*conditions)

        query = (
            select(KnowledgeBase)
            .options(joinedload(KnowledgeBase.owner))
            .where(visibility)
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeBase.created_at.desc())
        )
        result = await db.execute(query)
        kbs = result.scalars().all()

        count_query = select(func.count(KnowledgeBase.id)).where(visibility)
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(kbs), total

    @staticmethod
    async def create_kb(db: AsyncSession, owner_id: UUID, data: KnowledgeBaseCreate) -> KnowledgeBase:
        kb = KnowledgeBase(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            access_type=data.access_type,
            kb_type=data.kb_type,
            allowed_depts=data.allowed_depts,
            embedding_model=data.embedding_model,
            chunk_method=data.chunk_method,
            parser_config=data.parser_config,
            language=data.language,
        )

        rf_client = KnowledgeBaseService._get_ragflow_client()
        if rf_client:
            try:
                if await rf_client.is_available():
                    embed_model = data.embedding_model
                    if not embed_model and data.kb_type == "ragflow":
                        available = await rf_client.list_available_embedding_models()
                        if available:
                            embed_model = available[0]
                            kb.embedding_model = embed_model
                            logger.info(f"Auto-selected embedding model: {embed_model}")

                    rf_result = await rf_client.create_dataset(
                        name=data.name,
                        description=data.description or "",
                        embedding_model=embed_model,
                        chunk_method=data.chunk_method,
                        parser_config=data.parser_config,
                    )
                    rf_dataset_id = rf_result.get("data", {}).get("id")
                    if rf_dataset_id:
                        kb.ragflow_dataset_id = rf_dataset_id
                        logger.info(f"Created RAGFlow dataset: {rf_dataset_id}")
                else:
                    logger.warning("RAGFlow service unavailable, skipping sync")
            except Exception as e:
                logger.warning(f"Failed to sync to RAGFlow: {e}. Continuing without sync.")

        db.add(kb)
        await db.commit()
        await db.refresh(kb, attribute_names=["owner"])

        config = get_extensions_config()
        if config.storage.type.lower() == "local" or config.storage.retain_local_copy:
            kb_path = Path(config.storage.base_path) / str(owner_id) / "knowledge" / str(kb.id)
            kb_path.mkdir(parents=True, exist_ok=True)

        return kb

    @staticmethod
    async def update_kb(db: AsyncSession, kb: KnowledgeBase, data: KnowledgeBaseUpdate) -> KnowledgeBase:
        if data.name is not None:
            kb.name = data.name
        if data.description is not None:
            kb.description = data.description
        if data.access_type is not None:
            kb.access_type = data.access_type
        if data.kb_type is not None:
            kb.kb_type = data.kb_type
        if data.allowed_depts is not None:
            kb.allowed_depts = data.allowed_depts
        if data.embedding_model is not None:
            kb.embedding_model = data.embedding_model
        if data.chunk_method is not None:
            kb.chunk_method = data.chunk_method
        if data.parser_config is not None:
            kb.parser_config = data.parser_config
        if data.language is not None:
            kb.language = data.language

        if kb.ragflow_dataset_id:
            rf_client = KnowledgeBaseService._get_ragflow_client()
            if rf_client:
                try:
                    await rf_client.update_dataset(
                        dataset_id=kb.ragflow_dataset_id,
                        name=kb.name,
                        description=kb.description,
                        chunk_method=data.chunk_method if data.chunk_method else None,
                        parser_config=data.parser_config if data.parser_config else None,
                    )
                except Exception as e:
                    logger.warning(f"Failed to update RAGFlow dataset: {e}")

        await db.commit()
        await db.refresh(kb)
        return kb

    @staticmethod
    async def delete_kb(db: AsyncSession, kb: KnowledgeBase) -> None:
        config = get_extensions_config()
        if config.storage.type.lower() == "local" or config.storage.retain_local_copy:
            kb_path = Path(config.storage.base_path) / str(kb.owner_id) / "knowledge" / str(kb.id)
            if kb_path.exists():
                shutil.rmtree(kb_path)

        if kb.ragflow_dataset_id:
            rf_client = KnowledgeBaseService._get_ragflow_client()
            if rf_client:
                try:
                    await rf_client.delete_dataset(kb.ragflow_dataset_id)
                    logger.info(f"Deleted RAGFlow dataset: {kb.ragflow_dataset_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete RAGFlow dataset: {e}")

        await db.execute(sql_delete(Document).where(Document.knowledge_base_id == kb.id))
        await db.delete(kb)
        await db.commit()

    @staticmethod
    async def sync_kb_status(kb: KnowledgeBase) -> dict:
        """Sync knowledge base status from RAGFlow."""
        if not kb.ragflow_dataset_id:
            return {"status": "not_synced", "message": "Not synced to RAGFlow"}

        rf_client = KnowledgeBaseService._get_ragflow_client()
        if not rf_client:
            return {"status": "error", "message": "RAGFlow not configured"}

        try:
            rf_dataset = await rf_client.get_dataset(kb.ragflow_dataset_id)
            data = rf_dataset.get("data") or {}
            return {
                "status": data.get("status", "unknown"),
                "document_count": data.get("document_count", 0),
                "chunk_count": data.get("chunk_count", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to sync RAGFlow status: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def to_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
        try:
            owner_name = kb.owner.username if kb.owner else None
        except Exception:
            owner_name = None
        return KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            ragflow_dataset_id=kb.ragflow_dataset_id,
            owner_id=kb.owner_id,
            owner_name=owner_name,
            access_type=kb.access_type,
            kb_type=kb.kb_type,
            allowed_depts=kb.allowed_depts,
            embedding_model=kb.embedding_model,
            chunk_method=kb.chunk_method,
            parser_config=kb.parser_config,
            language=kb.language,
            status=kb.status,
            created_at=kb.created_at,
        )


class DocumentService:
    """Document service with RAGFlow integration."""

    @staticmethod
    def _get_ragflow_client() -> RAGFlowClient | None:
        """Get RAGFlow client if configured."""
        config = get_extensions_config()
        if not config.ragflow.api_key:
            return None
        return RAGFlowClient()

    @staticmethod
    async def get_doc_by_id(db: AsyncSession, doc_id: UUID) -> Document | None:
        from sqlalchemy import select

        stmt = select(Document).where(Document.id == doc_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_docs(db: AsyncSession, kb_id: UUID, skip: int = 0, limit: int = 100) -> tuple[list[Document], int]:
        from sqlalchemy import func, select

        query = select(Document).where(Document.knowledge_base_id == kb_id).offset(skip).limit(limit).order_by(Document.created_at.desc())
        result = await db.execute(query)
        docs = result.scalars().all()

        count_query = select(func.count(Document.id)).where(Document.knowledge_base_id == kb_id)
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(docs), total

    # Map our chunk_method to RAGFlow parser_id
    _CHUNK_METHOD_TO_PARSER: dict[str, str] = {
        "naive": "naive",
        "report": "manual",
        "laws": "laws",
        "paper": "paper",
        "book": "book",
        "qa": "qa",
    }

    # Supported file extensions per RAGFlow parser_id
    # Based on RAGFlow v0.25.3 documentation and actual behavior:
    # - manual (report): only pdf, docx
    # - naive: pdf, docx, xlsx, pptx, txt, md, csv, json, html, eml
    # - laws: pdf, docx
    # - paper: pdf
    # - book: pdf, docx, txt, md, epub
    # - qa: pdf, docx, xlsx, csv
    _PARSER_SUPPORTED_EXTENSIONS: dict[str, set[str]] = {
        "naive": {"pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "md", "csv", "json", "html", "eml", "jpeg", "jpg", "png", "gif", "bmp", "tiff"},
        "manual": {"pdf", "docx", "doc"},
        "laws": {"pdf", "docx", "doc"},
        "paper": {"pdf"},
        "book": {"pdf", "docx", "doc", "txt", "md", "epub"},
        "qa": {"pdf", "docx", "doc", "xlsx", "xls", "csv"},
    }

    @staticmethod
    def _build_parser_config(chunk_config: dict | None) -> tuple[str | None, dict | None]:
        """Map frontend chunk config to RAGFlow parser_id and parser_config."""
        if not chunk_config:
            return None, None

        chunk_method = chunk_config.get("chunk_method", "naive")
        parser_id = DocumentService._CHUNK_METHOD_TO_PARSER.get(chunk_method, "naive")

        parser_config: dict = {}
        if "chunk_token_num" in chunk_config:
            parser_config["chunk_token_count"] = chunk_config["chunk_token_num"]
        if chunk_config.get("ocr_enabled") or chunk_config.get("preserve_tables"):
            parser_config["layout_recognize"] = True

        return parser_id, parser_config if parser_config else None

    @staticmethod
    def _validate_file_type(file_ext: str, parser_id: str) -> None:
        """Validate that the file type is supported by the given RAGFlow parser.

        Raises ValueError if the file type is not supported.
        """
        supported = DocumentService._PARSER_SUPPORTED_EXTENSIONS.get(parser_id)
        if not supported:
            # Unknown parser — allow all types (best-effort)
            return
        if file_ext not in supported:
            sorted_exts = sorted(supported)
            ext_list = ", ".join(f".{e}" for e in sorted_exts)
            raise ValueError(
                f"当前分片方式不支持 .{file_ext} 格式的文件。"
                f"支持的格式: {ext_list}"
            )

    @staticmethod
    async def create_doc(
        db: AsyncSession,
        kb: KnowledgeBase,
        file_name: str,
        file_path: str,
        file_size: int,
        auto_parse: bool = True,
        content_type: str | None = None,
        chunk_config: dict | None = None,
    ) -> Document:
        """Create a document and optionally upload to RAGFlow."""
        file_ext = Path(file_name).suffix.lower().lstrip(".")
        doc = Document(
            knowledge_base_id=kb.id,
            name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_type=file_ext,
            status="uploaded",
        )

        if kb.ragflow_dataset_id:
            rf_client = DocumentService._get_ragflow_client()
            if rf_client:
                try:
                    parser_id, parser_config = DocumentService._build_parser_config(chunk_config)
                    if not parser_id:
                        parser_id = DocumentService._CHUNK_METHOD_TO_PARSER.get(kb.chunk_method, "naive")

                    # Validate file type against parser's supported formats
                    DocumentService._validate_file_type(file_ext, parser_id)

                    rf_result = await rf_client.upload_document(
                        dataset_id=kb.ragflow_dataset_id,
                        file_path=file_path,
                        file_name=file_name,
                        parser_id=parser_id,
                        parser_config=parser_config,
                    )
                    rf_doc_id = rf_result.get("data", {}).get("id")
                    if rf_doc_id:
                        doc.ragflow_document_id = rf_doc_id
                        doc.status = DocumentStatus.UPLOADING.value
                        logger.info(f"Uploaded document to RAGFlow: {rf_doc_id} (parser_id={parser_id})")

                        if chunk_config and chunk_config.get("chunk_method"):
                            kb.chunk_method = chunk_config["chunk_method"]

                        if auto_parse:
                            try:
                                await rf_client.parse_document(kb.ragflow_dataset_id, rf_doc_id)
                                logger.info(f"Triggered parsing for document: {rf_doc_id}")
                            except Exception as parse_err:
                                logger.warning(f"Failed to trigger parsing: {parse_err}")
                except Exception as e:
                    logger.warning(f"Failed to upload to RAGFlow: {e}. Continuing without RAGFlow sync.")
                    doc.status = DocumentStatus.PENDING.value

        config = get_extensions_config()
        storage = config.storage
        storage_provider = get_storage_provider()
        if storage.type.lower() == "minio":
            try:
                stored = await storage_provider.upload_local_file(
                    local_path=file_path,
                    owner_id=str(kb.owner_id),
                    kb_id=str(kb.id),
                    filename=file_name,
                    content_type=content_type,
                )
                if stored and stored.uri:
                    doc.file_path = stored.uri
                    logger.info(f"Uploaded document to MinIO: {stored.uri}")
                    if not storage.retain_local_copy and Path(file_path).exists():
                        Path(file_path).unlink()
            except Exception as e:
                logger.warning(f"Failed to upload document to MinIO: {e}")

        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def delete_doc(db: AsyncSession, doc: Document) -> None:
        if doc.ragflow_document_id:
            kb = await KnowledgeBaseService.get_kb_by_id(db, doc.knowledge_base_id)
            if kb and kb.ragflow_dataset_id:
                rf_client = DocumentService._get_ragflow_client()
                if rf_client:
                    try:
                        await rf_client.delete_document(kb.ragflow_dataset_id, doc.ragflow_document_id)
                        logger.info(f"Deleted RAGFlow document: {doc.ragflow_document_id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete RAGFlow document: {e}")

        storage_provider = get_storage_provider()
        config = get_extensions_config()
        if is_remote_uri(doc.file_path):
            try:
                await storage_provider.delete(doc.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete remote object: {e}")

        if config.storage.type.lower() == "local" or config.storage.retain_local_copy:
            kb = await KnowledgeBaseService.get_kb_by_id(db, doc.knowledge_base_id)
            if kb:
                local_path = Path(config.storage.base_path) / str(kb.owner_id) / "knowledge" / str(kb.id) / doc.name
                if local_path.exists():
                    local_path.unlink()

        await db.delete(doc)
        await db.commit()

    @staticmethod
    async def sync_doc_status(doc: Document, kb: KnowledgeBase) -> dict:
        """Sync document status from RAGFlow."""
        if not doc.ragflow_document_id or not kb.ragflow_dataset_id:
            return {"status": doc.status, "message": "Not synced to RAGFlow"}

        rf_client = DocumentService._get_ragflow_client()
        if not rf_client:
            return {"status": doc.status, "message": "RAGFlow not configured"}

        try:
            rf_doc = await rf_client.get_document(kb.ragflow_dataset_id, doc.ragflow_document_id)
            data = rf_doc.get("data", {})
            return {
                "status": to_doc_status(data.get("status")),
                "word_count": data.get("word_count", 0),
                "chunk_count": data.get("chunk_count", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to sync RAGFlow document status: {e}")
            return {"status": doc.status, "message": str(e)}

    @staticmethod
    def to_response(doc: Document) -> DocumentResponse:
        return DocumentResponse(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            name=doc.name,
            file_path=doc.file_path,
            file_size=doc.file_size,
            file_type=doc.file_type,
            ragflow_document_id=doc.ragflow_document_id,
            status=to_doc_status(doc.status),
            error_message=doc.error_message,
            created_at=doc.created_at,
        )
