"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { CheckCircle2, Circle, Loader2, ShieldCheck, XCircle } from "lucide-react";

import type { DAGNodeData } from "../types";

type NodeStatus = "pending" | "running" | "completed" | "error";

interface ProgressReviewNodeData extends DAGNodeData {
  status?: NodeStatus;
  reviewTotal?: number | null;
  reviewApproved?: number | null;
}

const STATUS_CONFIG: Record<
  NodeStatus,
  {
    border: string;
    bg: string;
    icon: React.ReactNode;
    pulse: string;
    label: string;
    labelColor: string;
  }
> = {
  completed: {
    border: "border-green-400",
    bg: "bg-green-50",
    icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
    pulse: "",
    label: "已通过",
    labelColor: "text-green-600",
  },
  running: {
    border: "border-blue-400",
    bg: "bg-blue-50",
    icon: <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />,
    pulse: "animate-pulse-ring",
    label: "审核中",
    labelColor: "text-blue-600",
  },
  pending: {
    border: "border-gray-300",
    bg: "bg-gray-50/50",
    icon: <Circle className="h-4 w-4 text-gray-400" />,
    pulse: "",
    label: "待审核",
    labelColor: "text-gray-500",
  },
  error: {
    border: "border-red-400",
    bg: "bg-red-50",
    icon: <XCircle className="h-4 w-4 text-red-500" />,
    pulse: "",
    label: "已驳回",
    labelColor: "text-red-600",
  },
};

export function ProgressReviewNode({ data }: NodeProps & { data: ProgressReviewNodeData }) {
  const status: NodeStatus = (data.status as NodeStatus) ?? "pending";
  const cfg = STATUS_CONFIG[status];
  const total = data.reviewTotal ?? 0;
  const approved = data.reviewApproved ?? 0;
  const pct = total > 0 ? Math.round((approved / total) * 100) : 0;

  // Use ShieldCheck for approval-type review nodes
  const isApproval = data.label?.includes("审批");
  const typeIcon = isApproval ? <ShieldCheck className="h-3 w-3 text-amber-600 mr-1" /> : null;

  return (
    <div
      className={`px-3.5 py-2.5 rounded-lg border-2 min-w-[160px] ${cfg.border} ${cfg.bg} ${cfg.pulse} transition-colors`}
    >
      <Handle type="target" position={Position.Top} className="!bg-red-400 !w-2 !h-2" />

      {/* Header */}
      <div className="flex items-center gap-1.5">
        {cfg.icon}
        <span className="text-xs font-semibold text-foreground truncate flex-1 flex items-center">
          {typeIcon}
          {data.label || "审核"}
        </span>
        <span className={`text-[10px] font-medium ${cfg.labelColor}`}>{cfg.label}</span>
      </div>

      {/* Review progress */}
      {total > 0 && (
        <div className="mt-2 space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">
              通过: {approved}/{total}
            </span>
            <span className="text-[10px] font-medium text-muted-foreground">{pct}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-gray-200 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${pct}%`,
                backgroundColor: status === "completed" ? "#22c55e" : status === "running" ? "#3b82f6" : "#9ca3af",
              }}
            />
          </div>
        </div>
      )}

      {/* Review mode */}
      {data.mode && (
        <div className="text-[10px] text-muted-foreground mt-1.5">
          模式: {data.mode === "chapter" ? "章节" : data.mode === "dimension" ? "维度" : "混合"}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-red-400 !w-2 !h-2" />
    </div>
  );
}
