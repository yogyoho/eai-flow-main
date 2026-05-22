"use client";

import { CheckCircle2, Clock, Loader2, AlertCircle } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  type: "project" | "chapter";
}

const STATUS_CONFIG: Record<string, { color: string; icon?: React.ReactNode }> = {
  // Project statuses
  planning: { color: "border-border bg-muted text-muted-foreground", icon: <Clock className="h-3 w-3" /> },
  writing: {
    color: "border-primary/20 bg-primary/10 text-primary",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  review: { color: "border-amber-500/20 bg-amber-500/10 text-amber-600", icon: <Clock className="h-3 w-3" /> },
  finalizing: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },
  archived: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Chapter statuses
  not_started: { color: "border-border bg-muted text-muted-foreground", icon: <Clock className="h-3 w-3" /> },
  pending_review: {
    color: "border-amber-500/20 bg-amber-500/10 text-amber-600",
    icon: <Clock className="h-3 w-3" />,
  },
  approved: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },
  signed: { color: "border-success/20 bg-success/10 text-success", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Error states
  error: { color: "border-destructive/20 bg-destructive/10 text-destructive", icon: <AlertCircle className="h-3 w-3" /> },
  failed: { color: "border-destructive/20 bg-destructive/10 text-destructive", icon: <AlertCircle className="h-3 w-3" /> },
};

const STATUS_LABELS: Record<string, string> = {
  planning: "规划中",
  writing: "编写中",
  review: "审核中",
  finalizing: "定稿中",
  archived: "已归档",
  not_started: "未开始",
  pending_review: "待审核",
  approved: "已通过",
  signed: "已签发",
  error: "错误",
  failed: "失败",
};

export function StatusBadge({ status, type }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.error!;
  const label = STATUS_LABELS[status] ?? status;

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
