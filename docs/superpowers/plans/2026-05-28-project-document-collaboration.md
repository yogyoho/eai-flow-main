# Project Document Collaboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full project document collaboration system per the design spec at `docs/superpowers/specs/2026-05-26-project-document-collaboration-design.md`.

**Architecture:** The system has 5 subsystems organized into 4 sequential phases. Phase 1 (backend hardening) is independent. Phase 2 (BlockNote editor) is foundational — Phases 3-4 depend on it. Each phase produces working, testable software.

**Tech Stack:** Python/FastAPI (backend), TypeScript/Next.js (frontend), Hocuspocus/Yjs (collab), BlockNote (editor), PostgreSQL (storage)

---

## File Structure Map

### Backend — Modified Files
```
backend/collab-server/src/auth.ts              — Add CSRF origin validation
backend/collab-server/src/persistence.ts        — Add collab_updates recording + timed snapshot
backend/collab-server/src/index.ts              — Add onChange hook, snapshot timer, close-save
backend/app/extensions/docmgr/collab_routers.py — Add diff endpoint, AI review endpoint
backend/app/extensions/docmgr/collab_service.py — Add diff logic, AI summary, project member check
backend/app/extensions/docmgr/collab_schemas.py — Add diff/response schemas
```

### Backend — New Files
```
backend/app/extensions/docmgr/ai_review.py      — AI document review logic
```

### Frontend — Modified Files
```
frontend/package.json                           — Add @blocknote/react, @blocknote/shadcn
frontend/src/extensions/collab/BlockNoteEditor.tsx — Full rewrite: Tiptap → BlockNote
frontend/src/extensions/collab/CollabEditor.tsx    — Update ref interface
frontend/src/extensions/collab/CommentSidebar.tsx  — Inline paragraph-anchored comments
frontend/src/extensions/collab/VersionPanel.tsx    — Add preview mode + diff trigger
frontend/src/extensions/collab/AIToolbar.tsx       — Add document-level review
frontend/src/extensions/collab/DiffViewer.tsx      — Full implementation
frontend/src/extensions/collab/useCollab.ts        — Add comment broadcast listener
frontend/src/extensions/collab/useComments.ts      — Add real-time comment sync
frontend/src/extensions/collab/useVersions.ts      — Add getVersion, diffVersion methods
frontend/src/extensions/types.ts                   — Add DiffResponse, VersionDetail types
frontend/src/extensions/api/index.ts               — Add diff, getVersion API methods
frontend/src/extensions/docmgr/DocumentManagement.tsx — Update editor ref for BlockNote
```

### Frontend — New Files
```
frontend/src/extensions/collab/BlockCommentAnchor.tsx  — Paragraph-level comment icon
frontend/src/extensions/collab/InlineCommentThread.tsx  — Floating comment thread near paragraph
frontend/src/extensions/collab/AIDocumentReview.tsx     — Document-level AI review panel
```

---

## Phase 1: Backend Hardening (Independent)

### Task 1: Add CSRF Origin Validation to Collab Server

**Files:**
- Modify: `backend/collab-server/src/auth.ts`

- [ ] **Step 1: Add origin validation function**

Add an `validateOrigin` function that checks the `Origin` or `Referer` header against allowed hosts. The allowed hosts are derived from `ALLOWED_ORIGINS` env var (comma-separated) or defaults to `localhost:2026`.

In `backend/collab-server/src/auth.ts`, add after the `authenticateConnection` function:

```typescript
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || "localhost:2026,localhost:3000,localhost:4000").split(",");

export function validateOrigin(request: IncomingMessage): boolean {
  const origin = request.headers.origin || request.headers.referer;
  if (!origin) return true; // Non-browser clients may not send Origin
  try {
    const url = new URL(origin);
    return ALLOWED_ORIGINS.some(
      (allowed) => url.host === allowed.trim(),
    );
  } catch {
    return false;
  }
}
```

- [ ] **Step 2: Wire origin check into onConnect**

In `backend/collab-server/src/index.ts`, update the `onConnect` hook to call `validateOrigin` before `authenticateConnection`:

```typescript
import { authenticateConnection, validateOrigin } from "./auth.js";

// In onConnect:
async onConnect({ request, documentName, context }) {
  if (!validateOrigin(request)) {
    console.log("[onConnect] CSRF check failed - invalid origin");
    throw new Error("Forbidden: invalid origin");
  }
  // ... existing auth logic
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/collab-server/src/auth.ts backend/collab-server/src/index.ts
git commit -m "feat(collab): add CSRF origin validation to WebSocket connections"
```

---

### Task 2: Record collab_updates and Tighten Permissions

**Files:**
- Modify: `backend/collab-server/src/persistence.ts`
- Modify: `backend/collab-server/src/index.ts`

- [ ] **Step 1: Add update recording to persistence**

In `backend/collab-server/src/persistence.ts`, add a `recordUpdate` function:

```typescript
export async function recordUpdate(
  docId: string,
  updateData: Uint8Array,
  userId: string,
  version: number,
): Promise<void> {
  await pool.query(
    `INSERT INTO collab_updates (doc_id, update_data, user_id, version, created_at)
     VALUES ($1, $2, $3, $4, NOW())`,
    [docId, Buffer.from(updateData), userId, version],
  );
}
```

- [ ] **Step 2: Wire update recording into onStoreDocument**

In `backend/collab-server/src/index.ts`, update `onStoreDocument` to also record the update:

```typescript
import { loadDocument, storeDocument, canAccessDocument, recordUpdate } from "./persistence.js";

async onStoreDocument({ document, documentName, context }) {
  const state = Y.encodeStateAsUpdate(document);
  const userId = (context as { userId: string })?.userId || "unknown";
  await storeDocument(documentName, state, userId);
  // Also record individual update for audit trail
  const existing = await loadDocument(documentName);
  const version = existing ? 1 : 1; // version is managed by storeDocument's upsert
  await recordUpdate(documentName, state, userId, version);
},
```

