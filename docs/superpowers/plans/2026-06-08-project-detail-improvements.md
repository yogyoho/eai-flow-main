# Project Detail Page Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix file count, chapter progress, member management, and sync-status on the project overview page.

**Architecture:** Update the `getStats` API to count only final documents. Add a `finalize-doc` endpoint that parses Markdown headings and fuzzy-matches them to template chapters. Replace member role dropdowns with badges. Fix admin member auto-add.

**Tech Stack:** Python 3.12+ (FastAPI, SQLAlchemy), TypeScript (React 19, Next.js 16)

---

### Task 1: Update getStats to filter by status='final'

**Files:**
- Modify: `backend/app/extensions/project/routers.py:989-1045`

- [ ] **Step 1: Update the SQL query to filter by status**

Read the current `get_project_stats` function at line 989. Find the doc_stmt and update the WHERE clause:

```python
# In get_project_stats, replace:
doc_stmt = (
    select(
        func.count(AIDocument.id).label("count"),
        func.coalesce(func.sum(AIDocument.file_size), 0).label("total_size"),
    )
    .where(AIDocument.project_id == project_id)
)

# With:
doc_stmt = (
    select(
        func.count(AIDocument.id).label("count"),
        func.coalesce(func.sum(AIDocument.file_size), 0).label("total_size"),
    )
    .where(
        AIDocument.project_id == project_id,
        AIDocument.status == "final",
    )
)
```

- [ ] **Step 2: Restart gateway and verify**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 3: Verify the endpoint returns 0 for a project with no final docs**

```bash
docker exec deer-flow-gateway bash -c 'curl -s http://localhost:8001/api/extensions/project/projects/deda53e3-647f-4253-aa07-055a393f2b35/stats | python -m json.tool'
```

Expected: `"document_count": 0` (currently no docs have status=final)

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/project/routers.py
git commit -m "feat: filter getStats document_count to only status=final documents"
```

---

### Task 2: POST /finalize-doc endpoint with Markdown chapter matching

**Files:**
- Create: `backend/app/extensions/project/chapter_matching.py`
- Modify: `backend/app/extensions/project/routers.py` (add endpoint)
- Modify: `frontend/src/extensions/project/api.ts` (add API method)

- [ ] **Step 1: Create chapter_matching.py**

Create `backend/app/extensions/project/chapter_matching.py`:

```python
"""Match Markdown headings to template chapter titles using fuzzy matching."""

import re
from difflib import SequenceMatcher

HEADING_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
MIN_MATCH_RATIO = 0.6


def extract_headings(markdown_content: str) -> list[str]:
    """Extract all ## heading text from markdown content."""
    if not markdown_content:
        return []
    return [m.group(1).strip() for m in HEADING_PATTERN.finditer(markdown_content)]


def split_by_headings(markdown_content: str) -> dict[str, str]:
    """Split markdown into sections keyed by ## heading text."""
    if not markdown_content:
        return {}
    sections: dict[str, str] = {}
    parts = re.split(r"^##\s+", markdown_content, flags=re.MULTILINE)
    for part in parts[1:]:  # skip content before first ## heading
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections[heading] = body
    return sections


