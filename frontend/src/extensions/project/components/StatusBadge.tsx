"use client";

import { CheckCircle2, Clock, Loader2, AlertCircle, Pencil } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  type: "project" | "chapter";
}

// EAI-CUSTOM: canonical statuses (ADR 2026-08-02 P4). Legacy aliases kept only
// during the transition so stale-fed badges still render sensibly.
const STATUS_CONFIG: Record<string, { color: string; icon?: React.ReactNode }> = {
  // Project statuses
  draft: {
    color: "border-primary/20 bg-primary/10 text-primary",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  in_review: { color: "border-warning/20 bg-warning/10 text-warning", icon: <Clock className="h-3 w-3" /> },
  approved: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },
  archived: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Chapter statuses
  pending: { color: "border-border bg-muted text-muted-foreground", icon: <Clock className="h-3 w-3" /> },
  reviewing: {
    color: "border-warning/20 bg-warning/10 text-warning",
    icon: <Clock className="h-3 w-3" />,
  },

  // Legacy aliases (transition shim)
  writing: {
    color: "border-primary/20 bg-primary/10 text-primary",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  review: { color: "border-warning/20 bg-warning/10 text-warning", icon: <Clock className="h-3 w-3" /> },
  signed: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Error states
  error: { color: "border-destructive/20 bg-destructive/10 text-destructive", icon: <AlertCircle className="h-3 w-3" /> },
  failed: { color: "border-destructive/20 bg-destructive/10 text-destructive", icon: <AlertCircle className="h-3 w-3" /> },
};

const STATUS_LABELS: Record<string, string> = {
  draft: "编写中",
  in_review: "审核中",
  approved: "已通过",
  archived: "已归档",
  pending: "未开始",
  reviewing: "审核中",
  writing: "编写中",
  review: "审核中",
  signed: "已签发",
  error: "错误",
  failed: "失败",
};

export function StatusBadge({ status, type }: StatusBadgeProps) {
  let config = STATUS_CONFIG[status] ?? STATUS_CONFIG.error!;
  const label = STATUS_LABELS[status] ?? status;

  // Chapter draft (writing) uses Pencil icon instead of spinning Loader2
  if (type === "chapter" && (status === "draft" || status === "writing")) {
    config = { ...config, icon: <Pencil className="h-3 w-3" /> };
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium border",
        config?.color,
      )}
    >
      {config?.icon}
      {label}
    </span>
  );
}
