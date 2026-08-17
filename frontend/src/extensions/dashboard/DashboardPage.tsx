"use client";

import { Sliders } from "lucide-react";
import { useState } from "react";

import Header from "./components/Header";
import { LogPanel } from "./components/LogPanel";
import { MetricsRow } from "./components/MetricsRow";
import { MiniCalendar } from "./components/MiniCalendar";
import { NotificationPreferencePanel } from "./components/NotificationPreferencePanel";
import { ProjectPanel } from "./components/ProjectPanel";
import { QuickPanel } from "./components/QuickPanel";
import { TaskPanel } from "./components/TaskPanel";
import { useMyStats } from "./hooks/useMyStats";

import "./dashboard.css";

export function DashboardPage() {
  const [prefsOpen, setPrefsOpen] = useState(false);
  const {
    data: statsData,
    isLoading: statsLoading,
    refetch: refreshStats,
  } = useMyStats();

  return (
    <div className="dashboard-shell cyber-grid relative flex min-h-full flex-col selection:bg-blue-500/30 selection:text-white">
      {/* Ambient glows */}
      <div className="pointer-events-none absolute top-1/4 left-10 h-96 w-96 rounded-full bg-purple-500/5 blur-[120px]" />
      <div className="pointer-events-none absolute right-10 bottom-1/4 h-96 w-96 rounded-full bg-blue-500/5 blur-[120px]" />

      {/* Header */}
      <Header />

      {/* Main Stage */}
      <main className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 items-start gap-6 px-4 py-6 md:px-8 lg:grid-cols-12">
        {/* Full-width metrics row */}
        <div className="lg:col-span-12">
          <MetricsRow
            data={statsData}
            loading={statsLoading}
            onRefresh={() => refreshStats()}
          />
        </div>

        {/* LEFT 7 cols */}
        <div className="flex flex-col gap-6 lg:col-span-7">
          <TaskPanel />
          <ProjectPanel />
        </div>

        {/* RIGHT 5 cols */}
        <div className="flex flex-col gap-6 lg:col-span-5">
          <QuickPanel />
          <LogPanel />

          <div className="db-card relative flex flex-col rounded-xl p-4 md:p-5">
            <div className="absolute top-0 right-0 h-3 w-3 border-t border-r border-blue-500/25 bg-blue-500/10" />
            <MiniCalendar />
          </div>

          {/* Notification Preferences */}
          <div className="db-card flex items-center justify-between rounded-xl p-3.5 text-xs">
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 animate-pulse text-purple-500" />
              <span className="db-text-primary font-semibold">
                通知偏好设置{" "}
                <span className="font-cyber text-[10px] font-normal text-slate-500">
                  ALERT CONFIGS
                </span>
              </span>
            </div>
            <button
              onClick={() => setPrefsOpen(!prefsOpen)}
              className="font-cyber cursor-pointer text-xs font-bold text-blue-600 transition-all hover:text-blue-500"
            >
              {prefsOpen ? "折叠 CLOSE" : "展开 EXPAND"}
            </button>
          </div>

          {prefsOpen && (
            <div className="db-card flex flex-col gap-3 overflow-hidden rounded-xl p-4 text-xs">
              <NotificationPreferencePanel />
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="db-text-subtle font-cyber mt-8 border-t border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] px-6 py-4 text-center text-[10px] leading-relaxed tracking-widest select-none">
        XXXX工程 · 企业智能体应用平台 v0.5.0
        <div className="mt-0.5 text-[9px] text-slate-400">
          © 2026 XXXX工程有限公司
        </div>
      </footer>
    </div>
  );
}
