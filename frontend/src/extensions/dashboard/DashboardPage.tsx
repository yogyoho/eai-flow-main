"use client";

import { TodayTasks } from "./components/TodayTasks";
import { MyProjects } from "./components/MyProjects";
import { StatsPanel } from "./components/StatsPanel";
import { QuickActions } from "./components/QuickActions";

export function DashboardPage() {
  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Quick actions */}
      <div className="mb-6">
        <QuickActions />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6">
        {/* Left column */}
        <div className="space-y-6">
          {/* Today's tasks */}
          <section>
            <h2 className="text-lg font-semibold mb-3">今日待办</h2>
            <TodayTasks />
          </section>

          {/* My projects */}
          <section>
            <h2 className="text-lg font-semibold mb-3">我的项目</h2>
            <MyProjects />
          </section>
        </div>

        {/* Right sidebar */}
        <aside className="space-y-6">
          {/* Stats */}
          <section className="rounded-lg border p-4">
            <h3 className="text-sm font-semibold mb-3">我的统计</h3>
            <StatsPanel />
          </section>
        </aside>
      </div>
    </div>
  );
}
