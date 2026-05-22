"use client";

import { CheckCircle2, Clock, Loader2, AlertCircle } from "lucide-react";

import {
  MILESTONE_STATUS_LABELS,
  type Milestone,
  type MilestoneStatus,
} from "@/extensions/project/types";
import { cn } from "@/lib/utils";

const STATUS_CONFIG: Record<
  MilestoneStatus,
  { color: string; dotColor: string; icon: React.ReactNode; label: string }
> = {
  completed: {
    color: "text-success border-success/30 bg-success/5",
    dotColor: "bg-success",
    icon: <CheckCircle2 className="h-4 w-4 text-success" />,
    label: MILESTONE_STATUS_LABELS.completed,
  },
  overdue: {
    color: "text-destructive border-destructive/30 bg-destructive/5",
    dotColor: "bg-destructive",
    icon: <AlertCircle className="h-4 w-4 text-destructive" />,
    label: MILESTONE_STATUS_LABELS.overdue,
  },
  in_progress: {
    color: "text-primary border-primary/30 bg-primary/5",
    dotColor: "bg-primary",
    icon: <Loader2 className="h-4 w-4 text-primary animate-spin" />,
    label: MILESTONE_STATUS_LABELS.in_progress,
  },
  pending: {
    color: "text-muted-foreground border-border bg-muted/50",
    dotColor: "bg-muted-foreground",
    icon: <Clock className="h-4 w-4 text-muted-foreground" />,
    label: MILESTONE_STATUS_LABELS.pending,
  },
};

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

interface MilestoneTimelineProps {
  milestones: Milestone[];
}

export function MilestoneTimeline({ milestones }: MilestoneTimelineProps) {
  if (milestones.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        暂无里程碑
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {milestones.map((milestone, index) => {
        const config = STATUS_CONFIG[milestone.status];
        const isLast = index === milestones.length - 1;

        return (
          <div key={milestone.id} className="flex gap-4">
            {/* Left: vertical line + dot */}
            <div className="flex flex-col items-center shrink-0">
              <div
                className={cn(
                  "h-8 w-8 rounded-full flex items-center justify-center border-2 shrink-0",
                  config.color,
                )}
              >
                {config.icon}
              </div>
              {!isLast && (
                <div className="w-0.5 flex-1 bg-border min-h-[24px]" />
              )}
            </div>

            {/* Right: card */}
            <div className={cn("flex-1 pb-6", isLast && "pb-0")}>
              <div className="rounded-lg border border-border bg-background p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-foreground">
                    {milestone.name}
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium border",
                      config.color,
                    )}
                  >
                    {config.label}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  截止日期：{formatDate(milestone.dueDate)}
                  {milestone.completedAt && (
                    <span className="ml-2">
                      完成日期：{formatDate(milestone.completedAt)}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
