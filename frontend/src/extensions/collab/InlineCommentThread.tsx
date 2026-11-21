"use client";

import { X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { CollabComment } from "../types";

import { CommentThread } from "./CommentThread";

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
    <div className="bg-background border-border absolute top-0 right-0 z-50 flex max-h-96 w-72 flex-col rounded-lg border shadow-lg">
      <div className="border-border flex items-center justify-between border-b p-2">
        <span className="text-muted-foreground text-xs font-medium">评论</span>
        <Button
          size="icon"
          variant="ghost"
          className="h-5 w-5"
          onClick={onClose}
        >
          <X className="h-3 w-3" />
        </Button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-2">
        <CommentThread
          comments={comments}
          onReply={onReply}
          onResolve={onResolve}
          onReopen={onReopen}
          onDelete={onDelete}
        />
      </div>

      <div className="border-border border-t p-2">
        <Textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="添加回复..."
          className="min-h-[40px] resize-none text-xs"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
              void handleCreate();
          }}
        />
        <Button
          size="sm"
          className="mt-1 h-7 w-full text-xs"
          onClick={handleCreate}
          disabled={submitting || !newComment.trim()}
        >
          回复
        </Button>
      </div>
    </div>
  );
}
