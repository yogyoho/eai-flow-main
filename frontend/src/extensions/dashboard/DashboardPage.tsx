"use client";

import { useState, useMemo } from "react";
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

  const taskSummary = useMemo(() => {
    if (!tasksData || tasksData.total_count === 0) return "没有待办任务";
    const parts: string[] = [];
    parts.push(`${tasksData.total_count} 项待办`);
    if (tasksData.urgent_count > 0) parts.push(`${tasksData.urgent_count} 项紧急`);
    return parts.join("，");
  }, [tasksData]);

  const projectCount = projectsData?.total_count ?? 0;

  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          {getGreeting()}，Admin
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {taskSummary}
          {projectCount > 0 && ` · ${projectCount} 个项目`}
          <span className="ml-3 text-muted-foreground/60">{formatDate()}</span>
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Link
          href="/projects?action=create"
          className="flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">新建项目</span>
        </Link>
        <Link
          href="/"
          className="flex items-center gap-1.5 px-4 py-2 rounded-md border border-border text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <Pen className="h-4 w-4" />
          <span className="hidden sm:inline">AI 写作</span>
        </Link>
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
      <span className="bg-muted text-muted-foreground text-xs px-2 py-0.5 rounded-full">
        {projectsData.total_count}
      </span>
    );
  }, [projectsData]);

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      <DashboardHeader />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
        {/* Left column */}
        <div className="space-y-5 min-w-0">
          {/* 我的待办 */}
          <DashboardCard
            title="我的待办"
            icon={ListTodo}
            badge={urgentBadge}
          >
            <TodayTasks />
          </DashboardCard>

          {/* 我的项目 */}
          <DashboardCard
            title="我的项目"
            icon={FolderKanban}
            badge={projectCountBadge}
          >
            <MyProjects />
          </DashboardCard>
        </div>

        {/* Right sidebar */}
        <aside className="space-y-5">
          {/* 快捷入口 */}
          <DashboardCard title="快捷入口" icon={Compass}>
            <QuickLinks />
          </DashboardCard>

          {/* 消息通知 */}
          <DashboardCard
            title="消息通知"
            icon={Bell}
          >
            <NotificationFeed />
          </DashboardCard>

          {/* 我的统计 */}
          <DashboardCard title="我的统计" icon={BarChart3}>
            <StatsPanel />
          </DashboardCard>

          {/* 日程 */}
          <DashboardCard title="日程" icon={CalendarDays}>
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
  );
}
