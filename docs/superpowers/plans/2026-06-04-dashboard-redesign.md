# Dashboard Workspace Full Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the dashboard workspace page with unified card design, fixed data flow, and improved UX across all 4 problem areas.

**Architecture:** Create a reusable `DashboardCard` wrapper component, then refactor each dashboard section to use it. Split the header QuickActions into action buttons (stay in header) and navigation links (new QuickLinks card in sidebar). Fix backend task query if needed. Replace emoji icons with Lucide in notifications.

**Tech Stack:** React 19, Next.js 16, Tailwind CSS 4, Lucide React icons, TanStack Query, FastAPI (backend)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/extensions/dashboard/components/DashboardCard.tsx` | Reusable card wrapper with title, icon, badge, action slot |
| `frontend/src/extensions/dashboard/components/QuickLinks.tsx` | 2×2 grid of navigation links for sidebar |

### Modified Files
| File | Changes |
|------|---------|
| `frontend/src/extensions/dashboard/DashboardPage.tsx` | Full rewrite: new header + grid layout + DashboardCard wrappers |
| `frontend/src/extensions/dashboard/components/TodayTasks.tsx` | Rename to "我的待办", wrap in DashboardCard, improve empty state |
| `frontend/src/extensions/dashboard/components/MyProjects.tsx` | Wrap in DashboardCard, unify title size |
| `frontend/src/extensions/dashboard/components/NotificationFeed.tsx` | Emoji → Lucide icons, bigger buttons, better unread styling |
| `frontend/src/extensions/dashboard/components/StatsPanel.tsx` | Refactor from 4-row to 2×2 grid with icons |
| `frontend/src/extensions/dashboard/components/MiniCalendar.tsx` | Wrap in DashboardCard (parent handles this) |
| `backend/app/extensions/dashboard/service.py` | Add debug logging to `get_my_tasks` for empty-state diagnosis |

### Deleted Files
| File | Reason |
|------|--------|
| `frontend/src/extensions/dashboard/components/QuickActions.tsx` | Functionality split into header buttons + QuickLinks card |

---

## Task 1: Create DashboardCard Component

**Files:**
- Create: `frontend/src/extensions/dashboard/components/DashboardCard.tsx`

- [ ] **Step 1: Write the DashboardCard component**

```tsx
// frontend/src/extensions/dashboard/components/DashboardCard.tsx
"use client";

