"use client";

import Link from "next/link";
import { Eye, Pen, ArrowRight, AlertTriangle } from "lucide-react";
import type { TaskItem } from "../types";

const TYPE_ICONS = {
  review: Eye,
  writing: Pen,
  phase_lead: ArrowRight,
  ai_writing: Pen,
  rejection: AlertTriangle,
} as const;

function priorityColor(score: number) {
  if (score >= 50) return "text-red-500";
  if (score >= 30) return "text-amber-500";
  return "text-gray-400";
}

export function TaskItemCard({ task }: { task: TaskItem }) {
  const Icon = TYPE_ICONS[task.type] || Eye;

  return (
    <div className="flex items-center gap-3 rounded-lg border p-3 hover:bg-accent/50 transition-colors">
      <div className={priorityColor(task.priority_score)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">
          {task.action_label}: {task.chapter_title || task.phase_label || ""}
        </p>
        <p className="text-xs text-muted-foreground truncate">
          项目: {task.project_name}
          {task.due_date && ` · 截止: ${new Date(task.due_date).toLocaleDateString()}`}
        </p>
      </div>
      <Link
        href={task.action_url}
        className="text-xs text-primary hover:underline whitespace-nowrap"
      >
        {task.action_label} →
      </Link>
    </div>
  );
}
