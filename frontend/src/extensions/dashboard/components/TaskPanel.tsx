"use client";

import { CheckCircle2, ListChecks, Circle, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useMyTasks } from "../hooks/useMyTasks";

export function TaskPanel() {
  const { data, isLoading } = useMyTasks();
  const [activeTab, setActiveTab] = useState<"pending" | "completed">("pending");
  const tasks = data?.tasks ?? [];
  const pendingCount = tasks.filter(t => t.type !== "completed").length; // ponytail: all shown tasks are pending in our system
  const filteredTasks = activeTab === "completed" ? [] : tasks;

  if (isLoading) {
    return (
      <div className="db-card rounded-xl p-4 md:p-6 relative">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-48 bg-slate-200 rounded" />
          <div className="h-16 bg-slate-100 rounded-lg" />
          <div className="h-16 bg-slate-100 rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="db-card rounded-xl p-4 md:p-6 relative flex flex-col h-full overflow-hidden">
      <div className="absolute top-0 right-0 w-3 h-3 bg-blue-500/20 clip-corners" />

      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
            <ListChecks className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            我的待办 <span className="text-xs font-normal text-slate-500">My Task Matrix</span>
          </h2>
        </div>
        <div className="flex items-center gap-2 font-cyber text-xs">
          <button onClick={() => setActiveTab("pending")}
            className={`px-2.5 py-1 rounded transition-all cursor-pointer ${activeTab === "pending" ? "bg-blue-500/15 border border-blue-500/30 text-blue-600 font-bold" : "text-slate-500 hover:text-slate-700"}`}>
            待办 ({pendingCount})
          </button>
          <button onClick={() => setActiveTab("completed")}
            className={`px-2.5 py-1 rounded transition-all cursor-pointer ${activeTab === "completed" ? "bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 font-bold" : "text-slate-500 hover:text-slate-700"}`}>
            已完成 ({tasks.length - pendingCount})
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[320px] pr-1.5 flex flex-col gap-2.5">
        {filteredTasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center flex-1">
            <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-3 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
              <CheckCircle2 className="w-8 h-8 text-emerald-500 animate-pulse" />
            </div>
            <h3 className="text-sm font-bold text-emerald-600 tracking-wide">所有任务已完成</h3>
            <p className="text-xs text-slate-500 mt-1 font-mono-db">ALL PROTOCOLS VERIFIED // 0 QUEUED</p>
          </div>
        ) : (
          filteredTasks.map(task => (
            <div key={task.id}
              className="p-3 border border-[var(--db-border-color-muted)] hover:border-slate-400/40 bg-slate-400/5 hover:bg-slate-400/10 rounded-lg flex items-start justify-between gap-3 group transition-colors shadow-sm">
              <div className="flex items-start gap-2.5 min-w-0">
                <Circle className="w-4 h-4 mt-0.5 text-slate-400 group-hover:text-blue-500 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold leading-relaxed db-text-primary">{task.action_label}</p>
                  <p className="text-[10px] text-slate-500 font-mono-db mt-0.5 truncate max-w-[280px]">
                    {task.project_name}{task.chapter_title ? ` · ${task.chapter_title}` : ""}
                  </p>
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-cyber uppercase border ${task.is_urgent ? "border-red-500 bg-red-500/10 text-red-500 shadow-[0_0_8px_rgba(239,68,68,0.2)]" : "border-amber-500 bg-amber-500/10 text-amber-600"}`}>
                      {task.is_urgent ? "URGENT" : task.is_blocking ? "BLOCKING" : "NORMAL"}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-cyber bg-slate-400/10 text-slate-500 uppercase">{task.type}</span>
                  </div>
                </div>
              </div>
              {task.action_url && (
                <Link href={task.action_url} className="text-slate-400 hover:text-blue-500 p-1 rounded hover:bg-slate-400/10 opacity-0 group-hover:opacity-100 transition-all cursor-pointer flex-shrink-0">
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
