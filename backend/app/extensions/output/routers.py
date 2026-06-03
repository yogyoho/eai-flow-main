"""FastAPI router for layout template CRUD and report generation."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.output.generator import generate_docx
from app.extensions.output.schemas import (
    LayoutTemplateCreate,
    LayoutTemplateListResponse,
    LayoutTemplateResponse,
    LayoutTemplateUpdate,
)
from app.extensions.output.service import LayoutTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/output", tags=["output"])

# Directory for generated files
_OUTPUT_DIR = Path(tempfile.gettempdir()) / "eai_output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/templates", response_model=LayoutTemplateListResponse)
async def list_templates(db: AsyncSession = Depends(get_db)):
    templates = await LayoutTemplateService.list_templates(db)
    return LayoutTemplateListResponse(
        items=[LayoutTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


@router.get("/templates/{template_id}", response_model=LayoutTemplateResponse)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return LayoutTemplateResponse.model_validate(template)


@router.post("/templates", response_model=LayoutTemplateResponse, status_code=201)
async def create_template(data: LayoutTemplateCreate, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.create_template(db, data)
    return LayoutTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=LayoutTemplateResponse)
async def update_template(
    template_id: UUID,
    data: LayoutTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    updated = await LayoutTemplateService.update_template(db, template, data)
    return LayoutTemplateResponse.model_validate(updated)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_builtin:
        raise HTTPException(status_code=403, detail="Built-in templates cannot be deleted")
    await LayoutTemplateService.delete_template(db, template)


@router.post("/templates/{template_id}/duplicate", response_model=LayoutTemplateResponse, status_code=201)
async def duplicate_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await LayoutTemplateService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    duplicated = await LayoutTemplateService.duplicate_template(db, template)
    return LayoutTemplateResponse.model_validate(duplicated)


# --- Report Generation ---


class GenerateResponse(BaseModel):
    task_id: str
    status: str  # queued | processing | completed | failed
    download_url: str | None = None
    file_name: str | None = None


@router.post("/generate", response_model=GenerateResponse)
async def generate_report(
    source: str = Form(...),
    format: str = Form("docx"),
    layout_template_id: str = Form(...),
    watermark: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    chapter_ids: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Generate a report from either a project or an uploaded markdown file."""
    # Validate template exists
    try:
        tmpl_uuid = uuid.UUID(layout_template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid layout_template_id")

    template = await LayoutTemplateService.get_template(db, tmpl_uuid)
    if not template:
        raise HTTPException(status_code=404, detail="Layout template not found")

    # Collect markdown content
    markdown_content: str | None = None

    if source == "project":
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required when source is 'project'")
        # TODO: fetch project chapters and assemble markdown from DB
        markdown_content = f"# 项目报告\n\n> 项目 ID: {project_id}\n\n*（项目章节内容将在此处生成）*\n"
    elif source == "markdown":
        if not file:
            raise HTTPException(status_code=400, detail="file is required when source is 'markdown'")
        raw = await file.read()
        try:
            markdown_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            markdown_content = raw.decode("gbk", errors="replace")
        logger.info("Markdown upload received: %s (%d bytes)", file.filename, len(raw))
    else:
        raise HTTPException(status_code=400, detail="source must be 'project' or 'markdown'")

    # Build template data dict for the generator
    template_data = {
        "page_settings": template.page_settings or {},
        "body_styles": template.body_styles or {},
        "heading_styles": template.heading_styles or [],
        "table_styles": template.table_styles,
        "figure_styles": template.figure_styles,
        "header_footer": template.header_footer,
        "reference_style": template.reference_style,
        "appendix_rules": template.appendix_rules,
    }

    # Generate DOCX
    task_id = str(uuid.uuid4())
    ext = "docx" if format in ("docx", "preview") else "docx"  # always docx for now
    file_name = f"report_{task_id[:8]}.{ext}"
    output_path = _OUTPUT_DIR / f"{task_id}.{ext}"

    try:
        generate_docx(
            markdown_content=markdown_content,
            template_data=template_data,
            output_path=output_path,
            watermark=watermark,
        )
    except Exception as e:
        logger.error("Report generation failed: %s", e, exc_info=True)
        return GenerateResponse(task_id=task_id, status="failed")

    download_url = f"/api/extensions/output/download/{task_id}"

    return GenerateResponse(
        task_id=task_id,
        status="completed",
        download_url=download_url,
        file_name=file_name,
    )


@router.get("/download/{task_id}")
async def download_report(task_id: str):
    """Download a generated report file by task ID."""
    # Find the file — could be .docx or .pdf
    for ext in ("docx", "pdf"):
        path = _OUTPUT_DIR / f"{task_id}.{ext}"
        if path.exists():
            return FileResponse(
                path=str(path),
                filename=f"report_{task_id[:8]}.{ext}",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == "docx" else "application/pdf",
            )

    raise HTTPException(status_code=404, detail="Generated file not found")
