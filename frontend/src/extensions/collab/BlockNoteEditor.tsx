"use client";

import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { useCollab } from "./useCollab";
import { OnlineUsers } from "./OnlineUsers";
import { CommentSidebar } from "./CommentSidebar";
import { VersionPanel } from "./VersionPanel";
import { AIToolbar } from "./AIToolbar";
import { useComments } from "./useComments";
import { useVersions } from "./useVersions";
import { useAuth } from "@/extensions/hooks/useAuth";
import { forwardRef, useCallback, useImperativeHandle, useMemo, useState } from "react";
import { MessageSquare, History, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/shadcn/style.css";

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

    const collabFragment = ydoc ? ydoc.getXmlFragment("document-store") : undefined;

    // Derive a stable color from user ID so it doesn't change across re-renders
    const collabUser = useMemo(() => {
      const name = currentUser?.full_name || currentUser?.username || "User";
      const colorIdx = currentUser
        ? currentUser.id.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % COLLAB_USER_COLORS.length
        : Math.floor(Math.random() * COLLAB_USER_COLORS.length);
      return { name, color: COLLAB_USER_COLORS[colorIdx] ?? "#6366f1" };
    }, [currentUser]);

    const editor = useCreateBlockNote({
      collaboration: ydoc && collabFragment
        ? {
            fragment: collabFragment,
            user: { name: collabUser.name, color: collabUser.color },
            ...(provider?.awareness ? { provider: { awareness: provider.awareness } } : {}),
          }
        : undefined,
      initialContent: initialContent ? (() => {
        try { return JSON.parse(initialContent); } catch { return undefined; }
      })() : undefined,
    });

    useImperativeHandle(ref, () => ({
      getMarkdown: () => {
        const blocks = editor.document;
        return blocks.map((block: any) => {
          if (typeof block.content === "string") return block.content;
          if (Array.isArray(block.content)) {
            return block.content.map((c: any) => c.text || "").join("");
          }
          return "";
        }).join("\n\n");
      },
      getSelectedText: () => {
        try { return editor.getSelectedText() || ""; } catch { return ""; }
      },
      replaceSelection: (text: string) => {
        try {
          const sel = editor.getSelection();
          if (sel && sel.blocks.length > 0) {
            editor.insertBlocks([{ type: "paragraph", content: text }], sel.blocks[0]!.id, "after");
          }
        } catch { /* noop */ }
      },
    }));

    const handleCreateComment = useCallback(
      async (blockId: string, content: string): Promise<void> => {
        await createComment({ block_id: blockId, content });
      },
      [createComment],
    );

    const handleReply = useCallback(
      async (parentId: string, content: string): Promise<void> => {
        await createComment({ block_id: selectedBlockId ?? "", content, parent_id: parentId });
      },
      [createComment, selectedBlockId],
    );

    const handleResolve = useCallback(
      async (commentId: string): Promise<void> => {
        await resolveComment(commentId);
      },
      [resolveComment],
    );

    const handleReopen = useCallback(
      async (commentId: string): Promise<void> => {
        await reopenComment(commentId);
      },
      [reopenComment],
    );

    const handleDelete = useCallback(
      async (commentId: string): Promise<void> => {
        await deleteComment(commentId);
      },
      [deleteComment],
    );

    const handleCreateVersion = useCallback(
      async (summary?: string): Promise<void> => {
        await createVersion(summary);
      },
      [createVersion],
    );

    const handleRestoreVersion = useCallback(
      async (version: number): Promise<void> => {
        await restoreVersion(version);
      },
      [restoreVersion],
    );

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
            {editor && <BlockNoteView editor={editor} theme={"light"} />}
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
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
            </div>
            <AIToolbar selectedText="" fullText="" onApplyResult={() => {}} />
          </div>
        )}
      </div>
    );
  },
);
