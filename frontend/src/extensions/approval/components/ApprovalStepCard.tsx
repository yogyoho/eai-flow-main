"use client";

import { cn } from "@/lib/utils";
import { Check, Loader2, XCircle, Circle } from "lucide-react";
import type { ApprovalStep } from "../types";

interface ApprovalStepCardProps {
  step: ApprovalStep;
  status: "pending" | "current" | "completed" | "rejected";
  reviewerName?: string;
}

const statusConfig = {
  completed: {
    circleClass: "bg-green-500 text-white border-green-500",
    icon: Check,
    statusText: "已通过",
  },
  current: {
    circleClass: "bg-primary text-primary-foreground border-primary",
    icon: Loader2,
    iconClass: "animate-spin",
    statusText: "审批中",
  },
  pending: {
    circleClass: "bg-muted text-muted-foreground border-muted-foreground/30",
    icon: Circle,
    statusText: "待审批",
  },
  rejected: {
    circleClass: "bg-destructive text-white border-destructive",
    icon: XCircle,
    statusText: "已退回",
  },
} as const;

export function ApprovalStepCard({
  step,
  status,
  reviewerName,
}: ApprovalStepCardProps) {
  const config = statusConfig[status];
  const IconComponent = config.icon;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl border border-border bg-background p-4",
        status === "current" && "ring-2 ring-primary/30"
      )}
    >
      {/* Step number circle */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
          config.circleClass
        )}
      >
        <IconComponent className={cn("h-4 w-4", "iconClass" in config && config.iconClass)} />
      </div>

      {/* Step info */}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{step.name}</span>
          <span className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-muted text-muted-foreground">
            {step.requiredRole}
          </span>
        </div>
        {reviewerName && (
          <span className="text-xs text-muted-foreground">
            审批人：{reviewerName}
          </span>
        )}
      </div>

      {/* Status text */}
      <span
        className={cn(
          "shrink-0 text-xs font-medium",
          status === "completed" && "text-green-600",
          status === "current" && "text-primary",
          status === "pending" && "text-muted-foreground",
          status === "rejected" && "text-destructive"
        )}
      >
        {config.statusText}
      </span>
    </div>
  );
}
