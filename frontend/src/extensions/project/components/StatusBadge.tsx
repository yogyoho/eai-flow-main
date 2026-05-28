"use client";

import { CheckCircle2, Clock, Loader2, AlertCircle, Pencil } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  type: "project" | "chapter";
}

const STATUS_CONFIG: Record<string, { color: string; icon?: React.ReactNode }> = {
  // Project statuses
  planning: { color: "border-[#E2E8F0] bg-[#F9FAFB] text-[#94A3B8]", icon: <Clock className="h-3 w-3" /> },
  writing: {
    color: "border-[#0746FF]/20 bg-[#EBF0FF] text-[#0746FF]",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  review: { color: "border-[#F59E0B]/20 bg-[#FFFBEB] text-[#F59E0B]", icon: <Clock className="h-3 w-3" /> },
  finalizing: { color: "border-[#10B981]/20 bg-[#ECFDF5] text-[#10B981]", icon: <CheckCircle2 className="h-3 w-3" /> },
  archived: { color: "border-[#10B981]/20 bg-[#ECFDF5] text-[#10B981]", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Chapter statuses
  not_started: { color: "border-[#E2E8F0] bg-[#F9FAFB] text-[#94A3B8]", icon: <Clock className="h-3 w-3" /> },
  pending_review: {
    color: "border-[#F59E0B]/20 bg-[#FFFBEB] text-[#F59E0B]",
    icon: <Clock className="h-3 w-3" />,
  },
  approved: { color: "border-[#10B981]/20 bg-[#ECFDF5] text-[#10B981]", icon: <CheckCircle2 className="h-3 w-3" /> },
  signed: { color: "border-[#10B981]/20 bg-[#ECFDF5] text-[#10B981]", icon: <CheckCircle2 className="h-3 w-3" /> },

  // Error states
  error: { color: "border-[#EF4444]/20 bg-[#FEF2F2] text-[#EF4444]", icon: <AlertCircle className="h-3 w-3" /> },
  failed: { color: "border-[#EF4444]/20 bg-[#FEF2F2] text-[#EF4444]", icon: <AlertCircle className="h-3 w-3" /> },
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
  let config = STATUS_CONFIG[status] ?? STATUS_CONFIG.error!;
  const label = STATUS_LABELS[status] ?? status;

  // Chapter "writing" uses Pencil icon instead of spinning Loader2
  if (type === "chapter" && status === "writing") {
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
