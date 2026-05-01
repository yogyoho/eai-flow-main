"""Web scraper API routers."""

import logging
import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.web_scraper.predefined_schemas import list_all_schemas
from app.extensions.web_scraper.schemas import (
    ImportResultResponse,
    ScrapDraftCreate,
    ScrapDraftDetailResponse,
    ScrapDraftImport,
    ScrapDraftListResponse,
    ScrapDraftResponse,
    ScrapDraftUpdate,
    ScrapeRequest,
    ScrapeResponse,
    ScrapeResultResponse,
)
from app.extensions.web_scraper.service import AuthConfig, ProxyConfig, ScrapeConfig, scraper_service
from app.extensions.web_scraper.services.draft_service import ScrapDraftService
from app.extensions.web_scraper.task_manager import TaskStatus, task_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/extensions/web-scraper", tags=["Web Scraper"])


@router.post("/scrape", response_model=ScrapeResponse, status_code=status.HTTP_201_CREATED)
async def create_scrape_task(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permission("kb:read")),
):
    """Create a web scraping task."""
    proxy_cfg = ProxyConfig()
    if request.proxy:
        proxy_cfg = ProxyConfig(
            enabled=request.proxy.enabled,
            proxy_type=request.proxy.proxy_type,
            host=request.proxy.host,
            port=request.proxy.port,
            username=request.proxy.username,
            password=request.proxy.password,
            country=request.proxy.country,
        )

    auth_cfg = AuthConfig()
    if request.auth:
        auth_cfg = AuthConfig(
            enabled=request.auth.enabled,
            auth_type=request.auth.auth_type,
            username=request.auth.username,
            password=request.auth.password,
            token=request.auth.token,
            cookies=request.auth.cookies,
            headers=request.auth.headers,
        )

    config = ScrapeConfig(
        url=str(request.url),
        prompt=request.prompt,
        provider=request.provider,
        schema_name=request.schema_name,
        llm_model=request.llm_model,
        timeout=request.timeout,
        proxy=proxy_cfg,
        auth=auth_cfg,
    )

    task_id, task = task_manager.create(
        url=str(request.url),
        prompt=request.prompt,
        provider=request.provider,
        schema_name=request.schema_name,
        proxy_enabled=request.proxy.enabled if request.proxy else False,
        auth_enabled=request.auth.enabled if request.auth else False,
    )

    background_tasks.add_task(_run_scrape_task, task_id, config)

    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message="Task created, executing...",
    )


async def _run_scrape_task(task_id: str, config: ScrapeConfig):
    """Run scrape task in background."""
    await task_manager.update(task_id, status=TaskStatus.RUNNING)

    async for event in scraper_service.scrape(config, auto_fallback=True):
        await task_manager.emit(task_id, event)

        if event["type"] == "result":
            await task_manager.update(
                task_id,
                status=TaskStatus.COMPLETED,
                result=event.get("content"),
                provider_used=event.get("provider_used"),
            )
        elif event["type"] == "error":
            await task_manager.update(
                task_id,
                status=TaskStatus.FAILED,
                error=event.get("message"),
            )


@router.get("/stream/{task_id}")
async def stream_scrape_logs(
    task_id: str,
    current_user=Depends(require_permission("kb:read")),
):
    """SSE streaming logs."""
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        async for msg in task_manager.stream(task_id):
            yield msg

    return EventSourceResponse(event_generator())


@router.get("/result/{task_id}", response_model=ScrapeResultResponse)
async def get_scrape_result(
    task_id: str,
    current_user=Depends(require_permission("kb:read")),
):
    """Get task result."""
    task = task_manager.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(status_code=202, detail="Task is running")

    return ScrapeResultResponse(
        task_id=task_id,
        status=task.status.value,
        result=task.result,
        error=task.error,
        provider_used=task.provider_used,
    )


@router.get("/providers")
async def list_providers(
    current_user=Depends(require_permission("kb:read")),
):
    """Get available provider list."""
    return {"providers": scraper_service.get_providers()}


@router.get("/schemas")
async def list_schemas(
    current_user=Depends(require_permission("kb:read")),
):
    """Get predefined schema list."""
    return {"schemas": list_all_schemas()}


