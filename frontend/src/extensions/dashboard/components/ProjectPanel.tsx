"use client";

import { FolderGit, Layers, Server, Activity } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import { useMyProjects } from "../hooks/useMyProjects";

export function ProjectPanel() {
  const { data, isLoading } = useMyProjects();

  if (isLoading) {
    return (
      <div className="db-card relative rounded-xl p-4 md:p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-48 rounded bg-slate-200" />
          <div className="h-24 rounded-lg bg-slate-100" />
        </div>
      </div>
    );
  }

  const allProjects = data?.groups ? Object.values(data.groups).flat() : [];
  const totalCount = data?.total_count ?? 0;

  return (
    <div className="db-card relative flex h-full flex-col overflow-hidden rounded-xl p-4 md:p-6">
      <div className="absolute top-0 left-0 h-[1px] w-full bg-gradient-to-r from-transparent via-blue-500/20 to-transparent" />
      <div className="clip-corners absolute right-0 bottom-0 h-3 w-3 bg-purple-500/20" />

      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="rounded-md border border-purple-500/20 bg-purple-500/10 p-1.5 text-purple-500">
            <Layers className="h-4 w-4" />
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            我的项目{" "}
            <span className="text-xs font-normal text-slate-500">
              Project Nodes
            </span>
          </h2>
        </div>
        <span className="font-cyber text-xs text-purple-500">
          {totalCount} total
        </span>
      </div>

      <div className="flex max-h-[350px] flex-1 flex-col gap-4 overflow-y-auto pr-1.5">
        {allProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-full border border-slate-400/20 bg-slate-400/10 text-slate-500">
              <FolderGit className="h-8 w-8" />
            </div>
            <h3 className="text-sm font-semibold text-slate-500">暂无项目</h3>
            <p className="font-mono-db mt-1 text-[10px] text-slate-500">
              NO ACTIVE WORKSPACE PROJECTS LOADED
            </p>
            <Link
              href="/projects?action=create"
              className="mt-4 cursor-pointer rounded border border-purple-500/20 bg-purple-500/15 px-3 py-1.5 text-xs font-bold text-purple-600 transition-all hover:border-purple-500/40 hover:text-purple-500"
            >
              创建新项目
            </Link>
          </div>
        ) : (
          allProjects.map((proj) => (
            <Link
              key={proj.project_id}
              href={`/projects/${proj.project_id}`}
              className="group block rounded-lg border border-[var(--db-border-color-muted)] bg-slate-400/5 p-4 no-underline transition-all duration-200 hover:border-purple-500/30 hover:bg-slate-400/10"
            >
              <div className="mb-2.5 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="db-text-primary truncate text-sm font-bold tracking-wide transition-colors group-hover:text-purple-600">
                    {proj.project_name}
                  </h3>
                  <p className="mt-0.5 line-clamp-2 max-w-[420px] text-[11px] leading-normal text-slate-500">
                    {proj.role_label}
                    {proj.current_phase ? ` · ${proj.current_phase}` : ""}
                  </p>
                </div>
                <div className="relative flex h-12 w-12 flex-shrink-0 items-center justify-center">
                  <svg className="h-full w-full -rotate-90 transform">
                    <circle
                      cx="24"
                      cy="24"
                      r="19"
                      className="text-slate-200"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="transparent"
                    />
                    <circle
                      cx="24"
                      cy="24"
                      r="19"
                      className="glow-purple text-purple-500"
                      strokeWidth="3.5"
                      strokeDasharray={`${2 * Math.PI * 19}`}
                      strokeDashoffset={`${2 * Math.PI * 19 * (1 - (proj.progress_pct ?? 0) / 100)}`}
                      strokeLinecap="round"
                      stroke="currentColor"
                      fill="transparent"
                    />
                  </svg>
                  <span className="db-text-primary font-cyber absolute text-[10px] font-bold">
                    {proj.progress_pct ?? 0}%
                  </span>
                </div>
              </div>
              <div className="mb-3.5 h-1 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="glow-purple h-full bg-gradient-to-r from-purple-500 to-indigo-500 transition-all duration-1000"
                  style={{ width: `${proj.progress_pct ?? 0}%` }}
                />
              </div>
              <div className="font-cyber flex items-center justify-between border-t border-[var(--db-border-color-muted)] pt-2.5 text-[11px] text-slate-500">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5">
                    <Server className="h-3 w-3 text-slate-400" />
                    进度:{" "}
                    <span className="db-text-primary font-bold">
                      {proj.progress_pct ?? 0}%
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Activity className="h-3 w-3 text-slate-400" />
                    状态:{" "}
                    <span className="font-bold text-purple-500 uppercase">
                      {proj.status}
                    </span>
                  </span>
                </div>
                <span
                  className={cn(
                    "rounded border px-2 py-0.5 text-[9px] font-bold uppercase",
                    proj.status === "writing"
                      ? "border-blue-500/20 bg-blue-500/10 text-blue-600"
                      : proj.status === "review"
                        ? "border-amber-500/20 bg-amber-500/10 text-amber-600 shadow-[0_0_8px_rgba(245,158,11,0.1)]"
                        : proj.status === "completed"
                          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
                          : "border-slate-200 bg-slate-100 text-slate-500",
                  )}
                >
                  {proj.status}
                </span>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
