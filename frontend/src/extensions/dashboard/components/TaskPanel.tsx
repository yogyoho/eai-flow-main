"use client";

import { CheckCircle2, ListChecks, Circle, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useMyTasks } from "../hooks/useMyTasks";

export function TaskPanel() {
  const { data, isLoading } = useMyTasks();
  const [activeTab, setActiveTab] = useState<"pending" | "completed">(
    "pending",
  );
  const tasks = data?.tasks ?? [];
  const pendingCount = tasks.length; // ponytail: task.type union has no 'completed' — every task is pending
  const filteredTasks = activeTab === "completed" ? [] : tasks;

  if (isLoading) {
    return (
      <div className="db-card relative rounded-xl p-4 md:p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-48 rounded bg-slate-200" />
          <div className="h-16 rounded-lg bg-slate-100" />
          <div className="h-16 rounded-lg bg-slate-100" />
        </div>
      </div>
    );
  }

  return (
    <div className="db-card relative flex h-full flex-col overflow-hidden rounded-xl p-4 md:p-6">
      <div className="clip-corners absolute top-0 right-0 h-3 w-3 bg-blue-500/20" />

      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="rounded-md border border-blue-500/20 bg-blue-500/10 p-1.5 text-blue-500">
            <ListChecks className="h-4 w-4" />
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            我的待办{" "}
            <span className="text-xs font-normal text-slate-500">
              My Task Matrix
            </span>
          </h2>
        </div>
        <div className="font-cyber flex items-center gap-2 text-xs">
          <button
            onClick={() => setActiveTab("pending")}
            className={`cursor-pointer rounded px-2.5 py-1 transition-all ${activeTab === "pending" ? "border border-blue-500/30 bg-blue-500/15 font-bold text-blue-600" : "text-slate-500 hover:text-slate-700"}`}
          >
            待办 ({pendingCount})
          </button>
          <button
            onClick={() => setActiveTab("completed")}
            className={`cursor-pointer rounded px-2.5 py-1 transition-all ${activeTab === "completed" ? "border border-emerald-500/30 bg-emerald-500/15 font-bold text-emerald-600" : "text-slate-500 hover:text-slate-700"}`}
          >
            已完成 ({tasks.length - pendingCount})
          </button>
        </div>
      </div>

      <div className="flex max-h-[320px] flex-1 flex-col gap-2.5 overflow-y-auto pr-1.5">
        {filteredTasks.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
            <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
              <CheckCircle2 className="h-8 w-8 animate-pulse text-emerald-500" />
            </div>
            <h3 className="text-sm font-bold tracking-wide text-emerald-600">
              所有任务已完成
            </h3>
            <p className="font-mono-db mt-1 text-xs text-slate-500">
              ALL PROTOCOLS VERIFIED // 0 QUEUED
            </p>
          </div>
        ) : (
          filteredTasks.map((task) => (
            <div
              key={task.id}
              className="group flex items-start justify-between gap-3 rounded-lg border border-[var(--db-border-color-muted)] bg-slate-400/5 p-3 shadow-sm transition-colors hover:border-slate-400/40 hover:bg-slate-400/10"
            >
              <div className="flex min-w-0 items-start gap-2.5">
                <Circle className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400 group-hover:text-blue-500" />
                <div className="min-w-0">
                  <p className="db-text-primary text-xs leading-relaxed font-semibold">
                    {task.action_label}
                  </p>
                  <p className="font-mono-db mt-0.5 max-w-[280px] truncate text-[10px] text-slate-500">
                    {task.project_name}
                    {task.chapter_title ? ` · ${task.chapter_title}` : ""}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span
                      className={`font-cyber rounded border px-1.5 py-0.5 text-[9px] uppercase ${task.is_urgent ? "border-red-500 bg-red-500/10 text-red-500 shadow-[0_0_8px_rgba(239,68,68,0.2)]" : "border-amber-500 bg-amber-500/10 text-amber-600"}`}
                    >
                      {task.is_urgent
                        ? "URGENT"
                        : task.is_blocking
                          ? "BLOCKING"
                          : "NORMAL"}
                    </span>
                    <span className="font-cyber rounded bg-slate-400/10 px-1.5 py-0.5 text-[9px] text-slate-500 uppercase">
                      {task.type}
                    </span>
                  </div>
                </div>
              </div>
              {task.action_url && (
                <Link
                  href={task.action_url}
                  className="flex-shrink-0 cursor-pointer rounded p-1 text-slate-400 opacity-0 transition-all group-hover:opacity-100 hover:bg-slate-400/10 hover:text-blue-500"
                >
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
