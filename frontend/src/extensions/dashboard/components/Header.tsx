"use client";

import {
  LayoutDashboard,
  Plus,
  BrainCircuit,
  FolderKanban,
  ListTodo,
} from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";

import { useAuth } from "@/extensions/hooks/useAuth";

import { useMyStats } from "../hooks/useMyStats";
import { useMyTasks } from "../hooks/useMyTasks";

function getGreeting() {
  const h = new Date().getHours();
  if (h < 6) return "凌晨好";
  if (h < 12) return "上午好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

export default function Header() {
  const { user } = useAuth();
  const { data: tasksData } = useMyTasks();
  const { data: statsData } = useMyStats();
  const [time, setTime] = useState("");
  const [millis, setMillis] = useState("");

  useEffect(() => {
    const t = setInterval(() => {
      const n = new Date();
      const y = n.getFullYear();
      const mo = String(n.getMonth() + 1).padStart(2, "0");
      const d = String(n.getDate()).padStart(2, "0");
      const hh = String(n.getHours()).padStart(2, "0");
      const mi = String(n.getMinutes()).padStart(2, "0");
      const ss = String(n.getSeconds()).padStart(2, "0");
      setTime(`${y}年${mo}月${d}日 ${hh}:${mi}:${ss}`);
      setMillis(String(n.getMilliseconds()).padStart(3, "0"));
    }, 100);
    return () => clearInterval(t);
  }, []);

  const displayName = user?.full_name ?? user?.username ?? "";
  const taskCount = tasksData?.total_count ?? 0;
  const projectCount = statsData?.projects_count ?? 0;

  return (
    <header className="scanlines relative z-10 w-full border-b border-blue-500/15 bg-white/90 p-4 shadow-[0_1px_10px_rgba(0,0,0,0.03)] backdrop-blur-md md:px-8 md:py-5 dark:border-cyan-500/15 dark:bg-slate-950/80">
      {/* Background glow node — dark only */}
      <div className="pointer-events-none absolute top-0 left-1/4 hidden h-24 w-1/3 rounded-full bg-cyan-500/10 blur-[100px] dark:block" />
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center rounded-lg border border-blue-200 bg-blue-50 p-3 text-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.15)] transition-colors dark:border-cyan-500/30 dark:bg-cyan-950/40 dark:text-cyan-400 dark:shadow-[0_0_12px_rgba(6,182,212,0.15)]">
            <LayoutDashboard className="h-6 w-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="text-xl font-bold tracking-tight text-slate-900 transition-colors md:text-2xl dark:text-white"
                suppressHydrationWarning
              >
                {getGreeting()},{" "}
                <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text font-extrabold text-transparent dark:from-cyan-400 dark:to-purple-400">
                  {displayName || "Administrator"}
                </span>
              </h1>
              <span className="font-cyber inline-flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-600 uppercase transition-colors dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400 dark:shadow-[0_0_8px_rgba(16,185,129,0.15)]">
                <span className="h-1.5 w-1.5 animate-ping rounded-full bg-emerald-400" />
                Secure Mode
              </span>
            </div>
            <p className="font-mono-db mt-1 flex items-center gap-2 text-xs text-slate-600 transition-colors md:text-sm dark:text-slate-400">
              <span className="text-blue-600 dark:text-cyan-400">
                ⚡ 系统就绪
              </span>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <span>
                {taskCount === 0 ? "所有任务已完成" : `待办任务: ${taskCount}`}
              </span>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <span
                className="font-cyber hidden sm:inline"
                suppressHydrationWarning
              >
                {time}
              </span>
              <span className="font-cyber hidden font-bold text-blue-600 sm:inline dark:text-cyan-400">
                .{millis} MS
              </span>
            </p>
          </div>
        </div>

        <div className="font-cyber hidden items-center gap-6 border-l border-slate-200 pl-6 text-xs text-slate-500 transition-colors lg:flex dark:border-slate-800 dark:text-slate-400">
          <div className="flex items-center gap-2">
            <FolderKanban className="h-4 w-4 text-blue-600 dark:text-cyan-400" />
            <div>
              <div className="text-[9px] tracking-wider uppercase">
                Active Projects
              </div>
              <div className="text-sm font-bold text-slate-900 dark:text-white">
                {projectCount}
                <span className="text-[10px] text-blue-600 dark:text-cyan-400">
                  {" "}
                  个
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ListTodo className="h-4 w-4 text-purple-600 dark:text-purple-400" />
            <div>
              <div className="text-[9px] tracking-wider uppercase">
                Pending Tasks
              </div>
              <div className="text-sm font-bold text-slate-900 dark:text-white">
                {taskCount}
                <span className="text-[10px] text-purple-600 dark:text-purple-400">
                  {" "}
                  项
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/projects?action=create"
            className="flex items-center gap-1.5 rounded-lg border border-blue-400/20 bg-gradient-to-r from-blue-600 to-blue-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg transition-all hover:shadow-blue-500/20 active:opacity-90 dark:border-cyan-400/20 dark:from-blue-600 dark:to-cyan-500 dark:hover:shadow-cyan-500/20"
          >
            <Plus className="h-4 w-4" />
            <span>新建项目</span>
          </Link>
          <Link
            href="/knowledge-factory"
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-100 px-4 py-2.5 text-sm font-semibold text-blue-700 transition-all hover:border-blue-500/40 hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-900/80 dark:text-cyan-300 dark:hover:border-cyan-500/40 dark:hover:bg-slate-800 dark:hover:text-cyan-200"
          >
            <BrainCircuit className="animate-spin-slow h-4 w-4 text-purple-600 dark:text-purple-400" />
            <span>知识加工</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
