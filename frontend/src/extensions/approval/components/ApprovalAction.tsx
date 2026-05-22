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
          className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-2">
        <button
          onClick={() => handleAction("approve")}
          disabled={loading}
          className={cn(
            "flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium",
            "bg-green-600 text-white hover:bg-green-700 active:bg-green-800",
            "disabled:opacity-50 disabled:cursor-not-allowed"
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
            "border-red-300 bg-background text-red-600 hover:bg-red-50 active:bg-red-100",
            "dark:border-red-800 dark:hover:bg-red-950",
            "disabled:opacity-50 disabled:cursor-not-allowed"
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
            "bg-transparent text-muted-foreground hover:bg-muted active:bg-muted/80",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          <MessageSquare className="h-4 w-4" />
          评论
        </button>
      </div>
    </div>
  );
}
