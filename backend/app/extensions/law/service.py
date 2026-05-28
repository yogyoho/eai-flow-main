"""Business logic for law management."""

import logging
import os
import tempfile
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.extensions.config import get_extensions_config
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.models import KnowledgeBase, Law, LawTemplateRelation

from .schemas import (
    LawCreate,
    LawMetadata,
    LawResponse,
    LawStatistics,
    LawTemplateRelationCreate,
    LawUpdate,
    RAGFlowKBStatus,
    RAGFlowStatusResponse,
)

logger = logging.getLogger(__name__)


# RAGFlow知识库映射 — 按分块策略分为2个逻辑隔离的知识库：
# - ragflow-laws-legal: 法律/法规/规章 → laws parser（识别条/款/项结构）
# - ragflow-laws-standards: 各类标准/规范 → manual parser（按章/节标题边界分块）
# 各 law_type 通过元数据（law_type 字段）实现逻辑隔离，无需物理隔离
RAGFLOW_KB_MAPPING = {
    "law": "ragflow-laws-legal",
    "regulation": "ragflow-laws-legal",
    "rule": "ragflow-laws-legal",
    "national": "ragflow-laws-standards",
    "industry": "ragflow-laws-standards",
    "local": "ragflow-laws-standards",
    "technical": "ragflow-laws-standards",
}

# 去重后的唯一知识库名称及其对应的分块策略
RAGFLOW_DATASET_GROUPS = {
    "ragflow-laws-legal": "laws",
    "ragflow-laws-standards": "manual",
}

# RAGFlow分块策略映射: law_type -> chunk_method (parser_id)
# 法律/法规/规章 → laws parser（识别条/款/项结构）
# 标准/规范 → manual parser（按章/节标题边界分块）
# parser_config 不在此处设置，由 RAGFlow 使用其默认值
# (chunk_token_num=512, delimiter="\n!?。；！？", layout_recognize="DeepDOC")
_LAW_CHUNK_METHOD: dict[str, str] = {
    "law": "laws",
    "regulation": "laws",
    "rule": "laws",
    "national": "manual",
    "industry": "manual",
    "local": "manual",
    "technical": "manual",
}


