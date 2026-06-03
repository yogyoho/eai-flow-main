# Project Doc Tab Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the project detail "文档编辑" tab with a document list from the project's thread tasks, embedding CollabEditor with traceability + version history in-tab. Remove standalone "溯源" and "版本历史" tabs.

**Architecture:** Extract a `ProjectDocListPanel` from the existing `DocumentManagement` document list pattern. Create a `DocCollabView` wrapper for in-tab editing. EditorTab becomes a simple state-driven view switcher (list ↔ editor). Remove two tabs from the registry.

**Tech Stack:** React 19, TypeScript, Next.js 16, TanStack Query, CollabEditor (BlockNote + Yjs), useDocuments hook

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/src/extensions/docmgr/ProjectDocListPanel.tsx` | Create | Document list panel scoped to a single project |
| `frontend/src/extensions/project/tabs/DocCollabView.tsx` | Create | In-tab collab editor with sidebars |
| `frontend/src/extensions/project/tabs/EditorTab.tsx` | Rewrite | State-driven list ↔ editor switcher |
| `frontend/src/extensions/project/tabRegistry.ts` | Edit | Remove `traceability` and `history` entries |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | Edit | Remove lazy imports for deleted tabs, remove rendering branches |
| `frontend/src/extensions/project/tabs/TraceabilityTab.tsx` | Delete | Functionality moved into DocCollabView |
| `frontend/src/extensions/project/tabs/HistoryTab.tsx` | Delete | Functionality moved into DocCollabView |

---

### Task 1: Create `ProjectDocListPanel` component

**Files:**
- Create: `frontend/src/extensions/docmgr/ProjectDocListPanel.tsx`

This component reuses the `useDocuments` hook and card rendering patterns from `DocumentManagement.tsx`. It shows all documents for a given project (file refs + AI-generated docs), with search, grid/list toggle, and pagination.

- [ ] **Step 1: Create the component file**

```tsx
// frontend/src/extensions/docmgr/ProjectDocListPanel.tsx
"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import {
  Archive,
  FileText,
  Grid3X3,
  List,
  Plus,
  Search,
  Star,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { useDocuments } from "./useDocuments";
import type { AIDocument } from "../types";

export interface ProjectDocListPanelProps {
  projectId: string;
  projectName: string;
  onSelectDoc: (doc: AIDocument) => void;
}

