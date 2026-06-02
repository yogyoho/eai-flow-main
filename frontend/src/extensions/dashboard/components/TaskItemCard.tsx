"use client";

import Link from "next/link";
import { Eye, Pen, ArrowRight, AlertTriangle, ChevronRight } from "lucide-react";
import type { TaskItem } from "../types";

const TYPE_ICONS = {
  review: Eye,
  writing: Pen,
  phase_lead: ArrowRight,
  ai_writing: Pen,
  rejection: AlertTriangle,
} as const;

const TYPE_LABELS: Record<string, string> = {
  review: "待审核",
  writing: "撰写中",
  phase_lead: "阶段推进",
  ai_writing: "AI撰写",
  rejection: "被驳回",
};

export function TaskItemCard({ task }: { task: TaskItem }) {
  const Icon = TYPE_ICONS[task.type] || Eye;
  const isUrgent = task.is_urgent || (task.priority_score ?? 0) >= 50;

  return (
    <div
      className={`rounded-lg border-l-[3px] px-4 py-3 hover:bg-accent/30 transition-colors ${
        isUrgent ? "border-l-red-500 bg-red-50/30" : "border-l-primary"
      }`}
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <p className="text-sm font-medium truncate flex-1">
          {task.chapter_title || task.phase_label || task.action_label}
        </p>
        <span className="text-xs px-1.5 py-0.5 rounded bg-muted shrink-0">
          {TYPE_LABELS[task.type] || task.action_label}
        </span>
        <Link
          href={task.action_url}
          className="text-muted-foreground hover:text-primary shrink-0"
        >
          <ChevronRight className="h-4 w-4" />
        </Link>
      </div>
      <p className="text-xs text-muted-foreground mt-1 ml-6">
        {task.project_name}
        {task.due_date && (
          <> · 截止: {new Date(task.due_date).toLocaleDateString()}</>
        )}
      </p>
    </div>
  );
}
