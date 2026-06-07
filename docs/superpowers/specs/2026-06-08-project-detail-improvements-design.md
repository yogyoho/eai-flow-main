# Design: Project Detail Page UX Improvements

Date: 2026-06-08
Branch: merge-2.0-rc
Context: Project detail page (overview tab) needs data-driven stat updates and cleaner member management.

---

## Problem Statement

The project detail page has four issues that break user trust:

1. **File count always shows 0** — stats come from thread uploads, not from AI-generated documents in the AIDocument table
2. **Chapter progress is static** — derived from the template outline, never reflects AI-generated content
3. **Member management is confusing** — admin appears as project member, non-owner members have role-change dropdowns which should be badges
4. **Workflow node order shows the topological sort of the DAG correctly**, but users expect a specific visual order

Additionally: member role badges should display properly, and the UX needs file-status indicators.

---

## Design Decisions

### Decision 1: File count — only final documents

**Rationale:** AI may generate temporary files, metadata dumps, and partial drafts. Counting all files inflates the stat and misleads users. Only user-marked final documents count.

**Implementation:**
- `GET /projects/{id}/stats` already queries AIDocument table
- Add `WHERE status='final'` filter
- Frontend: add "Mark as Final" button to EditorTab

### Decision 2: Chapter progress — dynamic Markdown parsing

**Rationale:** Chapter progress must reflect the actual report content, not the template outline. AI can generate one complete document or multiple chapter files. In both cases, parsing the final merged document's Markdown headings gives the ground truth.

**Implementation:**
- `POST /projects/{id}/finalize-doc` endpoint
- On finalize: scan `##` headings in doc content, fuzzy-match to template chapter titles
- Matched chapters → status=completed, update word_count_current from section byte length
- Unmatched chapters → remain pending
- Multiple final docs → chapter progress is the union of all matches

### Decision 3: Member card — badges, not dropdowns

**Rationale:** Roles are set during project creation and should not be casually changed. The dropdown UX invites accidental role changes. Badges are clearer and safer.

**Implementation:**
- Remove `<Select>` role-change dropdown for non-owner members
- All members show role badge (`MEMBER_ROLE_LABELS`)
- Keep delete button (remove member) for non-owners
- Keep "Add Member" button in header
- Remove admin from being auto-added as project member

### Decision 4: Workflow order — correct as-is

**Rationale:** The status endpoint already computes topological order correctly. The display matches the DAG edges. If users want a different order, they should edit the workflow template graph.

### Additional Improvements

- Add sync-status indicator to overview (last sync time, success/failure)
- Document editor: preview-merge before final merge
- Chapter progress: show chapter-to-document mapping

---

## Architecture

```
User clicks "Mark as Final" on a document
  │
  ▼
POST /projects/{id}/finalize-doc  { doc_id }
  │
  ├─► Set doc.status = "final"
  │
  ├─► Parse doc.content Markdown
  │     Extract ## headings
  │     Fuzzy match against template chapter titles
  │
  ├─► Update matched ProjectChapter rows
  │     status → "completed"
  │     word_count_current → section byte length
  │
  └─► Return { matched_count, unmatched_headings }
```

```
GET /projects/{id}/stats (updated)
  │
  ├─► COUNT AIDocument WHERE project_id=X AND status='final' → documentCount
  ├─► SUM(file_size) for final docs → documentTotalSize
  ├─► COUNT + status aggregation from ProjectChapter → chapter stats
  └─► Return ProjectStatsResponse
```

---

## Implementation Tasks

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Update `getStats` to filter by `status='final'` | `project/routers.py` | S |
| 2 | Implement `POST /projects/{id}/finalize-doc` with Markdown parsing | `project/routers.py`, new `chapter_matching.py` | M |
| 3 | Add "Mark as Final" button to EditorTab | `EditorTab.tsx`, `project/api.ts` | M |
| 4 | Replace member role dropdown with badges | `OverviewTab.tsx` | S |
| 5 | Fix admin auto-added as project member | `project/service.py` | S |
| 6 | Add sync-status indicator to overview | `OverviewTab.tsx` | S |

---

## Edge Cases

- **Empty document marked final**: skip parsing, return matched_count=0
- **Heading doesn't match any chapter**: add to `unmatched_headings` in response
- **Multiple docs marked final for same chapter**: take the most recent match
- **Admin accesses project**: has system permissions but is not listed as a member
- **Fuzzy match threshold**: `difflib.SequenceMatcher.ratio() >= 0.6` considered a match

## Success Criteria

- [ ] New project with AI-generated docs → file count shows 0 until user marks final
- [ ] Marking doc as final → chapter progress updates automatically
- [ ] Member card shows lisi as "负责人" badge, zhaoliu/wanger as "组员" badges
- [ ] Admin is not listed as project member
- [ ] Workflow progress shows correct topological order
