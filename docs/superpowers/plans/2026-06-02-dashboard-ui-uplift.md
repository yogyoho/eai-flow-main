# Dashboard UI Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the dashboard page top bar, today's tasks, and project list to match shadcn-admin design patterns.

**Architecture:** Pure frontend CSS/component refactor — no API or data changes. Modify 4 files in `frontend/src/extensions/dashboard/`.

**Tech Stack:** React 19, Tailwind CSS 4, Lucide icons, existing shadcn UI primitives

**Spec:** `docs/superpowers/specs/2026-06-02-dashboard-ui-uplift-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/extensions/dashboard/DashboardPage.tsx` | Modify | Top bar: title left, buttons right |
| `frontend/src/extensions/dashboard/components/QuickActions.tsx` | Modify | Restyle buttons for right-aligned header |
| `frontend/src/extensions/dashboard/components/TodayTasks.tsx` | Modify | Card container, empty state, urgent badge |
| `frontend/src/extensions/dashboard/components/TaskItemCard.tsx` | Modify | Left border color, layout rows, status badge |
| `frontend/src/extensions/dashboard/components/MyProjects.tsx` | Modify | Group header styling, count badges |
| `frontend/src/extensions/dashboard/components/ProjectMiniCard.tsx` | Modify | Avatar, role badge colors, card hover, progress bar |

---

### Task 1: Top Bar — Title + Right-Aligned Buttons

**Files:**
- Modify: `frontend/src/extensions/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/extensions/dashboard/components/QuickActions.tsx`

- [ ] **Step 1: Update DashboardPage.tsx — replace QuickActions wrapper with header layout**

Replace lines 17–21 of `DashboardPage.tsx` (the `<div className="mb-6"><QuickActions /></div>` block) with:

```tsx
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-xl">我的工作台</h1>
        <QuickActions />
      </div>
```

- [ ] **Step 2: Update QuickActions.tsx — compact button group for header**

Replace the entire `QuickActions.tsx` with:

```tsx
"use client";

import Link from "next/link";
import { Pen, FileText, LayoutGrid, FolderOpen } from "lucide-react";

const actions = [
  { label: "个人写作", icon: Pen, href: "/" },
  { label: "从模板创建", icon: FileText, href: "/projects?action=create" },
  { label: "项目看板", icon: LayoutGrid, href: "/projects" },
  { label: "我的文档", icon: FolderOpen, href: "/documents" },
];

export function QuickActions() {
  return (
    <div className="flex items-center gap-2">
      {actions.map((a) => (
        <Link
          key={a.label}
          href={a.href}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <a.icon className="h-4 w-4" />
          <span className="hidden sm:inline">{a.label}</span>
        </Link>
      ))}
    </div>
  );
}
```

Key changes: `gap-2` tighter spacing, `px-3 py-1.5` smaller padding, `hidden sm:inline` hides labels on mobile, muted text color with accent hover.

- [ ] **Step 3: Verify in browser**

Run: `docker compose -p eai-docker restart frontend`
Open: `http://localhost:2026/dashboard`
Expected: Title "我的工作台" on left, 4 icon buttons on right. On narrow screens, button labels hide.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/dashboard/DashboardPage.tsx frontend/src/extensions/dashboard/components/QuickActions.tsx
git commit -m "style(dashboard): header with title left and buttons right-aligned"
```

---

### Task 2: Today's Tasks — Card Container + Empty State + Urgent Badge

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/TodayTasks.tsx`

- [ ] **Step 1: Update TodayTasks.tsx — card container, empty state, urgent badge**

Replace the entire `TodayTasks.tsx` with:

```tsx
"use client";

import { Inbox } from "lucide-react";
import { useMyTasks } from "../hooks/useMyTasks";
import { TaskItemCard } from "./TaskItemCard";

export function TodayTasks() {
  const { data, isLoading } = useMyTasks();

  if (isLoading) {
    return (
      <div className="rounded-xl border bg-card shadow-sm p-5 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }

  if (!data || data.tasks.length === 0) {
    return (
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="px-5 pt-5 pb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">今日待办</h2>
        </div>
        <div className="py-10 flex flex-col items-center gap-2">
          <Inbox className="h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">暂无待办任务</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card shadow-sm">
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold">今日待办</h2>
        {data.urgent_count > 0 && (
          <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-medium">
            紧急 {data.urgent_count}
          </span>
        )}
      </div>
      <div className="space-y-2 px-5 pb-5">
        {data.tasks.map((task) => (
          <TaskItemCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-14 rounded-lg bg-muted animate-pulse" />;
}
```

