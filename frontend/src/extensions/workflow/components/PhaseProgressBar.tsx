"use client";

import { CheckCircle2, Circle, Loader2, AlertCircle } from "lucide-react";

import type { WorkflowNodeStatus } from "@/extensions/workflow/types";
import { cn } from "@/lib/utils";

interface PhaseProgressBarProps {
  nodes: WorkflowNodeStatus[];
  graphVersion?: number;
}

/** A compact multi-phase progress bar for v2 workflows. */
export function PhaseProgressBar({ nodes, graphVersion = 1 }: PhaseProgressBarProps) {
  // For v2: group nodes by parent_phase_id to show phase → task hierarchy
  if (graphVersion === 2) {
    return <PhasePipeline nodes={nodes} />;
  }
  // V1: simple linear progress
  return <SimpleProgress nodes={nodes} />;
}

// ── V2 Phase Pipeline ──

function PhasePipeline({ nodes }: { nodes: WorkflowNodeStatus[] }) {
  // Group: phase nodes first, task nodes under their parent
  const phaseNodes = nodes.filter((n) => n.nodeType === "phase" || n.nodeType === "subflow");
  const taskNodes = nodes.filter((n) => n.parentPhaseId);

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case "running": return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case "error": return <AlertCircle className="w-4 h-4 text-red-500" />;
      default: return <Circle className="w-4 h-4 text-gray-300" />;
    }
  };

  if (phaseNodes.length === 0) {
    return <SimpleProgress nodes={nodes} />;
  }

  return (
    <div className="space-y-3">
      {phaseNodes.map((phase) => {
        const tasks = taskNodes.filter((t) => t.parentPhaseId === phase.nodeId);
        const completedTasks = tasks.filter((t) => t.status === "completed").length;
        const totalTasks = tasks.length;

        return (
          <div key={phase.nodeId} className="rounded-lg border border-border bg-card overflow-hidden">
            {/* Phase header */}
            <div className={cn(
              "flex items-center gap-2 px-3 py-2 text-sm font-medium",
              phase.status === "completed" ? "bg-green-50 text-green-700" :
              phase.status === "running" ? "bg-blue-50 text-blue-700" :
              "bg-muted/30 text-muted-foreground",
            )}>
              {statusIcon(phase.status)}
              <span className="flex-1 truncate">{phase.label}</span>
              {totalTasks > 0 && (
                <span className="text-xs tabular-nums">
                  {completedTasks}/{totalTasks}
                </span>
              )}
              {phase.chapterTotal != null && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {phase.chapterCompleted ?? 0}/{phase.chapterTotal} 章节
                </span>
              )}
            </div>
            {/* Task list */}
            {totalTasks > 0 && (
              <div className="divide-y divide-border/50">
                {tasks.map((task) => (
                  <div key={task.nodeId} className="flex items-center gap-2 px-4 py-1.5 text-xs">
                    {statusIcon(task.status)}
                    <span className="flex-1 truncate text-muted-foreground">{task.label}</span>
                    {task.nodeType === "review" && task.reviewTotal != null && (
                      <span className="text-[10px] tabular-nums text-muted-foreground">
                        {task.reviewApproved ?? 0}/{task.reviewTotal}
                        {task.reviewMode && ` (${task.reviewMode === "all" ? "会签" : task.reviewMode === "any" ? "或签" : task.reviewMode === "ratio" ? "比例" : "顺序"})`}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── V1 Simple Progress ──

function SimpleProgress({ nodes }: { nodes: WorkflowNodeStatus[] }) {
  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />;
      case "running": return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />;
      case "error": return <AlertCircle className="w-3.5 h-3.5 text-red-500" />;
      default: return <Circle className="w-3.5 h-3.5 text-gray-300" />;
    }
  };

  return (
    <div className="space-y-1">
      {nodes.map((n) => (
        <div key={n.nodeId} className="flex items-center gap-2 px-2 py-1 text-xs">
          {statusIcon(n.status)}
          <span className={cn("flex-1 truncate", n.status === "completed" ? "text-muted-foreground line-through" : "text-foreground")}>
            {n.label}
          </span>
          <span className="text-[10px] text-muted-foreground capitalize">{n.nodeType}</span>
        </div>
      ))}
    </div>
  );
}
