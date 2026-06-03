# Design: Unify Project Doc Tab with Document Space

> **Date**: 2026-06-03
> **Status**: Draft
> **Scope**: Project detail "文档编辑" tab redesign — remove duplicate doc/traceability/history tabs, reuse docmgr components

---

## Problem

Project detail page (`ProjectWorkspace`) has three independent tabs:
- **文档编辑 (editor)** — chapter outline + CollabEditor
- **溯源 (traceability)** — source attribution panel
- **版本历史 (history)** — version diff/restore

These duplicate functionality already available in the document space (`/docmgr`) when editing a project document via CollabEditor (which includes built-in traceability and version history sidebars). Maintaining two implementations creates drift and wastes effort.

Additionally, the chapter outline in EditorTab is rigid — real projects have dynamic chapter structures that change throughout the lifecycle. Users need access to all project documents (AI-generated docs + file references from thread tasks), not just chapter-structured content.

## Solution

1. **Replace EditorTab content** with the document space's project-folder document list (reuse existing `useDocuments` hook + card components).
2. **Embed CollabEditor in-tab** — clicking a document loads the full collaborative editing experience (editor + traceability sidebar + version history sidebar) within the tab content area.
3. **Remove `traceability` and `history` tabs** from `tabRegistry.ts` — these features are accessible inside the editor.

## User Flow

```
项目详情页 → 文档编辑 tab
  │
  ├── Default view: Document list (grid/list toggle)
  │   ├── Search bar + filter
  │   ├── DocCard / FileRefCard grid (reused from docmgr)
  │   │   ├── Title, file type icon, size, last modified
  │   │   └── Click → opens in-tab editor
  │   └── Pagination / "Load more"
  │
  └── Editor view (when a document is selected)
      ├── Top bar: ← Back button + document title + actions
      ├── CollabEditor (BlockNote + Yjs)
      └── Side panels: 溯源 | 版本历史 (toggle buttons)
```

## Architecture

### Component Refactoring

**Extract from `DocumentManagement.tsx`:**

The current `DocumentManagement.tsx` is a monolith (1338 lines). We extract the document list section into a standalone component:

1. **`ProjectDocListPanel`** (new file: `docmgr/ProjectDocListPanel.tsx`)
   - Props:
     ```ts
     interface ProjectDocListPanelProps {
       projectId: string;
       projectName: string;
       onSelectDoc: (doc: AIDocument) => void;
     }
     ```
   - Internally uses `useDocuments` hook with `project_scope` filter
   - Renders search bar, grid/list toggle, DocCard/FileRefCard grid, pagination
   - Reuses existing card components from `docmgr/`

2. **`DocCollabView`** (new file: `project/tabs/DocCollabView.tsx`)
   - Props:
     ```ts
     interface DocCollabViewProps {
       doc: AIDocument;
       projectId: string;
       onBack: () => void;
     }
     ```
   - Top bar: back button, document title, sidebar toggle buttons
   - Content: `CollabEditor` component
   - Sidebars: traceability info + `VersionPanel` (from collab extension)
   - Calls `useVersions` hook for version history

### EditorTab Rewrite

**File**: `project/tabs/EditorTab.tsx`

Replace entire content with a state-driven view switcher:

```tsx
function EditorTab({ project, projectId, ... }) {
  const [selectedDoc, setSelectedDoc] = useState<AIDocument | null>(null);

  if (selectedDoc) {
    return (
      <DocCollabView
        doc={selectedDoc}
        projectId={projectId}
        onBack={() => setSelectedDoc(null)}
      />
    );
  }

  return (
    <ProjectDocListPanel
      projectId={projectId}
      projectName={project.name}
      onSelectDoc={setSelectedDoc}
    />
  );
}
```

### Tab Registry Changes

**File**: `project/tabRegistry.ts`

Remove these entries:
- `traceability` tab (id: "traceability")
- `history` tab (id: "history")

Keep remaining tabs: overview, workflow, editor, review, settings.

### Files Changed

| File | Action | Description |
|------|--------|-------------|
| `docmgr/ProjectDocListPanel.tsx` | **Create** | Extracted document list panel with search/filter/pagination |
| `project/tabs/DocCollabView.tsx` | **Create** | Embedded collab editor with traceability + version sidebars |
| `project/tabs/EditorTab.tsx` | **Rewrite** | Replace chapter-based editor with doc list → editor view |
| `project/tabRegistry.ts` | **Edit** | Remove traceability and history tab entries |
| `project/ProjectWorkspace.tsx` | **Edit** | Remove lazy imports for TraceabilityTab, HistoryTab |
| `project/tabs/TraceabilityTab.tsx` | **Delete** | No longer needed |
| `project/tabs/HistoryTab.tsx` | **Delete** | No longer needed |

### Data Flow

```
EditorTab
  ├── No doc selected → ProjectDocListPanel
  │   ├── useDocuments({ project_scope: projectId, q, skip, limit })
  │   ├── Renders DocCard / FileRefCard grid
  │   └── onSelectDoc(doc) → setSelectedDoc(doc)
  │
  └── Doc selected → DocCollabView
      ├── CollabEditor({ documentId: doc.id, projectId })
      │   └── BlockNoteEditor → Yjs + Hocuspocus
      ├── Traceability sidebar (inline, reading content sources)
      └── VersionPanel sidebar (useVersions hook)
```

### Backend

No backend changes needed. All APIs already exist:
- `GET /api/extensions/documents?project_scope={projectId}` — document list with search/pagination
- Collab document CRUD — via existing collab_routers
- Version history — via existing collab version endpoints
- Source traceability — via existing content_sources endpoints

## Design Decisions

1. **Why extract components instead of importing DocumentManagement?**
   DocumentManagement is a full-page shell (sidebar + list + editor). We only need the list portion, and embedding the whole page would create layout conflicts. Extracting the list panel keeps it composable.

2. **Why embed the editor instead of navigating to /docmgr?**
   User stays in the project context. The top-level project header, tab bar, and navigation remain visible. Going to /docmgr would lose the project context.

3. **Why remove tabs instead of redirecting?**
   Three tabs for one feature creates confusion. Users expect "文档编辑" to include editing + traceability + history. Removing the extra tabs simplifies the mental model.

4. **Why not keep the chapter outline?**
   Chapter outlines are dynamic and may not match the actual documents. The document list from the project's thread tasks is the source of truth for what documents exist.

## Testing

- Verify document list loads correctly filtered by project
- Verify clicking a document opens CollabEditor in-tab
- Verify back button returns to document list
- Verify traceability info displays in sidebar
- Verify version history loads and diff works
- Verify traceability and history tabs no longer appear
- Verify grid/list toggle and search work
- Verify pagination works for projects with many documents
