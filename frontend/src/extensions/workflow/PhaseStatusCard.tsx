"use client";

import type { WorkflowNodeStatus } from "./types";

interface PhaseStatusCardProps {
  node: WorkflowNodeStatus;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "border-muted bg-muted/20",
  running: "border-blue-300 bg-blue-50",
  completed: "border-green-300 bg-green-50",
  error: "border-red-300 bg-red-50",
};

const STATUS_ICONS: Record<string, string> = {
  pending: "○",
  running: "◉",
  completed: "✓",
  error: "✗",
};

const NODE_TYPE_COLORS: Record<string, string> = {
  phase: "text-blue-600",
  review: "text-amber-600",
  condition: "text-purple-600",
  ai_generate: "text-cyan-600",
  merge: "text-gray-600",
};

export function PhaseStatusCard({ node }: PhaseStatusCardProps) {
  const style = STATUS_STYLES[node.status] ?? STATUS_STYLES.pending;
  const icon = STATUS_ICONS[node.status] ?? "○";
  const typeColor = NODE_TYPE_COLORS[node.nodeType] ?? "text-foreground";

  return (
    <div className={`rounded-lg border p-3 ${style}`}>
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className={`truncate text-sm font-medium ${typeColor}`}>
            {node.label}
          </div>
          <div className="text-muted-foreground text-[10px]">
            {node.nodeType} · {node.nodeId}
          </div>
        </div>
        <span className="text-muted-foreground text-[10px] font-medium uppercase">
          {node.status}
        </span>
      </div>
    </div>
  );
}
