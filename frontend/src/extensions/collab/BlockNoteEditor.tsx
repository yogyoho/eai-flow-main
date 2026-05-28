"use client";

import { useCreateBlockNote, BlockNoteViewRaw } from "@blocknote/react";
import { BlockNoteView as ShadcnBlockNoteView } from "@blocknote/shadcn";

// import "@blocknote/shadcn/style.css";
// import "@blocknote/react/style.css";
import { MessageSquare, History, Sparkles } from "lucide-react";
import { Component, forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/extensions/hooks/useAuth";

import type { CollabComment } from "../types";
import { AIDocumentReview } from "./AIDocumentReview";
import { AIToolbar } from "./AIToolbar";
import { BlockCommentAnchor } from "./BlockCommentAnchor";
import { CommentSidebar } from "./CommentSidebar";
import { InlineCommentThread } from "./InlineCommentThread";
import { OnlineUsers } from "./OnlineUsers";
import { useCollab } from "./useCollab";
import { useComments } from "./useComments";
import { useVersions } from "./useVersions";
import { VersionPanel } from "./VersionPanel";

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

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}
class EditorErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[EditorErrorBoundary] Full error:", error);
    console.error("[EditorErrorBoundary] Component stack:", info.componentStack);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="text-muted-foreground text-sm p-4">
          <p className="font-medium mb-2">编辑器加载失败</p>
          <pre className="text-xs whitespace-pre-wrap break-all bg-muted p-2 rounded">
            {this.state.error?.message}
            {"\n"}
            {this.state.error?.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

export const BlockNoteEditor = forwardRef<BlockNoteEditorRef, BlockNoteEditorProps>(
  function BlockNoteEditor({ documentId, initialContent: _initialContent }, ref) {
    const { ydoc, provider, connected, synced, users, broadcastEvent } = useCollab(documentId);
    const { comments, createComment, resolveComment, reopenComment, deleteComment } = useComments(documentId, broadcastEvent);
    const { versions, loading: versionsLoading, createVersion, restoreVersion, diffResult, diffLoading, diffVersions } = useVersions(documentId);
    const { user: currentUser } = useAuth();
    const [sidePanel, setSidePanel] = useState<SidePanel>(null);
    const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
    const [inlineThreadBlockId, setInlineThreadBlockId] = useState<string | null>(null);
    const [mounted, setMounted] = useState(false);

    useEffect(() => { setMounted(true); }, []);

    const collabUser = useMemo(() => {
      const name = currentUser?.full_name || currentUser?.username || "User";
      const colorIdx = currentUser
        ? currentUser.id.split("").reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % COLLAB_USER_COLORS.length
        : Math.floor(Math.random() * COLLAB_USER_COLORS.length);
      return { name, color: COLLAB_USER_COLORS[colorIdx] ?? "#6366f1" };
    }, [currentUser]);

    const commentsByBlock = useMemo(() => {
      const map = new Map<string, CollabComment[]>();
      for (const c of comments) {
        const list = map.get(c.block_id) ?? [];
        list.push(c);
        map.set(c.block_id, list);
      }
      return map;
    }, [comments]);

    const editor = useCreateBlockNote({}, []);

    // Track selected block via onSelectionChange
    useEffect(() => {
      const unsubscribe = editor.onSelectionChange(() => {
        const cursorPos = editor.getTextCursorPosition();
        if (cursorPos.block) {
          setSelectedBlockId(cursorPos.block.id);
        }
      });
      return unsubscribe;
    }, [editor]);

    useImperativeHandle(ref, () => ({
      getMarkdown: () => {
        return editor.blocksToMarkdownLossy();
      },
      getSelectedText: () => {
        return editor.getSelectedText();
      },
      replaceSelection: (text: string) => {
        editor.focus();
        const blocks = editor.tryParseMarkdownToBlocks(text);
        const selection = editor.getSelection();
        if (selection && selection.blocks.length > 0) {
          editor.replaceBlocks(
            selection.blocks.map((b) => b.id),
            blocks,
          );
        } else {
          const cursorBlock = editor.getTextCursorPosition().block;
          editor.insertBlocks(blocks, cursorBlock, "after");
        }
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

    if (!mounted || !editor) {
      return (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          加载编辑器...
        </div>
      );
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
              <EditorErrorBoundary fallback={<div className="text-muted-foreground text-sm">编辑器加载失败</div>}>
                <BlockNoteViewRaw editor={editor} />
              </EditorErrorBoundary>

              {/* Comment anchors for each block with unresolved comments */}
              {Array.from(commentsByBlock.entries()).map(([blockId, blockComments]) => (
                <BlockCommentAnchor
                  key={blockId}
                  blockId={blockId}
                  comments={blockComments}
                  onClick={(id) => {
                    setSelectedBlockId(id);
                    setSidePanel("comments");
                  }}
                />
              ))}

              {/* Inline comment thread floating near selected block */}
              {inlineThreadBlockId && commentsByBlock.has(inlineThreadBlockId) && (
                <InlineCommentThread
                  comments={commentsByBlock.get(inlineThreadBlockId) ?? []}
                  onCreateComment={handleCreateComment}
                  onReply={handleReply}
                  onResolve={handleResolve}
                  onReopen={handleReopen}
                  onDelete={handleDelete}
                  onClose={() => setInlineThreadBlockId(null)}
                />
              )}
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
            diffResult={diffResult}
            diffLoading={diffLoading}
            onCreateVersion={handleCreateVersion}
            onRestoreVersion={handleRestoreVersion}
            onPreviewVersion={(version) => diffVersions(version)}
            onDiffVersions={(from, to) => diffVersions(from, to)}
            onClose={() => setSidePanel(null)}
          />
        )}
        {sidePanel === "ai" && (
          <div className="w-80 border-l border-border bg-background flex flex-col h-full">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="font-medium text-sm">AI 助手</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
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
      </div>
    );
  },
);