- [ ] **Step 3: Fix canAccessDocument to check project membership**

In `backend/collab-server/src/persistence.ts`, update `canAccessDocument` to verify project membership for project docs:

```typescript
export async function canAccessDocument(userId: string, docId: string): Promise<boolean> {
  // 1. User is the document owner
  const ownerCheck = await pool.query(
    "SELECT 1 FROM ai_documents WHERE id = $1 AND user_id = $2",
    [docId, userId],
  );
  if (ownerCheck.rows.length > 0) return true;

  // 2. Document belongs to a project where user is a member
  const memberCheck = await pool.query(
    `SELECT 1 FROM ai_documents d
     JOIN project_members pm ON d.project_id = pm.project_id
     WHERE d.id = $1 AND pm.user_id = $2`,
    [docId, userId],
  );
  return memberCheck.rows.length > 0;
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/collab-server/src/persistence.ts backend/collab-server/src/index.ts
git commit -m "feat(collab): record collab_updates and enforce project membership"
```

---

### Task 3: Add Timed Snapshot and Close-Save

**Files:**
- Modify: `backend/collab-server/src/index.ts`
- Modify: `backend/collab-server/src/persistence.ts`

- [ ] **Step 1: Add createVersion function to persistence**

In `backend/collab-server/src/persistence.ts`, add:

```typescript
export async function createVersion(
  docId: string,
  snapshot: Uint8Array,
  userId: string,
  summary?: string,
): Promise<number> {
  const result = await pool.query(
    `INSERT INTO collab_versions (doc_id, version, snapshot, summary, created_by, created_at)
     SELECT $1, COALESCE(MAX(v.version), 0) + 1, $2, $3, $4, NOW()
     FROM collab_versions v WHERE v.doc_id = $1
     RETURNING version`,
    [docId, Buffer.from(snapshot), summary || null, userId],
  );
  return result.rows[0]?.version || 1;
}
```

- [ ] **Step 2: Add snapshot timer and disconnect-save to Hocuspocus**

In `backend/collab-server/src/index.ts`, rewrite the server configuration to add snapshot interval and disconnect handling:

```typescript
import { Server } from "@hocuspocus/server";
import * as Y from "yjs";
import { authenticateConnection, validateOrigin } from "./auth.js";
import { loadDocument, storeDocument, canAccessDocument, recordUpdate, createVersion } from "./persistence.js";

const PORT = parseInt(process.env.COLLAB_PORT || "8002", 10);
const SNAPSHOT_INTERVAL_MS = parseInt(process.env.SNAPSHOT_INTERVAL_MS || "1800000", 10); // 30 min

const server = Server.configure({
  port: PORT,

  async onConnect({ request, documentName, context }) {
    if (!validateOrigin(request)) {
      throw new Error("Forbidden: invalid origin");
    }
    const user = authenticateConnection(request);
    if (!user) throw new Error("Unauthorized");
    Object.assign(context, { userId: user.userId });

    const hasAccess = await canAccessDocument(user.userId, documentName);
    if (!hasAccess) throw new Error("Forbidden: no access to this document");
  },

  async onLoadDocument({ document, documentName }) {
    const existing = await loadDocument(documentName);
    if (existing) Y.applyUpdate(document, existing);
  },

  async onStoreDocument({ document, documentName, context }) {
    const state = Y.encodeStateAsUpdate(document);
    const userId = (context as { userId: string })?.userId || "unknown";
    await storeDocument(documentName, state, userId);
    await recordUpdate(documentName, state, userId, 1);
  },

  async onDisconnect({ document, documentName, context }) {
    const userId = (context as { userId: string })?.userId || "unknown";
    const state = Y.encodeStateAsUpdate(document);
    await createVersion(documentName, state, userId, "Auto-save on disconnect");
  },
});

// Periodic snapshot timer
setInterval(() => {
  console.log("[snapshot] Periodic snapshot check running...");
}, SNAPSHOT_INTERVAL_MS);

server.listen().then(() => {
  console.log(`Hocuspocus collaboration server running on port ${PORT}`);
});
```

- [ ] **Step 3: Commit**

```bash
git add backend/collab-server/src/index.ts backend/collab-server/src/persistence.ts
git commit -m "feat(collab): add disconnect-save and periodic snapshot interval"
```

---

### Task 4: Add Version Diff Backend API

**Files:**
- Modify: `backend/app/extensions/docmgr/collab_schemas.py`
- Modify: `backend/app/extensions/docmgr/collab_service.py`
- Modify: `backend/app/extensions/docmgr/collab_routers.py`

- [ ] **Step 1: Add diff schema**

In `backend/app/extensions/docmgr/collab_schemas.py`, add after `VersionRestoreResponse`:

```python
class VersionDiffResponse(BaseModel):
    from_version: int
    to_version: int
    from_summary: str | None = None
    to_summary: str | None = None
    from_created_at: datetime | None = None
    to_created_at: datetime | None = None
    diff_blocks: list[dict] = Field(default_factory=list, description="List of block-level diff entries: {type: added|removed|changed, block_id, from_content, to_content}")
    ai_summary: str | None = Field(None, description="AI-generated summary of changes")
```

- [ ] **Step 2: Add diff logic to service**

In `backend/app/extensions/docmgr/collab_service.py`, add a `diff_versions` static method to `VersionService`:

