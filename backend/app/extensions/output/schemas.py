"""Pydantic schemas for layout template CRUD."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Nested schemas (mirror frontend types.ts) ---


class PageSettingsSchema(BaseModel):
    paperSize: str = "A4"
    orientation: str = "portrait"
    marginTop: float = 2.54
    marginBottom: float = 2.54
    marginLeft: float = 3.17
    marginRight: float = 3.17


class CoverTemplateSchema(BaseModel):
    showLogo: bool = True
    logoPosition: str = "center"
    showTitle: bool = True
    showClient: bool = True
    showDate: bool = True
    showProjectNumber: bool = True


class TocSettingsSchema(BaseModel):
    maxDepth: int = 3
    showPageNumbers: bool = True
    leaderDots: bool = True


class BodyStylesSchema(BaseModel):
    fontFamily: str = "宋体"
    fontSize: int = 12
    lineHeight: float = 1.5
    paragraphSpacing: int = 6
    firstLineIndent: int = 2


class HeadingStyleSchema(BaseModel):
    level: int
    fontFamily: str = "黑体"
    fontSize: int = 14
    fontWeight: int = 700
    color: str = "#333333"
    numbering: str = "decimal"


class TableStylesSchema(BaseModel):
    headerBg: str = "#2B579A"
    headerColor: str = "#FFFFFF"
    borderColor: str = "#CCCCCC"
    stripeRows: bool = True


class FigureStylesSchema(BaseModel):
    captionPosition: str = "below"
    numbering: str = "chapter"
    showSource: bool = True


class HeaderFooterSchema(BaseModel):
    headerText: str = ""
    footerText: str = ""
    showPageNumber: bool = True
    showLogo: bool = False


class AppendixRulesSchema(BaseModel):
    numbering: str = "A-B-C"
    separateToc: bool = False


# --- Create / Update / Response ---


class LayoutTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str = Field(..., min_length=1, max_length=100)
    page_settings: PageSettingsSchema
    cover_template: CoverTemplateSchema | None = None
    toc_settings: TocSettingsSchema | None = None
    body_styles: BodyStylesSchema
    heading_styles: list[HeadingStyleSchema] = Field(default_factory=list)
    table_styles: TableStylesSchema | None = None
    figure_styles: FigureStylesSchema | None = None
    header_footer: HeaderFooterSchema | None = None
    reference_style: str = "gb7714"
    appendix_rules: AppendixRulesSchema | None = None


class LayoutTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    report_type: str | None = Field(None, min_length=1, max_length=100)
    page_settings: PageSettingsSchema | None = None
    cover_template: CoverTemplateSchema | None = None
    toc_settings: TocSettingsSchema | None = None
    body_styles: BodyStylesSchema | None = None
    heading_styles: list[HeadingStyleSchema] | None = None
    table_styles: TableStylesSchema | None = None
    figure_styles: FigureStylesSchema | None = None
    header_footer: HeaderFooterSchema | None = None
    reference_style: str | None = None
    appendix_rules: AppendixRulesSchema | None = None


class LayoutTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    is_builtin: bool
    page_settings: dict
    cover_template: dict | None = None
    toc_settings: dict | None = None
    body_styles: dict
    heading_styles: list
    table_styles: dict | None = None
    figure_styles: dict | None = None
    header_footer: dict | None = None
    reference_style: str
    appendix_rules: dict | None = None
    created_at: datetime
    updated_at: datetime


class LayoutTemplateListResponse(BaseModel):
    items: list[LayoutTemplateResponse]
    total: int
