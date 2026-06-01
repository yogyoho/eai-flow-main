"use client";

import type { WorkflowNodeStatus } from "./types";

interface TimelineViewProps {
  nodes: WorkflowNodeStatus[];
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-muted",
  running: "bg-blue-500",
  completed: "bg-green-500",
  error: "bg-red-500",
};

const STATUS_STROKE: Record<string, string> = {
  pending: "border-muted-foreground/30",
  running: "border-blue-400",
  completed: "border-green-400",
  error: "border-red-400",
};

const ICONS: Record<string, string> = {
  phase: "⬡",
  review: "✓",
  condition: "◇",
  ai_generate: "✦",
  merge: "◎",
};

export function TimelineView({ nodes }: TimelineViewProps) {
  if (nodes.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        暂无工作流节点
      </div>
    );
  }

  return (
    <div className="relative py-2">
      {/* Vertical connector line */}
      <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

      <div className="space-y-0">
        {nodes.map((node, idx) => {
          const isLast = idx === nodes.length - 1;
          const color = STATUS_COLORS[node.status] || STATUS_COLORS.pending;
          const stroke = STATUS_STROKE[node.status] || STATUS_STROKE.pending;
          const icon = ICONS[node.nodeType] || "●";

          return (
            <div key={node.nodeId} className="relative flex items-start gap-3 py-3">
              {/* Timeline dot */}
              <div
                className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 ${stroke} ${color} text-white text-sm`}
              >
                {icon}
              </div>

              {/* Content */}
              <div className={`flex-1 min-w-0 ${isLast ? "" : "pb-1"}`}>
                <div className="text-sm font-medium truncate">
                  {node.label}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-muted-foreground uppercase">
                    {node.nodeType}
                  </span>
                  <span className="text-[10px] text-muted-foreground">·</span>
                  <span
                    className={`text-[10px] font-medium ${
                      node.status === "completed"
                        ? "text-green-600"
                        : node.status === "running"
                          ? "text-blue-600"
                          : node.status === "error"
                            ? "text-red-600"
                            : "text-muted-foreground"
                    }`}
                  >
                    {node.status === "pending" && "待启动"}
                    {node.status === "running" && "执行中"}
                    {node.status === "completed" && "已完成"}
                    {node.status === "error" && "错误"}
                  </span>
                </div>
                {node.startedAt && (
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    开始: {new Date(node.startedAt).toLocaleString()}
                  </div>
                )}
                {node.completedAt && (
                  <div className="text-[10px] text-muted-foreground">
                    完成: {new Date(node.completedAt).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
