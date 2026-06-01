# Phase 2: AI Content Traceability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paragraph-level source traceability to AI-generated content — every data point, quote, and paragraph can be traced back to its origin (knowledge base, RAG retrieval, AI model, human edit, regulation, template).

**Architecture:** AI generates content with `[source:type:ref]` markers. A `traceability.py` service parses these markers on write and stores them in `content_sources` table. BlockNote custom extension renders inline annotations (colored underlines + superscript numbers) and footnotes. Missing source detection API highlights un-attributed paragraphs.

**Tech Stack:** SQLAlchemy async, Pydantic, BlockNote custom extension, FastAPI, PostgreSQL JSONB

**Spec:** `docs/superpowers/specs/2026-05-29-workflow-engine-traceability-review-design.md` (Section 5)

---

## File Structure

### New Files (Backend)

```
backend/app/extensions/workflow/traceability.py    # Source parsing service
backend/tests/test_traceability.py                 # Tests for parsing + API
```

### Modified Files (Backend)

```
backend/app/extensions/workflow/models.py          # Add ContentSource model
backend/app/extensions/workflow/schemas.py         # Add source schemas
backend/app/extensions/workflow/routers.py          # Add source endpoints
backend/app/extensions/database.py                  # Add content_sources table migration
```

### New Files (Frontend)

```
frontend/src/extensions/workflow/TraceabilityPanel.tsx   # Main panel
frontend/src/extensions/workflow/SourceAnnotation.tsx     # Inline annotation renderer
frontend/src/extensions/workflow/SourceFootnote.tsx       # Footnote list
frontend/src/extensions/workflow/createSourceExtension.ts # BlockNote custom extension
```

---

## Task 1: ContentSource Model + Migration

**Files:**
- Modify: `backend/app/extensions/workflow/models.py`
- Modify: `backend/app/extensions/database.py`

- [ ] **Step 1: Add ContentSource model to models.py**

Append to `backend/app/extensions/workflow/models.py`:

```python
class ContentSource(Base):
    """Paragraph-level source traceability for AI-generated content."""

    __tablename__ = "content_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("project_chapters.id"), nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ContentSource {self.source_type}:{self.source_ref} block={self.block_index}>"
```

Note: Use `metadata_` as Python attribute name (with `name="metadata"` in mapped_column) to avoid conflict with SQLAlchemy's reserved `metadata` attribute.

- [ ] **Step 2: Add migration in database.py**

Append inside `migrate_db()`:

```python
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS content_sources ("
        "  id UUID PRIMARY KEY,"
        "  chapter_id UUID NOT NULL REFERENCES project_chapters(id),"
        "  block_index INTEGER NOT NULL,"
        "  source_type VARCHAR(30) NOT NULL,"
        "  source_ref VARCHAR(500),"
        "  snippet TEXT,"
        "  confidence FLOAT,"
        "  metadata JSONB,"
        "  created_at TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_content_sources_chapter "
        "ON content_sources (chapter_id, block_index)"
    ))
```

- [ ] **Step 3: Verify**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow.models import ContentSource; print('Fields:', [c.name for c in ContentSource.__table__.columns])"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/workflow/models.py backend/app/extensions/database.py && git commit -m "feat(traceability): add ContentSource model and migration"
```

---

## Task 2: Source Schemas + Traceability Service

**Files:**
- Modify: `backend/app/extensions/workflow/schemas.py`
- Create: `backend/app/extensions/workflow/traceability.py`

- [ ] **Step 1: Add schemas to schemas.py**

Append:

```python
class ContentSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chapter_id: UUID
    block_index: int
    source_type: str
    source_ref: str | None = None
    snippet: str | None = None
    confidence: float | None = None
    metadata: dict | None = None
    created_at: datetime | None = None

class ContentSourceListResponse(BaseModel):
    sources: list[ContentSourceOut] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)

class SourceMissingResult(BaseModel):
    block_index: int
    preview: str = ""
```

- [ ] **Step 2: Create traceability.py**

```python
import re
from typing import NamedTuple


class ParsedSource(NamedTuple):
    block_index: int
    source_type: str
    source_ref: str
    snippet: str
    confidence: float | None = None
    metadata: dict | None = None


