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
  const roleBadgeClass =
    ROLE_COLORS[project.role_label] ?? "bg-muted text-muted-foreground";

  return (
    <Link
      href={`/projects/${project.project_id}`}
      className="bg-card hover:border-primary/20 block rounded-lg border px-4 py-3 transition-all hover:shadow-md"
    >
      <div className="flex items-center gap-3">
        {/* Avatar */}
        <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium">
          {firstChar}
        </div>
        {/* Name + phase */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-sm font-medium">
              {project.project_name}
            </p>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${roleBadgeClass}`}
            >
              {ROLE_LABELS[project.role_label] ?? project.role_label}
            </span>
          </div>
          {project.current_phase && (
            <p className="text-muted-foreground mt-0.5 text-xs">
              {project.current_phase}
            </p>
          )}
        </div>
      </div>
      {/* Progress bar */}
      <div className="mt-2 ml-11 flex items-center gap-2">
        <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full rounded-full transition-all"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
        <span className="text-muted-foreground shrink-0 text-xs">
          {project.progress_pct}%
        </span>
      </div>
      {project.pending_task_count > 0 && (
        <p className="text-muted-foreground mt-1 ml-11 text-xs">
          {project.pending_task_count} 项待办
        </p>
      )}
    </Link>
  );
}
