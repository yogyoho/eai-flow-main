"""API request/response models for web scraper."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class ProxyConfig(BaseModel):
    """Proxy configuration."""

    enabled: bool = False
    proxy_type: str = "http"
    host: str = ""
    port: int = 0
    username: str | None = None
    password: str | None = None
    country: str | None = None


class AuthConfig(BaseModel):
    """Authentication configuration."""

    enabled: bool = False
    auth_type: str = "basic"
    username: str | None = None
    password: str | None = None
    token: str | None = None
    cookies: dict[str, str] | None = None
    headers: dict[str, str] | None = None


class ScrapeRequest(BaseModel):
    """Scrape request."""

    url: HttpUrl = Field(..., description="Target URL")
    prompt: str = Field(
        default="Extract all important information from the webpage, organize as Markdown.",
        description="Extraction instruction",
    )
    provider: Literal["browser_use_local", "jina", "firecrawl"] = Field(
        default="browser_use_local",
        description="Scrape Provider: browser_use_local, jina, firecrawl",
    )
    schema_name: str | None = Field(
        default=None,
        description="Predefined schema name",
    )
    custom_schema: str | None = Field(
        default=None,
        description="Custom JSON Schema (JSON string)",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model name (from system config)",
    )
    timeout: int = Field(default=120, ge=10, le=600)
    proxy: ProxyConfig | None = None
    auth: AuthConfig | None = None


class ScrapeResponse(BaseModel):
    """Scrape response."""

    task_id: str
    status: str
    message: str


class ScrapeResultResponse(BaseModel):
    """Scrape result response."""

    task_id: str
    status: str
    result: str | None = None
    error: str | None = None
    provider_used: str | None = None
    structured_data: dict | None = None


class ProviderInfo(BaseModel):
    """Provider info."""

    name: str
    supports_structured: bool
    is_primary: bool


class SchemaInfo(BaseModel):
    """Schema info."""

    name: str
    display_name: str
    description: str
    category: str
    supports_structured: bool


class ScrapDraftCreate(BaseModel):
    """Create draft request."""

    source_url: str = Field(..., description="Source URL")
    source_title: str | None = Field(None, description="Source title")
    schema_name: str = Field(..., description="Schema name")
    schema_display_name: str | None = Field(None, description="Schema display name")
    raw_content: str = Field(..., description="Scraped Markdown content")
    structured_data: str | None = Field(None, description="Structured data JSON")
    title: str = Field(..., description="Draft title")
    tags: list[str] = Field(default_factory=list, description="Tags")
    category: str | None = Field(None, description="Category")


class ScrapDraftUpdate(BaseModel):
    """Update draft request."""

    title: str | None = None
    raw_content: str | None = None
    structured_data: str | None = None
    tags: list[str] | None = None
    category: str | None = None


class ScrapDraftImport(BaseModel):
    """Import to knowledge base request."""

    knowledge_base_id: UUID = Field(..., description="Target knowledge base ID")
    chunk_method: str | None = Field("naive", description="Chunk method")
    auto_parse: bool = Field(True, description="Auto parse")


class ScrapDraftResponse(BaseModel):
    """Draft response."""

    id: UUID
    source_url: str
    source_title: str | None
    schema_name: str
    schema_display_name: str | None
    title: str
    tags: list[str]
    category: str | None
    status: str
    source_provider: str
    scrape_date: str
    knowledge_base_id: UUID | None
    created_at: str
    updated_at: str


class ScrapDraftDetailResponse(ScrapDraftResponse):
    """Draft detail response."""

    raw_content: str
    structured_data: str | None
    document_id: str | None


class ScrapDraftListResponse(BaseModel):
    """Draft list response."""

    drafts: list[ScrapDraftResponse]
    total: int
    page: int
    page_size: int


class ImportResultResponse(BaseModel):
    """Import result response."""

    success: bool
    draft_id: UUID
    document_id: str
    knowledge_base_id: UUID
    message: str