def parse_source_markers(content: str, block_start_index: int = 0) -> list[ParsedSource]:
    """Parse [N] source markers from AI-generated content.
    
    AI output format:
        Text with data[1] and more[2].
        
        [1] source:rag_retrieval:知识库「...」→「文档」p.23
        [2] source:regulation:GB 3095-2012 表2
    """
    sources: list[ParsedSource] = []
    
    # Split into blocks (paragraphs)
    blocks = content.split("\n\n")
    
    # Collect footnotes: [N] source:type:ref
    footnotes: dict[str, dict] = {}
    footnote_pattern = re.compile(r"^\[(\d+)\]\s+source:(\w+):(.+)$", re.MULTILINE)
    for block in blocks:
        for match in footnote_pattern.finditer(block):
            num, stype, sref = match.group(1), match.group(2), match.group(3).strip()
            footnotes[num] = {"type": stype, "ref": sref}
    
    # Find inline markers: text[N]
    inline_pattern = re.compile(r"\[(\d+)\]")
    block_idx = block_start_index
    for block in blocks:
        if footnote_pattern.match(block.strip()):
            continue  # Skip footnote blocks
        
        for match in inline_pattern.finditer(block):
            num = match.group(1)
            if num in footnotes:
                fn = footnotes[num]
                # Extract snippet (text around the marker)
                start = max(0, match.start() - 30)
                end = min(len(block), match.end() + 30)
                snippet = block[start:end].strip()
                
                sources.append(ParsedSource(
                    block_index=block_idx,
                    source_type=fn["type"],
                    source_ref=fn["ref"],
                    snippet=snippet,
                ))
        block_idx += 1
    
    return sources


def find_missing_sources(content: str) -> list[dict]:
    """Find paragraphs/blocks that have no source annotations.
    
    Returns list of {"block_index": N, "preview": "first 50 chars"}.
    """
    blocks = content.split("\n\n")
    missing = []
    footnote_pattern = re.compile(r"^\[\d+\]\s+source:", re.MULTILINE)
    inline_pattern = re.compile(r"\[\d+\]")
    
    for idx, block in enumerate(blocks):
        if footnote_pattern.match(block.strip()):
            continue
        if not block.strip():
            continue
        # Check if block has any inline [N] markers
        if not inline_pattern.search(block):
            missing.append({
                "block_index": idx,
                "preview": block.strip()[:50],
            })
    
    return missing
```

- [ ] **Step 3: Verify**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "
from app.extensions.workflow.traceability import parse_source_markers, find_missing_sources
text = 'SO₂浓度0.045mg/m³[1]，低于标准0.15mg/m³[2]。\n\n[1] source:rag_retrieval:知识库「监测」→「报告」p.23\n[2] source:regulation:GB 3095-2012 表2'
sources = parse_source_markers(text)
print('Sources found:', len(sources))
for s in sources:
    print(f'  block={s.block_index} type={s.source_type} ref={s.source_ref[:40]}')
missing = find_missing_sources('有数据[1]的段落\n\n没有来源的段落\n\n[1] source:ai:thread-123')
print('Missing:', missing)
print('OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/workflow/schemas.py backend/app/extensions/workflow/traceability.py && git commit -m "feat(traceability): add source schemas and parsing service"
```

---

## Task 3: Source API Endpoints

**Files:**
- Modify: `backend/app/extensions/workflow/routers.py`

- [ ] **Step 1: Add source endpoints to routers.py**

Import ContentSource model, ContentSourceOut, ContentSourceListResponse, and traceability functions.

Add 2 new endpoints:

```python
@router.get("/projects/{project_id}/chapters/{chapter_id}/sources", response_model=ContentSourceListResponse)
async def get_chapter_sources(
    project_id: UUID,
    chapter_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    from .models import ContentSource
    result = await db.execute(
        select(ContentSource)
        .where(ContentSource.chapter_id == chapter_id)
        .order_by(ContentSource.block_index)
    )
    sources = result.scalars().all()
    
    # Stats by type
    stats: dict[str, int] = {}
    for s in sources:
        stats[s.source_type] = stats.get(s.source_type, 0) + 1
    
    return ContentSourceListResponse(
        sources=[ContentSourceOut.model_validate(s) for s in sources],
        stats=stats,
    )


@router.get("/projects/{project_id}/chapters/{chapter_id}/sources/missing")
async def get_missing_sources(
    project_id: UUID,
    chapter_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    from app.extensions.models import ProjectChapter
    from .traceability import find_missing_sources
    
    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter or not chapter.content:
        return {"missing": []}
    
    return {"missing": find_missing_sources(chapter.content)}
```