class LawService:
    """法规管理服务"""

    # ---- 文件解析 ----

    @staticmethod
    async def parse_file_content(file_path: str, ext: str) -> str:
        """
        根据文件扩展名解析文件内容，返回纯文本。
        支持: .pdf, .docx, .doc, .txt, .md
        """
        if ext == ".pdf":
            return await LawService._parse_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return LawService._parse_docx(file_path)
        else:
            # txt / md
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                return f.read()

    @staticmethod
    async def _parse_pdf(file_path: str) -> str:
        """使用 markitdown 解析 PDF"""
        loop = __import__("asyncio").get_event_loop()
        return await loop.run_in_executor(None, LawService._parse_pdf_sync, file_path)

    @staticmethod
    def _parse_pdf_sync(file_path: str) -> str:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content or ""

    @staticmethod
    def _parse_docx(file_path: str) -> str:
        """使用 python-docx 解析 Word 文档"""
        import docx

        doc = docx.Document(file_path)
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    # --------------------

    @staticmethod
    def get_ragflow_dataset_id(law_type: str) -> str:
        """根据法规类型获取对应的RAGFlow知识库名称"""
        return RAGFLOW_KB_MAPPING.get(law_type, "ragflow-laws-default")

    @staticmethod
    def get_chunk_method(law_type: str) -> str | None:
        """根据法规类型获取 RAGFlow chunk_method（parser_id）。"""
        return _LAW_CHUNK_METHOD.get(law_type)

    @staticmethod
    async def _ensure_kb_registered(
        db: AsyncSession,
        owner_id: uuid.UUID,
        kb_name: str,
        ragflow_dataset_id: str | None,
        chunk_method: str,
    ) -> bool:
        """确保法规标准库在 knowledge_bases 表中注册为公开知识库。"""
        config = get_extensions_config()
        law_config = config.law.dataset_display_info.get(kb_name)
        display_name = law_config.name if law_config and law_config.name else kb_name
        display_desc = law_config.description if law_config and law_config.description else f"法规标准库 - {kb_name}"

        try:
            existing = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.name == display_name)
            )
            kb_record = existing.scalar_one_or_none()

            if kb_record is None:
                kb_record = KnowledgeBase(
                    name=display_name,
                    description=display_desc,
                    owner_id=owner_id,
                    access_type="public",
                    kb_type="ragflow",
                    ragflow_dataset_id=ragflow_dataset_id,
                    chunk_method=chunk_method,
                    status="active",
                )
                db.add(kb_record)
                await db.commit()
                logger.info("Registered law KB in knowledge_bases table: %s", display_name)
            elif ragflow_dataset_id and not kb_record.ragflow_dataset_id:
                kb_record.ragflow_dataset_id = ragflow_dataset_id
                await db.commit()
                logger.info("Updated ragflow_dataset_id for law KB: %s", display_name)

            return True
        except Exception as e:
            logger.error("Failed to register law KB %s: %s", kb_name, e)
            await db.rollback()
            return False

    @staticmethod
    async def ensure_ragflow_kb_exists(
        rf_client: RAGFlowClient,
        law_type: str,
        db: AsyncSession | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> str | None:
        """确保指定类型的RAGFlow知识库存在，返回dataset_id"""
        kb_name = LawService.get_ragflow_dataset_id(law_type)

        try:
            # 尝试获取现有知识库
            existing = await rf_client.get_dataset_by_name(kb_name)
            if existing:
                dataset_id = existing.get("id")
                if db and owner_id and dataset_id:
                    chunk_method = LawService.get_chunk_method(law_type) or "naive"
                    await LawService._ensure_kb_registered(db, owner_id, kb_name, dataset_id, chunk_method)
                return dataset_id
        except Exception as e:
            logger.warning(f"获取RAGFlow知识库失败: {e}")

        # 不存在则创建
        try:
            chunk_method = LawService.get_chunk_method(law_type)
            result = await rf_client.create_dataset(
                name=kb_name,
                description=f"法规标准库 - {law_type}",
                chunk_method=chunk_method,
            )
            dataset_id = result.get("data", {}).get("id")
            if db and owner_id and dataset_id:
                await LawService._ensure_kb_registered(db, owner_id, kb_name, dataset_id, chunk_method or "naive")
            return dataset_id
        except Exception as e:
            logger.error(f"创建RAGFlow知识库失败: {e}")
            return None

    @staticmethod
    def _law_to_response(law: Law) -> LawResponse:
        """将Law模型转换为响应Schema"""
        # 解析扩展元数据
        metadata = law.metadata_json or {}
        keywords = metadata.get("keywords", [])
        referred_laws = metadata.get("referred_laws", [])
        sector = metadata.get("sector")
        version = metadata.get("version", "1.0")
        supersedes = metadata.get("supersedes")
        superseded_by = metadata.get("superseded_by")
        source_url = metadata.get("source_url")

        # 获取关联的模板
        linked_templates = [str(rel.template_id) for rel in (law.__dict__.get("template_relations") or []) if rel.template_id]

        return LawResponse(
            id=law.id,
            title=law.title,
            law_number=law.law_number,
            law_type=law.law_type,
            status=law.status,
            department=law.department,
            effective_date=law.effective_date,
            update_date=law.update_date,
            ref_count=law.ref_count or 0,
            view_count=law.view_count or 0,
            content=law.content,
            summary=law.summary,
            ragflow_dataset_id=law.ragflow_dataset_id,
            ragflow_document_id=law.ragflow_document_id,
            is_synced=law.is_synced or "pending",
            last_sync_at=law.last_sync_at,
            keywords=keywords,
            referred_laws=referred_laws,
            sector=sector,
            version=version,
            supersedes=supersedes,
            superseded_by=superseded_by,
            source_url=source_url,
            linked_templates=linked_templates,
            created_at=law.created_at,
            updated_at=law.updated_at,
        )

    @staticmethod
    def _build_metadata_json(
        keywords: list[str] = None,
        referred_laws: list[str] = None,
        sector: str = None,
        version: str = "1.0",
        supersedes: str = None,
        superseded_by: str = None,
        source_url: str = None,
    ) -> dict:
        """构建扩展元数据JSON"""
        return {
            "keywords": keywords or [],
            "referred_laws": referred_laws or [],
            "sector": sector,
            "version": version,
            "supersedes": supersedes,
            "superseded_by": superseded_by,
            "source_url": source_url,
        }

    @staticmethod
    async def list_laws(
        db: AsyncSession,
        law_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Law], int]:
        """获取法规列表"""
        query = select(Law).options(joinedload(Law.template_relations))

        if law_type:
            query = query.where(Law.law_type == law_type)
        if status:
            query = query.where(Law.status == status)
        if keyword:
            query = query.where(Law.title.ilike(f"%{keyword}%") | Law.law_number.ilike(f"%{keyword}%"))

        # 统计总数
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # 分页查询
        query = query.order_by(Law.created_at.desc())
        query = query.offset((page - 1) * limit).limit(limit)

        result = await db.execute(query)
        laws = list(result.scalars().unique().all())

        return laws, total

    @staticmethod
    async def get_statistics(db: AsyncSession) -> LawStatistics:
        """获取法规统计信息"""
        # 总数
        total_result = await db.execute(select(func.count(Law.id)))
        total_count = total_result.scalar() or 0

        # 现行有效
        active_result = await db.execute(select(func.count(Law.id)).where(Law.status == "active"))
        active_count = active_result.scalar() or 0

        # 已废止
        deprecated_result = await db.execute(select(func.count(Law.id)).where(Law.status == "deprecated"))
        deprecated_count = deprecated_result.scalar() or 0

        # 已同步
        synced_result = await db.execute(select(func.count(Law.id)).where(Law.is_synced == "synced"))
        synced_count = synced_result.scalar() or 0

        # 待同步
        pending_result = await db.execute(select(func.count(Law.id)).where(Law.is_synced == "pending"))
        pending_sync_count = pending_result.scalar() or 0

        # 同步失败
        failed_result = await db.execute(select(func.count(Law.id)).where(Law.is_synced == "failed"))
        failed_sync_count = failed_result.scalar() or 0

        return LawStatistics(
            total_count=total_count,
            active_count=active_count,
            deprecated_count=deprecated_count,
            synced_count=synced_count,
            pending_sync_count=pending_sync_count,
            failed_sync_count=failed_sync_count,
        )

    @staticmethod
    async def get_by_type_counts(db: AsyncSession) -> dict[str, int]:
        """获取按类型统计的数量"""
        result = await db.execute(select(Law.law_type, func.count(Law.id)).group_by(Law.law_type))
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def get_by_status_counts(db: AsyncSession) -> dict[str, int]:
        """获取按状态统计的数量"""
        result = await db.execute(select(Law.status, func.count(Law.id)).group_by(Law.status))
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def get_law(db: AsyncSession, law_id: str) -> Law | None:
        """获取单个法规"""
        query = select(Law).options(joinedload(Law.template_relations)).where(Law.id == law_id)
        result = await db.execute(query)
        return result.unique().scalar_one_or_none()

    @staticmethod
    async def create_law(db: AsyncSession, data: LawCreate) -> Law:
        """创建法规"""
        law = Law(
            title=data.title,
            law_number=data.law_number,
            law_type=data.law_type,
            status=data.status or "active",
            department=data.department,
            effective_date=data.effective_date,
            update_date=data.update_date,
            content=data.content,
            summary=data.summary,
            ragflow_dataset_id=LawService.get_ragflow_dataset_id(data.law_type),
            is_synced="pending",
            metadata_json=LawService._build_metadata_json(
                keywords=data.keywords,
                referred_laws=data.referred_laws,
                sector=data.sector,
                version=data.version,
                supersedes=data.supersedes,
                superseded_by=data.superseded_by,
                source_url=data.source_url,
            ),
        )

        db.add(law)
        await db.commit()
        await db.refresh(law)
        return law

    @staticmethod
    async def update_law(db: AsyncSession, law: Law, data: LawUpdate) -> Law:
        """更新法规"""
        if data.title is not None:
            law.title = data.title
        if data.law_number is not None:
            law.law_number = data.law_number
        if data.status is not None:
            law.status = data.status
        if data.department is not None:
            law.department = data.department
        if data.effective_date is not None:
            law.effective_date = data.effective_date
        if data.update_date is not None:
            law.update_date = data.update_date
        if data.content is not None:
            law.content = data.content
        if data.summary is not None:
            law.summary = data.summary

        # 更新扩展元数据
        if any(
            [
                data.keywords is not None,
                data.referred_laws is not None,
                data.sector is not None,
                data.version is not None,
                data.supersedes is not None,
                data.superseded_by is not None,
                data.source_url is not None,
            ]
        ):
            metadata = law.metadata_json or {}
            if data.keywords is not None:
                metadata["keywords"] = data.keywords
            if data.referred_laws is not None:
                metadata["referred_laws"] = data.referred_laws
            if data.sector is not None:
                metadata["sector"] = data.sector
            if data.version is not None:
                metadata["version"] = data.version
            if data.supersedes is not None:
                metadata["supersedes"] = data.supersedes
            if data.superseded_by is not None:
                metadata["superseded_by"] = data.superseded_by
            if data.source_url is not None:
                metadata["source_url"] = data.source_url
            law.metadata_json = metadata

        law.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(law)
        return law

    @staticmethod
    async def delete_law(db: AsyncSession, law: Law) -> None:
        """删除法规，若已同步则先删除 RAGFlow 文档"""
        if law.is_synced == "synced" and law.ragflow_document_id and law.ragflow_dataset_id:
            config = get_extensions_config()
            if config.ragflow.api_key:
                rf_client = RAGFlowClient()
                try:
                    await rf_client.delete_document(law.ragflow_dataset_id, law.ragflow_document_id)
                    logger.info("Deleted RAGFlow document %s for law %s", law.ragflow_document_id, law.id)
                except Exception as e:
                    logger.error("Failed to delete RAGFlow document %s for law %s: %s", law.ragflow_document_id, law.id, e)
                    raise
        await db.delete(law)
        await db.commit()

    @staticmethod
    async def increment_view_count(db: AsyncSession, law: Law) -> None:
        """增加查看次数"""
        law.view_count = (law.view_count or 0) + 1
        await db.commit()

    @staticmethod
    async def increment_ref_count(db: AsyncSession, law: Law) -> None:
        """增加引用次数"""
        law.ref_count = (law.ref_count or 0) + 1
        await db.commit()

    @staticmethod
    async def sync_to_ragflow(
        db: AsyncSession,
        law: Law,
        file_path: str = None,
        file_name: str | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> tuple[bool, str]:
        """同步法规到 RAGFlow，返回 (成功, 错误信息)"""
        config = get_extensions_config()
        if not config.ragflow.api_key:
            msg = "RAGFlow API Key 未配置，请在扩展设置中配置 RAGFlow"
            logger.warning(msg)
            return False, msg

        rf_client = RAGFlowClient()
        dataset_id = await LawService.ensure_ragflow_kb_exists(rf_client, law.law_type, db=db, owner_id=owner_id)
        if not dataset_id:
            msg = f"RAGFlow 知识库不存在且创建失败 (law_type={law.law_type})，请先调用 init-ragflow 初始化知识库"
            logger.warning(msg)
            law.is_synced = "failed"
            await db.commit()
            return False, msg

        temp_upload_path: str | None = None

        try:
            metadata = law.metadata_json or {}
            law_metadata = LawMetadata(
                law_number=law.law_number,
                effective_date=(law.effective_date.strftime("%Y-%m-%d") if law.effective_date else None),
                issuing_authority=law.department,
                keywords=metadata.get("keywords", []),
                referred_laws=metadata.get("referred_laws", []),
                sector=metadata.get("sector"),
            )

            upload_path = file_path
            upload_name = file_name

            if upload_path is None and law.ragflow_document_id is None and law.content:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".txt",
                    delete=False,
                    encoding="utf-8",
                ) as temp_file:
                    temp_file.write(law.content)
                    temp_upload_path = temp_file.name

                upload_path = temp_upload_path
                upload_name = f"{law.law_number or law.id}.txt"

            if upload_path and law.ragflow_document_id is None:
                parser_id = LawService.get_chunk_method(law.law_type)
                result = await rf_client.upload_document(
                    dataset_id=dataset_id,
                    file_path=upload_path,
                    file_name=upload_name or os.path.basename(upload_path),
                    parser_id=parser_id,
                )
                ragflow_doc_id = result.get("data", {}).get("id")
                if ragflow_doc_id:
                    law.ragflow_document_id = ragflow_doc_id
                    await rf_client.update_document_metadata(
                        dataset_id=dataset_id,
                        document_id=ragflow_doc_id,
                        metadata=law_metadata.model_dump(exclude_none=True),
                    )
                    await rf_client.parse_document(dataset_id, ragflow_doc_id)
            elif law.ragflow_document_id:
                await rf_client.update_document_metadata(
                    dataset_id=dataset_id,
                    document_id=law.ragflow_document_id,
                    metadata=law_metadata.model_dump(exclude_none=True),
                )
            else:
                msg = "法规无正文内容且无上传文件，无法同步到 RAGFlow"
                logger.warning("No file or content available for law sync: %s", law.id)
                law.is_synced = "failed"
                await db.commit()
                return False, msg

            law.ragflow_dataset_id = dataset_id
            law.is_synced = "synced"
            law.last_sync_at = datetime.utcnow()
            await db.commit()
            return True, ""

        except Exception as e:
            msg = f"RAGFlow 同步异常: {e}"
            logger.error(f"同步法规到 RAGFlow 失败: {e}")
            law.is_synced = "failed"
            await db.commit()
            return False, msg
        finally:
            if temp_upload_path and os.path.exists(temp_upload_path):
                os.unlink(temp_upload_path)

    @staticmethod
    async def auto_register_law_kbs(db: AsyncSession, owner_id: uuid.UUID) -> list[str]:
        """检查 RAGFlow 中已存在的法规知识库，自动注册到 knowledge_bases 表。"""
        config = get_extensions_config()
        if not config.ragflow.api_key:
            return []

        rf_client = RAGFlowClient()
        registered = []

        for kb_name, chunk_method in RAGFLOW_DATASET_GROUPS.items():
            try:
                existing = await rf_client.get_dataset_by_name(kb_name)
                if existing:
                    dataset_id = existing.get("id")
                    if dataset_id:
                        ok = await LawService._ensure_kb_registered(
                            db, owner_id, kb_name, dataset_id, chunk_method
                        )
                        if ok:
                            registered.append(kb_name)
            except Exception:
                pass

        return registered

    @staticmethod
    async def get_ragflow_status(db: AsyncSession, owner_id: uuid.UUID | None = None) -> RAGFlowStatusResponse:
        """获取所有法规类型的RAGFlow知识库状态"""
        config = get_extensions_config()

        # 自动注册：如果 RAGFlow 可达，尝试补注册缺失的 KB 记录
        if config.ragflow.api_key and owner_id:
            try:
                await LawService.auto_register_law_kbs(db, owner_id)
            except Exception:
                pass

        if not config.ragflow.api_key:
            # RAGFlow未配置，返回所有missing状态
            statuses = [
                RAGFlowKBStatus(
                    type=law_type,
                    kb_name=RAGFLOW_KB_MAPPING[law_type],
                    exists=False,
                    status="missing",
                    error_message="RAGFlow未配置",
                )
                for law_type in RAGFLOW_KB_MAPPING.keys()
            ]
            return RAGFlowStatusResponse(
                statuses=statuses,
                total_kbs=len(RAGFLOW_DATASET_GROUPS),
                healthy_kbs=0,
                missing_kbs=len(RAGFLOW_DATASET_GROUPS),
                error_kbs=0,
            )

        rf_client = RAGFlowClient()
        statuses = []
        healthy = 0
        missing = 0
        errors = 0

        # 按唯一dataset查询（避免重复查询同一知识库）
        dataset_cache: dict[str, dict] = {}

        for kb_name in RAGFLOW_DATASET_GROUPS:
            try:
                existing = await rf_client.get_dataset_by_name(kb_name)
                if existing:
                    dataset_id = existing.get("id")
                    doc_count = 0
                    try:
                        docs = await rf_client.list_documents(dataset_id)
                        doc_count = len(docs.get("data", {}).get("docs", []))
                    except Exception:
                        pass
                    dataset_cache[kb_name] = {
                        "exists": True,
                        "dataset_id": dataset_id,
                        "doc_count": doc_count,
                        "status": "healthy",
                    }
                    healthy += 1
                else:
                    dataset_cache[kb_name] = {
                        "exists": False,
                        "status": "missing",
                    }
                    missing += 1
            except Exception as e:
                dataset_cache[kb_name] = {
                    "exists": False,
                    "status": "error",
                    "error_message": str(e),
                }
                errors += 1

        # 查询已注册的法规知识库
        registered_kb_names = set()
        try:
            kb_result = await db.execute(
                select(KnowledgeBase.name).where(KnowledgeBase.kb_type == "law")
            )
            registered_kb_names = {row[0] for row in kb_result.all()}
        except Exception:
            pass

        # 按每个 law_type 展开状态（多个 type 共享同一 dataset）
        config = get_extensions_config()
        for law_type, kb_name in RAGFLOW_KB_MAPPING.items():
            cached = dataset_cache.get(kb_name, {})
            law_cfg = config.law.dataset_display_info.get(kb_name)
            display_name = law_cfg.name if law_cfg and law_cfg.name else kb_name
            statuses.append(
                RAGFlowKBStatus(
                    type=law_type,
                    kb_name=kb_name,
                    exists=cached.get("exists", False),
                    dataset_id=cached.get("dataset_id"),
                    document_count=cached.get("doc_count", 0),
                    status=cached.get("status", "unknown"),
                    error_message=cached.get("error_message"),
                    kb_registered=display_name in registered_kb_names,
                )
            )

        return RAGFlowStatusResponse(
            statuses=statuses,
            total_kbs=len(RAGFLOW_DATASET_GROUPS),
            healthy_kbs=healthy,
            missing_kbs=missing,
            error_kbs=errors,
        )

    # ========== 模板关联管理 ==========

    @staticmethod
    async def link_template(
        db: AsyncSession,
        law: Law,
        data: LawTemplateRelationCreate,
    ) -> LawTemplateRelation:
        """关联模板到法规"""
        # 检查是否已存在关联
        existing = await db.execute(
            select(LawTemplateRelation).where(
                LawTemplateRelation.law_id == law.id,
                LawTemplateRelation.template_id == data.template_id,
            )
        )
        existing_relation = existing.scalar_one_or_none()

        if existing_relation:
            # 更新已有关联
            if data.section_title is not None:
                existing_relation.section_title = data.section_title
            if data.notes is not None:
                existing_relation.notes = data.notes
            await db.commit()
            return existing_relation

        # 创建新关联
        relation = LawTemplateRelation(
            law_id=law.id,
            template_id=data.template_id,
            section_title=data.section_title,
            notes=data.notes,
        )
        db.add(relation)

        # 增加引用计数
        law.ref_count = (law.ref_count or 0) + 1

        await db.commit()
        await db.refresh(relation)
        return relation

    @staticmethod
    async def unlink_template(db: AsyncSession, law: Law, template_id: str) -> bool:
        """取消关联模板"""
        result = await db.execute(
            select(LawTemplateRelation).where(
                LawTemplateRelation.law_id == law.id,
                LawTemplateRelation.template_id == template_id,
            )
        )
        relation = result.scalar_one_or_none()

        if relation:
            await db.delete(relation)
            # 减少引用计数
            law.ref_count = max(0, (law.ref_count or 1) - 1)
            await db.commit()
            return True
        return False

    @staticmethod
    async def get_law_templates(db: AsyncSession, law_id: str) -> list[dict]:
        """获取法规关联的所有模板"""
        result = await db.execute(select(LawTemplateRelation).where(LawTemplateRelation.law_id == law_id))
        relations = result.scalars().all()

        return [
            {
                "id": str(rel.id),
                "template_id": rel.template_id,
                "section_title": rel.section_title,
                "notes": rel.notes,
                "created_at": rel.created_at.isoformat() if rel.created_at else None,
            }
            for rel in relations
        ]

    @staticmethod
    async def get_template_laws(db: AsyncSession, template_id: str) -> list[LawResponse]:
        """获取引用某模板的所有法规"""
        result = await db.execute(select(Law).options(joinedload(Law.template_relations)).join(LawTemplateRelation, LawTemplateRelation.law_id == Law.id).where(LawTemplateRelation.template_id == template_id))
        laws = list(result.scalars().unique().all())
        return [LawService._law_to_response(law) for law in laws]
