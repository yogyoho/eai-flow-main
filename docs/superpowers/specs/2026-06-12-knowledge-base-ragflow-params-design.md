# Knowledge Base Creation — RAGFlow Parameter Enhancement

**Date:** 2026-06-12
**Status:** Draft
**Scope:** Enhance the "create knowledge base" dialog to expose RAGFlow-specific parameters (chunk method, embedding model, chunk size, delimiter, PDF parser) when the user selects "RAGFlow" as the knowledge base type.

## Problem

When creating a knowledge base with `kb_type="ragflow"`, the dialog only collects `name`, `access_type`, `kb_type`, and `description`. The backend calls `RAGFlowClient.create_dataset()` but does **not** pass `chunk_method` or `parser_config` to the RAGFlow API, even though both the client and the schema support them. Users have no way to control how RAGFlow chunks and parses their documents at creation time.

## Current Flow

1. Frontend dialog collects: `name`, `access_type`, `kb_type`, `description`
2. `POST /api/extensions/knowledge-bases` with `CreateKnowledgeBaseRequest`
3. `KnowledgeBaseService.create_kb()` → `rf_client.create_dataset(name, description, embedding_model)` — **no chunk_method or parser_config**
4. RAGFlow creates the dataset with default settings (`chunk_method="naive"`, `parser_config={}`)

## Proposed Flow

1. Frontend dialog collects: `name`, `access_type`, `kb_type`, `description`
2. **When `kb_type === "ragflow"`**: also collects `chunk_method`, `embedding_model`, `parser_config` (chunk_token_num, delimiter, layout_recognize)
3. `POST /api/extensions/knowledge-bases` with extended `CreateKnowledgeBaseRequest`
4. `KnowledgeBaseService.create_kb()` → `rf_client.create_dataset(name, description, embedding_model, chunk_method, parser_config)` — **all parameters passed**
5. RAGFlow creates the dataset with user-specified settings

## Design

### Frontend: Conditional RAGFlow Parameters Panel

When `kb_type === "ragflow"` is selected, a "RAGFlow 参数" section appears in the create dialog with 5 fields:

#### Field 1: Chunk Method (`chunk_method`)

Dropdown with labels mapped to RAGFlow API values:

| Label (Chinese) | API value | Applicable file formats |
|---|---|---|
| 通用 (General) | `naive` | MD, DOCX, XLSX, PPT, PDF, TXT, images, CSV, JSON, EML, HTML |
| 问答 (Q&A) | `qa` | XLSX, XLS, CSV/TXT |
| 手册 (Manual) | `manual` | PDF |
| 表格 (Table) | `table` | XLSX, XLS, CSV/TXT |
| 论文 (Paper) | `paper` | PDF |
| 书籍 (Book) | `book` | DOCX, PDF, TXT |
| 法律 (Laws) | `laws` | DOCX, PDF, TXT |
| 演示文稿 (Presentation) | `presentation` | PDF, PPTX |
| 图片 (Picture) | `picture` | JPEG, JPG, PNG, TIF, GIF |
| 整篇 (One) | `one` | DOCX, XLSX, XLS, PDF, TXT |
| 标签集 (Tag) | `tag` | XLSX, CSV/TXT |

Default: `naive` (通用).

#### Field 2: Embedding Model (`embedding_model`)

Dropdown populated dynamically from `GET /api/extensions/knowledge-bases/ragflow/embedding-models`. Shows loading spinner while fetching. If fetch fails, falls back to a text input where user can type `model_name@factory` format.

Default: first available model from RAGFlow.

#### Field 3: Chunk Size (`parser_config.chunk_token_num`)

Slider control: range 128–2048, step 128, default 512. Displays current value next to the slider (matches existing "检索配置" tab pattern in KnowledgeBaseDetail).

#### Field 4: Delimiter (`parser_config.delimiter`)

Text input with default value `\n`.

#### Field 5: PDF Parser (`parser_config.layout_recognize`)

Dropdown:

| Label (Chinese) | API value | Description |
|---|---|---|
| DeepDOC (默认) | `DeepDOC` | OCR + layout analysis, table/column recognition. Slower but more accurate. |
| 快速解析 | `Naive` | No OCR or layout recognition. Fast text extraction. Best for text-heavy documents. |

Default: `DeepDOC`.

### Frontend: New API Endpoint for Embedding Models

