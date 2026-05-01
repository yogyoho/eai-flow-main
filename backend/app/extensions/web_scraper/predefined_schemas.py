"""Predefined structured data schemas for law/standard documents."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ScrapeProvider(str, Enum):
    """Scrape service providers."""

    BROWSER_USE_LOCAL = "browser_use_local"
    JINA = "jina"
    FIRECRAWL = "firecrawl"


class NationalStandard(BaseModel):
    """National standard document structured extraction."""

    standard_id: str = Field(description="Standard number, e.g. GB/T 50378-2019")
    standard_name: str = Field(description="Standard name")
    category: Literal["国家标准", "强制性标准", "推荐性标准"] = Field(description="Standard category")

    issuing_authority: str = Field(description="Issuing authority/department")
    issue_date: str | None = Field(default=None, description="Issue date")
    implementation_date: str | None = Field(default=None, description="Implementation date")

    scope: str | None = Field(default=None, description="Scope of application")
    main_content: str | None = Field(default=None, description="Main content summary")
    superseded_standard: str | None = Field(default=None, description="Superseded standard number")

    has_pdf: bool = Field(default=False, description="Whether PDF is available")
    pdf_url: str | None = Field(default=None, description="PDF download link")

    keywords: list[str] = Field(default_factory=list, description="Keywords")
    department_tags: list[str] = Field(default_factory=list, description="Department tags")


class IndustryStandard(BaseModel):
    """Industry standard document structured extraction."""

    standard_id: str = Field(description="Standard number, e.g. HJ 1234-2021")
    standard_name: str = Field(description="Standard name")
    industry_code: str = Field(description="Industry code, e.g. HJ(environment), NB(energy), QB(light industry)")

    issuing_authority: str = Field(description="Issuing department")
    issue_date: str | None = Field(default=None, description="Issue date")
    implementation_date: str | None = Field(default=None, description="Implementation date")
    filing_date: str | None = Field(default=None, description="Filing date")

    scope: str | None = Field(default=None, description="Scope of application")
    main_technical_content: str | None = Field(default=None, description="Main technical content")
    referenced_standards: list[str] = Field(default_factory=list, description="Referenced standard numbers")

    has_pdf: bool = Field(default=False, description="Whether PDF is available")
    has_word: bool = Field(default=False, description="Whether Word version is available")
    attachment_urls: list[str] = Field(default_factory=list, description="Attachment download links")

    keywords: list[str] = Field(default_factory=list, description="Keywords")
    subject_areas: list[str] = Field(default_factory=list, description="Subject areas")


class Regulation(BaseModel):
    """Regulation/rule document structured extraction."""

    regulation_type: Literal["法律", "行政法规", "部门规章", "地方性法规", "地方政府规章"] = Field(description="Regulation type")
    regulation_name: str = Field(description="Regulation name")
    regulation_id: str | None = Field(default=None, description="Document number")

    issuing_authority: str = Field(description="Issuing authority")
    issue_date: str = Field(description="Issue date")
    implementation_date: str = Field(description="Implementation date")
    effective_date: str | None = Field(default=None, description="Effective date")

    validity: Literal["现行有效", "已被修改", "已废止", "尚未生效"] = Field(description="Regulation validity")
    modification_record: str | None = Field(default=None, description="Modification history")

    scope: str | None = Field(default=None, description="Scope of application")
    main_content: str | None = Field(default=None, description="Main content summary")

    has_pdf: bool = Field(default=False, description="Whether PDF is available")
    pdf_url: str | None = Field(default=None, description="PDF link")

    related_regulations: list[str] = Field(default_factory=list, description="Related regulations")
    keywords: list[str] = Field(default_factory=list, description="Keywords")


class Specification(BaseModel):
    """Technical specification/regulation structured extraction."""

    spec_id: str = Field(description="Specification number")
    spec_name: str = Field(description="Specification name")
    spec_type: Literal["技术规范", "操作规程", "作业指导书", "管理办法", "实施细则"] = Field(description="Specification type")

    issuing_authority: str = Field(description="Issuing unit")
    issue_date: str | None = Field(default=None, description="Issue date")
    version: str = Field(default="V1.0", description="Version number")

    scope: str | None = Field(default=None, description="Scope of application")
    main_chapters: list[str] = Field(default_factory=list, description="Main chapter titles")
    core_requirements: str | None = Field(default=None, description="Core requirements")

    has_appendix: bool = Field(default=False, description="Whether appendix is available")
    has_attachments: bool = Field(default=False, description="Whether attachments are available")
    attachment_urls: list[str] = Field(default_factory=list, description="Attachment links")

    keywords: list[str] = Field(default_factory=list, description="Keywords")
    professional_areas: list[str] = Field(default_factory=list, description="Professional areas")


class PolicyDocument(BaseModel):
    """Policy document/notice structured extraction."""

    doc_title: str = Field(description="Document title")
    doc_number: str | None = Field(default=None, description="Document number")
    doc_type: Literal["通知", "公告", "意见", "批复", "决定", "函"] = Field(description="Document type")

    issuing_authority: str = Field(description="Issuing authority")
    issue_date: str = Field(description="Issue date")

    topic_categories: list[str] = Field(default_factory=list, description="Topic categories")
    industry_categories: list[str] = Field(default_factory=list, description="Industry categories")
    main_content: str | None = Field(default=None, description="Main content summary")

    related_docs: list[str] = Field(default_factory=list, description="Related documents")
    attachment_urls: list[str] = Field(default_factory=list, description="Attachment links")


class GeneralStandard(BaseModel):
    """General document structured extraction (fallback)."""

    title: str = Field(description="Document title")
    doc_id: str | None = Field(default=None, description="Document number")

    issuing_authority: str | None = Field(default=None, description="Issuing authority")
    issue_date: str | None = Field(default=None, description="Issue date")
    effective_date: str | None = Field(default=None, description="Effective date")

    scope: str | None = Field(default=None, description="Scope of application")
    summary: str | None = Field(default=None, description="Content summary")

    doc_type: str | None = Field(default=None, description="Document type")
    keywords: list[str] = Field(default_factory=list, description="Keywords")
    attachments: list[str] = Field(default_factory=list, description="Attachment links")


PREDEFINED_SCHEMAS = {
    "national_standard": {
        "name": "国家标准 (GB)",
        "name_en": "National Standard",
        "description": "National standard documents, suitable for GB/T, GB standards",
        "schema": NationalStandard,
        "prompt": """Extract the following information from the national standard document:
1. Standard number (e.g. GB/T 50378-2019)
2. Standard name
3. Standard category (mandatory/recommended)
4. Issuing authority
5. Issue date and implementation date
6. Scope of application
7. Main content
8. Superseded standard (if any)
9. Whether PDF download is available, and extract the PDF link
10. Keywords

**Important**:
- PDF links must be complete URLs like `pdf_url: https://...`. If the page shows relative paths, construct absolute URLs.
- If the page shows skeleton/placeholder, wait for the page to fully load before extracting.
- If you encounter "element index not found" errors, prefer using JavaScript scrolling.
- Already extracted partial information is still valuable; no need to wait for all fields.
- If you cannot find certain fields, infer reasonably from available information.""",
        "category": "法规标准",
    },
    "industry_standard": {
        "name": "行业标准",
        "name_en": "Industry Standard",
        "description": "Industry standard documents, suitable for HJ, NB, QB standards",
        "schema": IndustryStandard,
        "prompt": """Extract the following information from the industry standard document:
1. Standard number (e.g. HJ 1234-2021)
2. Standard name
3. Industry code (HJ=environment, NB=energy, QB=light industry, JB=machinery)
4. Issuing department
5. Issue date, implementation date, filing date (if available)
6. Scope of application
7. Main technical content
8. Referenced standard numbers
9. Whether PDF/Word attachments are available, extract download links
10. Keywords and subject areas""",
        "category": "法规标准",
    },
    "regulation": {
        "name": "法规/规章",
        "name_en": "Regulation",
        "description": "Laws and regulations documents",
        "schema": Regulation,
        "prompt": """Extract the following information from the regulation document:
1. Regulation type (law/administrative regulation/department regulation/local regulation)
2. Regulation name
3. Document number
4. Issuing authority
5. Issue date
6. Implementation date
7. Validity status (effective/superseded/repealed/not yet effective)
8. Modification history (if any)
9. Scope of application
10. Main content summary
11. Whether PDF full text is available, extract PDF link
12. Related regulations (if any)
13. Keywords""",
        "category": "法规标准",
    },
    "specification": {
        "name": "技术规范/规程",
        "name_en": "Specification",
        "description": "Technical specifications, operating procedures, work instructions",
        "schema": Specification,
        "prompt": """Extract the following information from the technical specification document:
1. Specification number
2. Specification name
3. Specification type (technical spec/operating procedure/work instruction/management method)
4. Issuing unit
5. Issue date
6. Version number
7. Scope of application
8. Main chapter titles
9. Core requirements
10. Whether appendix or attachments are available, extract download links
11. Keywords
12. Professional areas""",
        "category": "法规标准",
    },
    "policy_document": {
        "name": "政策文件/通知",
        "name_en": "Policy Document",
        "description": "Notices, announcements, opinions, official replies",
        "schema": PolicyDocument,
        "prompt": """Extract the following information from the policy document:
1. Document title
2. Document number (if any)
3. Document type (notice/announcement/opinion/reply/decision/letter)
4. Issuing authority
5. Issue date
6. Topic categories
7. Industry categories
8. Main content summary
9. Related documents (if any)
10. Attachment links (if any)""",
        "category": "法规标准",
    },
    "general": {
        "name": "通用提取",
        "name_en": "General",
        "description": "General web content extraction, organized as Markdown",
        "schema": None,
        "prompt": "Extract all important information from the webpage, organized as clear Markdown format. Include title, date, source, key content, etc.",
        "category": "通用",
    },
    "project_info": {
        "name": "项目信息",
        "name_en": "Project Info",
        "description": "Construction project basic information extraction",
        "schema": None,
        "prompt": """Extract the following from project information:
1. Project name
2. Construction unit
3. Construction site
4. Total investment
5. Construction period (if any)
6. Approval document number (if any)
7. Main construction content
8. Environmental measures (if any)

Output in Markdown format.""",
        "category": "通用",
    },
    "environmental_impact": {
        "name": "环境影响评价",
        "name_en": "EIA Report",
        "description": "Environmental impact assessment report content extraction",
        "schema": None,
        "prompt": """Extract the following from EIA report:
1. Project basic information
2. Wastewater treatment plan
3. Exhaust gas treatment plan
4. Solid waste disposal plan
5. Noise control measures
6. Environmental monitoring plan
7. Environmental protection investment estimate (if any)
8. Evaluation conclusions

Output in Markdown format with tables and lists where appropriate.""",
        "category": "通用",
    },
}


def get_schema_by_name(name: str):
    """Get schema class by name."""
    schema_info = PREDEFINED_SCHEMAS.get(name)
    if schema_info:
        return schema_info["schema"]
    return None


def get_schema_prompt(name: str) -> str:
    """Get extraction prompt for schema."""
    schema_info = PREDEFINED_SCHEMAS.get(name)
    if schema_info:
        return schema_info["prompt"]
    return "Extract all important information from the webpage, organized as clear Markdown format."


def get_schemas_by_category(category: str) -> list[dict]:
    """Get all schemas in a category."""
    return [{"name": k, **v} for k, v in PREDEFINED_SCHEMAS.items() if v.get("category") == category]


def list_all_schemas() -> list[dict]:
    """List all schemas with their categories."""
    result = []
    for name, info in PREDEFINED_SCHEMAS.items():
        result.append(
            {
                "name": name,
                "display_name": info["name"],
                "name_en": info.get("name_en", ""),
                "description": info["description"],
                "category": info.get("category", "通用"),
                "supports_structured": info["schema"] is not None,
            }
        )
    return result