Key changes:
- Wrapped in `rounded-xl border bg-card shadow-sm` card container
- Header inside card with `px-5 pt-5 pb-3`
- Urgent badge: `bg-red-100 text-red-700 rounded-full` pill
- Empty state: `Inbox` icon + centered text inside card
- Items wrapped in `px-5 pb-5` container

- [ ] **Step 2: Remove redundant section wrapper from DashboardPage.tsx**

In `DashboardPage.tsx`, replace the Today's Tasks section (lines 26–30):

```tsx
          {/* Today's tasks */}
          <section>
            <h2 className="text-lg font-semibold mb-3">今日待办</h2>
            <TodayTasks />
          </section>
```

with:

```tsx
          {/* Today's tasks */}
          <TodayTasks />
```

The title is now inside `TodayTasks.tsx` itself.

- [ ] **Step 3: Verify in browser**

Expected: Tasks inside a card with shadow. Empty state shows Inbox icon. Urgent badge is a red pill.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/dashboard/components/TodayTasks.tsx frontend/src/extensions/dashboard/DashboardPage.tsx
git commit -m "style(dashboard): today tasks card container, empty state, urgent badge"
```

---

### Task 3: Task Item Cards — Left Border Color + Status Badge

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/TaskItemCard.tsx`

- [ ] **Step 1: Update TaskItemCard.tsx — left border, two-row layout, status badge**

Replace the entire `TaskItemCard.tsx` with:

```tsx
"use client";

import Link from "next/link";
import { Eye, Pen, ArrowRight, AlertTriangle, ChevronRight } from "lucide-react";
import type { TaskItem } from "../types";

const TYPE_ICONS = {
  review: Eye,
  writing: Pen,
  phase_lead: ArrowRight,
  ai_writing: Pen,
  rejection: AlertTriangle,
} as const;

const TYPE_LABELS: Record<string, string> = {
  review: "待审核",
  writing: "撰写中",
  phase_lead: "阶段推进",
  ai_writing: "AI撰写",
  rejection: "被驳回",
};

export function TaskItemCard({ task }: { task: TaskItem }) {
  const Icon = TYPE_ICONS[task.type] || Eye;
  const isUrgent = task.is_urgent || (task.priority_score ?? 0) >= 50;

  return (
    <div
      className={`rounded-lg border-l-[3px] px-4 py-3 hover:bg-accent/30 transition-colors ${
        isUrgent ? "border-l-red-500 bg-red-50/30" : "border-l-primary"
      }`}
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <p className="text-sm font-medium truncate flex-1">
          {task.chapter_title || task.phase_label || task.action_label}
        </p>
        <span className="text-xs px-1.5 py-0.5 rounded bg-muted shrink-0">
          {TYPE_LABELS[task.type] || task.action_label}
        </span>
        <Link
          href={task.action_url}
          className="text-muted-foreground hover:text-primary shrink-0"
        >
          <ChevronRight className="h-4 w-4" />
        </Link>
      </div>
      <p className="text-xs text-muted-foreground mt-1 ml-6">
        {task.project_name}
        {task.due_date && (
          <> · 截止: {new Date(task.due_date).toLocaleDateString()}</>
        )}
      </p>
    </div>
  );
}
```

Key changes:
- Left border: `border-l-[3px]` — red for urgent, primary for normal
- Urgent cards get `bg-red-50/30` subtle background
- Row 1: icon + title + type badge + chevron arrow
- Row 2: project name + due date, indented with `ml-6`
- Status badge: `bg-muted rounded` pill with Chinese type labels
- Arrow changed from text link to `ChevronRight` icon

- [ ] **Step 2: Verify in browser**

Expected: Tasks show colored left border. Urgent tasks have red border + subtle background. Type shown as badge.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/dashboard/components/TaskItemCard.tsx
git commit -m "style(dashboard): task cards with left border, status badge, two-row layout"
```

---

### Task 4: Project List — Group Headers + Count Badges

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/MyProjects.tsx`

- [ ] **Step 1: Update MyProjects.tsx — styled group headers, card spacing**

Replace the entire `MyProjects.tsx` with:

```tsx
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

Key changes:
- Group header: `flex items-center justify-between w-full px-3 py-2 rounded-lg hover:bg-accent/50`
- Count moved to right as badge: `bg-muted text-muted-foreground text-xs px-2 py-0.5 rounded-full`
- Card spacing: `space-y-2 mt-2` (removed `ml-2` indent)
- Empty state: `FolderOpen` icon + text

- [ ] **Step 2: Remove redundant section wrapper from DashboardPage.tsx**

In `DashboardPage.tsx`, replace the My Projects section:

```tsx
          {/* My projects */}
          <section>
            <h2 className="text-lg font-semibold mb-3">我的项目</h2>
            <MyProjects />
          </section>
