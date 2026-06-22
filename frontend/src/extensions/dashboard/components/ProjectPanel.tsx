"use client";

import { FolderGit, Layers, Server, Activity } from "lucide-react";
import Link from "next/link";

import { useMyProjects } from "../hooks/useMyProjects";
import { cn } from "@/lib/utils";

export function ProjectPanel() {
  const { data, isLoading } = useMyProjects();

  if (isLoading) {
    return (
      <div className="db-card rounded-xl p-4 md:p-6 relative">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-48 bg-slate-200 rounded" />
          <div className="h-24 bg-slate-100 rounded-lg" />
        </div>
      </div>
    );
  }

  const allProjects = data?.groups ? Object.values(data.groups).flat() : [];
  const totalCount = data?.total_count ?? 0;

  return (
    <div className="db-card rounded-xl p-4 md:p-6 relative flex flex-col h-full overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-blue-500/20 to-transparent" />
      <div className="absolute bottom-0 right-0 w-3 h-3 bg-purple-500/20 clip-corners" />

      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-500/10 border border-purple-500/20 text-purple-500 rounded-md">
            <Layers className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            我的项目 <span className="text-xs font-normal text-slate-500">Project Nodes</span>
          </h2>
        </div>
        <span className="text-xs text-purple-500 font-cyber">{totalCount} total</span>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[350px] pr-1.5 flex flex-col gap-4">
        {allProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <div className="w-16 h-16 rounded-full bg-slate-400/10 border border-slate-400/20 flex items-center justify-center mb-3 text-slate-500">
              <FolderGit className="w-8 h-8" />
            </div>
            <h3 className="text-sm font-semibold text-slate-500">暂无项目</h3>
            <p className="text-[10px] text-slate-500 font-mono-db mt-1">NO ACTIVE WORKSPACE PROJECTS LOADED</p>
            <Link href="/projects?action=create"
              className="mt-4 px-3 py-1.5 bg-purple-500/15 text-purple-600 hover:text-purple-500 rounded border border-purple-500/20 text-xs hover:border-purple-500/40 transition-all cursor-pointer font-bold">
              创建新项目
            </Link>
          </div>
        ) : (
          allProjects.map(proj => (
            <Link key={proj.project_id} href={`/projects/${proj.project_id}`}
              className="p-4 border border-[var(--db-border-color-muted)] hover:border-purple-500/30 bg-slate-400/5 hover:bg-slate-400/10 rounded-lg group transition-all duration-200 block no-underline">
              <div className="flex items-start justify-between gap-3 mb-2.5">
                <div className="min-w-0">
                  <h3 className="text-sm font-bold db-text-primary tracking-wide truncate group-hover:text-purple-600 transition-colors">
                    {proj.project_name}
                  </h3>
                  <p className="text-[11px] text-slate-500 mt-0.5 max-w-[420px] leading-normal line-clamp-2">
                    {proj.role_label}{proj.current_phase ? ` · ${proj.current_phase}` : ""}
                  </p>
                </div>
                <div className="relative w-12 h-12 flex-shrink-0 flex items-center justify-center">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle cx="24" cy="24" r="19" className="text-slate-200" strokeWidth="3.5" stroke="currentColor" fill="transparent" />
                    <circle cx="24" cy="24" r="19" className="text-purple-500 glow-purple" strokeWidth="3.5"
                      strokeDasharray={`${2 * Math.PI * 19}`}
                      strokeDashoffset={`${2 * Math.PI * 19 * (1 - (proj.progress_pct ?? 0) / 100)}`}
                      strokeLinecap="round" stroke="currentColor" fill="transparent" />
                  </svg>
                  <span className="absolute text-[10px] font-bold db-text-primary font-cyber">{proj.progress_pct ?? 0}%</span>
                </div>
              </div>
              <div className="w-full h-1 bg-slate-200 rounded-full overflow-hidden mb-3.5">
                <div className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 glow-purple transition-all duration-1000"
                  style={{ width: `${proj.progress_pct ?? 0}%` }} />
              </div>
              <div className="flex items-center justify-between text-[11px] font-cyber text-slate-500 border-t border-[var(--db-border-color-muted)] pt-2.5">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5">
                    <Server className="w-3 h-3 text-slate-400" />
                    进度: <span className="db-text-primary font-bold">{proj.progress_pct ?? 0}%</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Activity className="w-3 h-3 text-slate-400" />
                    状态: <span className="text-purple-500 font-bold uppercase">{proj.status}</span>
                  </span>
                </div>
                <span className={cn(
                  "px-2 py-0.5 rounded text-[9px] uppercase font-bold border",
                  proj.status === "writing" ? "bg-blue-500/10 border-blue-500/20 text-blue-600" :
                  proj.status === "review" ? "bg-amber-500/10 border-amber-500/20 text-amber-600 shadow-[0_0_8px_rgba(245,158,11,0.1)]" :
                  proj.status === "completed" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600" :
                  "bg-slate-100 border-slate-200 text-slate-500"
                )}>
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