import { type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";

interface DashboardCardProps {
  title: string;
  icon?: LucideIcon;
  badge?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export function DashboardCard({
  title,
  icon: Icon,
  badge,
  action,
  children,
  className = "",
}: DashboardCardProps) {
  return (
    <div className={`rounded-xl border border-border bg-card shadow-sm ${className}`}>
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {badge}
        </div>
        {action}
      </div>
      <div className="px-5 pb-5">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/DashboardCard.tsx
git commit -m "feat(dashboard): add DashboardCard reusable wrapper component"
```

---

## Task 2: Create QuickLinks Component

**Files:**
- Create: `frontend/src/extensions/dashboard/components/QuickLinks.tsx`

This replaces the navigation half of the old QuickActions (项目看板, 我的文档, 模板中心, 设置).

- [ ] **Step 1: Write the QuickLinks component**

```tsx
// frontend/src/extensions/dashboard/components/QuickLinks.tsx
"use client";

import Link from "next/link";
import { LayoutGrid, FolderOpen, FileText, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface QuickLinkItem {
  label: string;
  icon: LucideIcon;
  href: string;
}

const links: QuickLinkItem[] = [
  { label: "项目看板", icon: LayoutGrid, href: "/projects" },
  { label: "我的文档", icon: FolderOpen, href: "/documents" },
  { label: "模板中心", icon: FileText, href: "/projects?action=create" },
  { label: "系统设置", icon: Settings, href: "/settings" },
];

export function QuickLinks() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {links.map((item) => (
        <Link
          key={item.label}
          href={item.href}
          className="flex flex-col items-center gap-1.5 rounded-lg border border-border p-3 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <item.icon className="h-5 w-5" />
          <span className="text-xs font-medium">{item.label}</span>
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/QuickLinks.tsx
git commit -m "feat(dashboard): add QuickLinks sidebar navigation grid"
```

---

## Task 3: Beautify NotificationFeed — Emoji → Lucide, Bigger Buttons, Better Unread

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/NotificationFeed.tsx`

- [ ] **Step 1: Replace the NotificationFeed component**

Replace the entire `NotificationFeed.tsx` file content with:

```tsx
// frontend/src/extensions/dashboard/components/NotificationFeed.tsx
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BellOff,
  Check,
  Eye,
  Rocket,
  SearchCheck,
  CheckCircle2,
  PartyPopper,
  AlarmClock,
  MessageCircle,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

// ── API ──

interface NotificationItem {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body?: string;
  project_id?: string;
  link?: string;
  is_read: boolean;
  created_at?: string;
}

interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

const BASE = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";

async function fetchNotifications(page = 0): Promise<NotificationListResponse> {
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications?skip=${page * 20}&limit=20`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

async function markRead(id: string): Promise<void> {
  await fetch(`${BASE}/api/extensions/dashboard/notifications/${id}/read`, {
    method: "PATCH",
    credentials: "include",
  });
}

async function markAllRead(): Promise<void> {
  await fetch(`${BASE}/api/extensions/dashboard/notifications/read-all`, {
    method: "POST",
    credentials: "include",
  });
}

// ── Notification type icons (Lucide, no emoji) ──

const TYPE_ICONS: Record<string, LucideIcon> = {
  phase_start: Rocket,
  review_pending: SearchCheck,
  review_complete: CheckCircle2,
  workflow_complete: PartyPopper,
  deadline: AlarmClock,
  mention: MessageCircle,
};

function getTypeIcon(type: string): LucideIcon {
  return TYPE_ICONS[type] || Bell;
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}天前`;
  return date.toLocaleDateString();
}

// ── NotificationFeed component ──

export function NotificationFeed() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(0),
    staleTime: 30_000,
  });

  const readMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const readAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data || data.notifications.length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        <BellOff className="h-6 w-6 mx-auto mb-1 opacity-50" />
        <p className="text-sm">暂无通知</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {data.unread_count > 0 && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">{data.unread_count} 条未读</span>
          <button
            onClick={() => readAllMutation.mutate()}
            className="text-xs text-primary hover:underline"
          >
            全部标为已读
          </button>
        </div>
      )}
      {data.notifications.map((n) => {
        const Icon = getTypeIcon(n.type);
        return (
          <div
            key={n.id}
            className={`flex items-start gap-2.5 rounded-md p-2.5 text-sm transition-colors ${
              n.is_read
                ? "text-muted-foreground"
                : "border-l-2 border-primary bg-accent/30"
            }`}
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{n.title}</p>
              {n.body && (
                <p className="text-xs text-muted-foreground line-clamp-2">{n.body}</p>
              )}
              <p className="text-xs text-muted-foreground mt-0.5">{formatTimeAgo(n.created_at)}</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {!n.is_read && (
                <button
                  onClick={() => readMutation.mutate(n.id)}
                  className="p-1.5 rounded hover:bg-accent"
                  title="标为已读"
                >
                  <Check className="h-4 w-4 text-muted-foreground" />
                </button>
              )}
              {n.link && (
                <Link
                  href={n.link}
                  className="p-1.5 rounded hover:bg-accent"
                  title="查看"
                >
                  <Eye className="h-4 w-4 text-muted-foreground" />
                </Link>
              )}
            </div>
          </div>
        );
      })}
      {data.total > 20 && (
        <button
          className="text-xs text-center text-primary hover:underline w-full mt-2"
          onClick={() => {/* TODO: expand or navigate to full notifications page */}}
        >
          查看全部通知 ({data.total} 条)
        </button>
      )}
    </div>
  );
}

// ── NotificationBadge (for header/navbar) ──

export function NotificationBadge() {
  const { data } = useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () => fetchNotifications(0),
    staleTime: 60_000,
  });

  const count = data?.unread_count ?? 0;

  return (
    <Link href="/dashboard" className="relative p-2 rounded-md hover:bg-accent">
      <Bell className="h-5 w-5" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </Link>
  );
}
```

Key changes from original:
- `TYPE_ICONS` changed from `Record<string, string>` (emoji) to `Record<string, LucideIcon>` (Lucide components)
- `getTypeIcon()` returns a LucideIcon component instead of an emoji string
- Each notification renders `<Icon className="h-4 w-4" />` instead of `<span>{emoji}</span>`
- Unread: `border-l-2 border-primary bg-accent/30` instead of `opacity-60` + `bg-accent/50`
- Read: `text-muted-foreground` instead of `opacity-60`
- Buttons: `h-4 w-4` icons + `p-1.5` padding (was `h-3 w-3` + `p-1`)
- Bottom text changed to clickable "查看全部通知" link

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/NotificationFeed.tsx
git commit -m "feat(dashboard): replace emoji with Lucide icons, enlarge buttons, improve unread styling in notifications"
```

---

## Task 4: Refactor StatsPanel to 2×2 Grid with Icons

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/StatsPanel.tsx`

- [ ] **Step 1: Rewrite StatsPanel**

Replace the entire `StatsPanel.tsx` content:

```tsx
// frontend/src/extensions/dashboard/components/StatsPanel.tsx
"use client";

import { FolderKanban, SearchCheck, PenTool, AlertTriangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMyStats } from "../hooks/useMyStats";

interface StatItem {
  label: string;
  value: number;
  color: string;
  icon: LucideIcon;
}

export function StatsPanel() {
  const { data } = useMyStats();

  if (!data) return null;

  const stats: StatItem[] = [
    { label: "进行中项目", value: data.projects_count, color: "text-primary", icon: FolderKanban },
    { label: "待审核", value: data.pending_reviews, color: "text-amber-500", icon: SearchCheck },
    { label: "待编写", value: data.pending_writing, color: "text-blue-500", icon: PenTool },
    { label: "逾期", value: data.overdue_count, color: "text-red-500", icon: AlertTriangle },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className="flex flex-col items-center gap-1 rounded-lg border border-border p-3"
        >
          <s.icon className={`h-4 w-4 ${s.color}`} />
          <span className={`text-lg font-semibold ${s.color}`}>{s.value}</span>
          <span className="text-[11px] text-muted-foreground">{s.label}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/StatsPanel.tsx
git commit -m "feat(dashboard): refactor StatsPanel to 2x2 grid with icons"
```

---

## Task 5: Refactor TodayTasks → "我的待办" with DashboardCard + Better Empty State

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/TodayTasks.tsx`

- [ ] **Step 1: Rewrite TodayTasks**

Replace the entire `TodayTasks.tsx` content:

```tsx
// frontend/src/extensions/dashboard/components/TodayTasks.tsx
"use client";

import { CheckCircle2, ListTodo, Inbox } from "lucide-react";
import { useMyTasks } from "../hooks/useMyTasks";
import { TaskItemCard } from "./TaskItemCard";

export function TodayTasks() {
  const { data, isLoading } = useMyTasks();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  // Empty state — no tasks at all
  if (!data || data.tasks.length === 0) {
    return (
      <div className="py-8 flex flex-col items-center gap-2">
        <CheckCircle2 className="h-8 w-8 text-green-500/60" />
        <p className="text-sm text-muted-foreground">所有任务已完成</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Urgent badge in header handled by parent DashboardCard */}
      {data.tasks.map((task) => (
        <TaskItemCard key={task.id} task={task} />
      ))}
      {data.total_count > data.tasks.length && (
        <p className="text-xs text-center text-muted-foreground pt-1">
          还有 {data.total_count - data.tasks.length} 项任务
        </p>
      )}
    </div>
  );
}
```

Key changes:
- Title "今日待办" removed (parent `DashboardPage` will provide it via `DashboardCard` title="我的待办")
- Empty state changed from `Inbox` + "暂无待办任务" to `CheckCircle2` + "所有任务已完成"
- Removed the wrapping card div (parent `DashboardCard` handles that)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/TodayTasks.tsx
git commit -m "feat(dashboard): rename TodayTasks to '我的待办', improve empty state, prepare for DashboardCard wrapping"
```

---

## Task 6: Wrap MyProjects in DashboardCard + Unify Title

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/MyProjects.tsx`

- [ ] **Step 1: Update MyProjects to remove its own title**

The title "我的项目" will be provided by the parent `DashboardCard`. Remove the section-level heading. Replace the entire `MyProjects.tsx` content:

```tsx
// frontend/src/extensions/dashboard/components/MyProjects.tsx
"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FolderOpen } from "lucide-react";
import { useMyProjects } from "../hooks/useMyProjects";
import { ProjectMiniCard } from "./ProjectMiniCard";

const GROUP_LABELS: Record<string, string> = {
  owner: "我负责的项目",
  phase_lead: "作为阶段负责人",
  reviewer: "作为审核人",
  writer: "作为撰写人",
  viewer: "仅查看",
};

export function MyProjects() {
  const { data, isLoading } = useMyProjects();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data || data.total_count === 0) {
    return (
      <div className="py-6 flex flex-col items-center gap-2">
        <FolderOpen className="h-10 w-10 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">暂无项目</p>
      </div>
    );
  }

  const toggleGroup = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {Object.entries(data.groups).map(([key, projects]) => (
        <div key={key}>
          <button
            onClick={() => toggleGroup(key)}
            className="flex items-center justify-between w-full px-3 py-2 rounded-lg hover:bg-accent/50 transition-colors"
          >
            <span className="flex items-center gap-1.5 text-sm font-medium">
              {collapsed.has(key) ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
              {GROUP_LABELS[key] || key}
            </span>
            <span className="bg-muted text-muted-foreground text-xs px-2 py-0.5 rounded-full">
              {projects.length}
            </span>
          </button>
          {!collapsed.has(key) && (
            <div className="space-y-2 mt-2">
              {projects.map((p) => (
                <ProjectMiniCard key={p.project_id} project={p} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

Note: This is the same logic as before but without any wrapping `<section>` or `<h2>` — the parent `DashboardPage` will provide the `DashboardCard` wrapper with title="我的项目".

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/dashboard/components/MyProjects.tsx
git commit -m "refactor(dashboard): remove MyProjects own title, prepare for DashboardCard wrapping"
```

---

## Task 7: Rewrite DashboardPage — New Header + Grid + All Cards

**Files:**
- Modify: `frontend/src/extensions/dashboard/DashboardPage.tsx`
- Delete: `frontend/src/extensions/dashboard/components/QuickActions.tsx`

This is the main orchestration task. It wires everything together.

- [ ] **Step 1: Rewrite DashboardPage**

Replace the entire `DashboardPage.tsx` content:

```tsx
// frontend/src/extensions/dashboard/DashboardPage.tsx
"use client";

import { useState, useEffect, useMemo } from "react";
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
            action={
              <span className="text-xs text-muted-foreground">通知</span>
            }
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
```

Key changes:
- New `DashboardHeader` with greeting + task summary + date + two action buttons (新建项目 primary, AI 写作 outline)
- All sections wrapped in `DashboardCard` with icon + title + optional badge/action
- Left column: "我的待办" + "我的项目"
- Right sidebar: "快捷入口" → "消息通知" → "我的统计" → "日程" → "通知偏好设置"
- Grid gap changed from `gap-6` to `gap-5`
- Right column width: `320px` (was `300px`)

- [ ] **Step 2: Delete QuickActions.tsx**

```bash
rm frontend/src/extensions/dashboard/components/QuickActions.tsx
```

- [ ] **Step 3: Verify no other file imports QuickActions**

Search the codebase for any remaining import of QuickActions. The only consumer was `DashboardPage.tsx` which we just rewrote.

```bash
grep -r "QuickActions" frontend/src/ --include="*.tsx" --include="*.ts"
```

Expected: No results.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/dashboard/DashboardPage.tsx
git rm frontend/src/extensions/dashboard/components/QuickActions.tsx
git commit -m "feat(dashboard): rewrite DashboardPage with new header, unified cards, and QuickLinks sidebar"
```

---

## Task 8: Add Backend Debug Logging for Empty Tasks Diagnosis

**Files:**
- Modify: `backend/app/extensions/dashboard/service.py`

The user reports tasks are always empty even when they have assignments. We add logging to diagnose whether the queries return data or if the user simply has no matching records.

- [ ] **Step 1: Add logging to `get_my_tasks`**

In `backend/app/extensions/dashboard/service.py`, after line 86 (`async def get_my_tasks(...)`) and before line 87 (`tasks: list[TaskItem] = []`), add logging statements after each query section:

After line 95 (`review_result = await db.execute(review_stmt)`), add:
```python
    review_rows = review_result.all()
    logger.info("my-tasks: user=%s reviews_found=%d", user_id, len(review_rows))
    for review, proj_name in review_rows:
```
(Note: change `review_result.all()` on line 96 to use the pre-fetched `review_rows`)

After line 126 (`for ch in chapter_result.scalars().all():`), add a log line. Insert before line 116 (`for pid in project_ids:`):
```python
    logger.info("my-tasks: user=%s project_ids=%d", user_id, len(project_ids))
```

After line 146 (`duties_result = await db.execute(duties_stmt)`), add:
```python
    duties_rows = duties_result.scalars().all()
    logger.info("my-tasks: user=%s duties_found=%d", user_id, len(duties_rows))
```

After line 186 (`tasks.sort(...)`), add:
```python
    logger.info("my-tasks: user=%s total=%d urgent=%d", user_id, len(tasks), sum(1 for t in tasks if t.priority_score >= 50))
```

The final modified `get_my_tasks` function should look like:

```python
async def get_my_tasks(db: AsyncSession, user_id: UUID) -> MyTasksResponse:
    """Aggregate all actionable tasks for a user across their projects."""
    tasks: list[TaskItem] = []

    # 1. Pending reviews assigned to this user
    review_stmt = (
        select(PhaseReview, ReportProject.name.label("project_name"))
        .join(ReportProject, PhaseReview.project_id == ReportProject.id)
        .where(PhaseReview.reviewer_id == user_id, PhaseReview.status == "pending")
    )
    review_result = await db.execute(review_stmt)
    review_rows = review_result.all()
    logger.info("my-tasks: user=%s reviews_found=%d", user_id, len(review_rows))
    for review, proj_name in review_rows:
        tasks.append(
            TaskItem(
                id=f"review-{review.id}",
                type="review",
                priority_score=_compute_priority("review", review.created_at),
                project_id=review.project_id,
                project_name=proj_name,
                phase_node=review.phase_node,
                chapter_id=review.chapter_id,
                action_label="开始审核",
                action_url=f"/projects/{review.project_id}?tab=review",
            )
        )

    # 2. Writing tasks — chapters assigned to this user in draft/writing status
    member_stmt = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    member_result = await db.execute(member_stmt)
    project_ids = [row[0] for row in member_result.all()]
    logger.info("my-tasks: user=%s project_ids=%d", user_id, len(project_ids))

    for pid in project_ids:
        chapter_stmt = (
            select(ProjectChapter)
            .where(
                ProjectChapter.project_id == pid,
                ProjectChapter.assigned_to == user_id,
                ProjectChapter.status.in_(["draft", "writing"]),
            )
        )
        chapter_result = await db.execute(chapter_stmt)
        for ch in chapter_result.scalars().all():
            tasks.append(
                TaskItem(
                    id=f"writing-{ch.id}",
                    type="writing",
                    priority_score=_compute_priority("writing", None),
                    project_id=pid,
                    project_name="",  # filled below
                    chapter_id=ch.id,
                    chapter_title=ch.title,
                    action_label="继续编写",
                    action_url=f"/projects/{pid}?tab=editor&chapter={ch.id}",
                )
            )

    # 3. Phase lead tasks — user is phase_lead for the current phase that hasn't started
    duties_stmt = select(ProjectMember).where(
        ProjectMember.user_id == user_id,
        ProjectMember.phase_duties.isnot(None),
    )
    duties_result = await db.execute(duties_stmt)
    duties_rows = duties_result.scalars().all()
    logger.info("my-tasks: user=%s duties_found=%d", user_id, len(duties_rows))
    for member in duties_rows:
        if not member.phase_duties:
            continue
        for phase_key, duty_info in member.phase_duties.items():
            if duty_info.get("duty") != "lead":
                continue
            # Check if this phase is the current one and needs action
            proj_stmt = select(ReportProject).where(ReportProject.id == member.project_id)
            proj_result = await db.execute(proj_stmt)
            proj = proj_result.scalar_one_or_none()
            if not proj or proj.status not in ("in_progress",):
                continue
            phase_node = phase_key.replace("phase-", "phase-")
            if proj.current_phase_node == phase_node:
                tasks.append(
                    TaskItem(
                        id=f"lead-{member.project_id}-{phase_key}",
                        type="phase_lead",
                        priority_score=_compute_priority("phase_lead", None, is_blocking=True),
                        project_id=member.project_id,
                        project_name=proj.name,
                        phase_node=phase_node,
                        action_label="进入项目",
                        action_url=f"/projects/{member.project_id}?tab=workflow",
                    )
                )

    # Fill project names for writing tasks
    proj_names: dict[UUID, str] = {}
    for task in tasks:
        if task.project_name == "" and task.project_id not in proj_names:
            proj_stmt = select(ReportProject.name).where(ReportProject.id == task.project_id)
            result = await db.execute(proj_stmt)
            name = result.scalar_one_or_none()
            proj_names[task.project_id] = name or ""
        if task.project_name == "":
            task.project_name = proj_names.get(task.project_id, "")

    # Sort by priority descending
    tasks.sort(key=lambda t: t.priority_score, reverse=True)

    urgent_count = sum(1 for t in tasks if t.priority_score >= 50)
    logger.info("my-tasks: user=%s total=%d urgent=%d", user_id, len(tasks), urgent_count)

    return MyTasksResponse(
        tasks=tasks,
        urgent_count=urgent_count,
        total_count=len(tasks),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/dashboard/service.py
git commit -m "debug(dashboard): add logging to get_my_tasks for empty-state diagnosis"
```

---

## Task 9: Verify Build and Restart Services

**Files:** None (verification only)

- [ ] **Step 1: Run frontend type check**

```bash
cd frontend && pnpm typecheck
```

Expected: No type errors. All new components use correct types.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && pnpm lint
```

Expected: No lint errors.

- [ ] **Step 3: Restart Docker services**

```bash
docker compose -p eai-docker restart gateway frontend
```

- [ ] **Step 4: Verify page loads at http://localhost:2026/dashboard**

Open the page in a browser and check:
1. Header shows greeting + task summary + date + two action buttons
2. Left column has two cards: "我的待办" and "我的项目"
3. Right sidebar has: "快捷入口" (2×2 grid) → "消息通知" → "我的统计" (2×2 grid) → "日程" → "通知偏好设置"
4. Notification icons are Lucide (not emoji)
5. Notification mark-as-read buttons are larger and easier to click
6. All cards have consistent rounded-xl + border + bg-card styling

- [ ] **Step 5: Check backend logs for task diagnosis**

```bash
docker compose -p eai-docker logs gateway --tail 50 | grep "my-tasks"
```

Look for log lines like:
```
my-tasks: user=UUID reviews_found=0
my-tasks: user=UUID project_ids=0
my-tasks: user=UUID duties_found=0
my-tasks: user=UUID total=0 urgent=0
```

If all counts are 0, the issue is data-layer (user has no assignments in the DB). If counts are >0 but page shows empty, it's a frontend rendering issue.

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat(dashboard): workspace full redesign — unified cards, new header, beautified notifications, fixed layout consistency"
```

---

## Summary of Changes

| Problem | Fix | Task |
|---------|-----|------|
| "今日待办" always empty | Rename to "我的待办", add backend logging, positive empty state | 5, 8 |
| Header buttons mixed action+nav | Split: header keeps actions, new QuickLinks card for nav | 2, 7 |
| Notification emoji + small buttons | Lucide icons, bigger click targets, better unread/read distinction | 3 |
| "我的项目" title inconsistent | Wrap all sections in unified DashboardCard | 1, 6, 7 |
| Stats panel plain list | 2×2 grid with icons | 4 |