```

with:

```tsx
          {/* My projects */}
          <section>
            <h2 className="text-lg font-semibold mb-3">我的项目</h2>
            <MyProjects />
          </section>
```

(Keep the section wrapper here since the title is still in DashboardPage — MyProjects manages groups, not the section title.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/dashboard/components/MyProjects.tsx
git commit -m "style(dashboard): project group headers with count badges and hover"
```

---

### Task 5: Project Mini Cards — Avatar + Role Badges + Hover

**Files:**
- Modify: `frontend/src/extensions/dashboard/components/ProjectMiniCard.tsx`

- [ ] **Step 1: Update ProjectMiniCard.tsx — avatar, role colors, card hover**

Replace the entire `ProjectMiniCard.tsx` with:

```tsx
"use client";

import Link from "next/link";
import type { MyProjectItem } from "../types";

const ROLE_LABELS: Record<string, string> = {
  owner: "负责人",
  phase_lead: "阶段负责人",
  reviewer: "审核人",
  writer: "撰写人",
  viewer: "查看者",
};

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-primary/10 text-primary",
  phase_lead: "bg-purple-100 text-purple-700",
  reviewer: "bg-amber-100 text-amber-700",
  writer: "bg-blue-100 text-blue-700",
  viewer: "bg-muted text-muted-foreground",
};

export function ProjectMiniCard({ project }: { project: MyProjectItem }) {
  const firstChar = project.project_name.charAt(0).toUpperCase();
  const roleBadgeClass = ROLE_COLORS[project.role_label] || "bg-muted text-muted-foreground";

  return (
    <Link
      href={`/projects/${project.project_id}`}
      className="block rounded-lg border bg-card px-4 py-3 hover:shadow-md hover:border-primary/20 transition-all"
    >
      <div className="flex items-center gap-3">
        {/* Avatar */}
        <div className="h-8 w-8 rounded-full bg-primary/10 text-primary text-xs font-medium flex items-center justify-center shrink-0">
          {firstChar}
        </div>
        {/* Name + phase */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium truncate">{project.project_name}</p>
            <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${roleBadgeClass}`}>
              {ROLE_LABELS[project.role_label] || project.role_label}
            </span>
          </div>
          {project.current_phase && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {project.current_phase}
            </p>
          )}
        </div>
      </div>
      {/* Progress bar */}
      <div className="flex items-center gap-2 mt-2 ml-11">
        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{project.progress_pct}%</span>
      </div>
      {project.pending_task_count > 0 && (
        <p className="text-xs text-muted-foreground mt-1 ml-11">
          {project.pending_task_count} 项待办
        </p>
      )}
    </Link>
  );
}
```

Key changes:
- Entire card is now a `<Link>` — fully clickable
- Card hover: `hover:shadow-md hover:border-primary/20 transition-all`
- Avatar: first character circle `h-8 w-8 rounded-full bg-primary/10 text-primary`
- Role badge colors per role (owner=purple, reviewer=amber, writer=blue, viewer=gray)
- Progress bar indented with `ml-11` to align with text
- Removed `border-border` in favor of default `border` (uses theme color)

- [ ] **Step 2: Verify in browser**

Expected: Each project shows avatar circle, colored role badge, progress bar. Entire card clickable with hover shadow.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/dashboard/components/ProjectMiniCard.tsx
git commit -m "style(dashboard): project cards with avatar, role badges, hover shadow"
```

---

### Task 6: Final Integration Check

**Files:**
- Verify: `frontend/src/extensions/dashboard/DashboardPage.tsx`

- [ ] **Step 1: Verify DashboardPage.tsx final state**

The file should look like:

```tsx
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
```

- [ ] **Step 2: Run type check**

```bash
cd frontend && pnpm typecheck
```

Expected: No type errors.

- [ ] **Step 3: Verify full page in browser**

Run: `docker compose -p eai-docker restart frontend`
Open: `http://localhost:2026/dashboard`

Checklist:
- [ ] Title "我的工作台" on left, 4 buttons on right
- [ ] Today tasks inside card with rounded corners and shadow
- [ ] Task items have colored left border (red=urgent, primary=normal)
- [ ] Task items show type badge and chevron arrow
- [ ] Empty state shows Inbox icon (if no tasks)
- [ ] Project groups have count badges on right
- [ ] Project cards show avatar circle, colored role badge, progress bar
- [ ] Project cards have hover shadow effect
- [ ] Sidebar (stats, calendar, notifications) unchanged
- [ ] Responsive: on narrow screen, button labels hide

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "style(dashboard): complete UI uplift matching shadcn-admin patterns"
```
