"use client";

import { useState, useEffect } from "react";
import { LayoutDashboard, Plus, BrainCircuit, FolderKanban, ListTodo } from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/extensions/hooks/useAuth";
import { useMyTasks } from "../hooks/useMyTasks";
import { useMyStats } from "../hooks/useMyStats";

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

  const displayName = user?.full_name || user?.username || "";
  const taskCount = tasksData?.total_count ?? 0;
  const projectCount = statsData?.projects_count ?? 0;

  return (
    <header className="relative w-full border-b border-blue-500/15 dark:border-cyan-500/15 bg-white/90 dark:bg-slate-950/80 shadow-[0_1px_10px_rgba(0,0,0,0.03)] p-4 md:px-8 md:py-5 backdrop-blur-md z-10 scanlines">
      {/* Background glow node — dark only */}
      <div className="hidden dark:block absolute top-0 left-1/4 w-1/3 h-24 bg-cyan-500/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-3 border rounded-lg bg-blue-50 border-blue-200 text-blue-600 dark:bg-cyan-950/40 dark:border-cyan-500/30 dark:text-cyan-400 shadow-[0_0_12px_rgba(37,99,235,0.15)] dark:shadow-[0_0_12px_rgba(6,182,212,0.15)] flex items-center justify-center transition-colors">
            <LayoutDashboard className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl md:text-2xl font-bold tracking-tight text-slate-900 dark:text-white transition-colors" suppressHydrationWarning>
                {getGreeting()}, <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600 dark:from-cyan-400 dark:to-purple-400 font-extrabold">{displayName || "Administrator"}</span>
              </h1>
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] uppercase font-bold font-cyber border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 dark:shadow-[0_0_8px_rgba(16,185,129,0.15)] transition-colors">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                Secure Mode
              </span>
            </div>
            <p className="text-xs md:text-sm mt-1 font-mono-db flex items-center gap-2 text-slate-600 dark:text-slate-400 transition-colors">
              <span className="text-blue-600 dark:text-cyan-400">⚡ 系统就绪</span>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <span>{taskCount === 0 ? "所有任务已完成" : `待办任务: ${taskCount}`}</span>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <span className="hidden sm:inline" suppressHydrationWarning>{time}</span>
              <span className="font-bold hidden sm:inline font-mono-db text-blue-600 dark:text-cyan-400">.{millis} MS</span>
            </p>
          </div>
        </div>

        <div className="hidden lg:flex items-center gap-6 border-l pl-6 text-xs font-cyber border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 transition-colors">
          <div className="flex items-center gap-2">
            <FolderKanban className="w-4 h-4 text-blue-600 dark:text-cyan-400" />
            <div>
              <div className="uppercase text-[9px] tracking-wider">Active Projects</div>
              <div className="font-bold text-sm text-slate-900 dark:text-white">{projectCount}<span className="text-blue-600 dark:text-cyan-400 text-[10px]"> 个</span></div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ListTodo className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <div>
              <div className="uppercase text-[9px] tracking-wider">Pending Tasks</div>
              <div className="font-bold text-sm text-slate-900 dark:text-white">{taskCount}<span className="text-purple-600 dark:text-purple-400 text-[10px]"> 项</span></div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link href="/projects?action=create"
            className="flex items-center gap-1.5 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-blue-500 dark:from-blue-600 dark:to-cyan-500 text-white rounded-lg text-sm font-semibold shadow-lg hover:shadow-blue-500/20 dark:hover:shadow-cyan-500/20 active:opacity-90 border border-blue-400/20 dark:border-cyan-400/20 transition-all">
            <Plus className="w-4 h-4" />
            <span>新建项目</span>
          </Link>
          <Link href="/knowledge-factory"
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-slate-900/80 dark:hover:bg-slate-800 text-blue-700 dark:text-cyan-300 dark:hover:text-cyan-200 border border-slate-200 dark:border-slate-700 hover:border-blue-500/40 dark:hover:border-cyan-500/40 transition-all">
            <BrainCircuit className="w-4 h-4 text-purple-600 dark:text-purple-400 animate-spin-slow" />
            <span>知识加工</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
