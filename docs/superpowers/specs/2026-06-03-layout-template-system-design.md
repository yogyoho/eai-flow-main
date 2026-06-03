# Layout Template System Design

> Date: 2026-06-03
> Status: Approved

## Problem

The Report Output page (`/output`) expects `LayoutTemplate` data (page settings, fonts, margins, headers/footers), but no code path produces these templates. The Knowledge Factory's template extraction produces **content structure templates** (chapters, sections, writing rules), which are fundamentally different from **layout formatting templates** (typography, page geometry, visual styles). As a result, the Report Output page always shows "暂无排版模板".

## Solution

Implement a Layout Template management system with two data sources:

1. **Built-in seed templates** — 3-4 industry-standard templates seeded on first deployment
2. **User-created templates** — a template editor in the Report Output page for custom creation

Templates are stored in PostgreSQL via a new backend API module.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Layout Template Sources                │
│                                                         │
│  ① Built-in Seed          ② User Created                │
│  ┌───────────────────┐    ┌───────────────────────┐     │
│  │ 环评报告(国标)      │    │ Template Editor Form   │     │
│  │ 可行性研究报告      │    │ ├─ Page Settings       │     │
│  │ 技术咨询报告        │    │ ├─ Cover Template      │     │
│  │ 通用A4报告          │    │ ├─ Body/Heading Styles  │     │
│  └───────────────────┘    │ ├─ Table/Figure Styles   │     │
│         │                 │ ├─ Header/Footer         │     │
│         ▼                 │ └─ Reference/Appendix    │     │
│   Auto-seed on deploy     └───────────────────────┘     │
│   is_builtin = true              │                      │
│   Cannot be deleted              ▼                      │
│                           POST /output/templates        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              GET /output/templates
              (returns built-in + custom)
                          │
                          ▼
              Report Output - Templates Tab
              (card grid + create button)
```

## Module A: Backend — Layout Template CRUD API

### Database Table

Table name: `layout_templates`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default gen | Primary key |
| `name` | VARCHAR(200) | NOT NULL | Template display name |
| `report_type` | VARCHAR(100) | NOT NULL | Category tag (e.g., "environmental_assessment") |
| `is_builtin` | BOOLEAN | NOT NULL, default false | Built-in templates cannot be deleted |
| `page_settings` | JSONB | NOT NULL | Paper size, orientation, margins |
| `cover_template` | JSONB | NULL | Cover page configuration |
| `toc_settings` | JSONB | NULL | Table of contents configuration |
| `body_styles` | JSONB | NOT NULL | Body text font, size, line height |
| `heading_styles` | JSONB | NOT NULL, default '[]' | Array of heading level styles |
| `table_styles` | JSONB | NULL | Table header/striping/border styles |
| `figure_styles` | JSONB | NULL | Figure caption/numbering styles |
| `header_footer` | JSONB | NULL | Header/footer text and page number |
| `reference_style` | VARCHAR(50) | NOT NULL, default 'gb7714' | Citation format standard |
| `appendix_rules` | JSONB | NULL | Appendix numbering and TOC |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | Last update timestamp |

### API Endpoints

All endpoints are under the existing extensions router prefix. Auth required.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/output/templates` | List all templates (built-in + custom) |
| `POST` | `/output/templates` | Create a custom template |
| `GET` | `/output/templates/{id}` | Get template detail |
| `PUT` | `/output/templates/{id}` | Update template (built-in: only `name` editable) |
| `DELETE` | `/output/templates/{id}` | Delete template (built-in: returns 403) |

### Request/Response Schemas

**Create/Update Request Body:**

```json
{
  "name": "My Custom Template",
  "report_type": "feasibility_study",
  "page_settings": {
    "paperSize": "A4",
    "orientation": "portrait",
    "marginTop": 2.54,
    "marginBottom": 2.54,
    "marginLeft": 3.17,
    "marginRight": 3.17
  },
  "cover_template": null,
  "toc_settings": { "maxDepth": 3, "showPageNumbers": true, "leaderDots": true },
  "body_styles": {
    "fontFamily": "宋体",
    "fontSize": 12,
    "lineHeight": 1.5,
    "paragraphSpacing": 6,
    "firstLineIndent": 2
  },
  "heading_styles": [
    { "level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal" },
    { "level": 2, "fontFamily": "黑体", "fontSize": 14, "fontWeight": 700, "color": "#333333", "numbering": "decimal" }
  ],
  "table_styles": { "headerBg": "#2B579A", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": true },
  "figure_styles": { "captionPosition": "below", "numbering": "chapter", "showSource": true },
  "header_footer": { "headerText": "", "footerText": "", "showPageNumber": true, "showLogo": false },
  "reference_style": "gb7714",
  "appendix_rules": { "numbering": "A-B-C", "separateToc": false }
}
```

**Response:** Same shape as request, plus `id`, `is_builtin`, `created_at`, `updated_at`. API uses snake_case; frontend transforms to camelCase via existing `transforms.ts`.

