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

export function ProjectMiniCard({ project }: { project: MyProjectItem }) {
  return (
    <div className="rounded-lg border p-3 hover:bg-accent/50 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <Link
          href={`/projects/${project.project_id}`}
          className="text-sm font-medium hover:underline truncate"
        >
          {project.project_name}
        </Link>
        <span className="text-xs px-2 py-0.5 rounded-full bg-secondary shrink-0">
          {ROLE_LABELS[project.role_label] || project.role_label}
        </span>
      </div>
      {project.current_phase && (
        <p className="text-xs text-muted-foreground mb-1">
          阶段: {project.current_phase} ·{" "}
          {project.status === "in_progress" ? "进行中" : project.status}
        </p>
      )}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-secondary overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
        <span className="text-xs text-muted-foreground">{project.progress_pct}%</span>
      </div>
      {project.pending_task_count > 0 && (
        <p className="text-xs text-muted-foreground mt-1">
          待办: {project.pending_task_count}
        </p>
      )}
    </div>
  );
}
