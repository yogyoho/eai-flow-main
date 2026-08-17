"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { CollabComment } from "../types";

interface CommentThreadProps {
  comments: CollabComment[];
  onReply: (parentId: string, content: string) => Promise<void>;
  onResolve: (commentId: string) => Promise<void>;
  onReopen: (commentId: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}

export function CommentThread({
  comments,
  onReply,
  onResolve,
  onReopen,
}: CommentThreadProps) {
  const [replyText, setReplyText] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const topLevel = comments.filter((c) => c.parent_id === null);
  const rootComment = topLevel[0];
  const replies = comments.filter((c) => c.parent_id !== null);

  if (!rootComment) return null;

  const handleReply = async () => {
    if (!replyText.trim() || !replyingTo) return;
    setSubmitting(true);
    try {
      await onReply(replyingTo, replyText.trim());
      setReplyText("");
      setReplyingTo(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <div
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-medium text-white"
          style={{ backgroundColor: "#6366f1" }}
        >
          {(rootComment.full_name ?? rootComment.username ?? "?")
            .charAt(0)
            .toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-2">
            <span className="text-sm font-medium">
              {rootComment.full_name ?? rootComment.username}
            </span>
            <span className="text-muted-foreground text-[10px]">
              {new Date(rootComment.created_at).toLocaleString("zh-CN", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
          <p className="text-foreground/90 text-sm whitespace-pre-wrap">
            {rootComment.content}
          </p>
          <div className="mt-1 flex gap-2">
            <button
              className="text-muted-foreground hover:text-foreground text-[10px]"
              onClick={() => setReplyingTo(rootComment.id)}
            >
              回复
            </button>
            {rootComment.resolved ? (
              <button
                className="text-muted-foreground hover:text-foreground text-[10px]"
                onClick={() => onReopen(rootComment.id)}
              >
                重新打开
              </button>
            ) : (
              <button
                className="text-muted-foreground hover:text-foreground text-[10px]"
                onClick={() => onResolve(rootComment.id)}
              >
                标记已解决
              </button>
            )}
          </div>
        </div>
      </div>

      {replies.map((reply) => (
        <div key={reply.id} className="ml-4 flex gap-2">
          <div
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-medium text-white"
            style={{ backgroundColor: "#8b5cf6" }}
          >
            {(reply.full_name ?? reply.username ?? "?").charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-2">
              <span className="text-xs font-medium">
                {reply.full_name ?? reply.username}
              </span>
              <span className="text-muted-foreground text-[10px]">
                {new Date(reply.created_at).toLocaleString("zh-CN", {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
            <p className="text-foreground/90 text-sm whitespace-pre-wrap">
              {reply.content}
            </p>
          </div>
        </div>
      ))}

      {replyingTo && (
        <div className="ml-4 flex gap-2">
          <Textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder="输入回复..."
            className="min-h-[60px] text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                void handleReply();
            }}
          />
          <div className="flex flex-col gap-1">
            <Button
              size="sm"
              onClick={handleReply}
              disabled={submitting || !replyText.trim()}
            >
              发送
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setReplyingTo(null);
                setReplyText("");
              }}
            >
              取消
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