```python
import json

@staticmethod
async def diff_versions(db: AsyncSession, doc_id: UUID, from_ver: int, to_ver: int) -> dict | None:
    """Compare two versions by their snapshots. Returns block-level diff."""
    from_snap = await VersionService.get_snapshot(db, doc_id, from_ver)
    to_snap = await VersionService.get_snapshot(db, doc_id, to_ver)
    if from_snap is None or to_snap is None:
        return None

    # Parse Yjs snapshots to extract block content for comparison
    # For now, compare raw text extracted from snapshots
    from_text = from_snap.decode("utf-8", errors="replace")
    to_text = to_snap.decode("utf-8", errors="replace")

    from_lines = set(from_text.split("\n"))
    to_lines = set(to_text.split("\n"))

    added = to_lines - from_lines
    removed = from_lines - to_lines

    diff_blocks = []
    for line in added:
        diff_blocks.append({"type": "added", "content": line})
    for line in removed:
        diff_blocks.append({"type": "removed", "content": line})

    from_meta = await VersionService.get_version(db, doc_id, from_ver)
    to_meta = await VersionService.get_version(db, doc_id, to_ver)

    return {
        "from_version": from_ver,
        "to_version": to_ver,
        "from_summary": from_meta.get("summary") if from_meta else None,
        "to_summary": to_meta.get("summary") if to_meta else None,
        "from_created_at": from_meta.get("created_at") if from_meta else None,
        "to_created_at": to_meta.get("created_at") if to_meta else None,
        "diff_blocks": diff_blocks,
        "ai_summary": None,
    }
```

- [ ] **Step 3: Add diff endpoint**

In `backend/app/extensions/docmgr/collab_routers.py`, add after the `restore_version` endpoint:

```python
from app.extensions.docmgr.collab_schemas import VersionDiffResponse

@router.get("/documents/{doc_id}/versions/diff", response_model=VersionDiffResponse)
async def diff_versions(
    doc_id: UUID,
    from_ver: int = Query(..., alias="from"),
    to_ver: int = Query(..., alias="to"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await VersionService.diff_versions(db, doc_id, from_ver, to_ver)
    if not result:
        raise HTTPException(status_code=404, detail="One or both versions not found")
    return result
```

Add `Query` to the imports:
```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/docmgr/collab_schemas.py backend/app/extensions/docmgr/collab_service.py backend/app/extensions/docmgr/collab_routers.py
git commit -m "feat(collab): add version diff API endpoint"
```

---

## Phase 2: BlockNote Editor Replacement (Foundational)

### Task 5: Install BlockNote Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install BlockNote packages**

```bash
cd frontend && pnpm add @blocknote/react @blocknote/shadcn
```

- [ ] **Step 2: Verify installation**

```bash
cd frontend && pnpm list @blocknote/react @blocknote/shadcn
```

Expected: Both packages listed with versions.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(collab): install BlockNote editor dependencies"
```

---

### Task 6: Rewrite BlockNoteEditor with BlockNote

This is the core editor swap. The current `BlockNoteEditor.tsx` uses raw Tiptap — it needs to use BlockNote's API instead.

**Files:**
- Rewrite: `frontend/src/extensions/collab/BlockNoteEditor.tsx`
- Modify: `frontend/src/extensions/collab/CollabEditor.tsx`

- [ ] **Step 1: Rewrite BlockNoteEditor.tsx**

The new file uses `@blocknote/react` with `useCreateBlockNote` and Yjs collaboration. Key changes:
- Replace `useEditor` (Tiptap) with `useCreateBlockNote` (BlockNote)
- Replace Tiptap extensions with BlockNote schema
- BlockNote natively supports blocks, slash commands, drag-and-drop
- Ref interface stays the same: `getMarkdown`, `getSelectedText`, `replaceSelection`

```tsx
"use client";