`GET /api/extensions/knowledge-bases/ragflow/embedding-models`

Response:
```json
{
  "models": ["BAAI/bge-large-zh-v1.5@BAAI", "text-embedding-v2@Tongyi-Qianwen"]
}
```

If RAGFlow is unavailable:
```json
{
  "models": [],
  "error": "RAGFlow service unavailable"
}
```

### Backend: Schema Changes

Add `parser_config` field to `KnowledgeBaseBase` (inherited by `KnowledgeBaseCreate` and `KnowledgeBaseUpdate`):

```python
class KnowledgeBaseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    access_type: str = "private"
    kb_type: str = "ragflow"
    allowed_depts: list[UUID] | None = None
    embedding_model: str | None = None
    chunk_method: str = "naive"
    parser_config: dict | None = None  # NEW
```

### Backend: Model Changes

Add `parser_config` column to `KnowledgeBase` model:

```python
parser_config = Column(JSON, nullable=True, default=None)
```

### Backend: Database Migration

In `database.py` `migrate_db()`:

```sql
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS parser_config JSON DEFAULT NULL;
```

### Backend: Service Changes

**`KnowledgeBaseService.create_kb()`** — pass `chunk_method` and `parser_config` to `create_dataset`:

```python
rf_result = await rf_client.create_dataset(
    name=data.name,
    description=data.description or "",
    embedding_model=embed_model,
    chunk_method=data.chunk_method,      # NEW
    parser_config=data.parser_config,     # NEW
)
```

Also store `parser_config` on the `KnowledgeBase` model and persist `chunk_method` properly.

**`KnowledgeBaseService.update_kb()`** — pass updated `parser_config` and `chunk_method` to `update_dataset`.

**`KnowledgeBaseService.to_response()`** — include `parser_config` in the response.

### Backend: Router Changes

New endpoint for listing available embedding models:

```python
@router.get("/ragflow/embedding-models")
async def list_ragflow_embedding_models(
    current_user: CurrentUser = Depends(require_permission("kb:create")),
):
    rf_client = RAGFlowClient()
    models = await rf_client.list_available_embedding_models()
    return {"models": models}
```

### Frontend: Type Changes

Add `parser_config` to request/response types:

```typescript
interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  access_type?: string;
  kb_type?: string;
  allowed_depts?: string[];
  embedding_model?: string;
  chunk_method?: string;
  parser_config?: {
    chunk_token_num?: number;
    delimiter?: string;
    layout_recognize?: string;
  };
}

interface KnowledgeBase {
  // ... existing fields
  parser_config?: {
    chunk_token_num?: number;
    delimiter?: string;
    layout_recognize?: string;
    [key: string]: unknown;  // allow other RAGFlow config keys
  };
}
```

## Files to Change

| File | Change |
|---|---|
| `backend/app/extensions/schemas.py` | Add `parser_config: dict \| None = None` to `KnowledgeBaseBase` |
| `backend/app/extensions/models.py` | Add `parser_config = Column(JSON, nullable=True)` to `KnowledgeBase` |
| `backend/app/extensions/database.py` | Add `ALTER TABLE ... ADD COLUMN parser_config` to `migrate_db()` |
| `backend/app/extensions/knowledge/service.py` | Pass `chunk_method` + `parser_config` in `create_kb()` and `update_kb()`; include in `to_response()` |
| `backend/app/extensions/knowledge/routers.py` | Add `GET /ragflow/embedding-models` endpoint |
| `frontend/src/extensions/types/index.ts` | Add `parser_config` to KB request/response types |
| `frontend/src/app/knowledge/page.tsx` | Add conditional RAGFlow parameters section to create dialog |

## Error Handling

- **Embedding model fetch fails**: Show text input as fallback. User can manually type `model_name@factory`.
- **RAGFlow unavailable**: Create KB without RAGFlow sync (existing behavior — log warning and continue).
- **RAGFlow rejects parameters**: Return error message to user via toast notification.
- **Invalid `parser_config` values**: RAGFlow API validates and returns error codes — surface to user.

## What This Does NOT Include (YAGNI)

- Per-document `parser_config` override (already exists in upload flow via `chunk_config` form field)
- Ingestion pipeline selection (`parse_type` + `pipeline_id`) — advanced feature, can be added later
- RAPTOR / GraphRAG toggles — advanced features for future
- Auto-keywords / auto-questions settings — secondary parameters