export function ProjectDocListPanel({ projectId, projectName, onSelectDoc }: ProjectDocListPanelProps) {
  const {
    docs, total, loading, page, pageSize, setPage,
    setFilter, toggleStar, deleteDoc,
  } = useDocuments({ project_scope: "project", folder: projectName });

  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const debouncedSearch = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync search to filter with debounce
  const handleSearch = (v: string) => {
    setSearch(v);
    if (debouncedSearch.current) clearTimeout(debouncedSearch.current);
    debouncedSearch.current = setTimeout(
      () => setFilter((f) => ({ ...f, q: v || undefined })),
      400,
    );
  };

  const totalPages = Math.ceil(total / pageSize);

  const formatDate = (d: string | null) => {
    if (!d) return "-";
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(d));
  };

  const formatSize = (bytes: number | null | undefined) => {
    if (!bytes) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const FILE_ICONS: Record<string, string> = {
    md: "📝", py: "🐍", js: "📜", ts: "📘", json: "📋", pdf: "📕",
    docx: "📘", xlsx: "📊", csv: "📊", txt: "📄", html: "🌐", css: "🎨",
  };
  const fileIcon = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() ?? "";
    return FILE_ICONS[ext] ?? "📄";
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header: search + view toggle */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="搜索文档..."
            className="h-8 rounded-md border-border bg-background pl-8 text-xs"
          />
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{total} 个文档</span>
        <div className="flex h-7 items-center overflow-hidden rounded border border-border">
          <button onClick={() => setViewMode("grid")} className={cn("flex h-7 w-7 items-center justify-center", viewMode === "grid" ? "bg-muted text-foreground" : "text-muted-foreground")}>
            <Grid3X3 className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setViewMode("list")} className={cn("flex h-7 w-7 items-center justify-center", viewMode === "list" ? "bg-muted text-foreground" : "text-muted-foreground")}>
            <List className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading && docs.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">加载中...</div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Archive className="mb-2 h-8 w-8" />
            <p className="text-sm">暂无文档</p>
            <p className="text-xs">AI 任务生成的文档和文件将显示在这里</p>
          </div>
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {docs.map((doc) => (
              <button
                key={doc.id}
                type="button"
                onClick={() => onSelectDoc(doc)}
                className="flex flex-col items-start rounded-lg border border-border bg-background p-3 text-left transition-all hover:border-primary/30 hover:shadow-sm"
              >
                <span className="text-xl mb-1">{doc.doc_type === "file_ref" ? fileIcon(doc.title) : "📝"}</span>
                <p className="line-clamp-2 text-sm font-medium text-foreground">{doc.title}</p>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                  {doc.doc_type === "file_ref" && doc.file_size != null && (
                    <span>{formatSize(doc.file_size)}</span>
                  )}
                  <span>{formatDate(doc.updated_at)}</span>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-2 text-left font-medium">名称</th>
                <th className="py-2 text-left font-medium">类型</th>
                <th className="py-2 text-left font-medium">大小</th>
                <th className="py-2 text-left font-medium">更新时间</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr
                  key={doc.id}
                  onClick={() => onSelectDoc(doc)}
                  className="cursor-pointer border-b border-border/50 transition-colors hover:bg-muted/50"
                >
                  <td className="py-2 flex items-center gap-2">
                    <span>{doc.doc_type === "file_ref" ? fileIcon(doc.title) : "📝"}</span>
                    <span className="truncate max-w-[200px]">{doc.title}</span>
                  </td>
                  <td className="py-2 text-muted-foreground">{doc.doc_type === "file_ref" ? "文件" : "文档"}</td>
                  <td className="py-2 text-muted-foreground">{doc.doc_type === "file_ref" ? formatSize(doc.file_size) : "-"}</td>
                  <td className="py-2 text-muted-foreground">{formatDate(doc.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border px-4 py-2">
          <span className="text-xs text-muted-foreground">
            第 {page} / {totalPages} 页
          </span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)} className="h-7 text-xs">
              上一页
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="h-7 text-xs">
              下一页
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep ProjectDocListPanel`
Expected: No errors for ProjectDocListPanel

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/ProjectDocListPanel.tsx
git commit -m "feat(docmgr): extract ProjectDocListPanel component"
```

---

### Task 2: Create `DocCollabView` component

**Files:**
- Create: `frontend/src/extensions/project/tabs/DocCollabView.tsx`

This component wraps CollabEditor with a top bar (back button + title) and sidebar toggles for version history and traceability.

- [ ] **Step 1: Create the component file**

```tsx
// frontend/src/extensions/project/tabs/DocCollabView.tsx
"use client";

import { ArrowLeft, History, Link2, X } from "lucide-react";
import { useState, useCallback } from "react";

import { cn } from "@/lib/utils";
import { CollabEditor } from "@/extensions/collab/CollabEditor";
import { VersionPanel } from "@/extensions/collab/VersionPanel";
import { useVersions } from "@/extensions/collab/useVersions";
import type { AIDocument } from "@/extensions/types";

export interface DocCollabViewProps {
  doc: AIDocument;
  projectId: string;
  onBack: () => void;
}

type Sidebar = "none" | "versions" | "traceability";

export function DocCollabView({ doc, projectId, onBack }: DocCollabViewProps) {
  const [sidebar, setSidebar] = useState<Sidebar>("none");
  const {
    versions, loading: versionsLoading,
    createVersion, restoreVersion,
    diffResult, diffLoading, diffVersions, reload: reloadVersions,
  } = useVersions(doc.id);

  const toggleSidebar = useCallback((target: Sidebar) => {
    setSidebar((prev) => (prev === target ? "none" : target));
  }, []);

  const handleCloseSidebar = useCallback(() => setSidebar("none"), []);

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <button
          type="button"
          onClick={onBack}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{doc.title}</span>
        <button
          type="button"
          onClick={() => toggleSidebar("traceability")}
          className={cn(
            "flex h-7 items-center gap-1 rounded-md px-2 text-xs transition-colors",
            sidebar === "traceability" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted",
          )}
        >
          <Link2 className="h-3.5 w-3.5" />
          溯源
        </button>
        <button
          type="button"
          onClick={() => toggleSidebar("versions")}
          className={cn(
            "flex h-7 items-center gap-1 rounded-md px-2 text-xs transition-colors",
            sidebar === "versions" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted",
          )}
        >
          <History className="h-3.5 w-3.5" />
          版本历史
        </button>
      </div>

      {/* Main content + sidebar */}
      <div className="flex flex-1 min-h-0">
        {/* Editor */}
        <div className="flex-1 min-w-0">
          <CollabEditor
            documentId={doc.id}
            initialContent={doc.content ?? ""}
            projectId={projectId}
          />
        </div>

        {/* Sidebar panel */}
        {sidebar !== "none" && (
          <div className="w-[320px] shrink-0 border-l border-border bg-background overflow-y-auto">
            {sidebar === "versions" && (
              <VersionPanel
                versions={versions}
                loading={versionsLoading}
                diffLoading={diffLoading}
                diffResult={diffResult}
                onCreateVersion={async (summary, aiSummary, content) => {
                  await createVersion(summary, aiSummary, content);
                }}
                onRestoreVersion={restoreVersion}
                onPreviewVersion={async (v) => { await diffVersions(v); }}
                onDiffVersions={diffVersions}
                onClose={handleCloseSidebar}
              />
            )}
            {sidebar === "traceability" && (
              <div className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-foreground">溯源信息</h3>
                  <button type="button" onClick={handleCloseSidebar} className="text-muted-foreground hover:text-foreground">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">
                    溯源面板在编辑器内通过行内标记（source markers）展示内容来源。编辑文档时，包含溯源标记的段落会显示来源标注。
                  </p>
                </div>
                <div className="mt-3 space-y-2">
                  <div className="text-xs text-muted-foreground">文档信息</div>
                  <div className="text-xs">
                    <span className="text-muted-foreground">ID: </span>
                    <span className="font-mono text-foreground">{doc.id.slice(0, 8)}...</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-muted-foreground">类型: </span>
                    <span className="text-foreground">{doc.doc_type === "file_ref" ? "文件引用" : "文档"}</span>
                  </div>
                  {doc.source_thread_id && (
                    <div className="text-xs">
                      <span className="text-muted-foreground">来源线程: </span>
                      <span className="font-mono text-foreground">{doc.source_thread_id.slice(0, 8)}...</span>
                    </div>
                  )}
                  <div className="text-xs">
                    <span className="text-muted-foreground">创建时间: </span>
                    <span className="text-foreground">{doc.created_at ? new Date(doc.created_at).toLocaleString("zh-CN") : "-"}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-muted-foreground">更新时间: </span>
                    <span className="text-foreground">{doc.updated_at ? new Date(doc.updated_at).toLocaleString("zh-CN") : "-"}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep DocCollabView`
Expected: No errors for DocCollabView

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/tabs/DocCollabView.tsx
git commit -m "feat(project): create DocCollabView with version history + traceability sidebars"
```

---

### Task 3: Rewrite `EditorTab` as state-driven view switcher

**Files:**
- Modify: `frontend/src/extensions/project/tabs/EditorTab.tsx`

Replace the entire chapter-outline-based content with a simple two-state component: document list (default) or document editor (when a doc is selected).

- [ ] **Step 1: Rewrite EditorTab.tsx**

```tsx
// frontend/src/extensions/project/tabs/EditorTab.tsx
"use client";

import { useState } from "react";

import type { AIDocument } from "@/extensions/types";
import type { ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { ProjectDocListPanel } from "@/extensions/docmgr/ProjectDocListPanel";
import { DocCollabView } from "./DocCollabView";

export interface EditorTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  visibleChapterIds?: string[];
}

export function EditorTab({ project, projectId }: EditorTabProps) {
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

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep EditorTab`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/tabs/EditorTab.tsx
git commit -m "feat(project): rewrite EditorTab with doc list + in-tab editor"
```

---

### Task 4: Remove `traceability` and `history` tabs from registry

**Files:**
- Modify: `frontend/src/extensions/project/tabRegistry.ts`
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`
- Delete: `frontend/src/extensions/project/tabs/TraceabilityTab.tsx`
- Delete: `frontend/src/extensions/project/tabs/HistoryTab.tsx`

- [ ] **Step 1: Edit `tabRegistry.ts` — remove the two tab entries**

Find and remove the entries with `id: "traceability"` and `id: "history"` from the `TAB_REGISTRY` array. The remaining tabs should be: `overview`, `workflow`, `editor`, `review`, `settings`.

- [ ] **Step 2: Edit `ProjectWorkspace.tsx` — remove lazy imports and render branches**

Remove these two dynamic import lines:
```tsx
const TraceabilityTab = dynamic(() => import("./tabs/TraceabilityTab").then((m) => ({ default: m.TraceabilityTab })), { ssr: false });
const HistoryTab = dynamic(() => import("./tabs/HistoryTab").then((m) => ({ default: m.HistoryTab })), { ssr: false });
```

Remove these two render branches in the tab content section:
```tsx
) : activeTab === "traceability" ? (
  <TraceabilityTab {...tabProps} />
) : activeTab === "history" ? (
  <HistoryTab {...tabProps} />
```

- [ ] **Step 3: Delete the two tab files**

```bash
rm frontend/src/extensions/project/tabs/TraceabilityTab.tsx
rm frontend/src/extensions/project/tabs/HistoryTab.tsx
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -i "TraceabilityTab\|HistoryTab\|tabRegistry"`
Expected: No errors referencing the deleted files

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/extensions/project/
git commit -m "refactor(project): remove standalone traceability and history tabs"
```

---

### Task 5: Manual verification in browser

- [ ] **Step 1: Restart frontend container**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 2: Open project detail page**

Navigate to `/projects` → click any project card.

- [ ] **Step 3: Verify tab bar**

Confirm that only these tabs appear: 项目概览, 流程看板, 文档编辑, 审核工作台, 项目设置. The "溯源" and "版本历史" tabs should be gone.

- [ ] **Step 4: Click "文档编辑" tab**

Verify the document list loads showing project documents (grid view with search bar and view toggle).

- [ ] **Step 5: Click a document card**

Verify the CollabEditor loads in-tab with a back button and document title.

- [ ] **Step 6: Click "版本历史" button in editor toolbar**

Verify the version history sidebar opens and loads versions.

- [ ] **Step 7: Click "溯源" button in editor toolbar**

Verify the traceability sidebar opens with document metadata.

- [ ] **Step 8: Click back arrow**

Verify it returns to the document list.

- [ ] **Step 9: Commit verification**

```bash
git commit --allow-empty -m "verify: project doc tab unification works in browser"
```
