"use client";

import "./patch-prosemirror";
import { useCreateBlockNote, FormattingToolbar, FormattingToolbarController, getFormattingToolbarItems, useComponentsContext } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { AIExtension, AIMenu, AIMenuController, AIToolbarButton } from "@blocknote/xl-ai";
import { en as coreEn } from "@blocknote/core/locales";
import { en as aiEn } from "@blocknote/xl-ai/locales";
import { DefaultChatTransport } from "ai";
import "@blocknote/react/style.css";
import "@blocknote/shadcn/style.css";
import "@blocknote/xl-ai/style.css";
import { BookOpen, History, MessageSquare, Sparkles } from "lucide-react";
import { OutlinePanel } from "./OutlinePanel";
import { Component, forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/extensions/hooks/useAuth";

import type { CollabComment } from "../types";
import { AIDocumentReview } from "./AIDocumentReview";
import { getCollabAIMenuItems } from "./aiMenuItems";
import { TraceabilityPanel } from "@/extensions/workflow/TraceabilityPanel";
import { BlockCommentAnchor } from "./BlockCommentAnchor";
import { CommentSidebar } from "./CommentSidebar";
import { InlineCommentThread } from "./InlineCommentThread";
import { OnlineUsers } from "./OnlineUsers";
import { useCollab } from "./useCollab";
import { useComments } from "./useComments";
import { useVersions } from "./useVersions";
import { VersionPanel } from "./VersionPanel";
import {
  type TraceabilitySource,
  registerTraceabilityPlugin,
  updateTraceabilitySources,
} from "./traceability-extension";
import { registerHumanWrittenPlugin, resetHumanWrittenTracking } from "./human-written-plugin";
import { workflowApi } from "@/extensions/workflow/api";

export interface BlockNoteEditorRef {
  getMarkdown: () => string;
  getSelectedText: () => string;
  replaceSelection: (text: string) => void;
}

interface BlockNoteEditorProps {
  documentId: string;
  initialContent?: string;
  projectId?: string;
  chapterId?: string;
  /**
   * Optional list of block IDs to show in the outline panel.
   * When provided, only headings whose block ID is in this list will be displayed.
   */
  visibleChapterIds?: string[];
}

type SidePanel = "comments" | "versions" | "ai" | "traceability" | null;

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

function CommentToolbarButton({ editor, onOpen }: {
  editor: ReturnType<typeof useCreateBlockNote>;
  onOpen: (savedRange: Range) => void;
}) {
  const Components = useComponentsContext();
  if (!Components) return null;

  // Intercept mousedown + click so BlockNote's toolbar controller never
  // sees this interaction.  We save the selection range synchronously
  // (before BlockNote can clear it) and pass it to onOpen.  The toolbar is
  // dismissed programmatically after the popover mounts.
  const blockToolbarEvents = (e: React.MouseEvent<HTMLSpanElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
    const range = sel.getRangeAt(0);
    onOpen(range);
    // Dismiss the formatting toolbar once React has flushed the popover
    setTimeout(() => {
      const editable = document.querySelector('[contenteditable="true"]') as HTMLElement | null;
      editable?.blur();
    }, 80);
  };

  return (
    <span
      onMouseDown={blockToolbarEvents}
      onMouseUp={blockToolbarEvents}
      onClick={blockToolbarEvents}
    >
      <Components.FormattingToolbar.Button
        mainTooltip={"评论"}
      >
        <MessageSquare style={{ width: 14, height: 14 }} />
      </Components.FormattingToolbar.Button>
    </span>
  );
}

export const BlockNoteEditor = forwardRef<BlockNoteEditorRef, BlockNoteEditorProps>(
  function BlockNoteEditor({ documentId, initialContent, projectId, chapterId, visibleChapterIds }, ref) {
    const { ydoc, connected, synced, users, broadcastEvent } = useCollab(documentId);
    const { comments, createComment, resolveComment, reopenComment, deleteComment } = useComments(documentId, broadcastEvent);
    const { versions, loading: versionsLoading, createVersion, restoreVersion, diffResult, diffLoading, diffVersions } = useVersions(documentId);
    const { user: currentUser } = useAuth();
    const [sidePanel, setSidePanel] = useState<SidePanel>(null);
    const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
    const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
    const [inlineThreadBlockId, setInlineThreadBlockId] = useState<string | null>(null);
    const [mounted, setMounted] = useState(false);
    const seededDocsRef = useRef<Set<string>>(new Set());

    // Comment popover state (lifted above FormattingToolbar so it survives toolbar close)
    const [commentOpen, setCommentOpen] = useState(false);
    const [commentText, setCommentText] = useState("");
    const [commentSubmitting, setCommentSubmitting] = useState(false);
    const highlightRef = useRef<HTMLSpanElement | null>(null);
    const popoverVirtualRef = useRef<{ getBoundingClientRect: () => DOMRect } | null>(null);

    const applyHighlight = (savedRange: Range) => {
      const rangeRect = savedRange.getBoundingClientRect();
      try {
        const span = document.createElement("span");
        span.style.backgroundColor = "#fef9c3";
        span.style.borderRadius = "2px";
        span.dataset.collabCommentHighlight = "true";
        savedRange.surroundContents(span);
        highlightRef.current = span;
        popoverVirtualRef.current = {
          getBoundingClientRect: () => {
            if (highlightRef.current?.isConnected) {
              return highlightRef.current.getBoundingClientRect();
            }
            return rangeRect;
          },
        };
      } catch {
        // surroundContents fails when selection crosses element boundaries —
        // fall back to the raw range rect so the popover still has an anchor
        popoverVirtualRef.current = {
          getBoundingClientRect: () => rangeRect,
        };
      }
    };

    const removeHighlight = () => {
      const span = highlightRef.current;
      if (span && span.parentNode) {
        const parent = span.parentNode;
        while (span.firstChild) {
          parent.insertBefore(span.firstChild, span);
        }
        parent.removeChild(span);
        parent.normalize();
      }
      highlightRef.current = null;
      popoverVirtualRef.current = null;
    };

    const handleCommentOpen = (savedRange: Range) => {
      const rangeRect = savedRange.getBoundingClientRect();
      // Always provide a fallback so the popover has somewhere to anchor
      const fallbackRect: DOMRect = (rangeRect.width > 0 ? rangeRect : {
        x: window.innerWidth / 2,
        y: window.innerHeight / 3,
        width: 1,
        height: 1,
        top: window.innerHeight / 3,
        right: window.innerWidth / 2 + 1,
        bottom: window.innerHeight / 3 + 1,
        left: window.innerWidth / 2,
      }) as DOMRect;
      popoverVirtualRef.current = {
        getBoundingClientRect: () => fallbackRect,
      };
      applyHighlight(savedRange);
      setCommentOpen(true);
    };

    const handleCommentOpenChange = (open: boolean) => {
      if (!open) {
        removeHighlight();
        setCommentOpen(false);
      }
      // Opening is handled by handleCommentOpen (called from toolbar button)
    };

    const dismissToolbar = () => {
      window.getSelection()?.removeAllRanges();
      // Blur the editor's contenteditable element to dismiss the formatting toolbar
      const editable = document.querySelector('[contenteditable="true"]') as HTMLElement | null;
      editable?.blur();
    };

    const handleCommentSubmit = async () => {
      if (!commentText.trim()) return;
      setCommentSubmitting(true);
      try {
        const cursorBlock = editor.getTextCursorPosition().block;
        await createComment({ block_id: cursorBlock.id, content: commentText.trim() });
        setCommentText("");
        // Keep the highlight after submission so it persists as a visual
        // indicator that the text has an associated comment.
        setCommentOpen(false);
        dismissToolbar();
        setSidePanel("comments");
      } finally {
        setCommentSubmitting(false);
      }
    };

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

    const aiTransport = useMemo(
      () =>
        new DefaultChatTransport({
          api: "/api/collab/ai-chat",
          credentials: "include",
        }),
      [],
    );

    const editor = useCreateBlockNote(
      {
        // Merge base BlockNote dictionary with AI dictionary so both
        // core UI and xl-ai components have translations.
        dictionary: { ...coreEn, ai: aiEn } as any,
        collaboration: {
          fragment: ydoc.getXmlFragment("document-store"),
          user: collabUser,
        },
        extensions: [
          AIExtension({ transport: aiTransport }),
        ],
      },
      [ydoc, aiTransport],
    );

    useEffect(() => {
      const source = initialContent?.trim();
      if (!synced || !source || seededDocsRef.current.has(documentId)) return;

      // Priority 1: Server signaled pending markdown via Yjs metadata
      const meta = ydoc.getMap("_collabMeta");
      const pendingMarkdown = meta.get("pendingMarkdown");
      if (pendingMarkdown && typeof pendingMarkdown === "string" && pendingMarkdown.trim()) {
        try {
          const blocks = editor.tryParseMarkdownToBlocks(pendingMarkdown.trim());
          if (blocks.length > 0) {
            editor.replaceBlocks(
              editor.document.map((block) => block.id),
              blocks,
            );
          }
          // Clear the flag so it doesn't re-seed on subsequent opens
          meta.delete("pendingMarkdown");
        } catch (error) {
          console.error("[BlockNoteEditor] Failed to seed from server markdown:", error);
        }
        seededDocsRef.current.add(documentId);
        return;
      }

      // Priority 2: Standard seeding — only if editor has no real content.
      // Check whether any block contains actual text (not just empty paragraphs).
      const hasRealContent = editor.document.some((block) => {
        if (block.type !== "paragraph") return true;
        const children = (block as Record<string, unknown>).children;
        const content = (block as Record<string, unknown>).content;
        if (Array.isArray(children) && children.length > 0) return true;
        if (Array.isArray(content)) {
          return content.some(
            (c: Record<string, unknown>) =>
              typeof c.text === "string" && (c.text as string).trim().length > 0,
          );
        }
        return false;
      });

      if (hasRealContent) {
        seededDocsRef.current.add(documentId);
        return;
      }

      try {
        const blocks = editor.tryParseMarkdownToBlocks(source);
        if (blocks.length === 0) return;
        editor.replaceBlocks(
          editor.document.map((block) => block.id),
          blocks,
        );
        seededDocsRef.current.add(documentId);
      } catch (error) {
        console.error("[BlockNoteEditor] Failed to seed collaborative content:", error);
      }
    }, [documentId, editor, initialContent, synced, ydoc]);

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

    // ── Traceability: register ProseMirror plugins on mount ──
    useEffect(() => {
      const view = (editor as any)._tiptapEditor?.view;
      if (view) {
        registerTraceabilityPlugin(view);
        registerHumanWrittenPlugin(view);
      }
    }, [editor]);

    // ── Human-written: reset tracking when chapter changes ──
    useEffect(() => {
      const view = (editor as any)._tiptapEditor?.view;
      if (view && chapterId) {
        resetHumanWrittenTracking(view);
      }
    }, [editor, chapterId]);

    // ── Traceability: fetch sources and push decorations ──
    useEffect(() => {
      if (!projectId || !chapterId) return;

      let cancelled = false;
      const view = (editor as any)._tiptapEditor?.view;
      if (!view) return;

      workflowApi
        .getSources(projectId, chapterId)
        .then((data) => {
          if (cancelled) return;
          const sources: TraceabilitySource[] = (data.sources || []).map(
            (s: any, i: number) => ({
              index: (s.blockIndex ?? i) + 1, // block_index is 0-based; markers are 1-based
              sourceType: s.sourceType ?? "ai_generated",
              sourceRef: s.sourceRef ?? "",
              snippet: s.snippet ?? null,
              confidence: s.confidence ?? null,
            }),
          );
          updateTraceabilitySources(view, sources);
        })
        .catch((err) => {
          console.warn("[BlockNoteEditor] Failed to fetch traceability sources:", err);
        });

      return () => {
        cancelled = true;
      };
    }, [projectId, chapterId, editor]);

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
      <div className="flex-1 flex h-full min-h-0">
        {/* Left: Chapter outline */}
        <OutlinePanel editor={editor} onChapterSelect={setSelectedChapterId} visibleChapterIds={visibleChapterIds} />

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
                onClick={() => setSidePanel(sidePanel === "ai" ? null : "ai")} title="AI 文档审查">
                <Sparkles className="w-4 h-4" />
              </Button>
              {projectId && (
                <Button size="icon" variant={sidePanel === "traceability" ? "secondary" : "ghost"}
                  onClick={() => setSidePanel(sidePanel === "traceability" ? null : "traceability")} title="溯源">
                  <BookOpen className="w-4 h-4" />
                </Button>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto min-h-0">
            <div className="mx-auto px-8 pt-10 pb-32 relative" style={{ maxWidth: 780 }}>
              <EditorErrorBoundary fallback={<div className="text-muted-foreground text-sm">编辑器加载失败</div>}>
                <BlockNoteView
                  editor={editor}
                  sideMenu
                  slashMenu
                  formattingToolbar={false}
                  linkToolbar
                  tableHandles
                >
                  <FormattingToolbarController
                    formattingToolbar={() => (
                      <FormattingToolbar>
                        {...getFormattingToolbarItems()}
                        <CommentToolbarButton
                          editor={editor}
                          onOpen={handleCommentOpen}
                        />
                        <AIToolbarButton />
                      </FormattingToolbar>
                    )}
                  />
                  <AIMenuController
                    aiMenu={() => (
                      <AIMenu
                        items={(editor, status) => getCollabAIMenuItems(editor, status)}
                      />
                    )}
                  />
                </BlockNoteView>
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

            {/* Comment popover — rendered outside the formatting toolbar so it
                survives the toolbar closing on click. Opens from the toolbar
                button via handleCommentOpen.
                PopoverAnchor uses a virtual ref tracking the highlight span
                so the popover positions itself next to the selected text.
                Always render the anchor (Radix needs a stable ref), and
                pass the RefObject itself (not .current). */}
            <Popover open={commentOpen} onOpenChange={handleCommentOpenChange} modal={false}>
              <PopoverAnchor virtualRef={popoverVirtualRef} />
              <PopoverContent className="w-72" align="center" side="bottom" sideOffset={8}>
                <div className="space-y-3">
                  <p className="text-sm font-medium">添加评论</p>
                  <Textarea
                    placeholder="输入评论内容..."
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    rows={3}
                    className="resize-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        handleCommentSubmit();
                      }
                    }}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        removeHighlight();
                        setCommentText("");
                        setCommentOpen(false);
                        dismissToolbar();
                      }}
                    >
                      取消
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleCommentSubmit}
                      disabled={commentSubmitting || !commentText.trim()}
                    >
                      {commentSubmitting ? "提交中..." : "提交评论"}
                    </Button>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
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
              <span className="font-medium text-sm">AI 文档审查</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <AIDocumentReview
                docId={documentId}
                documentContent={editor.blocksToMarkdownLossy()}
                onInsertComment={(blockId, comment) => {
                  handleCreateComment(blockId || selectedBlockId || "", `[AI 审查] ${comment}`);
                  setSidePanel("comments");
                }}
              />
            </div>
          </div>
        )}
        {sidePanel === "traceability" && projectId && (
          <div className="w-80 border-l border-border bg-background flex flex-col h-full">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="font-medium text-sm">溯源</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <TraceabilityPanel projectId={projectId} chapterId={selectedChapterId} />
            </div>
          </div>
        )}
      </div>
    );
  },
);