## Module B: Built-in Seed Templates

Seeded on first deployment. Four templates:

### 1. 环评报告（国标）

- **report_type**: `environmental_assessment`
- **Page**: A4 portrait, margins 2.54/2.54/3.17/3.17 cm
- **Body**: 宋体 12pt, line-height 1.5, first-line indent 2 chars
- **Headings**: 黑体, levels 1-3, decimal numbering
- **Tables**: header bg #2B579A, stripe rows
- **References**: gb7714
- **Cover**: show logo, title, client, date, project number

### 2. 可行性研究报告

- **report_type**: `feasibility_study`
- **Page**: A4 portrait, margins 2.5/2.5/2.8/2.8 cm
- **Body**: 仿宋 12pt, line-height 1.5
- **Headings**: 黑体, levels 1-4, decimal numbering
- **Tables**: header bg #1F4E79, stripe rows
- **References**: gb7714

### 3. 技术咨询报告

- **report_type**: `technical_consulting`
- **Page**: A4 portrait, margins 2.54/2.54/3.17/3.17 cm
- **Body**: 微软雅黑 11pt, line-height 1.75
- **Headings**: 微软雅黑, levels 1-3, decimal numbering
- **Tables**: header bg #3B5998, stripe rows
- **References**: gb7714

### 4. 通用A4报告

- **report_type**: `general`
- **Page**: A4 portrait, standard margins
- **Body**: 默认字体 12pt, line-height 1.5
- **Headings**: bold, levels 1-2, no numbering
- **Tables**: default styles, no stripes
- **References**: gb7714

### Seed Mechanism

- Seed function in `backend/app/extensions/output/seed.py`
- Called on app startup if `layout_templates` table has 0 rows with `is_builtin=true`
- Idempotent — uses fixed UUIDs for built-in templates so re-seeding is safe

## Module C: Frontend — Template Editor & Card Actions

### Template Card Enhancements

`LayoutTemplateCard` gets hover actions:
- **Custom templates**: Edit, Duplicate, Delete
- **Built-in templates**: Duplicate only (with tooltip "内置模板不可编辑")

### Template Editor

New component: `LayoutTemplateEditor.tsx` — a collapsible section form with these panels:

| Panel | Fields |
|-------|--------|
| **基本信息** | name, report_type (dropdown + custom input) |
| **页面设置** | paperSize (A4/A3/B5/letter), orientation, 4x margin inputs |
| **封面配置** | showLogo, logoPosition, showTitle, showClient, showDate, showProjectNumber |
| **正文样式** | fontFamily, fontSize, lineHeight, paragraphSpacing, firstLineIndent |
| **标题样式** | Dynamic array of heading levels (fontFamily, fontSize, fontWeight, color, numbering) |
| **表格样式** | headerBg (color picker), headerColor, borderColor, stripeRows toggle |
| **图表样式** | captionPosition, numbering, showSource |
| **页眉页脚** | headerText, footerText, showPageNumber, showLogo |
| **参考文献与附录** | referenceStyle (dropdown), appendix numbering, separateToc |

### Frontend File Changes

| File | Change |
|------|--------|
| `frontend/src/extensions/output/OutputManager.tsx` | TemplatesTab: add "新建模板" button, wire up editor modal |
| `frontend/src/extensions/output/components/LayoutTemplateCard.tsx` | Add hover actions (edit/duplicate/delete), `is_builtin` badge |
| `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` | **NEW** — Template editor form with collapsible sections |
| `frontend/src/extensions/output/types.ts` | Add `isBuiltin` field to `LayoutTemplate` |
| `frontend/src/extensions/output/api.ts` | Add `createTemplate`, `updateTemplate`, `deleteTemplate` methods |
| `frontend/src/extensions/output/transforms.ts` | Add `is_builtin` → `isBuiltin` mapping |

### Backend File Changes

| File | Change |
|------|--------|
| `backend/app/extensions/output/__init__.py` | **NEW** — Module init |
| `backend/app/extensions/output/models.py` | **NEW** — SQLAlchemy model for layout_templates |
| `backend/app/extensions/output/schemas.py` | **NEW** — Pydantic request/response schemas |
| `backend/app/extensions/output/routers.py` | **NEW** — FastAPI router with CRUD endpoints |
| `backend/app/extensions/output/service.py` | **NEW** — Business logic layer |
| `backend/app/extensions/output/seed.py` | **NEW** — Built-in template seed data |
| `backend/app/extensions/database.py` | Add layout_templates table to metadata |
| `backend/app/extensions/models.py` | Import and register the new model |

## Future Considerations (Out of Scope)

- **Smart extraction from sample reports** — enhance Knowledge Factory pipeline to extract layout info (fonts, margins) from uploaded PDF/DOCX files
- **Template import/export** — allow JSON import/export of templates
- **Template sharing** — project-level or organization-level template libraries
- **Template versioning** — track changes over time
- **Visual preview** — WYSIWYG preview of template styles