- [ ] **Step 2: Verify router loads**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow import router; print('Routes:', len(router.routes))"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/routers.py && git commit -m "feat(traceability): add source query and missing-detection endpoints"
```

---

## Task 4: Frontend Traceability Components

**Files:**
- Create: `frontend/src/extensions/workflow/createSourceExtension.ts`
- Create: `frontend/src/extensions/workflow/SourceAnnotation.tsx`
- Create: `frontend/src/extensions/workflow/SourceFootnote.tsx`
- Create: `frontend/src/extensions/workflow/TraceabilityPanel.tsx`

- [ ] **Step 1: Create SourceAnnotation.tsx**

Inline annotation component rendered inside BlockNote blocks. Shows colored underline + superscript number for each source reference.

```tsx
"use client";

export interface SourceAnnotationProps {
  index: number;
  sourceType: string;
  sourceRef: string;
  confidence: number | null;
}

const TYPE_COLORS: Record<string, string> = {
  rag_retrieval: "bg-blue-100 border-b-2 border-blue-400",
  knowledge_base: "bg-blue-50 border-b-2 border-blue-300",
  regulation: "bg-green-100 border-b-2 border-green-400",
  ai_generated: "bg-amber-100 border-b-2 border-amber-400",
  human_written: "bg-purple-100 border-b-2 border-purple-300",
  template: "bg-gray-100 border-b-2 border-gray-400",
  external_data: "bg-cyan-100 border-b-2 border-cyan-400",
};

export function SourceAnnotation({ index, sourceType, sourceRef, confidence }: SourceAnnotationProps) {
  const colorClass = TYPE_COLORS[sourceType] || "bg-gray-100 border-b-2 border-gray-300";

  return (
    <span className={`inline ${colorClass} px-0.5 rounded-sm group relative`}>
      <sup className="text-[10px] font-medium text-amber-700">{index}</sup>
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-[10px] rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
        {sourceType}: {sourceRef.slice(0, 60)}
        {confidence !== null && <span className="ml-1 text-gray-400">{(confidence * 100).toFixed(0)}%</span>}
      </span>
    </span>
  );
}
```

- [ ] **Step 2: Create SourceFootnote.tsx**

Footnote list rendered below the editor. Shows full source details for each annotation.

```tsx
"use client";

export interface SourceFootnoteProps {
  sources: Array<{
    id: string;
    blockIndex: number;
    sourceType: string;
    sourceRef: string;
    snippet: string | null;
    confidence: number | null;
  }>;
}

const TYPE_LABELS: Record<string, string> = {
  rag_retrieval: "RAG检索",
  knowledge_base: "知识库",
  regulation: "法规引用",
  ai_generated: "AI生成",
  human_written: "人工编写",
  template: "模板",
  external_data: "外部数据",
};

const TYPE_BADGE_COLORS: Record<string, string> = {
  rag_retrieval: "bg-blue-100 text-blue-700",
  knowledge_base: "bg-blue-50 text-blue-600",
  regulation: "bg-green-100 text-green-700",
  ai_generated: "bg-amber-100 text-amber-700",
  human_written: "bg-purple-100 text-purple-700",
  template: "bg-gray-100 text-gray-600",
  external_data: "bg-cyan-100 text-cyan-700",
};

