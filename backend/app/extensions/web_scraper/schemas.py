"""API request/response models for web scraper."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class ProxyConfig(BaseModel):
    """Proxy configuration."""
    enabled: bool = False
    proxy_type: str = "http"
    host: str = ""
    port: int = 0
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None


class AuthConfig(BaseModel):
    """Authentication configuration."""
    enabled: bool = False
    auth_type: str = "basic"
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    cookies: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]] = None


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
    schema_name: Optional[str] = Field(
        default=None,
        description="Predefined schema name",
    )
    custom_schema: Optional[str] = Field(
        default=None,
        description="Custom JSON Schema (JSON string)",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="LLM model name (from system config)",
    )
    timeout: int = Field(default=120, ge=10, le=600)
    proxy: Optional[ProxyConfig] = None
    auth: Optional[AuthConfig] = None


class ScrapeResponse(BaseModel):
    """Scrape response."""
    task_id: str
    status: str
    message: str


class ScrapeResultResponse(BaseModel):
    """Scrape result response."""
    task_id: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    provider_used: Optional[str] = None
    structured_data: Optional[dict] = None


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
    source_title: Optional[str] = Field(None, description="Source title")
    schema_name: str = Field(..., description="Schema name")
    schema_display_name: Optional[str] = Field(None, description="Schema display name")
    raw_content: str = Field(..., description="Scraped Markdown content")
    structured_data: Optional[str] = Field(None, description="Structured data JSON")
    title: str = Field(..., description="Draft title")
    tags: list[str] = Field(default_factory=list, description="Tags")
    category: Optional[str] = Field(None, description="Category")


class ScrapDraftUpdate(BaseModel):
    """Update draft request."""
    title: Optional[str] = None
    raw_content: Optional[str] = None
    structured_data: Optional[str] = None
    tags: Optional[list[str]] = None
    category: Optional[str] = None


class ScrapDraftImport(BaseModel):
    """Import to knowledge base request."""
    knowledge_base_id: UUID = Field(..., description="Target knowledge base ID")
    chunk_method: Optional[str] = Field("naive", description="Chunk method")
    auto_parse: bool = Field(True, description="Auto parse")


class ScrapDraftResponse(BaseModel):
    """Draft response."""
    id: UUID
    source_url: str
    source_title: Optional[str]
    schema_name: str
    schema_display_name: Optional[str]
    title: str
    tags: list[str]
    category: Optional[str]
    status: str
    source_provider: str
    scrape_date: str
    knowledge_base_id: Optional[UUID]
    created_at: str
    updated_at: str


class ScrapDraftDetailResponse(ScrapDraftResponse):
    """Draft detail response."""
    raw_content: str
    structured_data: Optional[str]
    document_id: Optional[str]


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
