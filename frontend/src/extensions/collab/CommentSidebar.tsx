"use client";

import { MessageSquare, CheckCircle2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { CollabComment } from "../types";

import { CommentThread } from "./CommentThread";

interface CommentSidebarProps {
  comments: CollabComment[];
  selectedBlockId: string | null;
  onCreateComment: (blockId: string, content: string) => Promise<void>;
  onReply: (parentId: string, content: string) => Promise<void>;
  onResolve: (commentId: string) => Promise<void>;
  onReopen: (commentId: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}

export function CommentSidebar({
  comments,
  selectedBlockId,
  onCreateComment,
  onReply,
  onResolve,
  onReopen,
  onDelete,
}: CommentSidebarProps) {
  const [newComment, setNewComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showResolved, setShowResolved] = useState(false);

  const threads = new Map<string, CollabComment[]>();
  for (const c of comments) {
    const rootId = c.parent_id ?? c.id;
    if (!threads.has(rootId)) threads.set(rootId, []);
    threads.get(rootId)!.push(c);
  }

  const threadEntries = Array.from(threads.entries());
  const openThreads = threadEntries.filter(
    ([, cs]) => !cs.some((c) => c.parent_id === null && c.resolved),
  );
  const resolvedThreads = threadEntries.filter(([, cs]) =>
    cs.some((c) => c.parent_id === null && c.resolved),
  );

  const handleCreate = async () => {
    if (!selectedBlockId || !newComment.trim()) return;
    setSubmitting(true);
    try {
      await onCreateComment(selectedBlockId, newComment.trim());
      setNewComment("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-border bg-background flex h-full w-80 flex-col border-l">
      <div className="border-border flex items-center justify-between border-b p-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="text-sm font-medium">评论</span>
          <span className="text-muted-foreground text-xs">
            ({openThreads.length})
          </span>
        </div>
        {resolvedThreads.length > 0 && (
          <button
            className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs"
            onClick={() => setShowResolved(!showResolved)}
          >
            <CheckCircle2 className="h-3 w-3" />
            {showResolved ? "隐藏已解决" : `已解决 (${resolvedThreads.length})`}
          </button>
        )}
      </div>

      {selectedBlockId && (
        <div className="border-border border-b p-3">
          <Textarea
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="添加评论..."
            className="min-h-[60px] text-sm"
          />
          <Button
            size="sm"
            className="mt-2 w-full"
            onClick={handleCreate}
            disabled={submitting || !newComment.trim()}
          >
            发表评论
          </Button>
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {openThreads.map(([rootId, cs]) => (
          <CommentThread
            key={rootId}
            comments={cs}
            onReply={onReply}
            onResolve={onResolve}
            onReopen={onReopen}
            onDelete={onDelete}
          />
        ))}

        {showResolved &&
          resolvedThreads.map(([rootId, cs]) => (
            <div key={rootId} className="opacity-50">
              <CommentThread
                comments={cs}
                onReply={onReply}
                onResolve={onResolve}
                onReopen={onReopen}
                onDelete={onDelete}
              />
            </div>
          ))}

        {openThreads.length === 0 && !selectedBlockId && (
          <p className="text-muted-foreground py-8 text-center text-sm">
            选中段落以添加评论
          </p>
        )}
      </div>
    </div>
  );
}