def match_headings_to_chapters(
    headings: list[str],
    chapter_titles: list[dict],  # [{"id": uuid, "title": str}, ...]
) -> list[dict]:
    """Fuzzy-match extracted headings to template chapter titles.

    Returns a list of matched chapters with word counts.
    Each entry: {"chapter_id": str, "title": str, "matched_heading": str, "word_count": int}
    """
    matches: list[dict] = []
    used_indices: set[int] = set()

    for heading in headings:
        best_ratio = 0.0
        best_idx = -1
        for i, ch in enumerate(chapter_titles):
            if i in used_indices:
                continue
            ratio = SequenceMatcher(None, heading.lower(), ch["title"].lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i

        if best_ratio >= MIN_MATCH_RATIO and best_idx >= 0:
            used_indices.add(best_idx)
            matches.append({
                "chapter_id": str(chapter_titles[best_idx]["id"]),
                "title": chapter_titles[best_idx]["title"],
                "matched_heading": heading,
            })

    return matches
```

- [ ] **Step 2: Add the finalize-doc endpoint to routers.py**

Add at the end of `backend/app/extensions/project/routers.py` (before the closing of the file):

```python
class FinalizeDocumentRequest(BaseModel):
    """Request to mark a document as final and sync chapter progress."""
    doc_id: UUID


class FinalizeDocumentResponse(BaseModel):
    """Response after finalizing a document."""
    doc_id: str
    status: str
    matched_chapters: int
    unmatched_headings: list[str] = []
    total_word_count: int = 0


@router.post("/projects/{project_id}/finalize-doc", response_model=FinalizeDocumentResponse)
async def finalize_document(
    project_id: UUID,
    body: FinalizeDocumentRequest,
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Mark a document as final and parse its markdown to update chapter progress.

    Scans ## headings in the document content, fuzzy-matches them against
    the project's template chapter titles, and updates matched chapters'
    status to 'completed' with word counts from the section content.
    """
    from app.extensions.models import AIDocument, ProjectChapter
    from app.extensions.knowledge_factory.models import ExtractionTemplate
    from .chapter_matching import extract_headings, split_by_headings, match_headings_to_chapters

    doc = await db.get(AIDocument, body.doc_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found in this project")

    # Set status to final
    doc.status = "final"
    await db.flush()

    # Get template chapter titles for matching
    project = await db.get(ReportProject, project_id)
    chapter_titles: list[dict] = []

    if project and project.template_id:
        template = await db.get(ExtractionTemplate, project.template_id)
        if template and template.root_sections_json:
            sections_data = template.root_sections_json or {}
            section_list = sections_data.get("sections", [])

            def _collect_titles(secs: list, result: list):
                for s in secs:
                    result.append({"id": s.get("id", ""), "title": s.get("title", "")})
                    _collect_titles(s.get("children", []), result)

            _collect_titles(section_list, chapter_titles)

    # Parse document content
    content = doc.content or ""
    headings = extract_headings(content)
    sections = split_by_headings(content)
    matches = match_headings_to_chapters(headings, chapter_titles)

    # Update matched chapters
    total_words = 0
    for match in matches:
        chapter_id = match["chapter_id"]
        heading = match["matched_heading"]
        section_text = sections.get(heading, "")
        word_count = len(section_text.encode("utf-8"))

        stmt = (
            ProjectChapter.__table__.update()
            .where(ProjectChapter.id == uuid.UUID(chapter_id))
            .where(ProjectChapter.project_id == project_id)
            .values(
                status="completed",
                word_count_current=ProjectChapter.word_count_current + word_count,
            )
        )
        await db.execute(stmt)
        total_words += word_count

    await db.commit()
    await db.refresh(doc)

    matched_headings = {m["matched_heading"] for m in matches}
    unmatched = [h for h in headings if h not in matched_headings]

    return FinalizeDocumentResponse(
        doc_id=str(doc.id),
        status=doc.status,
        matched_chapters=len(matches),
        unmatched_headings=unmatched,
        total_word_count=total_words,
    )
```

Note: This endpoint also needs the `from uuid import UUID` import (already present) and the `ReportProject` model import which is already imported elsewhere in the file.

- [ ] **Step 3: Restart gateway and verify**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 4: Add frontend API method**

In `frontend/src/extensions/project/api.ts`, add after the existing methods:

```typescript
  finalizeDocument: async (projectId: string, docId: string): Promise<{
    docId: string;
    status: string;
    matchedChapters: number;
    unmatchedHeadings: string[];
    totalWordCount: number;
  }> => {
    const csrf = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)?.[1] ?? "";
    return authFetch(`${API_BASE}/projects/${projectId}/finalize-doc`, {
      method: "POST",
      body: JSON.stringify({ doc_id: docId }),
    });
  },
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/project/chapter_matching.py backend/app/extensions/project/routers.py frontend/src/extensions/project/api.ts
git commit -m "feat: add finalize-doc endpoint with markdown chapter matching"
```

---

### Task 3: Add "Mark as Final" button to EditorTab

**Files:**
- Modify: `frontend/src/extensions/project/tabs/EditorTab.tsx`

- [ ] **Step 1: Read the current EditorTab to understand file listing**

Open `frontend/src/extensions/project/tabs/EditorTab.tsx`. Find where documents are listed (likely a `ProjectDocListPanel` or similar component). Identify where each document row renders.

- [ ] **Step 2: Add "Mark as Final" button to document rows**

Find the document row rendering section. After the document title display, add a button that calls `projectApi.finalizeDocument()`:

```tsx
import { CheckCheck } from "lucide-react";
import { toast } from "sonner";

// Inside the document row component, add after the title display:
{projectId && doc.status !== "final" && (
  <Button
    size="sm"
    variant="outline"
    className="h-6 text-[10px] gap-1 border-emerald-200 text-emerald-600 hover:bg-emerald-50"
    onClick={async () => {
      try {
        const result = await projectApi.finalizeDocument(projectId, doc.id);
        toast.success(`已标记为终稿，匹配 ${result.matchedChapters} 个章节`);
        // Dispatch event to refresh overview stats
        window.dispatchEvent(new CustomEvent("doc-status-changed"));
        onRefresh?.();
      } catch {
        toast.error("标记终稿失败");
      }
    }}
  >
    <CheckCheck className="h-3 w-3" />
    终稿
  </Button>
)}
```

- [ ] **Step 3: Restart frontend and verify**

```bash
docker compose -p eai-docker restart frontend
```

Navigate to http://localhost:2026/projects/deda53e3-647f-4253-aa07-055a393f2b35, click "文档编辑" tab, verify "终稿" button appears on document rows. Click it and check that the overview stats update.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/tabs/EditorTab.tsx
git commit -m "feat: add mark-as-final button to EditorTab document rows"
```

---

### Task 4: Replace member role dropdown with badges

**Files:**
- Modify: `frontend/src/extensions/project/tabs/OverviewTab.tsx:305-490`

- [ ] **Step 1: Remove handleRoleChange and update member rendering**

In `OverviewTab.tsx`, find the member rendering section (lines 449-490). Replace the role-change dropdown with a simple badge:

```tsx
// DELETE lines 457-475 (the Select dropdown for role change)
// REPLACE with badge display for ALL members:

<div key={m.id} className="flex items-center gap-2.5 px-3 py-2.5">
  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-medium text-primary">
    {(m.username ?? "?").charAt(0).toUpperCase()}
  </div>
  <span className="flex-1 text-sm text-foreground truncate">{m.username}</span>
  <Badge variant="secondary" className="text-[10px] font-normal shrink-0">
    {MEMBER_ROLE_LABELS[m.role as keyof typeof MEMBER_ROLE_LABELS] ?? m.role}
  </Badge>
  {canManageMembers && m.role !== "owner" && (
    <Button
      size="sm"
      variant="ghost"
      className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
      disabled={removingId === m.userId}
      onClick={() => handleRemoveMember(m.userId)}
    >
      {removingId === m.userId ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Trash2 className="h-3.5 w-3.5" />
      )}
    </Button>
  )}
</div>
```

- [ ] **Step 2: Remove unused imports and code**

- Remove the `Select` import if no longer used elsewhere in the file
- Remove the `handleRoleChange` function (lines 305-314)
- The `MEMBER_ROLE_LABELS` import should remain (still used for badges)

- [ ] **Step 3: Restart frontend and verify**

```bash
docker compose -p eai-docker restart frontend
```

Navigate to http://localhost:2026/projects/deda53e3-647f-4253-aa07-055a393f2b35, verify:
- lisi shows "负责人" badge
- zhaoliu shows "组员" badge  
- wanger shows "组员" badge
- No role-change dropdown appears

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/tabs/OverviewTab.tsx
git commit -m "fix: replace member role dropdown with badges, remove role-change UI"
```

---

### Task 5: Fix admin auto-added as project member

**Files:**
- Modify: `backend/app/extensions/project/service.py:506-513`

- [ ] **Step 1: Remove the auto-add of created_by as member**

In `create_project`, find lines 506-513:

```python
# Current code (line ~506):
if created_by:
    member = ProjectMember(
        project_id=project.id,
        user_id=created_by,
        role="owner",
    )
    db.add(member)
    await db.flush()
```

The `created_by` user (project creator) is always added as a member with `role="owner"`. For admin-created projects, this adds admin as a member. The fix: only auto-add the creator as a member if they are NOT already the creator (i.e., when the creator IS the intended project owner). Keep this logic for non-admin users who create their own projects.

Actually, the simplest fix: the issue is that admin created the project on behalf of lisi, but admin got auto-added as owner. The fix should be in the project creation wizard — it already passes `members` data. If `members_data` is provided, skip the auto-add of `created_by`. If `members_data` is empty/None (no members specified), add `created_by` as owner (backward compatible).

```python
    if created_by:
        # Only auto-add creator as owner if no members were specified
        # (backward compatible with API-based creation without members field)
        if not members_data:
            existing_creator = any(
                m["user_id"] == created_by for m in (members_data or [])
            )
            if not existing_creator:
                member = ProjectMember(
                    project_id=project.id,
                    user_id=created_by,
                    role="owner",
                )
                db.add(member)
                await db.flush()
```

Wait, looking at the logic more carefully: when `members_data` is passed (from the wizard), it already includes `leader` as `role="owner"`. So the creator (lisi) IS already in members_data as owner. The `created_by` is the authenticated user who made the API call (which could be admin). 

The simplest correct fix: only auto-add created_by when NO members are provided:

```python
    if created_by and not members_data:
        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="owner",
        )
        db.add(member)
        await db.flush()
```

- [ ] **Step 2: Restart gateway and verify**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 3: Verify admin is not in project members**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT pm.user_id, u.username, pm.role FROM project_members pm JOIN users u ON u.id = pm.user_id WHERE pm.project_id = 'deda53e3-647f-4253-aa07-055a393f2b35'"
```

Expected: lisi (owner), zhaoliu (member), wanger (member). No admin.

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/project/service.py
git commit -m "fix: only auto-add project creator as member when no members specified"
```

---

### Task 6: Add sync-status indicator to overview

**Files:**
- Modify: `frontend/src/extensions/project/tabs/OverviewTab.tsx`
- Modify: `frontend/src/extensions/project/api.ts` (add sync-status method if needed)

- [ ] **Step 1: Add sync-status state to OverviewTab**

In `OverviewTab.tsx`, add state and a fetch for sync status:

```tsx
// Add near the existing state declarations (around line 186):
const [lastSync, setLastSync] = useState<{ time: string; synced: number; skipped: number } | null>(null);
const [syncing, setSyncing] = useState(false);

// Add sync function
const handleSync = useCallback(async () => {
  setSyncing(true);
  try {
    const result = await projectApi.syncDocs(projectId);
    setLastSync({ time: new Date().toLocaleTimeString("zh-CN"), ...result });
    loadStats(); // refresh file count
    toast.success(`同步完成：${result.synced} 个新文件`);
  } catch {
    toast.error("同步失败");
  } finally {
    setSyncing(false);
  }
}, [projectId, loadStats]);

// Fetch on mount
useEffect(() => {
  handleSync();
}, []); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 2: Add sync-status display to the header section**

Add a small status line below the project creation date (around line 314-324):

```tsx
<p className="text-[13px] text-muted-foreground">
  创建于{" "}
  {project.createdAt
    ? new Date(project.createdAt).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "未知"}
  {lastSync && (
    <span className="ml-3 text-[11px] text-muted-foreground/70">
      · 上次同步: {lastSync.time}
      {lastSync.synced > 0 && ` (新增 ${lastSync.synced} 个文件)`}
    </span>
  )}
</p>
```

- [ ] **Step 3: Restart frontend and verify**

```bash
docker compose -p eai-docker restart frontend
```

Navigate to http://localhost:2026/projects/deda53e3-647f-4253-aa07-055a393f2b35, verify:
- Sync runs on page load
- "上次同步" time and count appears below the creation date
- After marking a doc as final, file count updates

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/tabs/OverviewTab.tsx
git commit -m "feat: add sync-status indicator with auto-sync on page load"
```

---

## Verification Checklist

After all tasks complete, run the end-to-end verification:

```bash
# 1. Restart both services
docker compose -p eai-docker restart gateway frontend

# 2. Backend tests
docker exec deer-flow-gateway bash -c 'cd /app/backend && PYTHONPATH=. .venv/bin/python -m pytest tests/ -k "project or workflow" -v --no-header -q 2>&1 | tail -5'

# 3. Manual page verification
# Navigate to http://localhost:2026/projects/deda53e3-647f-4253-aa07-055a393f2b35
# - File count should show actual number (after marking docs as final)
# - Chapter progress should update after finalize
# - Member card: lisi=负责人 badge, zhaoliu/wanger=组员 badges
# - Sync status line visible under creation date
```