@router.post("/extract-pdf")
async def extract_pdf_content(
    pdf_req: dict,
    current_user=Depends(require_permission("kb:read")),
):
    """Download PDF from URL and convert to Markdown text."""
    import tempfile

    pdf_url = pdf_req.get("pdf_url")
    if not pdf_url:
        raise HTTPException(status_code=400, detail="pdf_url is required")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(pdf_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not pdf_url.lower().endswith(".pdf"):
                logger.warning(f"URL may not be a PDF: {content_type}")

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {e}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(tmp_path)
        text = result.text_content or ""
        if not text.strip():
            raise HTTPException(status_code=422, detail="PDF content is empty or cannot be parsed")
        return {"content": text}
    except ImportError:
        raise HTTPException(status_code=500, detail="markitdown not installed, run: pip install markitdown")
    except Exception as e:
        logger.error(f"PDF conversion failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF conversion failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user=Depends(require_permission("kb:read")),
):
    """Cancel task."""
    success = await task_manager.cancel(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    return {"message": "Task cancelled"}


# ==================== Draft APIs ====================


@router.post("/drafts", response_model=ScrapDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    data: ScrapDraftCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Create a scrape draft."""

    draft = await ScrapDraftService.create_draft(
        db=db,
        user_id=current_user.id,
        data=data,
    )
    return ScrapDraftService.to_response(draft)


@router.get("/drafts", response_model=ScrapDraftListResponse)
async def list_drafts(
    status_filter: str | None = Query(None, alias="status", description="Status filter: draft/imported/deleted"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Get draft list."""
    drafts, total = await ScrapDraftService.list_drafts(
        db=db,
        user_id=current_user.id,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )

    return ScrapDraftListResponse(
        drafts=[ScrapDraftService.to_response(d) for d in drafts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/drafts/{draft_id}", response_model=ScrapDraftDetailResponse)
async def get_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Get draft detail."""

    draft = await ScrapDraftService.get_draft(db, draft_id, current_user.id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "deleted":
        raise HTTPException(status_code=404, detail="Draft has been deleted")

    return ScrapDraftService.to_detail_response(draft)


@router.put("/drafts/{draft_id}", response_model=ScrapDraftResponse)
async def update_draft(
    draft_id: UUID,
    data: ScrapDraftUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Update draft."""

    draft = await ScrapDraftService.get_draft(db, draft_id, current_user.id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "deleted":
        raise HTTPException(status_code=400, detail="Cannot edit deleted draft")
    if draft.status == "imported":
        raise HTTPException(status_code=400, detail="Cannot edit imported draft")

    updated = await ScrapDraftService.update_draft(db, draft, data)
    return ScrapDraftService.to_response(updated)


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Delete draft (soft delete)."""

    draft = await ScrapDraftService.get_draft(db, draft_id, current_user.id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    await ScrapDraftService.delete_draft(db, draft)
    return {"message": "Draft deleted"}


@router.post("/drafts/{draft_id}/import", response_model=ImportResultResponse)
async def import_draft(
    draft_id: UUID,
    data: ScrapDraftImport,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:upload")),
):
    """Import draft to knowledge base."""

    draft = await ScrapDraftService.get_draft(db, draft_id, current_user.id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "deleted":
        raise HTTPException(status_code=400, detail="Cannot import deleted draft")
    if draft.status == "imported":
        raise HTTPException(status_code=400, detail="Draft already imported to knowledge base")

    try:
        result = await ScrapDraftService.import_to_knowledge_base(
            db=db,
            draft=draft,
            kb_id=data.knowledge_base_id,
            chunk_method=data.chunk_method,
            auto_parse=data.auto_parse,
        )
        return ImportResultResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(f"Draft import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/drafts/{draft_id}/preview")
async def preview_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("kb:read")),
):
    """Preview draft content."""

    draft = await ScrapDraftService.get_draft(db, draft_id, current_user.id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    return {
        "id": str(draft.id),
        "title": draft.title,
        "raw_content": draft.raw_content,
        "structured_data": draft.structured_data,
        "source_url": draft.source_url,
        "schema_name": draft.schema_name,
    }
