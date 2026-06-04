"use client";

import { useState, useMemo, useEffect } from "react";
import { Plus, Pen, ListTodo, FolderKanban, Bell, BarChart3, CalendarDays, Compass } from "lucide-react";
import Link from "next/link";
import { TodayTasks } from "./components/TodayTasks";
import { MyProjects } from "./components/MyProjects";
import { StatsPanel } from "./components/StatsPanel";
import { QuickLinks } from "./components/QuickLinks";
import { NotificationFeed } from "./components/NotificationFeed";
import { NotificationPreferencePanel } from "./components/NotificationPreferencePanel";
import { MiniCalendar } from "./components/MiniCalendar";
import { DashboardCard } from "./components/DashboardCard";
import { useMyTasks } from "./hooks/useMyTasks";
import { useMyProjects } from "./hooks/useMyProjects";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 11) return "早上好";
  if (hour >= 11 && hour < 14) return "中午好";
  if (hour >= 14 && hour < 18) return "下午好";
  return "晚上好";
}

function formatDate(): string {
  const now = new Date();
  return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
}

function DashboardHeader() {
  const { data: tasksData } = useMyTasks();
  const { data: projectsData } = useMyProjects();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const taskSummary = useMemo(() => {
    if (!tasksData || tasksData.total_count === 0) return "没有待办任务";
    const parts: string[] = [];
    parts.push(`${tasksData.total_count} 项待办`);
    if (tasksData.urgent_count > 0) parts.push(`${tasksData.urgent_count} 项紧急`);
    return parts.join("，");
  }, [tasksData]);

  const projectCount = projectsData?.total_count ?? 0;

  return (
    <div className="relative -mx-4 -mt-6 px-6 pt-6 pb-8 mb-0 bg-gradient-to-r from-[#4F6AF6] to-[#7C5CFC] rounded-b-2xl">
      <div className="flex items-start justify-between max-w-7xl mx-auto">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            {mounted ? getGreeting() : "你好"}，Admin
          </h1>
          <p className="text-sm text-white/70 mt-1">
            {taskSummary}
            {projectCount > 0 && ` · ${projectCount} 个项目`}
            <span className="ml-3 text-white/50">{mounted ? formatDate() : ""}</span>
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link
            href="/projects?action=create"
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white text-[#4F6AF6] text-sm font-medium hover:bg-white/90 shadow-sm transition-colors"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">新建项目</span>
          </Link>
          <Link
            href="/"
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-white/30 text-sm text-white hover:bg-white/10 transition-colors"
          >
            <Pen className="h-4 w-4" />
            <span className="hidden sm:inline">AI 写作</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const [prefsOpen, setPrefsOpen] = useState(false);
  const { data: tasksData } = useMyTasks();
  const { data: projectsData } = useMyProjects();

  const urgentBadge = useMemo(() => {
    if (!tasksData || tasksData.urgent_count === 0) return undefined;
    return (
      <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-medium">
        紧急 {tasksData.urgent_count}
      </span>
    );
  }, [tasksData]);

  const projectCountBadge = useMemo(() => {
    if (!projectsData || projectsData.total_count === 0) return undefined;
    return (
      <span className="bg-violet-100 text-violet-700 text-xs px-2 py-0.5 rounded-full font-medium">
        {projectsData.total_count}
      </span>
    );
  }, [projectsData]);

  return (
    <div className="min-h-full bg-[#F8F9FC]">
      <div className="container mx-auto py-6 px-4 max-w-7xl">
        <DashboardHeader />

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 mt-5">
          {/* Left column */}
          <div className="space-y-5 min-w-0">
            {/* 我的待办 */}
            <DashboardCard
              title="我的待办"
              icon={ListTodo}
              iconColor="text-blue-600"
              badge={urgentBadge}
            >
              <TodayTasks />
            </DashboardCard>

            {/* 我的项目 */}
            <DashboardCard
              title="我的项目"
              icon={FolderKanban}
              iconColor="text-violet-600"
              badge={projectCountBadge}
            >
              <MyProjects />
            </DashboardCard>
          </div>

          {/* Right sidebar */}
          <aside className="space-y-5">
            {/* 快捷入口 */}
            <DashboardCard title="快捷入口" icon={Compass} iconColor="text-emerald-600">
              <QuickLinks />
            </DashboardCard>

            {/* 消息通知 */}
            <DashboardCard
              title="消息通知"
              icon={Bell}
              iconColor="text-amber-600"
            >
              <NotificationFeed />
            </DashboardCard>

            {/* 我的统计 */}
            <DashboardCard title="我的统计" icon={BarChart3} iconColor="text-indigo-600">
              <StatsPanel />
            </DashboardCard>

            {/* 日程 */}
            <DashboardCard title="日程" icon={CalendarDays} iconColor="text-rose-600">
              <MiniCalendar />
            </DashboardCard>

            {/* Notification preferences (collapsible) */}
            <DashboardCard
              title="通知偏好设置"
              action={
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setPrefsOpen(!prefsOpen)}
                >
                  {prefsOpen ? "收起" : "展开"}
                </button>
              }
            >
              {prefsOpen && <NotificationPreferencePanel />}
            </DashboardCard>
          </aside>
        </div>
      </div>
    </div>
  );
}
