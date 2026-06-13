# Remove Chapter Editing Sub-tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant "章节编辑" sub-tab from EditorTab.tsx, keeping only the "文档文件" file list view and DocCollabView editor.

**Architecture:** Single-file refactor. EditorTab currently has two modes (`chapters` / `files`) selected by a toggle bar. After this change, the "files" mode becomes the sole default view. The sessionStorage bridge from Overview → Editor (for opening chapter documents) continues to work unchanged since it bypasses the list view entirely and goes straight to DocCollabView.

**Tech Stack:** TypeScript, React 19, Tailwind CSS 4

---

### Task 1: Simplify EditorTab — remove chapter sub-tab

**Files:**
- Modify: `frontend/src/extensions/project/tabs/EditorTab.tsx`

- [ ] **Step 1: Remove unused imports and constants**

Replace the import block at lines 1-18 and the constants at lines 28-40 with the stripped-down version.

**Remove these imports:**
- `CheckCheck` (line 3) — only used in chapter complete button
- `Edit3` (line 3) — only used in chapter toggle buttons
- `FileText` (line 3) — only used in chapter empty state
- `User` (line 3) — only used in chapter assigned person display
- `Badge` (line 6) — only used in chapter status badges

**Keep these imports** (remove unused ones only):
```typescript
import { Files, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";

import type { AIDocument } from "@/extensions/types";

import ProjectDocListPanel from "../../docmgr/ProjectDocListPanel";
import { projectApi } from "@/extensions/project/api";
import type { ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { flattenChapters } from "@/extensions/project/utils";
import { DocCollabView } from "./DocCollabView";
```

Wait — verify what's still needed:
- `Files` — keep for header icon
- `Loader2` — keep (used in `openingId` logic if needed, but let's check... `openingId` is used in `handleEditChapter` which we're removing... but it's also used in the files view for selecting a doc. Let me re-check.)

Actually, let me re-read the code. `openingId` is set in `handleEditChapter` (lines 67-79), which is being removed. It's NOT used in ProjectDocListPanel (that takes `onSelectDoc` directly). Let me verify...

Looking at the code:
- `openingId` is only set in `handleEditChapter` (chapters mode) — line 68
- `openingId` is only read in `handleEditChapter` to set loading state — line 203
- `completingId` is only set/read in `handleMarkComplete` (chapters mode) — lines 83-95

Both `openingId` and `completingId` are only used in the chapters mode. Remove both.

Also check `flattenChapters` — used in line 49 for `flatChapters` which is only consumed in the chapters mode (line 187). So it can be removed.

And `toast` — only used in `handleEditChapter` and `handleMarkComplete`. After removing those, is toast used anywhere? In the files mode... no, `onSelectDoc` is just a setter. So `toast` can be removed too.

And `ScrollArea` — used in the chapters mode only (line 191). Is it needed in files mode? The files mode is just `ProjectDocListPanel` inside a `div`. So `ScrollArea` can be removed.

And `Button` — used in the toggle bar. After simplification, the toggle bar becomes a simple header. If we keep a simple header with just a label, we might not need Button. Let me think... we should keep a minimal header for context. We can use a simple `<div>` with text instead of buttons.

OK let me finalize the import list. The minimal EditorTab needs:
- `useCallback, useEffect, useState` from react
- `AIDocument` type
- `ProjectDocListPanel`
- `ReportProject` type
- `ProjectIdentity` type
- `DocCollabView`

But we also need `Files` icon for the header label, and maybe `Button` for the back button (though the back button is in DocCollabView). Let me keep it simple: just `Files` for the header icon.

Actually wait — there's no back button in the file list view. The back button is inside DocCollabView. So the file list view just needs ProjectDocListPanel. And a minimal header.

Let me just write the actual new file content in the plan. That's cleaner.

- [ ] **Step 1: Replace file content**

Replace `frontend/src/extensions/project/tabs/EditorTab.tsx` with:

```typescript
"use client";

import { Files } from "lucide-react";
import { useEffect, useState } from "react";

import type { AIDocument } from "@/extensions/types";

import ProjectDocListPanel from "../../docmgr/ProjectDocListPanel";
import type { ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { DocCollabView } from "./DocCollabView";

interface EditorTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  visibleChapterIds?: string[];
}

export function EditorTab({ projectId, onRefresh }: EditorTabProps) {
  const [selectedDoc, setSelectedDoc] = useState<AIDocument | null>(null);

  // Check for chapter doc passed from Overview tab via sessionStorage
  useEffect(() => {
    const stored = sessionStorage.getItem("openChapterDoc");
    if (stored) {
      try {
        const doc = JSON.parse(stored) as AIDocument;
        sessionStorage.removeItem("openChapterDoc");
        setSelectedDoc(doc);
      } catch {
        // invalid JSON, ignore
      }
    }
  }, []);

  // ── DocCollabView mode ──
  if (selectedDoc) {
    return (
      <DocCollabView
        doc={selectedDoc}
        projectId={projectId}
        onBack={() => {
          setSelectedDoc(null);
          onRefresh();
        }}
      />
    );
  }

  // ── File list (default view) ──
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border shrink-0">
        <Files className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-foreground">文档文件</span>
      </div>
      <div className="flex-1">
        <ProjectDocListPanel projectId={projectId} onSelectDoc={setSelectedDoc} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && pnpm typecheck
```

Expected: PASS (no type errors)

- [ ] **Step 3: Run lint**

```bash
cd frontend && pnpm lint
```

Expected: PASS (no lint errors)

- [ ] **Step 4: Run unit tests**

```bash
cd frontend && pnpm test
```

Expected: All tests pass. If `tabRegistry.test.ts` references the chapter mode, update that test.

- [ ] **Step 5: Check for test file that references chapter mode**

Read `frontend/tests/unit/project/tabRegistry.test.ts` — if it tests the chapter/files mode toggle, update or remove that test case.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/project/tabs/EditorTab.tsx
git commit -m "refactor: remove redundant chapter editing sub-tab from EditorTab

Chapter management is fully handled by OverviewTab's 章节进度 section.
The chapter editing sub-tab was a near-duplicate with identical UI and
logic. EditorTab is now a single-purpose document file list + editor view."
```

---

### Self-Review Checklist

- [x] Spec coverage: The single requirement ("Editor tab shows only the file list") maps to Step 1
- [x] Placeholder scan: No TBD/TODO/vague instructions
- [x] Type consistency: Props interface kept compatible (unused props `project`, `identity`, `visibleChapterIds` stay in the destructured signature for backward compatibility with callers)