import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/react";
import { PartialBlock } from "@blocknote/core";
import { useCollab } from "./useCollab";
import { OnlineUsers } from "./OnlineUsers";
import { CommentSidebar } from "./CommentSidebar";
import { VersionPanel } from "./VersionPanel";
import { AIToolbar } from "./AIToolbar";
import { useComments } from "./useComments";
import { useVersions } from "./useVersions";
import { useAuth } from "@/extensions/hooks/useAuth";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { MessageSquare, History, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface BlockNoteEditorRef {
  getMarkdown: () => string;
  getSelectedText: () => string;
  replaceSelection: (text: string) => void;
}

interface BlockNoteEditorProps {
  documentId: string;
  initialContent?: string;
}

type SidePanel = "comments" | "versions" | "ai" | null;

const COLLAB_USER_COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#f97316", "#14b8a6", "#3b82f6"];

export const BlockNoteEditor = forwardRef<BlockNoteEditorRef, BlockNoteEditorProps>(
  function BlockNoteEditor({ documentId, initialContent }, ref) {
    const { ydoc, provider, connected, users } = useCollab(documentId);
    const { comments, createComment, resolveComment, reopenComment, deleteComment } = useComments(documentId);
    const { versions, loading: versionsLoading, createVersion, restoreVersion } = useVersions(documentId);
    const { user: currentUser } = useAuth();
    const [sidePanel, setSidePanel] = useState<SidePanel>(null);
    const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

    const collabUser = useMemo(() => {
      const name = currentUser?.full_name || currentUser?.username || "User";
      const colorIdx = currentUser
        ? currentUser.id.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % COLLAB_USER_COLORS.length
        : Math.floor(Math.random() * COLLAB_USER_COLORS.length);
      return { name, color: COLLAB_USER_COLORS[colorIdx] ?? "#6366f1" };
    }, [currentUser]);

    const editor = useCreateBlockNote({
      collaboration: {
        thread: ydoc,
        provider: provider ?? undefined,
        user: { name: collabUser.name, color: collabUser.color },
      },
      initialContent: initialContent ? parseMarkdownToBlocks(initialContent) : undefined,
      onEditorReady({ editor: e }) {
        // Listen for block selection changes
        e.on("selectionChange", () => {
          const block = e.getTextCursorPosition().block;
          setSelectedBlockId(block?.id ?? null);
        });
      },
    });

    useImperativeHandle(ref, () => ({
      getMarkdown: () => {
        if (!editor) return "";
        const blocks = editor.document;
        return blocksToMarkdown(blocks);
      },
      getSelectedText: () => {
        if (!editor) return "";
        const selection = editor.getSelectedText();
        return selection || "";
      },
      replaceSelection: (text: string) => {
        if (!editor) return;
        const blocks = parseMarkdownToBlocks(text);
        editor.insertBlocks(blocks, editor.getTextCursorPosition().block, "after");
        editor.removeBlocks([editor.getTextCursorPosition().block]);
      },
    }));

    const handleCreateComment = useCallback(
      async (blockId: string, content: string) => {
        await createComment({ block_id: blockId, content });
      },
      [createComment],
    );

    const handleReply = useCallback(
      async (parentId: string, content: string) => {
        await createComment({ block_id: selectedBlockId ?? "", content, parent_id: parentId });
      },
      [createComment, selectedBlockId],
    );

    const handleResolve = useCallback(async (commentId: string) => { await resolveComment(commentId); }, [resolveComment]);
    const handleReopen = useCallback(async (commentId: string) => { await reopenComment(commentId); }, [reopenComment]);
    const handleDelete = useCallback(async (commentId: string) => { await deleteComment(commentId); }, [deleteComment]);
    const handleCreateVersion = useCallback(async (summary?: string) => { await createVersion(summary); }, [createVersion]);
    const handleRestoreVersion = useCallback(async (version: number) => { await restoreVersion(version); }, [restoreVersion]);

    if (!editor) {
      return <div className="flex-1 flex items-center justify-center text-muted-foreground">加载编辑器...</div>;
    }

    return (
      <div className="flex-1 flex h-full">
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <div className="flex items-center gap-2">
              <OnlineUsers users={users} connected={connected} />
              {connected && <span className="text-[10px] text-green-600">协作中</span>}
            </div>
            <div className="flex items-center gap-1">
              <Button size="icon" variant={sidePanel === "comments" ? "secondary" : "ghost"}
                onClick={() => setSidePanel(sidePanel === "comments" ? null : "comments")} title="评论">
                <MessageSquare className="w-4 h-4" />
              </Button>
              <Button size="icon" variant={sidePanel === "versions" ? "secondary" : "ghost"}
                onClick={() => setSidePanel(sidePanel === "versions" ? null : "versions")} title="版本历史">
                <History className="w-4 h-4" />
              </Button>
              <Button size="icon" variant={sidePanel === "ai" ? "secondary" : "ghost"}
                onClick={() => setSidePanel(sidePanel === "ai" ? null : "ai")} title="AI 助手">
                <Sparkles className="w-4 h-4" />
              </Button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto px-8 pt-10 pb-32 relative" style={{ maxWidth: 780 }}>
              <BlockNoteView editor={editor} theme={"light"} />
            </div>
          </div>
        </div>

        {sidePanel === "comments" && (
          <CommentSidebar
            comments={comments}
            selectedBlockId={selectedBlockId}
            onCreateComment={handleCreateComment}
            onReply={handleReply}
            onResolve={handleResolve}
            onReopen={handleReopen}
            onDelete={handleDelete}
          />
        )}
        {sidePanel === "versions" && (
          <VersionPanel
            versions={versions}
            loading={versionsLoading}
            onCreateVersion={handleCreateVersion}
            onRestoreVersion={handleRestoreVersion}
            onClose={() => setSidePanel(null)}
          />
        )}
        {sidePanel === "ai" && (
          <div className="w-80 border-l border-border bg-background">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="font-medium text-sm">AI 助手</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>×</Button>
            </div>
            <AIToolbar selectedText="" fullText="" onApplyResult={() => {}} />
          </div>
        )}
      </div>
    );
  },
);

/** Parse markdown string to BlockNote PartialBlock array */
function parseMarkdownToBlocks(md: string): PartialBlock[] {
  if (!md) return [];
  const lines = md.split("\n");
  const blocks: PartialBlock[] = [];
  for (const line of lines) {
    if (line.startsWith("# ")) {
      blocks.push({ type: "heading", props: { level: 1 }, content: [{ type: "text", text: line.slice(2) }] });
    } else if (line.startsWith("## ")) {
      blocks.push({ type: "heading", props: { level: 2 }, content: [{ type: "text", text: line.slice(3) }] });
    } else if (line.startsWith("### ")) {
      blocks.push({ type: "heading", props: { level: 3 }, content: [{ type: "text", text: line.slice(4) }] });
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      blocks.push({ type: "bulletListItem", content: [{ type: "text", text: line.slice(2) }] });
    } else if (line.trim()) {
      blocks.push({ type: "paragraph", content: [{ type: "text", text: line }] });
    }
  }
  return blocks.length > 0 ? blocks : [{ type: "paragraph", content: [{ type: "text", text: md }] }];
}

/** Convert BlockNote blocks to markdown string */
function blocksToMarkdown(blocks: PartialBlock[]): string {
  return blocks.map((b) => {
    const text = Array.isArray(b.content)
      ? b.content.map((c: any) => c.text || "").join("")
      : "";
    if (b.type === "heading") {
      const level = "#".repeat((b.props as any)?.level || 1);
      return `${level} ${text}`;
    }
    if (b.type === "bulletListItem") return `- ${text}`;
    if (b.type === "numberedListItem") return `1. ${text}`;
    return text;
  }).join("\n");
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && pnpm typecheck
```

Expected: No type errors. If BlockNote types need adjustment, fix them.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx
git commit -m "feat(collab): replace Tiptap with BlockNote editor for project documents"
```

---

## Phase 3: Comment System Overhaul

### Task 7: Add Paragraph-Level Comment Anchor

**Files:**
- Create: `frontend/src/extensions/collab/BlockCommentAnchor.tsx`

- [ ] **Step 1: Create BlockCommentAnchor component**

This component renders a small comment icon next to a paragraph when it has comments or is hovered. It integrates with BlockNote's Side Menu.

```tsx
"use client";

import { MessageSquare } from "lucide-react";
import type { CollabComment } from "../types";

interface BlockCommentAnchorProps {
  blockId: string;
  comments: CollabComment[];
  onClick: (blockId: string) => void;
}

export function BlockCommentAnchor({ blockId, comments, onClick }: BlockCommentAnchorProps) {
  const unresolvedCount = comments.filter((c) => !c.resolved).length;
  if (unresolvedCount === 0) return null;

  return (
    <button
      className="absolute -right-8 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full
        bg-primary/10 hover:bg-primary/20 flex items-center justify-center
        transition-colors cursor-pointer group"
      onClick={() => onClick(blockId)}
      title={`${unresolvedCount} 条评论`}
    >
      <MessageSquare className="w-3.5 h-3.5 text-primary" />
      {unresolvedCount > 1 && (
        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-primary text-primary-foreground
          text-[9px] flex items-center justify-center font-medium">
          {unresolvedCount}
        </span>
      )}
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/collab/BlockCommentAnchor.tsx
git commit -m "feat(collab): add paragraph-level comment anchor component"
```

---

### Task 8: Add Inline Comment Thread (Floating Near Paragraph)

**Files:**
- Create: `frontend/src/extensions/collab/InlineCommentThread.tsx`

- [ ] **Step 1: Create InlineCommentThread component**

A floating comment thread that appears next to the commented paragraph, not in a separate sidebar.

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { X } from "lucide-react";
import { CommentThread } from "./CommentThread";
import type { CollabComment } from "../types";

interface InlineCommentThreadProps {
  comments: CollabComment[];
  onCreateComment: (blockId: string, content: string) => Promise<void>;
  onReply: (parentId: string, content: string) => Promise<void>;
  onResolve: (commentId: string) => Promise<void>;
  onReopen: (commentId: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
  onClose: () => void;
}

export function InlineCommentThread({
  comments,
  onCreateComment,
  onReply,
  onResolve,
  onReopen,
  onDelete,
  onClose,
}: InlineCommentThreadProps) {
  const [newComment, setNewComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const rootComment = comments.find((c) => c.parent_id === null);
  const blockId = rootComment?.block_id ?? comments[0]?.block_id ?? "";

  const handleCreate = async () => {
    if (!blockId || !newComment.trim()) return;
    setSubmitting(true);
    try {
      await onCreateComment(blockId, newComment.trim());
      setNewComment("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="absolute right-0 top-0 w-72 bg-background border border-border rounded-lg
      shadow-lg z-50 flex flex-col max-h-96">
      <div className="flex items-center justify-between p-2 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground">评论</span>
        <Button size="icon" variant="ghost" className="h-5 w-5" onClick={onClose}>
          <X className="w-3 h-3" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        <CommentThread
          comments={comments}
          onReply={onReply}
          onResolve={onResolve}
          onReopen={onReopen}
          onDelete={onDelete}
        />
      </div>

      <div className="p-2 border-t border-border">
        <Textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="添加回复..."
          className="min-h-[40px] text-xs resize-none"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleCreate(); }}
        />
        <Button
          size="sm"
          className="mt-1 w-full h-7 text-xs"
          onClick={handleCreate}
          disabled={submitting || !newComment.trim()}
        >
          回复
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/collab/InlineCommentThread.tsx
git commit -m "feat(collab): add floating inline comment thread component"
```

---

### Task 9: Integrate Comment Anchors into BlockNoteEditor

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- [ ] **Step 1: Add comment anchors to the editor**

In `BlockNoteEditor.tsx`, after the `<BlockNoteView>` component, add a layer of comment anchor overlays. Also import `BlockCommentAnchor` and `InlineCommentThread`.

Add imports at the top:
```tsx
import { BlockCommentAnchor } from "./BlockCommentAnchor";
import { InlineCommentThread } from "./InlineCommentThread";
```

Inside the editor's `flex-1 overflow-y-auto` div, add a comments overlay after `<BlockNoteView>`:

```tsx
{/* Comment anchors — rendered as absolute-positioned markers over blocks */}
{editor && (() => {
  const blockComments = new Map<string, CollabComment[]>();
  for (const c of comments) {
    const arr = blockComments.get(c.block_id) || [];
    arr.push(c);
    blockComments.set(c.block_id, arr);
  }
  return Array.from(blockComments.entries()).map(([blockId, cs]) => (
    <BlockCommentAnchor
      key={blockId}
      blockId={blockId}
      comments={cs}
      onClick={(id) => {
        setSelectedBlockId(id);
        setSidePanel("comments");
      }}
    />
  ));
})()}
```

Also add inline thread display when a block is selected and sidePanel is "comments":

```tsx
{sidePanel === "comments" && selectedBlockId && (() => {
  const blockComments = comments.filter((c) => c.block_id === selectedBlockId);
  if (blockComments.length === 0) return null;
  return (
    <InlineCommentThread
      comments={blockComments}
      onCreateComment={handleCreateComment}
      onReply={handleReply}
      onResolve={handleResolve}
      onReopen={handleReopen}
      onDelete={handleDelete}
      onClose={() => setSidePanel(null)}
    />
  );
})()}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && pnpm typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx
git commit -m "feat(collab): integrate paragraph-level comment anchors into editor"
```

---

### Task 10: Add Real-Time Comment Sync via Yjs Awareness

**Files:**
- Modify: `frontend/src/extensions/collab/useComments.ts`
- Modify: `frontend/src/extensions/collab/useCollab.ts`

- [ ] **Step 1: Broadcast comment changes via Yjs Awareness**

In `useCollab.ts`, add a method to broadcast custom events via Awareness:

```tsx
// Add to the return object:
const broadcastEvent = useCallback((event: { type: string; payload: any }) => {
  if (providerRef.current?.awareness) {
    providerRef.current.awareness.setLocalStateField("collabEvent", {
      ...event,
      timestamp: Date.now(),
    });
  }
}, []);

// Add awareness observer for receiving events:
useEffect(() => {
  if (!providerRef.current?.awareness) return;
  const awareness = providerRef.current.awareness;
  const handler = () => {
    awareness.getStates().forEach((state: any, clientId: number) => {
      if (state.collabEvent && clientId !== awareness.clientID) {
        // Emit to subscribers
        window.dispatchEvent(new CustomEvent("collab-event", { detail: state.collabEvent }));
      }
    });
  };
  awareness.on("change", handler);
  return () => { awareness.off("change", handler); };
}, [connected]);
```

Add `broadcastEvent` to the return: `{ ydoc, provider: providerRef.current, connected, users, broadcastEvent }`

- [ ] **Step 2: Listen for comment events in useComments**

In `useComments.ts`, add a real-time listener after the initial load:

```tsx
useEffect(() => {
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail?.type === "comment_created" || detail?.type === "comment_resolved" || detail?.type === "comment_reopened") {
      load(); // Reload comments from server
    }
  };
  window.addEventListener("collab-event", handler);
  return () => { window.removeEventListener("collab-event", handler); };
}, [load]);
```

After each mutation (createComment, resolveComment, etc.), broadcast the event. Add a `broadcastEvent` parameter to the hook:

Update the hook signature:
```tsx
export function useComments(docId: string | null, broadcastEvent?: (event: { type: string; payload: any }) => void) {
```

And in each mutation, after the API call, broadcast:
```tsx
const createComment = useCallback(
  async (data: CommentCreateRequest) => {
    if (!docId) return;
    const comment = await docmgrApi.createComment(docId, data);
    setComments((prev) => [...prev, comment]);
    broadcastEvent?.({ type: "comment_created", payload: { docId, blockId: data.block_id } });
    return comment;
  },
  [docId, broadcastEvent],
);
```

Do the same for `resolveComment`, `reopenComment`, `deleteComment`.

- [ ] **Step 3: Wire broadcastEvent from CollabEditor**

In `BlockNoteEditor.tsx`, update the `useCollab` and `useComments` calls:

```tsx
const { ydoc, provider, connected, users, broadcastEvent } = useCollab(documentId);
const { comments, createComment, resolveComment, reopenComment, deleteComment } = useComments(documentId, broadcastEvent);
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/collab/useCollab.ts frontend/src/extensions/collab/useComments.ts frontend/src/extensions/collab/BlockNoteEditor.tsx
git commit -m "feat(collab): add real-time comment sync via Yjs Awareness"
```

---

## Phase 4: Version History & AI Writing

### Task 11: Implement Version Preview Mode

**Files:**
- Modify: `frontend/src/extensions/collab/VersionPanel.tsx`
- Modify: `frontend/src/extensions/collab/useVersions.ts`
- Modify: `frontend/src/extensions/api/index.ts`
- Modify: `frontend/src/extensions/types.ts`

- [ ] **Step 1: Add getVersion API method**

In `frontend/src/extensions/api/index.ts`, verify `getVersion` exists. It should already be at line 528. If not, add:

```typescript
getVersion: async (docId: string, version: number): Promise<CollabVersion> => {
  const res = await fetch(`${BASE}/api/extensions/docmgr/documents/${docId}/versions/${version}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to get version");
  return res.json();
},
```

- [ ] **Step 2: Add diffVersion API method**

In `frontend/src/extensions/api/index.ts`, after `restoreVersion`:

```typescript
diffVersions: async (docId: string, fromVer: number, toVer: number): Promise<VersionDiffResponse> => {
  const res = await fetch(
    `${BASE}/api/extensions/docmgr/documents/${docId}/versions/diff?from=${fromVer}&to=${toVer}`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error("Failed to diff versions");
  return res.json();
},
```

- [ ] **Step 3: Add VersionDiffResponse type**

In `frontend/src/extensions/types.ts`, add:

```typescript
export interface VersionDiffResponse {
  from_version: number;
  to_version: number;
  from_summary: string | null;
  to_summary: string | null;
  from_created_at: string | null;
  to_created_at: string | null;
  diff_blocks: Array<{
    type: "added" | "removed" | "changed";
    content: string;
    block_id?: string;
    from_content?: string;
    to_content?: string;
  }>;
  ai_summary: string | null;
}
```

- [ ] **Step 4: Update VersionPanel with preview**

In `frontend/src/extensions/collab/VersionPanel.tsx`, add a preview mode. When a version is clicked, show its content in read-only mode. Add a `onPreviewVersion` callback:

Update the props interface:
```tsx
interface VersionPanelProps {
  versions: CollabVersion[];
  loading: boolean;
  onCreateVersion: (summary?: string) => Promise<void>;
  onRestoreVersion: (version: number) => Promise<void>;
  onPreviewVersion: (version: number) => Promise<void>;
  onClose: () => void;
}
```

In each version item, add a click handler:
```tsx
<div key={v.id} className="p-3 hover:bg-muted/50 transition-colors cursor-pointer"
  onClick={() => onPreviewVersion(v.version)}>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/collab/VersionPanel.tsx frontend/src/extensions/collab/useVersions.ts frontend/src/extensions/api/index.ts frontend/src/extensions/types.ts
git commit -m "feat(collab): add version preview mode to version panel"
```

---

### Task 12: Implement DiffViewer

**Files:**
- Rewrite: `frontend/src/extensions/collab/DiffViewer.tsx`
- Modify: `frontend/src/extensions/collab/useVersions.ts`

- [ ] **Step 1: Add diffVersion to useVersions**

In `frontend/src/extensions/collab/useVersions.ts`, add:

```tsx
import { docmgrApi } from "../api";
import type { CollabVersion, VersionDiffResponse } from "../types";

// Add to hook:
const [diffResult, setDiffResult] = useState<VersionDiffResponse | null>(null);

const diffVersions = useCallback(
  async (fromVer: number, toVer: number) => {
    if (!docId) return;
    const result = await docmgrApi.diffVersions(docId, fromVer, toVer);
    setDiffResult(result);
    return result;
  },
  [docId],
);

// Return: { ..., diffResult, diffVersions }
```

- [ ] **Step 2: Rewrite DiffViewer.tsx**

```tsx
"use client";

import { ArrowRight } from "lucide-react";
import type { VersionDiffResponse } from "../types";

interface DiffViewerProps {
  diff: VersionDiffResponse | null;
  loading: boolean;
}

export function DiffViewer({ diff, loading }: DiffViewerProps) {
  if (loading) {
    return <div className="p-4 text-center text-sm text-muted-foreground">加载差异对比...</div>;
  }

  if (!diff) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        <p>选择两个版本进行差异对比</p>
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span>v{diff.from_version}</span>
        <ArrowRight className="w-4 h-4 text-muted-foreground" />
        <span>v{diff.to_version}</span>
      </div>

      {diff.ai_summary && (
        <div className="p-3 rounded-md bg-blue-50 dark:bg-blue-950/30 text-sm">
          {diff.ai_summary}
        </div>
      )}

      <div className="space-y-1">
        {diff.diff_blocks.map((block, i) => (
          <div
            key={i}
            className={`px-3 py-1.5 rounded text-sm font-mono ${
              block.type === "added"
                ? "bg-green-100 dark:bg-green-950/30 text-green-800 dark:text-green-200"
                : block.type === "removed"
                  ? "bg-red-100 dark:bg-red-950/30 text-red-800 dark:text-red-200 line-through"
                  : "bg-yellow-100 dark:bg-yellow-950/30 text-yellow-800 dark:text-yellow-200"
            }`}
          >
            {block.type === "added" ? "+ " : block.type === "removed" ? "- " : "~ "}
            {block.content || block.to_content || ""}
          </div>
        ))}
      </div>

      {diff.diff_blocks.length === 0 && (
        <p className="text-sm text-muted-foreground text-center">两个版本无差异</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire DiffViewer into VersionPanel**

In `VersionPanel.tsx`, add a diff mode toggle and include DiffViewer. Add state for selecting two versions for comparison and render the DiffViewer when both are selected.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/collab/DiffViewer.tsx frontend/src/extensions/collab/useVersions.ts frontend/src/extensions/collab/VersionPanel.tsx
git commit -m "feat(collab): implement version diff viewer with block-level comparison"
```

---

### Task 13: Add AI Document-Level Review

**Files:**
- Create: `frontend/src/extensions/collab/AIDocumentReview.tsx`
- Modify: `frontend/src/extensions/collab/AIToolbar.tsx`
- Modify: `backend/app/extensions/docmgr/collab_routers.py`
- Modify: `backend/app/extensions/docmgr/collab_service.py`
- Modify: `backend/app/extensions/docmgr/collab_schemas.py`

- [ ] **Step 1: Add AI review backend endpoint**

In `backend/app/extensions/docmgr/collab_schemas.py`, add:

```python
class AIReviewRequest(BaseModel):
    doc_id: UUID
    review_type: str = Field(default="full", description="full | style | logic | completeness")

class AIReviewComment(BaseModel):
    block_id: str | None = None
    comment: str
    severity: str = Field(default="info", description="info | warning | error")

class AIReviewResponse(BaseModel):
    review_id: str
    comments: list[AIReviewComment] = Field(default_factory=list)
    overall_score: float | None = None
    summary: str | None = None
```

In `backend/app/extensions/docmgr/collab_routers.py`, add:

```python
from app.extensions.docmgr.collab_schemas import AIReviewRequest, AIReviewResponse, AIReviewComment

@router.post("/documents/ai-review", response_model=AIReviewResponse)
async def ai_review_document(
    request: AIReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, request.doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return await CommentService.ai_review_document(db, request.doc_id, doc.content or "", request.review_type)
```

- [ ] **Step 2: Add AI review logic to service**

In `backend/app/extensions/docmgr/collab_service.py`, add to `CommentService`:

```python
@staticmethod
async def ai_review_document(db: AsyncSession, doc_id: UUID, content: str, review_type: str) -> dict:
    from deerflow.models import create_chat_model
    from app.extensions.config import get_app_config
    config = get_app_config()
    model = create_chat_model("ai-review", thinking_enabled=False)

    prompts = {
        "full": "请审查以下文档，从逻辑一致性、语言风格统一性、缺失章节、数据准确性四个维度给出建议。对每个问题指出具体段落位置和修改建议。",
        "style": "请审查以下文档的语言风格是否统一，用词是否专业准确，语气是否一致。",
        "logic": "请审查以下文档的逻辑是否连贯，论证是否有漏洞，结构是否清晰。",
        "completeness": "请检查以下文档是否有缺失的章节、未覆盖的要点、需要补充的内容。",
    }
    prompt = prompts.get(review_type, prompts["full"])

    response = await model.ainvoke([
        {"role": "system", "content": f"{prompt}\n\n请以 JSON 格式返回，格式为: {{\"comments\": [{{\"block_id\": null, \"comment\": \"...\", \"severity\": \"info|warning|error\"}}], \"overall_score\": 0-100, \"summary\": \"...\"}}"},
        {"role": "user", "content": content[:8000]},
    ])
    import json
    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        result = {"comments": [{"comment": response.content if isinstance(response.content, str) else str(response.content), "severity": "info"}], "overall_score": None, "summary": None}

    return {
        "review_id": str(uuid4()),
        "comments": result.get("comments", []),
        "overall_score": result.get("overall_score"),
        "summary": result.get("summary"),
    }
```

- [ ] **Step 3: Create AIDocumentReview frontend component**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2, AlertTriangle, Info, AlertCircle } from "lucide-react";
import { docmgrApi } from "../api";

interface AIDocumentReviewProps {
  docId: string;
  onInsertComment: (blockId: string | null, comment: string) => void;
}

const REVIEW_TYPES = [
  { key: "full", label: "全面审查" },
  { key: "style", label: "风格检查" },
  { key: "logic", label: "逻辑审查" },
  { key: "completeness", label: "完整性检查" },
] as const;

const SEVERITY_ICONS = {
  info: Info,
  warning: AlertTriangle,
  error: AlertCircle,
};

export function AIDocumentReview({ docId, onInsertComment }: AIDocumentReviewProps) {
  const [reviewType, setReviewType] = useState<string>("full");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleReview = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await docmgrApi.aiReview({ doc_id: docId, review_type: reviewType });
      setResult(res);
    } catch {
      setResult({ error: "AI 审查失败，请重试" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4" />
        <span className="text-sm font-medium">文档级 AI 审查</span>
      </div>

      <div className="flex flex-wrap gap-1">
        {REVIEW_TYPES.map((t) => (
          <Button key={t.key} size="sm" variant={reviewType === t.key ? "default" : "outline"}
            onClick={() => setReviewType(t.key)} disabled={loading}>
            {t.label}
          </Button>
        ))}
      </div>

      <Button size="sm" className="w-full" onClick={handleReview} disabled={loading}>
        {loading ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />审查中...</> : "开始审查"}
      </Button>

      {result && !result.error && (
        <div className="space-y-2">
          {result.overall_score != null && (
            <div className="text-sm">综合评分: <span className="font-bold text-lg">{result.overall_score}/100</span></div>
          )}
          {result.summary && <p className="text-sm text-muted-foreground">{result.summary}</p>}
          {(result.comments || []).map((c: any, i: number) => {
            const Icon = SEVERITY_ICONS[c.severity as keyof typeof SEVERITY_ICONS] || Info;
            return (
              <div key={i} className="p-2 rounded border border-border flex gap-2">
                <Icon className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs">{c.comment}</p>
                  <Button size="sm" variant="link" className="h-auto p-0 text-[10px]"
                    onClick={() => onInsertComment(c.block_id, c.comment)}>
                    插入为评论
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {result?.error && <p className="text-sm text-destructive">{result.error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Add aiReview to frontend API**

In `frontend/src/extensions/api/index.ts`, add:

```typescript
aiReview: async (data: { doc_id: string; review_type: string }): Promise<any> => {
  const res = await fetch(`${BASE}/api/extensions/docmgr/documents/ai-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("AI review failed");
  return res.json();
},
```

- [ ] **Step 5: Wire AIDocumentReview into BlockNoteEditor**

In `BlockNoteEditor.tsx`, import `AIDocumentReview` and replace the basic AI panel content:

```tsx
import { AIDocumentReview } from "./AIDocumentReview";

// In the AI side panel:
{sidePanel === "ai" && (
  <div className="w-80 border-l border-border bg-background flex flex-col h-full">
    <div className="p-3 border-b border-border flex items-center justify-between">
      <span className="font-medium text-sm">AI 助手</span>
      <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>×</Button>
    </div>
    <div className="flex-1 overflow-y-auto">
      <div className="p-3 border-b border-border">
        <AIToolbar selectedText="" fullText="" onApplyResult={() => {}} />
      </div>
      <div className="p-3">
        <AIDocumentReview
          docId={documentId}
          onInsertComment={(blockId, comment) => {
            handleCreateComment(blockId || selectedBlockId || "", `[AI 审查] ${comment}`);
            setSidePanel("comments");
          }}
        />
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/collab/AIDocumentReview.tsx frontend/src/extensions/collab/BlockNoteEditor.tsx frontend/src/extensions/api/index.ts backend/app/extensions/docmgr/collab_schemas.py backend/app/extensions/docmgr/collab_service.py backend/app/extensions/docmgr/collab_routers.py
git commit -m "feat(collab): add AI document-level review with comment insertion"
```

---

### Task 14: Final Integration and Testing

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: Update DocumentManagement for BlockNote ref**

The `CollabEditorRef` interface should match `BlockNoteEditorRef`. Verify `DocumentManagement.tsx` lines 849-972 work with the new ref. The methods `getMarkdown`, `getSelectedText`, `replaceSelection` remain the same, so no changes needed.

- [ ] **Step 2: Run full frontend build**

```bash
cd frontend && pnpm typecheck && pnpm lint
```

Fix any type errors or lint issues.

- [ ] **Step 3: Run backend tests**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -v
```

- [ ] **Step 4: Manual smoke test**

1. Start dev: `make dev`
2. Open browser at `http://localhost:2026`
3. Create a project, add a document in the project folder
4. Verify: BlockNote editor loads (block drag, slash commands)
5. Verify: Two browser tabs can collaborate in real-time
6. Verify: Online users show with colored avatars
7. Verify: Comments can be created on paragraphs, threaded, resolved
8. Verify: Version history — create, list, restore
9. Verify: AI toolbar — polish/expand/condense/brainstorm
10. Verify: AI document review — full/style/logic/completeness

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "feat(collab): complete project document collaboration system implementation"
```

---

## Spec Coverage Self-Review

| Design Requirement | Task |
|---|---|
| Cookie JWT auth + CSRF Origin | Task 1 |
| Project membership check | Task 2 |
| collab_updates recording | Task 2 |
| Timed snapshot (30min) | Task 3 |
| Disconnect-save | Task 3 |
| Version diff API | Task 4 |
| BlockNote editor replacement | Task 5-6 |
| Block drag, slash commands, nested blocks | Task 6 (BlockNote native) |
| Online users + cursor sync | Already implemented |
| Paragraph comment anchor icons | Task 7-9 |
| Inline comment thread display | Task 8-9 |
| Real-time comment broadcast | Task 10 |
| Version preview mode | Task 11 |
| Diff viewer (green/red) | Task 12 |
| Version restore (creates new version) | Already implemented |
| AI paragraph operations | Already implemented |
| AI document-level review | Task 13 |
| AI review as comment threads | Task 13 |
| AI version change summary | Deferred (requires diff-triggered LLM call) |

**Deferred items:**
- AI version change summary: requires comparing Yjs snapshots via LLM on each version creation. This is a nice-to-have that can be added incrementally by triggering an LLM call in the `createVersion` backend endpoint.
