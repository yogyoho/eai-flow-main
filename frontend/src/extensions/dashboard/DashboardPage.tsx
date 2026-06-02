"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Settings2 } from "lucide-react";
import { TodayTasks } from "./components/TodayTasks";
import { MyProjects } from "./components/MyProjects";
import { StatsPanel } from "./components/StatsPanel";
import { QuickActions } from "./components/QuickActions";
import { NotificationFeed } from "./components/NotificationFeed";
import { NotificationPreferencePanel } from "./components/NotificationPreferencePanel";
import { MiniCalendar } from "./components/MiniCalendar";

export function DashboardPage() {
  const [prefsOpen, setPrefsOpen] = useState(false);

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-xl">我的工作台</h1>
        <QuickActions />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6">
        {/* Left column */}
        <div className="space-y-6">
          {/* Today's tasks */}
          <TodayTasks />

          {/* My projects */}
          <section>
            <h2 className="text-lg font-semibold mb-3">我的项目</h2>
            <MyProjects />
          </section>
        </div>

        {/* Right sidebar */}
        <aside className="space-y-6">
          {/* Stats */}
          <section className="rounded-lg border border-border p-4">
            <h3 className="text-sm font-semibold mb-3">我的统计</h3>
            <StatsPanel />
          </section>

          {/* Calendar */}
          <section className="rounded-lg border border-border p-4">
            <h3 className="text-sm font-semibold mb-3">日程</h3>
            <MiniCalendar />
          </section>

          {/* Notifications */}
          <section className="rounded-lg border border-border p-4">
            <NotificationFeed />
          </section>

          {/* Notification preferences (collapsible) */}
          <section className="rounded-lg border border-border p-4">
            <button
              type="button"
              className="flex items-center gap-2 text-sm font-semibold w-full text-left"
              onClick={() => setPrefsOpen(!prefsOpen)}
            >
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              通知偏好设置
              {prefsOpen ? (
                <ChevronDown className="h-4 w-4 ml-auto text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 ml-auto text-muted-foreground" />
              )}
            </button>
            {prefsOpen && (
              <div className="mt-3">
                <NotificationPreferencePanel />
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
