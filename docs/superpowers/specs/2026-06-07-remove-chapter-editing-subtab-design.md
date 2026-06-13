# Design: Remove Chapter Editing Sub-tab from Editor Tab

Date: 2026-06-07
Branch: merge-2.0-rc
Context: The EditorTab currently has two sub-tabs — "章节编辑" (Chapter Edit) and "文档文件" (Document Files). The chapter editing functionality is fully duplicated by the Overview tab's "章节进度" section. This design removes the redundant sub-tab.

---

## Problem Statement

`EditorTab.tsx` currently has two modes via a toggle bar:

| Mode | Content |
|------|---------|
| 章节编辑 (default) | Chapter list from template outline — status badges, assignees, edit/mark-complete actions |
| 文档文件 | `ProjectDocListPanel` — flat list of AI-generated documents |

Both modes lead to `DocCollabView` when a user opens a document. The "章节编辑" mode is a near-exact copy of the Overview tab's "章节进度" section, which already shows chapter titles, status badges, assignees, and hover actions for edit and mark-complete. The only difference is navigation behavior on "edit" click.

**This creates three problems:**
1. **Redundancy** — chapter management UI lives in two places, confusing users
2. **Maintenance burden** — `handleEditChapter`, `handleMarkComplete`, permission checks (`canEditChapter`, `canMarkComplete`) are duplicated
3. **Unclear mental model** — Overview manages chapters AND Editor manages chapters → which is authoritative?

---

## Design Decision

**Remove the "章节编辑" sub-tab entirely.** Chapter management is the Overview tab's responsibility. The Editor tab becomes a single-purpose view: browse AI-generated documents and edit them.

### Before (current state)

```
EditorTab
├─ Toggle: [章节编辑] [文档文件]
├─ Mode=chapters → ChapterNode list + edit/complete actions
├─ Mode=files   → ProjectDocListPanel
└─ selectedDoc  → DocCollabView (editor)
```

### After (target state)

```
EditorTab
├─ Header: "文档文件" (+ count)
├─ ProjectDocListPanel
└─ selectedDoc → DocCollabView (editor)
```

### User flow

```
Overview tab (章节进度)
  └─ Click "编辑" on a chapter
       │
       ├─ sessionStorage ← openChapterDoc
       ├─ dispatch switchTab → "editor"
       │
       ▼
Editor tab
  └─ Detects openChapterDoc in sessionStorage
       └─ Opens DocCollabView with that document
            └─ Back → returns to ProjectDocListPanel (file list)
```

No change to the Overview → Editor flow. The sessionStorage bridge still works.

---

## Implementation

### File changes: `EditorTab.tsx`

**Remove:**
- `mode` state and toggle bar (both copies: lines 112-138 for files mode, lines 166-189 for chapters mode)
- Chapter list rendering — the entire `return` block at lines 164-271 (the chapters mode)
- `canEditChapter` function (lines 142-157)
- `canMarkComplete` function (lines 159-162)
- `handleMarkComplete` function (lines 80-94)
- `handleEditChapter` function (lines 66-78) — the flow from Overview uses sessionStorage, not direct clicks within EditorTab
- Unused imports: `CheckCheck`, `Edit3`, `FileText`, `User`, `Badge`, `flattenChapters`, `inferStatus`, `ChapterStatus` type, `ProjectChapter` type
- `STATUS_BADGE_STYLES` and `STATUS_LABELS` constants

**Keep:**
- `selectedDoc` state
- `openingId` state (may still be needed for file opening)
- `sessionStorage` check for `openChapterDoc` (the bridge from Overview)
- `DocCollabView` mode when `selectedDoc` is set
- `ProjectDocListPanel` as the default view

**Simplify:**
- The files-mode toggle bar (lines 112-138) becomes the main header — remove the toggle buttons, keep just a header label
- Remove `mode` state entirely

### No changes needed:
- `OverviewTab.tsx` — already has the full chapter management UI
- `DocCollabView.tsx` — unchanged
- `ProjectDocListPanel` — unchanged
- `projectApi` — unchanged
- `tabRegistry` — unchanged (the "editor" tab still exists and is registered)

---

## Edge Cases

- **No chapters in project**: N/A — Editor no longer deals with chapters
- **sessionStorage has openChapterDoc but doc is stale/deleted**: Existing error handling in DocCollabView handles this
- **User navigates directly to Editor tab without clicking from Overview**: Shows file list — same as today's "文档文件" mode

## Success Criteria

- [ ] Editor tab shows only the file list (no chapter toggle)
- [ ] Overview → click "编辑" on chapter → still switches to Editor and opens correct document
- [ ] Clicking back from DocCollabView returns to file list
- [ ] No TypeScript errors, no unused imports
- [ ] `pnpm typecheck` and `pnpm lint` pass