export function SourceFootnote({ sources }: SourceFootnoteProps) {
  if (sources.length === 0) return null;

  return (
    <div className="border-t pt-3 mt-3 space-y-2">
      <div className="text-xs font-semibold text-muted-foreground">溯源标注</div>
      {sources.map((source, idx) => (
        <div key={source.id} className="flex gap-2 items-baseline text-xs">
          <span className="font-bold text-amber-600">[{idx + 1}]</span>
          <span className={`px-1.5 py-0.5 rounded text-[10px] ${TYPE_BADGE_COLORS[source.sourceType] || "bg-gray-100"}`}>
            {TYPE_LABELS[source.sourceType] || source.sourceType}
          </span>
          <span className="text-muted-foreground flex-1 truncate">{source.sourceRef}</span>
          {source.confidence !== null && (
            <span className="text-[10px] text-muted-foreground">{(source.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create createSourceExtension.ts**

A BlockNote extension that detects `[source:type:ref]` patterns in block content and renders SourceAnnotation components. This is a stub that will be fully implemented when integrated with the actual BlockNote editor — for Phase 2 we provide the rendering components and the API layer.

```typescript
import type { BlockNoteEditor } from "@blocknote/react";

/**
 * BlockNote extension for source traceability.
 * 
 * Phase 2 provides the rendering components and API.
 * Full BlockNote integration (inline decoration) requires
 * ProseMirror plugin registration — implemented in integration phase.
 * 
 * Currently: The TraceabilityPanel renders alongside the editor,
 * querying sources from the API and displaying footnotes/stats.
 */
export function createSourceExtension() {
  return {
    name: "source-traceability",
    // Full ProseMirror plugin integration deferred to integration phase
  };
}
```

- [ ] **Step 4: Create TraceabilityPanel.tsx**

Main panel that shows source stats, footnotes, and missing source warnings for the current chapter.

```tsx
"use client";

import { useEffect, useState } from "react";
import { workflowApi } from "./api";
import { SourceFootnote } from "./SourceFootnote";

interface SourceData {
  id: string;
  blockIndex: number;
  sourceType: string;
  sourceRef: string;
  snippet: string | null;
  confidence: number | null;
}

interface TraceabilityPanelProps {
  projectId: string;
  chapterId: string | null;
}

export function TraceabilityPanel({ projectId, chapterId }: TraceabilityPanelProps) {
  const [sources, setSources] = useState<SourceData[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [missing, setMissing] = useState<Array<{ blockIndex: number; preview: string }>>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!chapterId) return;
    setLoading(true);
    Promise.all([
      workflowApi.getSources(projectId, chapterId),
      workflowApi.getMissingSources(projectId, chapterId),
    ]).then(([sourceRes, missingRes]) => {
      setSources(sourceRes.sources);
      setStats(sourceRes.stats);
      setMissing(missingRes.missing);
    }).finally(() => setLoading(false));
  }, [projectId, chapterId]);

  if (!chapterId) {
    return <div className="p-4 text-sm text-muted-foreground">选择章节查看溯源信息</div>;
  }

  if (loading) return <div className="p-4 text-sm text-muted-foreground">加载中...</div>;

  return (
    <div className="p-4 space-y-4">
      <div className="text-sm font-semibold">本章溯源</div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(stats).map(([type, count]) => (
          <div key={type} className="flex justify-between px-2 py-1 bg-muted/50 rounded text-xs">
            <span>{type}</span>
            <span className="font-medium">{count}</span>
          </div>
        ))}
        {Object.keys(stats).length === 0 && (
          <div className="text-xs text-muted-foreground col-span-2">暂无溯源信息</div>
        )}
      </div>

      {/* Missing sources warning */}
      {missing.length > 0 && (
        <div className="p-2 bg-red-50 border border-red-200 rounded">
          <div className="text-xs font-semibold text-red-700">缺少来源标注</div>
          <div className="mt-1 space-y-1">
            {missing.map((m, i) => (
              <div key={i} className="text-[10px] text-red-600">
                第 {m.blockIndex + 1} 段: "{m.preview}..."
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footnotes */}
      <SourceFootnote sources={sources} />
    </div>
  );
}
```

- [ ] **Step 5: Add getSources and getMissingSources to api.ts**

Add two methods to `workflowApi` in `frontend/src/extensions/workflow/api.ts`:

```typescript
  getSources: async (projectId: string, chapterId: string): Promise<{ sources: any[]; stats: Record<string, number> }> => {
    const resp = await authFetch(`${API_BASE}/projects/${projectId}/chapters/${chapterId}/sources`);
    return toCamelCase(await resp.json());
  },

  getMissingSources: async (projectId: string, chapterId: string): Promise<{ missing: Array<{ blockIndex: number; preview: string }> }> => {
    const resp = await authFetch(`${API_BASE}/projects/${projectId}/chapters/${chapterId}/sources/missing`);
    return toCamelCase(await resp.json());
  },
```

- [ ] **Step 6: Verify typecheck**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | head -20
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/workflow/ && git commit -m "feat(traceability): add frontend traceability panel with annotations and footnotes"
```

---

## Task 5: Integration — Wire TraceabilityPanel into CollabEditor

**Files:**
- Modify: `frontend/src/extensions/collab/CollabEditor.tsx`

- [ ] **Step 1: Add TraceabilityPanel as a sidebar**

Read `frontend/src/extensions/collab/CollabEditor.tsx` to understand its layout. Add TraceabilityPanel as an optional right sidebar that shows when viewing project documents.

Import:
```tsx
import { TraceabilityPanel } from "@/extensions/workflow/TraceabilityPanel";
```

Add state for chapter ID (from document metadata or props).

Render alongside the BlockNote editor:
```tsx
{showTraceability && chapterId && (
  <div className="w-72 border-l overflow-y-auto">
    <TraceabilityPanel projectId={projectId} chapterId={chapterId} />
  </div>
)}
```

- [ ] **Step 2: Verify and commit**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck
git add frontend/src/extensions/collab/CollabEditor.tsx && git commit -m "feat(traceability): integrate TraceabilityPanel into CollabEditor"
```
