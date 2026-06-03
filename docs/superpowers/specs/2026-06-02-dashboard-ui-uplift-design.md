# Dashboard UI Uplift Design

> Date: 2026-06-02
> Status: Approved
> Scope: Frontend only, no API/data changes

## Context

The current dashboard (`DashboardPage.tsx`) is functional but visually flat. Referencing `shadcn-admin` (D:\aiproj\qData\shadcn-admin-main) for design patterns — card styles, spacing, typography hierarchy, and component composition.

**Out of scope**: Stats panel, sidebar calendar, notification feed, notification preferences — these stay as-is.

## Changes

### 1. Top Bar Layout

**File**: `DashboardPage.tsx` (QuickActions area)

Replace the left-aligned button row with a flex header:

- Outer: `flex items-center justify-between`
- Left: `<h1 className="text-2xl font-bold tracking-tight">我的工作台</h1>`
  - Mobile: `text-xl`
- Right: Button group `flex items-center gap-2`
  - Each button: shadcn `Button variant="outline" size="sm"` style (icon + label)
  - Mobile: hide label text, show only icons

### 2. Today's Tasks

**File**: `TodayTasks.tsx`

#### Card Container
- `rounded-xl border bg-card shadow-sm`
- Header: `px-5 pt-5 pb-3 flex items-center justify-between`
  - Title: `text-base font-semibold`
  - Urgent badge (when `urgent_count > 0`): `bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full`

#### Task Items
- Outer: `rounded-lg border-l-[3px] px-4 py-3 hover:bg-accent/30 transition-colors`
- Left border color: urgent = `border-l-red-500`, normal = `border-l-primary`
- Row 1: icon(`h-4 w-4 text-muted-foreground`) + name(`text-sm font-medium truncate`) + status badge(`text-xs px-1.5 py-0.5 rounded bg-muted`)
- Row 2: `text-xs text-muted-foreground mt-1` — `projectName · 截止: date`
- Right arrow: `text-muted-foreground hover:text-primary`

#### Empty State
- `py-10 flex flex-col items-center gap-2`
- Icon: `InboxIcon` from lucide, `h-10 w-10 text-muted-foreground/50`
- Text: `text-sm text-muted-foreground` "暂无待办任务"

#### Internal Spacing
- Items: `space-y-2 px-5 pb-5`

### 3. Project List

**File**: `MyProjects.tsx` + `ProjectMiniCard`

#### Collapsible Group Headers
- `flex items-center justify-between w-full px-3 py-2 rounded-lg hover:bg-accent/50 transition-colors`
- Left: Chevron icon + role name (`text-sm font-medium`)
- Right: Count badge `bg-muted text-muted-foreground text-xs px-2 py-0.5 rounded-full`

#### Project Cards
- Outer: `rounded-lg border bg-card px-4 py-3 hover:shadow-md hover:border-primary/20 transition-all cursor-pointer`
  - Entire card is clickable (link wraps the card)
- Row 1 (`flex items-center justify-between`):
  - Avatar: `h-8 w-8 rounded-full bg-primary/10 text-primary text-xs font-medium flex items-center justify-center` (first letter of project name)
  - Project name: `text-sm font-medium truncate ml-3 flex-1`
  - Role badge: `text-xs px-2 py-0.5 rounded-full` with role-specific colors:
    - 负责人: `bg-primary/10 text-primary`
    - 审核人: `bg-amber-100 text-amber-700`
    - 撰写人: `bg-blue-100 text-blue-700`
    - 查看者: `bg-muted text-muted-foreground`
- Row 2 (`mt-2`, progress bar):
  - Track: `h-1.5 w-full rounded-full bg-muted`
  - Fill: `h-full rounded-full bg-primary transition-all`, width = `progress_pct%`
  - Percentage text: `text-xs text-muted-foreground ml-2`
- Card spacing: `space-y-2 mt-2`

#### Empty State
- `py-6 text-center text-sm text-muted-foreground`

## Files Modified

| File | Change |
|------|--------|
| `frontend/src/extensions/dashboard/DashboardPage.tsx` | Top bar: add title, move buttons to right |
| `frontend/src/extensions/dashboard/TodayTasks.tsx` | Card container, task item styling, empty state |
| `frontend/src/extensions/dashboard/MyProjects.tsx` | Card styling, progress bar, role badges, group headers |

## Risk

- **Low**: Purely CSS/class changes, no data/API changes
- All existing functionality preserved
- Responsive breakpoints maintained
