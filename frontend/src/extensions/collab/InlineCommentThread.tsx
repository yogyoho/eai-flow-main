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
