"use client";

import { Check, RotateCcw, MessageSquare, Loader2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

interface ApprovalActionProps {
  onAction: (action: "approve" | "reject" | "comment", comment: string) => void;
  loading: boolean;
}

export function ApprovalAction({ onAction, loading }: ApprovalActionProps) {
  const [comment, setComment] = useState("");

  const handleAction = (action: "approve" | "reject" | "comment") => {
    onAction(action, comment);
  };

  return (
    <div className="space-y-4">
      {/* Comment textarea */}
      <div>
        <label className="mb-1.5 block text-sm font-medium">审批意见</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="请输入审批意见..."
          rows={4}
          className="border-border bg-background placeholder:text-muted-foreground focus:ring-primary/30 w-full resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
        />
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-2">
        <button
          onClick={() => handleAction("approve")}
          disabled={loading}
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium",
            "bg-success text-success-foreground hover:bg-success/90 active:bg-success/80",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Check className="h-4 w-4" />
          )}
          通过
        </button>

        <button
          onClick={() => handleAction("reject")}
          disabled={loading}
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium",
            "border-destructive/30 bg-background text-destructive hover:bg-destructive/10 active:bg-destructive/20",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RotateCcw className="h-4 w-4" />
          )}
          退回修改
        </button>

        <button
          onClick={() => handleAction("comment")}
          disabled={loading || !comment.trim()}
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium",
            "text-muted-foreground hover:bg-muted active:bg-muted/80 bg-transparent",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          <MessageSquare className="h-4 w-4" />
          评论
        </button>
      </div>
    </div>
  );
}
