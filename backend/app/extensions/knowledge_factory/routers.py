"""FastAPI routers for knowledge factory extraction."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user_optional, require_permission
from app.extensions.database import get_db
from app.extensions.models import Document, KnowledgeBase, User
from app.extensions.schemas import CurrentUser as CurrentUserSchema
from sqlalchemy import select

from .pipeline import ExtractionPipeline
from .schemas import (
    ComplianceRuleResponse,
    ComplianceRuleListResponse,
    ComplianceRuleCreate,
    ComplianceRuleUpdate,
    ComplianceRuleImportResponse,
    ComplianceRuleBatchCreate,
    ComplianceRuleBatchResponse,
    ComplianceRuleOverviewResponse,
    RuleDictionariesResponse,
    ComplianceRuleStatusResponse,
    ComplianceRuleStatisticsResponse,
    ContentContract,
    CrossSectionRule,
    DictCategoryResponse,
    DictItemCreate,
    DictItemUpdate,
    DictItemResponse,
    DictItemListResponse,
    DomainCreate,
    DomainListResponse,
    DomainResponse,
    DomainUpdate,
    ExtractionConfig,
    ExtractionTaskCreate,
    ExtractionTaskListResponse,
    ExtractionTaskResponse,
    QualityAssessmentResult,
    StructureType,
    TemplateDocument,
    TemplateListItem,
    TemplateListResponse,
    TemplateResult,
    TemplateSection,
    TemplateUpdate,
    TemplateVersionResponse,
    TemplateRollbackRequest,
    TemplateRollbackResponse,
    StepStatusSchema,
    VersionCompareRequest,
    VersionDiff,
)
from app.extensions.settings.service import SystemConfigService
from .dictionary_loader import load_rule_dictionaries
from .seed_service import SeedImportService
from .service import (
    DictionaryService,
    DomainService,
    QualityService,
    TaskService,
    TemplateService,
    VersionCompareService,
)
from .models import (
    ComplianceRule,
    ExtractionTemplate,
    ExtractionTemplateVersion,
    ExtractionTask,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kf", tags=["knowledge-factory"])

# 跟踪正在运行的流水线 asyncio.Task，用于暂停/取消时真正中断执行
_pipeline_tasks: dict[str, asyncio.Task] = {}

CurrentUser = Annotated[CurrentUserSchema, Depends(require_permission("system:access"))]
OptionalUser = Annotated[Optional[CurrentUserSchema], Depends(get_current_user_optional)]


# ============== Domain APIs ==============


@router.post("/domains", response_model=DomainResponse)
async def create_domain(
    data: DomainCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """创建领域（管理员操作）"""
    existing = await DomainService.get_domain(db, data.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"领域 {data.id} 已存在")
    domain = await DomainService.create_domain(db, data)
    return domain


@router.get("/domains", response_model=DomainListResponse)
async def list_domains(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """列出所有领域"""
    domains = await DomainService.list_domains(db)
    return DomainListResponse(domains=domains, total=len(domains))


@router.put("/domains/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: str,
    data: DomainUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """更新领域"""
    domain = await DomainService.get_domain(db, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="领域不存在")
    await DomainService.update_domain(db, domain, data)
    await db.refresh(domain)
    return domain


@router.delete("/domains/{domain_id}")
async def delete_domain(
    domain_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """删除领域"""
    domain = await DomainService.get_domain(db, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="领域不存在")
    await DomainService.delete_domain(db, domain)
    return {"message": "领域已删除"}


_ALLOWED_INFER_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}


@router.post("/domains/infer-chapters")
async def infer_chapters(
    file: UploadFile = File(...),
    max_depth: int = Form(3),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _current_user: CurrentUser = None,
):
    """上传参考文档，AI 自动提取章节结构"""
    max_depth = max(1, min(6, max_depth))  # clamp to 1-6
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_INFER_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}，支持: {', '.join(sorted(_ALLOWED_INFER_EXTENSIONS))}")

    # 保存到临时文件
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB 限制
        raise HTTPException(status_code=400, detail="文件大小不能超过 20MB")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 解析文档为文本
        text = await asyncio.to_thread(_parse_document, tmp_path, ext)
        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文档中提取文本内容")

        # 解析 LLM 模型：优先使用系统基本设置中的默认模型
        system_config = await SystemConfigService.get_all(db) if db else {}
        system_default_model = system_config.get("default_model") or None

        # LLM 推断章节结构
        from .llm import ExtractionLLMClient

        llm = ExtractionLLMClient(model_name=system_default_model, max_content_chars=10000)
        try:
            result = await asyncio.to_thread(llm.infer_schema, filename, text, max_depth)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        if not result.get("sections"):
            raise HTTPException(status_code=422, detail="AI 未能识别出文档的章节结构，请检查文档内容是否包含章节标题")
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_document(file_path: str, ext: str) -> str:
    """根据文件类型解析文档为纯文本"""
    path = Path(file_path)
    if ext == ".pdf":
        from markitdown import MarkItDown

        md = MarkItDown()
        return md.convert(str(path)).text_content or ""
    elif ext in (".doc", ".docx"):
        try:
            import docx

            doc = docx.Document(str(path))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except ImportError:
            from markitdown import MarkItDown

            md = MarkItDown()
            return md.convert(str(path)).text_content or ""
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


# ============== Dictionary APIs ==============


@router.get("/dictionaries/categories", response_model=list[DictCategoryResponse])
async def list_dict_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """列出所有字典分类"""
    return await DictionaryService.list_categories(db)


@router.get("/dictionaries/{category}", response_model=DictItemListResponse)
async def list_dict_items(
    category: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """按分类列出字典项"""
    items, total = await DictionaryService.list_items(db, category, page, limit)
    return DictItemListResponse(items=items, total=total)


@router.post("/dictionaries", response_model=DictItemResponse, status_code=status.HTTP_201_CREATED)
async def create_dict_item(
    data: DictItemCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """创建字典项"""
    existing = await DictionaryService.get_item(db, data.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"字典项 {data.id} 已存在")
    return await DictionaryService.create_item(db, data)


@router.put("/dictionaries/{item_id}", response_model=DictItemResponse)
async def update_dict_item(
    item_id: str,
    data: DictItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """更新字典项"""
    item = await DictionaryService.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="字典项不存在")
    await DictionaryService.update_item(db, item, data)
    await db.refresh(item)
    return item


@router.delete("/dictionaries/{item_id}")
async def delete_dict_item(
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """删除字典项"""
    item = await DictionaryService.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="字典项不存在")
    await DictionaryService.delete_item(db, item)
    return {"message": "字典项已删除"}


# ============== Task APIs ==============


@router.post("/extraction/tasks", response_model=ExtractionTaskResponse)
async def create_task(
    data: ExtractionTaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """创建抽取任务（立即触发流水线执行）"""
    # 验证样例报告存在
    report_names = []
    for report_id in data.source_report_ids:
        result = await db.execute(select(Document).where(Document.id == report_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail=f"样例报告 {report_id} 不存在")
        report_names.append(doc.name)

    # 创建任务
    task = await TaskService.create_task(
        db, data, user_id=current_user.id
    )

    # 异步启动流水线（不阻塞 HTTP 请求）
    from app.extensions.database import get_session_factory
    bg_task = asyncio.create_task(run_pipeline_background(str(task.id), data, get_session_factory()))
    _pipeline_tasks[str(task.id)] = bg_task

    from .schemas import StepStatus as SS

    # 构建响应
    steps = [
        {"name": name, "status": SS.WAITING.value, "duration": None, "detail": ""}
        for name in ["文档解析", "章节推断", "元数据抽取", "模板融合", "合规校验"]
    ]
    return ExtractionTaskResponse(
        id=task.id,
        name=task.name,
        domain=task.domain,
        industry=task.industry,
        report_type=task.report_type,
        source_reports=report_names,
        status="pending",
        progress=0,
        steps=[_step_to_schema(s) for s in steps],
        result=None,
        error=None,
        created_at=task.created_at,
    )


async def run_pipeline_background(
    task_id: str,
    data: ExtractionTaskCreate,
    session_factory,
):
    """后台运行抽取流水线（使用传入的 session factory）"""
    tid = UUID(task_id)
    try:
        async with session_factory() as db:
            task = await TaskService.get_task(db, tid)
            if not task:
                return

            await TaskService.set_task_running(db, task)

            config = data.config or ExtractionConfig()

            # 收集文档信息
            report_docs = []
            for report_id in data.source_report_ids:
                result = await db.execute(
                    select(Document, KnowledgeBase)
                    .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
                    .where(Document.id == report_id)
                )
                row = result.first()
                if row:
                    doc, kb = row
                    report_docs.append({
                        "id": str(doc.id),
                        "name": doc.name,
                        "kb_id": str(kb.id),
                        "ragflow_document_id": doc.ragflow_document_id,
                        "ragflow_dataset_id": kb.ragflow_dataset_id,
                    })

            # 解析 LLM 模型：优先使用系统基本设置中的默认模型
            system_config = await SystemConfigService.get_all(db)
            system_default_model = system_config.get("default_model") or None
            effective_model = system_default_model or config.llm_model or None
            logger.info(f"[Task {task_id}] Resolved LLM model: system_default={system_default_model!r}, config_llm_model={config.llm_model!r}, effective={effective_model!r}")

            pipeline = ExtractionPipeline(
                llm_model=effective_model,
            )

            # 5 个流水线阶段名称，由 pipeline 的 _emit 回调按名称精准更新
            _PIPELINE_STEP_NAMES = ["文档解析", "章节推断", "元数据抽取", "模板融合", "合规校验"]

            # 用于接收每步完成的进度更新
            async def on_step(step_schema: StepStatusSchema):
                await db.refresh(task)
                steps = list(task.steps or [])
                new_status = step_schema.status.value if hasattr(step_schema.status, "value") else str(step_schema.status)
                # 按名称精准更新已有步骤（waiting → running → completed），避免重复追加
                updated = False
                for s in steps:
                    if s.get("name") == step_schema.name:
                        s["status"] = new_status
                        s["duration"] = step_schema.duration
                        s["detail"] = step_schema.detail
                        updated = True
                        break
                if not updated:
                    steps.append(step_schema.model_dump())
                logger.info(
                    f"[Task {task_id}] on_step: name={step_schema.name!r}, status={new_status!r}, "
                    f"duration={step_schema.duration!r}, detail={step_schema.detail!r}, "
                    f"updated={updated}, total_steps={len(steps)}"
                )
                # 进度 = 5 个流水线阶段中已完成的数量 / 5
                pipeline_steps = [s for s in steps if s.get("name") in _PIPELINE_STEP_NAMES]
                completed = sum(1 for s in pipeline_steps if s.get("status") == "completed")
                task.progress = int((completed / 5) * 100) if pipeline_steps else 0
                await TaskService.update_task_steps(db, task, steps)

            # 获取领域的标准章节作为参考结构
            reference_chapters = None
            if data.domain:
                domain_obj = await DomainService.get_domain(db, data.domain)
                if domain_obj and domain_obj.standard_chapters:
                    reference_chapters = domain_obj.standard_chapters
                    logger.info(f"[Task {task_id}] Loaded reference chapters from domain '{data.domain}': {len(reference_chapters.get('sections', []))} sections")

            result = await pipeline.run(
                task_id,
                report_docs,
                config,
                domain=data.domain,
                reference_chapters=reference_chapters,
                progress_callback=on_step,
            )

            await db.refresh(task)
            # 检查是否被暂停/取消中断
            if task.status in ("paused", "failed"):
                logger.info(f"Pipeline for task {task_id} was paused/cancelled, skipping template creation")
                _pipeline_tasks.pop(task_id, None)
                return

            from .models import ExtractionTemplate

            existing = await db.execute(
                select(ExtractionTemplate).where(
                    ExtractionTemplate.domain == data.domain,
                    ExtractionTemplate.name == data.target_template_name,
                    ExtractionTemplate.version == "v1.0",
                )
            )
            template = existing.scalar_one_or_none()

            if template:
                logger.info(f"Updating existing template {template.id}")
                template.root_sections_json = {"sections": result.sections}
                template.cross_section_rules = {"rules": result.cross_section_rules}
                template.completeness_score = result.completeness_score
                template.source_report_ids = [str(r) for r in data.source_report_ids]
            else:
                template = ExtractionTemplate(
                    domain=data.domain,
                    name=data.target_template_name,
                    version="v1.0",
                    status="draft",
                    root_sections_json={"sections": result.sections},
                    cross_section_rules={"rules": result.cross_section_rules},
                    completeness_score=result.completeness_score,
                    source_report_ids=[str(r) for r in data.source_report_ids],
                    created_by=task.created_by,
                )
                db.add(template)

            await db.commit()
            await db.refresh(template)

            task.target_template_id = template.id
            await TaskService.set_task_completed(
                db, task,
                result_template_json={
                    "template_id": str(template.id),
                    "name": template.name,
                    "version": template.version,
                    "domain": template.domain,
                    "completeness_score": result.completeness_score,
                    "chapters": result.chapters,
                    "sections": result.total_sections,
                },
            )
            logger.info(
                f"Pipeline completed for task {task_id}, template {template.id}, "
                f"{result.chapters} chapters, {result.total_sections} sections, "
                f"score {result.completeness_score}%"
            )

    except asyncio.CancelledError:
        logger.info(f"Pipeline for task {task_id} was cancelled via asyncio")
        try:
            async with session_factory() as db:
                task = await TaskService.get_task(db, tid)
                if task and task.status not in ("completed", "failed"):
                    task.status = "failed"
                    task.error_message = "任务已被取消"
                    task.completed_at = None
                    await db.commit()
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"Pipeline failed for task {task_id}")
        try:
            async with session_factory() as db:
                task = await TaskService.get_task(db, tid)
                if task:
                    await db.rollback()
                    await TaskService.set_task_failed(db, task, str(e))
        except Exception:
            pass
    finally:
        _pipeline_tasks.pop(task_id, None)


@router.get("/extraction/tasks", response_model=ExtractionTaskListResponse)
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """列出抽取任务（分页）"""
    tasks, total = await TaskService.list_tasks(db, status=status, page=page, limit=limit)

    # 填充报告名称
    task_responses = []
    for task in tasks:
        report_names = []
        for rid in (task.source_report_ids or []):
            try:
                # rid 可能是 UUID 对象或字符串
                doc_id = UUID(str(rid)) if not isinstance(rid, UUID) else rid
                result = await db.execute(select(Document).where(Document.id == doc_id))
                doc = result.scalar_one_or_none()
                if doc:
                    report_names.append(doc.name)
            except Exception:
                pass

        task_responses.append(ExtractionTaskResponse(
            id=task.id,
            name=task.name,
            domain=task.domain,
            source_reports=report_names,
            status=task.status,
            progress=task.progress,
            steps=[_step_to_schema(s) for s in (task.steps or [])],
            result=(
                TemplateResult(**task.result_template_json)
                if task.result_template_json else None
            ),
            error=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))

    return ExtractionTaskListResponse(tasks=task_responses, total=total)


@router.get("/extraction/tasks/{task_id}", response_model=ExtractionTaskResponse)
async def get_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取任务详情"""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    report_names = []
    for rid in (task.source_report_ids or []):
        try:
            # rid 可能是 UUID 对象或字符串
            doc_id = UUID(str(rid)) if not isinstance(rid, UUID) else rid
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if doc:
                report_names.append(doc.name)
        except Exception:
            pass

    return ExtractionTaskResponse(
        id=task.id,
        name=task.name,
        domain=task.domain,
        industry=task.industry,
        report_type=task.report_type,
        source_reports=report_names,
        status=task.status,
        progress=task.progress,
        steps=[_step_to_schema(s) for s in (task.steps or [])],
        result=(
            TemplateResult(**task.result_template_json)
            if task.result_template_json else None
        ),
        error=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.post("/extraction/tasks/{task_id}/pause")
async def pause_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """暂停任务（中断正在运行的流水线）"""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await TaskService.pause_task(db, task)
    # 取消后台 asyncio 任务
    bg = _pipeline_tasks.pop(str(task_id), None)
    if bg and not bg.done():
        bg.cancel()
    return {"message": "任务已暂停"}


@router.post("/extraction/tasks/{task_id}/resume")
async def resume_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """恢复任务（重新创建流水线）"""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "paused":
        raise HTTPException(status_code=400, detail="只有已暂停的任务可以恢复")

    await TaskService.resume_task(db, task)

    # 重建流水线配置并重新启动
    config_dict = task.config or {}
    config = ExtractionConfig(**config_dict) if config_dict else ExtractionConfig()
    new_data = ExtractionTaskCreate(
        name=task.name or "",
        domain=task.domain or "default",
        source_report_ids=[UUID(str(rid)) for rid in (task.source_report_ids or [])],
        target_template_name=task.name or "Template",
        config=config,
    )
    from app.extensions.database import get_session_factory
    bg_task = asyncio.create_task(run_pipeline_background(str(task.id), new_data, get_session_factory()))
    _pipeline_tasks[str(task.id)] = bg_task
    return {"message": "任务已恢复"}


@router.post("/extraction/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """取消任务（中断正在运行的流水线）"""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await TaskService.cancel_task(db, task)
    # 取消后台 asyncio 任务
    bg = _pipeline_tasks.pop(str(task_id), None)
    if bg and not bg.done():
        bg.cancel()
    return {"message": "任务已取消"}


@router.post("/extraction/tasks/{task_id}/rerun", response_model=ExtractionTaskResponse)
async def rerun_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """重新运行任务"""
    old_task = await TaskService.get_task(db, task_id)
    if not old_task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 清理旧的后台任务
    _pipeline_tasks.pop(str(task_id), None)

    from .schemas import ExtractionTaskCreate as ETC

    def to_uuid_str(rid):
        if hasattr(rid, '__str__'):
            return str(rid)
        return str(rid)

    config_dict = old_task.config or {}
    config = ExtractionConfig(**config_dict) if config_dict else None
    new_data = ETC(
        name=f"{old_task.name or 'Template'} (重试)",
        domain=old_task.domain or "default",
        source_report_ids=[UUID(to_uuid_str(rid)) for rid in (old_task.source_report_ids or [])],
        target_template_name=old_task.name or "Template",
        config=config,
    )
    return await create_task(new_data, db, current_user)


@router.delete("/extraction/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """删除单个任务（仅限已完成/失败/已暂停的任务）"""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in ("pending", "running"):
        raise HTTPException(status_code=400, detail="运行中的任务不能删除，请先暂停或取消")
    # 清理后台任务引用
    _pipeline_tasks.pop(str(task_id), None)
    await TaskService.delete_task(db, task)
    return {"message": "任务已删除"}


@router.delete("/extraction/tasks")
async def clear_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    statuses: Optional[str] = Query(None, description="要清除的状态，逗号分隔，默认 completed,failed"),
):
    """批量清除历史任务"""
    status_list = [s.strip() for s in statuses.split(",")] if statuses else ["completed", "failed"]
    for s in status_list:
        if s in ("pending", "running"):
            raise HTTPException(status_code=400, detail=f"不能清除运行中的任务（状态: {s}）")
    count = await TaskService.clear_tasks(db, statuses=status_list)
    return {"message": f"已清除 {count} 个任务", "deleted_count": count}


# ============== Template APIs ==============


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    domain: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """列出模板（分页）"""
    templates, total = await TemplateService.list_templates(
        db, domain=domain, status=status, page=page, limit=limit
    )
    items = []
    for t in templates:
        src_count = len(t.source_report_ids) if t.source_report_ids else 0
        created_by_name = None
        if t.created_by:
            result = await db.execute(select(User).where(User.id == t.created_by))
            u = result.scalar_one_or_none()
            if u:
                created_by_name = u.username
        items.append(TemplateListItem(
            id=t.id,
            domain=t.domain,
            name=t.name,
            version=t.version,
            status=t.status,
            completeness_score=t.completeness_score or 0,
            source_report_count=src_count,
            created_by=created_by_name,
            created_at=t.created_at,
            updated_at=t.updated_at,
        ))
    return TemplateListResponse(templates=items, total=total)


@router.get("/templates/{template_id}", response_model=TemplateDocument)
async def get_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取模板详情"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return TemplateService.to_template_document(template)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: UUID,
    data: TemplateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """更新模板（草稿状态）"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    if template.status == "published":
        raise HTTPException(status_code=400, detail="已发布的模板不能直接修改，请先取消发布")
    updated = await TemplateService.update_template(db, template, data)
    return {"message": "模板已更新", "id": str(updated.id)}


@router.post("/templates/{template_id}/publish")
async def publish_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """发布模板"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    await TemplateService.publish_template(db, template, user_id=current_user.id)
    return {"message": "模板已发布", "id": str(template.id)}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """删除模板"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    await TemplateService.delete_template(db, template)
    return {"message": "模板已删除"}


@router.get("/templates/{template_id}/export")
async def export_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """导出模板为 JSON 文件下载"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    content = export_template_json(
        domain=template.domain,
        template_name=template.name,
        version=template.version,
    )
    if content is None:
        raise HTTPException(status_code=404, detail="模板快照文件不存在")

    filename = f"{template.name}_{template.version}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/templates/{template_id}/versions", response_model=list[TemplateVersionResponse])
async def get_template_versions(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取模板版本历史"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    versions = await TemplateService.get_template_versions(db, template_id)
    result = []
    for v in versions:
        published_by_name = None
        if v.published_by:
            r = await db.execute(select(User).where(User.id == v.published_by))
            u = r.scalar_one_or_none()
            if u:
                published_by_name = u.username
        result.append(TemplateVersionResponse(
            id=v.id,
            version=v.version,
            changelog=v.changelog,
            published_by=published_by_name,
            published_at=v.published_at,
        ))
    return result


@router.post("/templates/{template_id}/rollback", response_model=TemplateRollbackResponse)
async def rollback_template(
    template_id: UUID,
    request: TemplateRollbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """回滚模板到指定版本。

    回滚后将：
    1. 从历史快照恢复章节结构和交叉规则
    2. 自动递增版本号
    3. 模板状态变为草稿
    """
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    # 验证版本存在
    target_version = await TemplateService.get_version_by_id(db, template_id, request.version_id)
    if not target_version:
        raise HTTPException(status_code=404, detail="指定的版本不存在")

    try:
        updated = await TemplateService.rollback_template(
            db=db,
            template=template,
            version_id=request.version_id,
            changelog=request.changelog,
            user_id=current_user.id,
        )
        return TemplateRollbackResponse(
            success=True,
            message=f"成功回滚到版本 {target_version.version}",
            template_id=updated.id,
            new_version=updated.version,
            restored_version=target_version.version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/templates/{template_id}/versions/{version_id}", response_model=TemplateVersionResponse)
async def get_template_version_detail(
    template_id: UUID,
    version_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取特定版本的详细信息（包括快照内容）"""
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    version = await TemplateService.get_version_by_id(db, template_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    published_by_name = None
    if version.published_by:
        r = await db.execute(select(User).where(User.id == version.published_by))
        u = r.scalar_one_or_none()
        if u:
            published_by_name = u.username

    return TemplateVersionResponse(
        id=version.id,
        version=version.version,
        changelog=version.changelog,
        published_by=published_by_name,
        published_at=version.published_at,
    )


@router.post("/templates/{template_id}/assess-quality", response_model=QualityAssessmentResult)
async def assess_template_quality(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """AI 评估模板质量。

    对模板进行多维度质量评估：
    - completeness（完整性）
    - accuracy（准确性）
    - consistency（一致性）
    - compliance（合规性）
    - freshness（时效性）
    """
    template = await TemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    # 构建用于评估的模板数据
    template_data = QualityService.build_template_data_for_assessment(template)

    # 调用 AI 评估服务
    result = QualityService.assess_template_quality(template_data)

    return QualityAssessmentResult(**result)


@router.post("/templates/compare", response_model=VersionDiff)
async def compare_template_versions(
    request: VersionCompareRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """对比两个模板版本的差异。

    返回新增、删除、修改的章节列表。
    """
    # 获取版本A
    stmt_a = select(ExtractionTemplateVersion).where(
        ExtractionTemplateVersion.id == request.version_a_id
    )
    result_a = await db.execute(stmt_a)
    version_a = result_a.scalar_one_or_none()
    if not version_a:
        raise HTTPException(status_code=404, detail="版本A不存在")

    # 获取版本B
    stmt_b = select(ExtractionTemplateVersion).where(
        ExtractionTemplateVersion.id == request.version_b_id
    )
    result_b = await db.execute(stmt_b)
    version_b = result_b.scalar_one_or_none()
    if not version_b:
        raise HTTPException(status_code=404, detail="版本B不存在")

    # 获取主模板以获取章节数据
    template_a = await TemplateService.get_template(db, version_a.template_id)
    template_b = await TemplateService.get_template(db, version_b.template_id)
    if not template_a or not template_b:
        raise HTTPException(status_code=404, detail="模板不存在")

    # 从快照中提取章节列表
    snapshot_a = version_a.snapshot_json or {}
    snapshot_b = version_b.snapshot_json or {}
    sections_a = snapshot_a.get("sections", template_a.root_sections_json or {}).get("sections", [])
    sections_b = snapshot_b.get("sections", template_b.root_sections_json or {}).get("sections", [])

    # 调用版本对比服务
    diff_result = VersionCompareService.compare_versions(
        version_a_sections=sections_a,
        version_b_sections=sections_b,
        version_a=version_a.version,
        version_b=version_b.version,
    )

    return VersionDiff(**diff_result)


# ============== Helpers ==============


def _step_to_schema(step_dict: dict) -> dict:
    """将 dict 转为 StepStatusSchema 兼容的 dict"""
    from .schemas import StepStatusSchema
    return StepStatusSchema(**step_dict).model_dump()


# ============== Compliance Rule APIs ==============


from .models import ComplianceRule
from sqlalchemy import func, or_


def _build_rule_response(rule: ComplianceRule) -> ComplianceRuleResponse:
    return ComplianceRuleResponse(
        id=rule.id,
        rule_id=rule.rule_id,
        name=rule.name,
        type=rule.type,
        type_name=rule.type_name,
        severity=rule.severity,
        severity_name=rule.severity_name,
        enabled=rule.enabled,
        description=rule.description,
        industry=rule.industry,
        industry_name=rule.industry_name,
        report_types=rule.report_types,
        applicable_regions=rule.applicable_regions,
        national_level=rule.national_level,
        source_sections=rule.source_sections,
        target_sections=rule.target_sections,
        validation_config=rule.validation_config,
        error_message=rule.error_message,
        auto_fix_suggestion=rule.auto_fix_suggestion,
        seed_version=rule.seed_version,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _get_rule_or_404(db: AsyncSession, rule_key: str) -> ComplianceRule:
    """通过 UUID 或业务规则编码获取规则。"""
    query = None
    try:
        query = select(ComplianceRule).where(ComplianceRule.id == UUID(rule_key))
        result = await db.execute(query)
        rule = result.scalar_one_or_none()
        if rule:
            return rule
    except ValueError:
        pass

    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.rule_id == rule_key)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_key} 不存在")
    return rule


async def _get_trigger_statistics_payload(
    db: AsyncSession,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    from datetime import datetime
    from .models import ComplianceRuleLog

    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    conditions = []
    if start:
        conditions.append(ComplianceRuleLog.executed_at >= start)
    if end:
        conditions.append(ComplianceRuleLog.executed_at <= end)

    if conditions:
        total_stmt = select(func.count()).where(*conditions)
    else:
        total_stmt = select(func.count()).select_from(ComplianceRuleLog)
    total_result = await db.execute(total_stmt)
    total_triggers = total_result.scalar() or 0

    blocked_conditions = conditions + [
        ComplianceRuleLog.check_result.in_(["fail", "warning"])
    ]
    blocked_stmt = select(func.count()).where(*blocked_conditions)
    blocked_result = await db.execute(blocked_stmt)
    blocked_triggers = blocked_result.scalar() or 0

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_stmt = select(func.count()).where(
        ComplianceRuleLog.executed_at >= month_start
    )
    month_result = await db.execute(month_stmt)
    month_triggers = month_result.scalar() or 0

    month_blocked_stmt = select(func.count()).where(
        ComplianceRuleLog.executed_at >= month_start,
        ComplianceRuleLog.check_result.in_(["fail", "warning"]),
    )
    month_blocked_result = await db.execute(month_blocked_stmt)
    month_blocked = month_blocked_result.scalar() or 0

    return {
        "total_triggers": total_triggers,
        "blocked_triggers": blocked_triggers,
        "month_triggers": month_triggers,
        "month_blocked": month_blocked,
        "pass_rate": (
            (total_triggers - blocked_triggers) / total_triggers * 100
            if total_triggers > 0 else 100
        ),
    }


@router.get("/rule-dictionaries", response_model=RuleDictionariesResponse)
async def get_rule_dictionaries(
    current_user: CurrentUser,
):
    """Return dictionaries for rule filters and editors (prefers DB)."""
    from .dictionary_loader import load_rule_dictionaries_from_db, load_rule_dictionaries

    db_data = await load_rule_dictionaries_from_db()
    if db_data is not None:
        return RuleDictionariesResponse(**db_data)
    return RuleDictionariesResponse(**load_rule_dictionaries())


@router.get("/rules", response_model=ComplianceRuleListResponse)
async def list_compliance_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    industry: Optional[str] = Query(None, description="按行业筛选"),
    report_type: Optional[str] = Query(None, description="按报告类型筛选"),
    region: Optional[str] = Query(None, description="按地区筛选"),
    rule_type: Optional[str] = Query(None, alias="type", description="按规则类型筛选"),
    severity: Optional[str] = Query(None, description="按严重级别筛选"),
    enabled: Optional[bool] = Query(None, description="按启用状态筛选"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """列出合规规则（支持多维度筛选）"""
    stmt = select(ComplianceRule)
    
    if industry:
        stmt = stmt.where(ComplianceRule.industry == industry)
    if report_type:
        stmt = stmt.where(ComplianceRule.report_types.any(report_type))
    if region:
        stmt = stmt.where(
            or_(
                ComplianceRule.national_level.is_(True),
                ComplianceRule.applicable_regions.any(region),
            )
        )
    if rule_type:
        stmt = stmt.where(ComplianceRule.type == rule_type)
    if severity:
        stmt = stmt.where(ComplianceRule.severity == severity)
    if enabled is not None:
        stmt = stmt.where(ComplianceRule.enabled == enabled)
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    stmt = stmt.order_by(ComplianceRule.severity.desc(), ComplianceRule.rule_id)
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    rules = result.scalars().all()

    rule_responses = [_build_rule_response(rule) for rule in rules]

    return ComplianceRuleListResponse(rules=rule_responses, total=total, page=page, limit=limit)


@router.post("/rules", response_model=ComplianceRuleResponse)
async def create_compliance_rule(
    data: ComplianceRuleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """创建合规规则"""
    rule = ComplianceRule(
        rule_id=data.rule_id,
        name=data.name,
        type=data.type,
        type_name=data.type_name,
        severity=data.severity,
        severity_name=data.severity_name,
        enabled=data.enabled,
        description=data.description,
        industry=data.industry,
        industry_name=data.industry_name,
        report_types=data.report_types,
        applicable_regions=data.applicable_regions,
        national_level=data.national_level,
        source_sections=data.source_sections,
        target_sections=data.target_sections,
        validation_config=data.validation_config,
        error_message=data.error_message,
        auto_fix_suggestion=data.auto_fix_suggestion,
        created_by=current_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    return _build_rule_response(rule)


@router.post("/rules/extract")
async def extract_rules_from_document(
    file: UploadFile = File(...),
    industry: str = Form(""),
    report_types: str = Form(""),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _current_user: CurrentUser = None,
):
    """上传法规文档，AI 自动提取合规校验规则"""
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_INFER_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 20MB")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = await asyncio.to_thread(_parse_document, tmp_path, ext)
        if not text.strip():
            raise HTTPException(status_code=422, detail="无法从文档中提取文本内容")

        system_config = await SystemConfigService.get_all(db) if db else {}
        system_default_model = system_config.get("default_model") or None

        from .llm import ExtractionLLMClient

        llm = ExtractionLLMClient(model_name=system_default_model, max_content_chars=15000)
        try:
            rt_list = [r.strip() for r in report_types.split(",") if r.strip()] if report_types else None
            rules = await asyncio.to_thread(
                llm.extract_compliance_rules, filename, text, industry, rt_list
            )
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {"rules": rules, "total": len(rules)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/rules/batch", response_model=ComplianceRuleBatchResponse)
async def batch_create_rules(
    data: ComplianceRuleBatchCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """批量创建合规规则"""
    created_rules = []
    skipped = 0
    errors = []

    for i, rule_data in enumerate(data.rules):
        try:
            existing = await db.execute(
                select(ComplianceRule).where(ComplianceRule.rule_id == rule_data.rule_id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            rule = ComplianceRule(
                rule_id=rule_data.rule_id,
                name=rule_data.name,
                type=rule_data.type,
                type_name=rule_data.type_name,
                severity=rule_data.severity,
                severity_name=rule_data.severity_name,
                enabled=rule_data.enabled,
                description=rule_data.description,
                industry=rule_data.industry,
                industry_name=rule_data.industry_name,
                report_types=rule_data.report_types,
                applicable_regions=rule_data.applicable_regions,
                national_level=rule_data.national_level,
                source_sections=rule_data.source_sections,
                target_sections=rule_data.target_sections,
                validation_config=rule_data.validation_config,
                error_message=rule_data.error_message,
                auto_fix_suggestion=rule_data.auto_fix_suggestion,
                created_by=current_user.id,
            )
            db.add(rule)
            await db.flush()
            created_rules.append(_build_rule_response(rule))
        except Exception as e:
            errors.append(f"规则 {rule_data.rule_id}: {e}")

    await db.commit()

    return ComplianceRuleBatchResponse(
        created=len(created_rules),
        skipped=skipped,
        errors=errors,
        created_rules=created_rules,
    )


@router.put("/rules/{rule_id}", response_model=ComplianceRuleResponse)
async def update_compliance_rule(
    rule_id: str,
    data: ComplianceRuleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """更新合规规则"""
    rule = await _get_rule_or_404(db, rule_id)
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(rule, key):
            setattr(rule, key, value)
    
    await db.commit()
    await db.refresh(rule)
    
    return _build_rule_response(rule)


@router.delete("/rules/{rule_id}")
async def delete_compliance_rule(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """删除合规规则"""
    rule = await _get_rule_or_404(db, rule_id)
    await db.delete(rule)
    await db.commit()
    return {"message": "规则已删除"}


@router.post("/rules/import-seed")
async def import_seed_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    force_update: bool = Query(False, description="强制更新已存在的规则"),
):
    """导入种子数据"""
    service = SeedImportService()
    result = await service.import_to_database(
        session=db,
        force_update=force_update,
        skip_existing=True,
    )
    return ComplianceRuleImportResponse(
        success=result.success,
        total=result.total,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        errors=result.errors,
        error_messages=result.error_messages,
    )


@router.get("/rules/seed-status")
async def get_seed_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取种子数据状态"""
    service = SeedImportService()
    status = await service.check_seed_status(db)
    return ComplianceRuleStatusResponse(**status)


@router.get("/rules/statistics")
async def get_compliance_rule_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取规则统计信息"""
    service = SeedImportService()
    stats = await service.get_rule_statistics(db)
    return ComplianceRuleStatisticsResponse(**stats)


@router.get("/rules/overview", response_model=ComplianceRuleOverviewResponse)
async def get_compliance_rule_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取规则引擎页面总览数据。"""
    service = SeedImportService()
    stats = await service.get_rule_statistics(db)
    seed_status = await service.check_seed_status(db)
    trigger_statistics = await _get_trigger_statistics_payload(db)

    return ComplianceRuleOverviewResponse(
        statistics=ComplianceRuleStatisticsResponse(**stats),
        seed_status=ComplianceRuleStatusResponse(**seed_status),
        trigger_statistics=trigger_statistics,
    )


# ============== Rule Execution APIs ==============


from .schemas import (
    ComplianceCheckRequest,
    ComplianceCheckResponse,
    ValidationIssueSchema,
)
from .engine import get_engine, CheckContext


@router.post("/rules/check", response_model=ComplianceCheckResponse)
async def check_compliance(
    data: ComplianceCheckRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """
    执行合规性检查

    传入报告数据，执行匹配的规则检查，返回检查结果。
    """
    # 构建检查上下文
    context = CheckContext(
        report_data=data.report_data or {},
        raw_text=data.raw_text,
        extracted_fields=data.extracted_fields or {},
        report_type=data.report_type,
        industry=data.industry,
        region=data.region,
        check_all=data.check_all,
        stop_on_first_fail=data.stop_on_first_fail,
        user_id=current_user.id,
        thread_id=data.thread_id,
    )

    # 获取引擎并执行检查
    engine = get_engine()
    result = await engine.check(context, rule_ids=data.rule_ids, db=db)

    # 构建响应
    issues = []
    for issue in result.issues:
        issues.append(ValidationIssueSchema(
            rule_id=issue.rule_id,
            rule_name=issue.rule_name,
            severity=issue.severity.value,
            check_result=issue.check_result.value,
            message=issue.message,
            field_name=issue.field_name,
            source_value=str(issue.source_value) if issue.source_value is not None else None,
            target_value=str(issue.target_value) if issue.target_value is not None else None,
            location=issue.location,
            suggestion=issue.suggestion,
            details=issue.details,
        ))

    return ComplianceCheckResponse(
        success=result.success,
        total_rules=result.total_rules,
        passed=result.passed,
        failed=result.failed,
        warnings=result.warnings,
        errors=result.errors,
        skipped=result.skipped,
        has_critical_issues=result.has_critical_issues,
        duration_ms=result.duration_ms,
        issues=issues,
    )


@router.post("/rules/check-single")
async def check_single_rule(
    rule_id: str,
    report_data: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    extracted_fields: Optional[dict] = None,
    current_user: OptionalUser = None,
):
    """
    检查单条规则

    用于在编辑报告时实时检查某条规则。
    """
    context = CheckContext(
        report_data=report_data,
        extracted_fields=extracted_fields or {},
        user_id=current_user.id if current_user else None,
    )

    engine = get_engine()
    result = await engine.check(context, rule_ids=[rule_id], db=db)

    return {
        "success": result.success,
        "issues": [
            {
                "rule_id": issue.rule_id,
                "message": issue.message,
                "severity": issue.severity.value,
                "field_name": issue.field_name,
                "suggestion": issue.suggestion,
            }
            for issue in result.issues
        ],
        "duration_ms": result.duration_ms,
    }


@router.get("/rules/validate/{rule_id}")
async def validate_rule(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """验证规则配置是否正确"""
    from sqlalchemy import select
    from .models import ComplianceRule

    # 获取规则
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.rule_id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")

    # 检查验证器是否存在
    from .engine import ValidatorRegistry
    validator_class = ValidatorRegistry.get_validator(rule.type)

    return {
        "rule_id": rule.rule_id,
        "type": rule.type,
        "validator_registered": validator_class is not None,
        "validation_config": rule.validation_config,
        "enabled": rule.enabled,
    }


# ============== Rule Execution Logs APIs ==============


@router.get("/rules/trigger-statistics")
async def get_trigger_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    start_date: Optional[str] = Query(None, description="统计起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="统计结束日期 YYYY-MM-DD"),
):
    """获取全局触发统计"""
    return await _get_trigger_statistics_payload(db, start_date=start_date, end_date=end_date)


# ============== Test Rule API ==============


@router.get("/rules/{rule_id}", response_model=ComplianceRuleResponse)
async def get_compliance_rule(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取规则详情"""
    rule = await _get_rule_or_404(db, rule_id)
    return _build_rule_response(rule)


@router.get("/rules/{rule_id}/logs")
async def get_rule_logs(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取规则执行日志"""
    from sqlalchemy import select
    from .models import ComplianceRule, ComplianceRuleLog

    # 获取规则
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.rule_id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")

    # 获取日志
    from sqlalchemy import desc
    logs_stmt = (
        select(ComplianceRuleLog)
        .where(ComplianceRuleLog.rule_id == rule.id)
        .order_by(desc(ComplianceRuleLog.executed_at))
        .offset(offset)
        .limit(limit)
    )
    logs_result = await db.execute(logs_stmt)
    logs = logs_result.scalars().all()

    # 获取总数
    from sqlalchemy import func
    count_stmt = select(func.count()).where(ComplianceRuleLog.rule_id == rule.id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    return {
        "rule_id": rule_id,
        "total": total,
        "logs": [
            {
                "id": str(log.id),
                "check_result": log.check_result,
                "check_details": log.check_details,
                "error_info": log.error_info,
                "thread_id": str(log.thread_id) if log.thread_id else None,
                "document_id": log.document_id,
                "executed_at": log.executed_at.isoformat() if log.executed_at else None,
            }
            for log in logs
        ],
    }


@router.get("/rules/{rule_id}/statistics")
async def get_rule_execution_statistics(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """获取规则执行统计"""
    from sqlalchemy import select
    from .models import ComplianceRule, ComplianceRuleLog
    from sqlalchemy import func, desc

    # 获取规则
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.rule_id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")

    # 统计各类结果数量
    total_stmt = select(func.count()).where(ComplianceRuleLog.rule_id == rule.id)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar() or 0

    stats = {
        "rule_id": rule_id,
        "rule_name": rule.name,
        "total_executions": total,
        "pass_count": 0,
        "fail_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "last_executed_at": None,
        "last_failed_at": None,
    }

    for result_type in ["pass", "fail", "warning", "error"]:
        count_stmt = select(func.count()).where(
            ComplianceRuleLog.rule_id == rule.id,
            ComplianceRuleLog.check_result == result_type,
        )
        count_result = await db.execute(count_stmt)
        count = count_result.scalar() or 0
        stats[f"{result_type}_count"] = count

    # 获取最近执行时间
    latest_stmt = (
        select(ComplianceRuleLog.executed_at)
        .where(ComplianceRuleLog.rule_id == rule.id)
        .order_by(desc(ComplianceRuleLog.executed_at))
        .limit(1)
    )
    latest_result = await db.execute(latest_stmt)
    latest = latest_result.scalar_one_or_none()
    if latest:
        stats["last_executed_at"] = latest.isoformat()

    # 获取最近失败时间
    failed_stmt = (
        select(ComplianceRuleLog.executed_at)
        .where(
            ComplianceRuleLog.rule_id == rule.id,
            ComplianceRuleLog.check_result.in_(["fail", "warning"]),
        )
        .order_by(desc(ComplianceRuleLog.executed_at))
        .limit(1)
    )
    failed_result = await db.execute(failed_stmt)
    failed = failed_result.scalar_one_or_none()
    if failed:
        stats["last_failed_at"] = failed.isoformat()

    return stats


@router.post("/rules/{rule_id}/test")
async def test_rule(
    rule_id: str,
    test_data: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """
    测试单条规则

    使用指定的测试数据执行规则验证。
    """
    from sqlalchemy import select
    from .models import ComplianceRule
    from .engine import get_engine, CheckContext, ValidatorRegistry

    # 获取规则
    result = await db.execute(
        select(ComplianceRule).where(ComplianceRule.rule_id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")

    # 检查验证器是否注册
    validator_class = ValidatorRegistry.get_validator(rule.type)
    if not validator_class:
        return {
            "success": False,
            "error": f"规则类型 '{rule.type}' 没有对应的验证器",
            "rule_id": rule_id,
        }

    # 构建测试上下文
    context = CheckContext(
        report_data=test_data.get("report_data", {}),
        raw_text=test_data.get("raw_text"),
        extracted_fields=test_data.get("extracted_fields", {}),
        user_id=current_user.id,
    )

    # 执行规则测试
    engine = get_engine()
    result = await engine.check(context, rule_ids=[rule_id], db=db)

    return {
        "success": result.success,
        "rule_id": rule_id,
        "rule_name": rule.name,
        "total_rules": result.total_rules,
        "passed": result.passed,
        "failed": result.failed,
        "warnings": result.warnings,
        "issues": [
            {
                "rule_id": issue.rule_id,
                "rule_name": issue.rule_name,
                "severity": issue.severity.value,
                "check_result": issue.check_result.value,
                "message": issue.message,
                "field_name": issue.field_name,
                "suggestion": issue.suggestion,
            }
            for issue in result.issues
            if issue.check_result.value != "pass"
        ],
        "duration_ms": result.duration_ms,
    }
