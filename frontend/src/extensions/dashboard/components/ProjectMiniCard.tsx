"use client";

import Link from "next/link";
import type { MyProjectItem } from "../types";

const ROLE_LABELS: Record<string, string> = {
  owner: "负责人",
  phase_lead: "阶段负责人",
  reviewer: "审核人",
  writer: "撰写人",
  viewer: "查看者",
};

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-primary/10 text-primary",
  phase_lead: "bg-purple-100 text-purple-700",
  reviewer: "bg-amber-100 text-amber-700",
  writer: "bg-blue-100 text-blue-700",
  viewer: "bg-muted text-muted-foreground",
};

export function ProjectMiniCard({ project }: { project: MyProjectItem }) {
  const firstChar = project.project_name.charAt(0).toUpperCase();
  const roleBadgeClass = ROLE_COLORS[project.role_label] || "bg-muted text-muted-foreground";

  return (
    <Link
      href={`/projects/${project.project_id}`}
      className="block rounded-lg border bg-card px-4 py-3 hover:shadow-md hover:border-primary/20 transition-all"
    >
      <div className="flex items-center gap-3">
        {/* Avatar */}
        <div className="h-8 w-8 rounded-full bg-primary/10 text-primary text-xs font-medium flex items-center justify-center shrink-0">
          {firstChar}
        </div>
        {/* Name + phase */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium truncate">{project.project_name}</p>
            <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${roleBadgeClass}`}>
              {ROLE_LABELS[project.role_label] || project.role_label}
            </span>
          </div>
          {project.current_phase && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {project.current_phase}
            </p>
          )}
        </div>
      </div>
      {/* Progress bar */}
      <div className="flex items-center gap-2 mt-2 ml-11">
        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{project.progress_pct}%</span>
      </div>
      {project.pending_task_count > 0 && (
        <p className="text-xs text-muted-foreground mt-1 ml-11">
          {project.pending_task_count} 项待办
        </p>
      )}
    </Link>
  );
}
