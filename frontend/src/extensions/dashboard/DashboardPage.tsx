"use client";

import { Sliders } from "lucide-react";
import { useState } from "react";

import Header from "./components/Header";
import { MetricsRow } from "./components/MetricsRow";
import { TaskPanel } from "./components/TaskPanel";
import { ProjectPanel } from "./components/ProjectPanel";
import { QuickPanel } from "./components/QuickPanel";
import { LogPanel } from "./components/LogPanel";
import { MiniCalendar } from "./components/MiniCalendar";
import { NotificationPreferencePanel } from "./components/NotificationPreferencePanel";
import { useMyStats } from "./hooks/useMyStats";

import "./dashboard.css";

export function DashboardPage() {
  const [prefsOpen, setPrefsOpen] = useState(false);
  const { data: statsData, isLoading: statsLoading, refetch: refreshStats } = useMyStats();

  return (
    <div className="dashboard-shell relative min-h-full flex flex-col cyber-grid selection:bg-blue-500/30 selection:text-white">
      {/* Ambient glows */}
      <div className="absolute top-1/4 left-10 w-96 h-96 bg-purple-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-10 w-96 h-96 bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Header */}
      <Header />

      {/* Main Stage */}
      <main className="flex-1 px-4 md:px-8 py-6 max-w-7xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Full-width metrics row */}
        <div className="lg:col-span-12">
          <MetricsRow data={statsData} loading={statsLoading} onRefresh={() => refreshStats()} />
        </div>

        {/* LEFT 7 cols */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <TaskPanel />
          <ProjectPanel />
        </div>

        {/* RIGHT 5 cols */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <QuickPanel />
          <LogPanel />

          <div className="db-card rounded-xl p-4 md:p-5 relative flex flex-col">
            <div className="absolute top-0 right-0 w-3 h-3 bg-blue-500/10 border-r border-t border-blue-500/25" />
            <MiniCalendar />
          </div>

          {/* Notification Preferences */}
          <div className="db-card rounded-xl p-3.5 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-purple-500 animate-pulse" />
              <span className="font-semibold db-text-primary">通知偏好设置 <span className="text-[10px] font-normal text-slate-500 font-cyber">ALERT CONFIGS</span></span>
            </div>
            <button onClick={() => setPrefsOpen(!prefsOpen)}
              className="text-blue-600 hover:text-blue-500 font-bold transition-all cursor-pointer font-cyber text-xs">
              {prefsOpen ? "折叠 CLOSE" : "展开 EXPAND"}
            </button>
          </div>

          {prefsOpen && (
            <div className="p-4 db-card rounded-xl text-xs flex flex-col gap-3 overflow-hidden">
              <NotificationPreferencePanel />
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] py-4 px-6 mt-8 text-center text-[10px] db-text-subtle font-cyber select-none tracking-widest leading-relaxed">
        吉林化工工程 · 企业智能体应用平台 v0.5.0
        <div className="text-[9px] text-slate-400 mt-0.5">© 2026 吉林化工工程有限公司</div>
      </footer>
    </div>
  );
}
