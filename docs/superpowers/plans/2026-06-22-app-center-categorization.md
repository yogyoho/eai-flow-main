# App Center 分类体系重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将应用中心分类从固定 6 个混合维度 category 重构为业务域（businessDomain）+ 功能阶段标签（stageTag）双层模型，支撑 50+ 应用扩展。

**Architecture:** 单层分类（businessDomain），通用分类硬编码兜底，业务域从 apps.ts 自动派生。功能阶段标签仅作卡片徽章展示，不参与筛选。涉及 7 个文件：types → config → apps data → hook → 3 个组件。

**Tech Stack:** TypeScript, React 19, Tailwind CSS 4, Lucide icons

---

## 文件变更清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `types.ts` | 修改 | 类型定义：CategoryKey → BusinessDomainKey，新增 StageTag |
| `config/categories.ts` | 修改 | 领域配置：DOMAIN_CONFIG、ACCENT_PALETTE、UNIVERSAL_DOMAINS、辅助函数 |
| `config/apps.ts` | 修改 | 9 个内置应用数据迁移 |
| `hooks/useApps.ts` | 修改 | 分类逻辑：category → businessDomain，领域选项自动派生 |
| `components/AppCard.tsx` | 修改 | 卡片：领域标签 + stageTag 徽章 |
| `components/CategoryTabs.tsx` | 修改 | 筛选 pill：类型重命名 |
| `components/AppCenterToolbar.tsx` | 修改 | 工具栏：prop 类型重命名 |

---

### Task 1: 更新类型定义

**Files:**
- Modify: `frontend/src/extensions/app-center/types.ts`

- [ ] **Step 1: 替换类型定义**

将 `types.ts` 完整替换为：

```typescript
import type { LucideIcon } from "lucide-react";

/** 业务域标识（动态扩展） */
export type BusinessDomainKey = string;

/** 功能阶段标签 */
export type StageTag =
  | "overview"     // 概览
  | "collect"      // 采集
  | "process"      // 加工
  | "collaborate"  // 协作
  | "output"       // 输出
  | "retrieve"     // 检索
  | "manage";      // 管理

/** 排序模式 */
export type SortMode = "default" | "alphabetical" | "favorites-first";

/** 图标容器强调色 */
export type AccentColor =
  | "blue"
  | "violet"
  | "cyan"
  | "amber"
  | "emerald"
  | "rose"
  | "indigo"
  | "teal"
  | "orange"
  | "sky"
  | "slate";

/** 单个应用的定义 */
export interface AppDefinition {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  /** 所属业务域 */
  businessDomain: BusinessDomainKey;
  /** 功能阶段标签（可选） */
  stageTag?: StageTag;
  path: string;
  licenseModule: string | null;
  adminOnly?: boolean;
  sortOrder: number;
  sortKey: string;
  isBuiltin: boolean;
}

/** 领域筛选值（含 "all"） */
export type DomainFilter = BusinessDomainKey | "all";
```

- [ ] **Step 2: 验证类型**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/types.ts
```

Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/types.ts
git commit -m "refactor(app-center): CategoryKey → BusinessDomainKey，新增 StageTag 类型"
```

---

### Task 2: 重构领域配置

**Files:**
- Modify: `frontend/src/extensions/app-center/config/categories.ts`

- [ ] **Step 1: 替换配置文件**

将 `config/categories.ts` 完整替换为：

```typescript
import type { AccentColor, BusinessDomainKey, StageTag } from "../types";

/**
 * 通用分类 —— 固定白名单，不属于任何业务域。
 * 数组顺序即 toolbar pill 中通用分类的展示顺序。
 */
export const UNIVERSAL_DOMAINS: BusinessDomainKey[] = [
  "universal",
  "admin",
];

export const UNIVERSAL_DOMAIN_SET: Set<BusinessDomainKey> = new Set(UNIVERSAL_DOMAINS);

/** 通用分类 label + accent（硬编码）。业务域按需自动分配。 */
export const DOMAIN_CONFIG: Record<string, { label: string; accent: AccentColor }> = {
  universal: { label: "通用工具", accent: "blue" },
  admin:     { label: "系统管理", accent: "slate" },
};

/** accent 调色板（通用分类占用后，业务域按首次出现顺序轮转） */
export const ACCENT_PALETTE: AccentColor[] = [
  "violet", "cyan", "amber", "emerald",
  "rose", "indigo", "teal", "orange", "sky", "blue",
];

/** 功能阶段标签中文映射 */
export const STAGE_LABELS: Record<StageTag, string> = {
  overview:    "概览",
  collect:     "采集",
  process:     "加工",
  collaborate: "协作",
  output:      "输出",
  retrieve:    "检索",
  manage:      "管理",
};

/**
 * 强调色 → 样式映射。
 * 完整字面量类名，确保 Tailwind v4 能静态扫描到并生成。
 */
export const ACCENT_STYLES: Record<
  AccentColor,
  { container: string; icon: string; tag: string }
> = {
  blue: {
    container: "bg-gradient-to-br from-blue-500/20 to-blue-500/10 ring-blue-500/25",
    icon: "text-blue-600 dark:text-blue-400",
    tag: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  },
  violet: {
    container: "bg-gradient-to-br from-violet-500/20 to-violet-500/10 ring-violet-500/25",
    icon: "text-violet-600 dark:text-violet-400",
    tag: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
  cyan: {
    container: "bg-gradient-to-br from-cyan-500/20 to-cyan-500/10 ring-cyan-500/25",
    icon: "text-cyan-600 dark:text-cyan-400",
    tag: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  },
  amber: {
    container: "bg-gradient-to-br from-amber-500/20 to-amber-500/10 ring-amber-500/25",
    icon: "text-amber-600 dark:text-amber-400",
    tag: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  emerald: {
    container: "bg-gradient-to-br from-emerald-500/20 to-emerald-500/10 ring-emerald-500/25",
    icon: "text-emerald-600 dark:text-emerald-400",
    tag: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  rose: {
    container: "bg-gradient-to-br from-rose-500/20 to-rose-500/10 ring-rose-500/25",
    icon: "text-rose-600 dark:text-rose-400",
    tag: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  },
  indigo: {
    container: "bg-gradient-to-br from-indigo-500/20 to-indigo-500/10 ring-indigo-500/25",
    icon: "text-indigo-600 dark:text-indigo-400",
    tag: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  },
  teal: {
    container: "bg-gradient-to-br from-teal-500/20 to-teal-500/10 ring-teal-500/25",
    icon: "text-teal-600 dark:text-teal-400",
    tag: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
  },
  orange: {
    container: "bg-gradient-to-br from-orange-500/20 to-orange-500/10 ring-orange-500/25",
    icon: "text-orange-600 dark:text-orange-400",
    tag: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
  },
  sky: {
    container: "bg-gradient-to-br from-sky-500/20 to-sky-500/10 ring-sky-500/25",
    icon: "text-sky-600 dark:text-sky-400",
    tag: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  slate: {
    container: "bg-gradient-to-br from-slate-500/20 to-slate-500/10 ring-slate-500/25",
    icon: "text-slate-600 dark:text-slate-300",
    tag: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  },
};

/**
 * 获取业务域的中文标签。
 * 优先查 DOMAIN_CONFIG（通用分类），否则将 key 本身作为 label（业务域的 key 即中文名）。
 */
export function getDomainLabel(key: BusinessDomainKey): string {
  return DOMAIN_CONFIG[key]?.label ?? key;
}

/**
 * 获取业务域的 accent 颜色。
 * 通用分类使用预定义 accent；业务域从调色板轮转分配（按首次出现顺序确定性映射）。
 */
export function getDomainAccent(
  key: BusinessDomainKey,
  domainOrder: BusinessDomainKey[],
): AccentColor {
  if (DOMAIN_CONFIG[key]) return DOMAIN_CONFIG[key].accent;

  const idx = domainOrder.indexOf(key);
  if (idx === -1) return "blue"; // fallback
  return ACCENT_PALETTE[idx % ACCENT_PALETTE.length];
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/config/categories.ts
```

Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/config/categories.ts
git commit -m "refactor(app-center): 领域配置 — DOMAIN_CONFIG + ACCENT_PALETTE + 辅助函数"
```

---

### Task 3: 迁移内置应用数据

**Files:**
- Modify: `frontend/src/extensions/app-center/config/apps.ts`

- [ ] **Step 1: 更新 apps.ts**

将 `config/apps.ts` 中的 `BUILTIN_APPS` 数组完整替换为：

```typescript
import {
  BookOpen,
  Bot,
  ClipboardList,
  Factory,
  FileOutput,
  FolderCheck,
  LayoutDashboard,
  PackageSearch,
  Settings2,
} from "lucide-react";

import type { AppDefinition } from "../types";

export const BUILTIN_APPS: AppDefinition[] = [
  {
    id: "dashboard",
    name: "工作台",
    description: "待办聚合与项目进度概览，开启高效的一天",
    icon: LayoutDashboard,
    businessDomain: "universal",
    stageTag: "overview",
    path: "/dashboard",
    licenseModule: null,
    sortOrder: 1,
    sortKey: "gongzuotai",
    isBuiltin: true,
  },
  {
    id: "smart-writing",
    name: "智能写作",
    description: "AI 辅助写作，从提纲到终稿全流程智能生成",
    icon: Bot,
    businessDomain: "universal",
    stageTag: "process",
    path: "/writing",
    licenseModule: null,
    sortOrder: 2,
    sortKey: "zhinengxiezuo",
    isBuiltin: true,
  },
  {
    id: "projects",
    name: "报告项目",
    description: "管理报告项目全生命周期，章节分配与审批跟踪",
    icon: ClipboardList,
    businessDomain: "报告编撰",
    stageTag: "collaborate",
    path: "/projects",
    licenseModule: "project",
    sortOrder: 3,
    sortKey: "baogaoxiangmu",
    isBuiltin: true,
  },
  {
    id: "docmgr",
    name: "文档空间",
    description: "团队文档协作中心，多人实时编辑与版本管理",
    icon: FolderCheck,
    businessDomain: "universal",
    stageTag: "collaborate",
    path: "/docmgr",
    licenseModule: "docmgr",
    sortOrder: 4,
    sortKey: "wendangkongjian",
    isBuiltin: true,
  },
  {
    id: "knowledge-factory",
    name: "知识工厂",
    description: "结构化知识生产流水线，从原始资料到可用知识库",
    icon: Factory,
    businessDomain: "知识管理",
    stageTag: "process",
    path: "/knowledge-factory",
    licenseModule: "knowledge",
    sortOrder: 5,
    sortKey: "zhishigongchang",
    isBuiltin: true,
  },
  {
    id: "knowledge",
    name: "知识库",
    description: "检索企业知识资产，RAG 增强问答与智能引用",
    icon: BookOpen,
    businessDomain: "知识管理",
    stageTag: "retrieve",
    path: "/knowledge",
    licenseModule: "knowledge",
    sortOrder: 6,
    sortKey: "zhishiku",
    isBuiltin: true,
  },
  {
    id: "output",
    name: "报告输出",
    description: "一键生成多格式报告成果，模板化排版与导出",
    icon: FileOutput,
    businessDomain: "报告编撰",
    stageTag: "output",
    path: "/output",
    licenseModule: "report",
    sortOrder: 7,
    sortKey: "baogaochushu",
    isBuiltin: true,
  },
  {
    id: "procurement",
    name: "采购管理",
    description: "合同价格分析与采购分项管理，聚类归并与统计",
    icon: PackageSearch,
    businessDomain: "采购管理",
    stageTag: "process",
    path: "/contract-price",
    licenseModule: null,
    sortOrder: 8,
    sortKey: "caigouguanli",
    isBuiltin: true,
  },
  {
    id: "admin",
    name: "系统管理",
    description: "用户、角色、部门与权限的统一管理后台",
    icon: Settings2,
    businessDomain: "admin",
    stageTag: "manage",
    path: "/admin",
    licenseModule: null,
    adminOnly: true,
    sortOrder: 9,
    sortKey: "xitongguanli",
    isBuiltin: true,
  },
];
```

> 注意：文件头部的 `import` 保持不变（仅移除不再使用的 `Factory` 等，实际均仍在使用故保留），只替换 `BUILTIN_APPS` 数组。

- [ ] **Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/config/apps.ts
```

Expected: 无类型错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/config/apps.ts
git commit -m "refactor(app-center): 9 个内置应用迁移至 businessDomain + stageTag"
```

---

### Task 4: 更新 useApps hook

**Files:**
- Modify: `frontend/src/extensions/app-center/hooks/useApps.ts`

- [ ] **Step 1: 替换 useApps.ts**

将 `hooks/useApps.ts` 完整替换为：

```typescript
"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/extensions/hooks/useAuth";
import { useLicense } from "@/extensions/license/useLicense";

import { BUILTIN_APPS } from "../config/apps";
import {
  getDomainLabel,
  UNIVERSAL_DOMAINS,
  UNIVERSAL_DOMAIN_SET,
} from "../config/categories";
import type {
  AppDefinition,
  BusinessDomainKey,
  DomainFilter,
  SortMode,
} from "../types";

export interface DomainFilterOption {
  key: DomainFilter;
  label: string;
  count: number;
}

export interface UseAppsReturn {
  apps: AppDefinition[];
  visibleApps: AppDefinition[];
  allApps: AppDefinition[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  sortMode: SortMode;
  setSortMode: (mode: SortMode) => void;
  activeDomain: DomainFilter;
  setActiveDomain: (d: DomainFilter) => void;
  domainOptions: DomainFilterOption[];
  licenseLoading: boolean;
}

/**
 * 应用中心主 hook：聚合搜索、排序、业务域筛选与权限过滤。
 */
export function useApps(
  favorites: Set<string>,
  isFavoriteHydrated: boolean,
): UseAppsReturn {
  const { user } = useAuth();
  const { hasModule, isLoading: licenseLoading } = useLicense();

  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("default");
  const [activeDomain, setActiveDomain] = useState<DomainFilter>("all");

  const isAdmin = user?.role_name === "Super Admin";

  // 1. 权限过滤
  const visibleApps = useMemo(() => {
    return BUILTIN_APPS.filter((app) => {
      if (app.adminOnly && !isAdmin) return false;
      if (app.licenseModule && !licenseLoading && !hasModule(app.licenseModule))
        return false;
      return true;
    });
  }, [hasModule, isAdmin, licenseLoading]);

  // 2. 业务域筛选项（通用域在前，业务域按首次出现顺序，含数量）
  const domainOptions = useMemo<DomainFilterOption[]>(() => {
    const counts = new Map<BusinessDomainKey, number>();
    const seenOrder: BusinessDomainKey[] = [];

    for (const app of visibleApps) {
      const d = app.businessDomain;
      if (!counts.has(d)) seenOrder.push(d);
      counts.set(d, (counts.get(d) ?? 0) + 1);
    }

    // 通用域在前（按 UNIVERSAL_DOMAINS 声明顺序），业务域按首次出现顺序
    const ordered = [
      ...UNIVERSAL_DOMAINS.filter((d) => counts.has(d)),
      ...seenOrder.filter((d) => !UNIVERSAL_DOMAIN_SET.has(d)),
    ];

    return [
      { key: "all", label: "全部", count: visibleApps.length },
      ...ordered.map((key) => ({
        key,
        label: getDomainLabel(key),
        count: counts.get(key) ?? 0,
      })),
    ];
  }, [visibleApps]);

  // 3. 搜索 + 域筛选 + 排序
  const apps = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let list = visibleApps;

    if (activeDomain !== "all") {
      list = list.filter((a) => a.businessDomain === activeDomain);
    }

    if (q) {
      list = list.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q),
      );
    }

    const sorted = [...list];
    switch (sortMode) {
      case "alphabetical":
        sorted.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
        break;
      case "favorites-first":
        sorted.sort((a, b) => {
          const af = isFavoriteHydrated && favorites.has(a.id) ? 0 : 1;
          const bf = isFavoriteHydrated && favorites.has(b.id) ? 0 : 1;
          if (af !== bf) return af - bf;
          return a.sortOrder - b.sortOrder;
        });
        break;
      case "default":
      default:
        sorted.sort((a, b) => a.sortOrder - b.sortOrder);
        break;
    }
    return sorted;
  }, [visibleApps, activeDomain, searchQuery, sortMode, favorites, isFavoriteHydrated]);

  return {
    apps,
    visibleApps,
    allApps: BUILTIN_APPS,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeDomain,
    setActiveDomain,
    domainOptions,
    licenseLoading,
  };
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/hooks/useApps.ts
```

Expected: 无类型错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/hooks/useApps.ts
git commit -m "refactor(app-center): useApps — category 筛选改为 businessDomain 自动派生"
```

---

### Task 5: 更新 AppCard 组件

**Files:**
- Modify: `frontend/src/extensions/app-center/components/AppCard.tsx`

- [ ] **Step 1: 更新卡片**

将 `components/AppCard.tsx` 完整替换为：

```typescript
"use client";

import { Star } from "lucide-react";
import Link from "next/link";
import { memo, useMemo } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import {
  ACCENT_STYLES,
  getDomainAccent,
  getDomainLabel,
  STAGE_LABELS,
} from "../config/categories";
import type { AppDefinition } from "../types";

interface AppCardProps {
  app: AppDefinition;
  isFavorite: boolean;
  onToggleFavorite: (appId: string) => void;
  /** 业务域首次出现顺序（用于 accent 确定性分配） */
  domainOrder: string[];
}

function AppCardImpl({
  app,
  isFavorite,
  onToggleFavorite,
  domainOrder,
}: AppCardProps) {
  const Icon = app.icon;
  const accentColor = useMemo(
    () => getDomainAccent(app.businessDomain, domainOrder),
    [app.businessDomain, domainOrder],
  );
  const accent = ACCENT_STYLES[accentColor];
  const domainLabel = getDomainLabel(app.businessDomain);
  const stageLabel = app.stageTag ? STAGE_LABELS[app.stageTag] : null;

  const handleFavoriteClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite(app.id);
  };

  return (
    <Link
      href={app.path}
      role="link"
      aria-label={`${app.name} — ${app.description}`}
      className={cn(
        "group relative flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm transition-all",
        "hover:-translate-y-1 hover:border-primary/30 hover:bg-accent/40 hover:shadow-lg hover:shadow-primary/5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        isFavorite && "border-primary/40 ring-1 ring-primary/10",
      )}
    >
      {/* 收藏按钮 */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={handleFavoriteClick}
            aria-label={isFavorite ? `取消收藏 ${app.name}` : `收藏 ${app.name}`}
            aria-pressed={isFavorite}
            className={cn(
              "absolute right-3 top-3 z-10 flex size-7 items-center justify-center rounded-full transition-all",
              "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
              isFavorite && "opacity-100",
              "hover:scale-110 active:scale-95",
              isFavorite
                ? "text-amber-500 hover:bg-amber-500/10"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <Star
              className="size-4 transition-all"
              fill={isFavorite ? "currentColor" : "none"}
              strokeWidth={isFavorite ? 0 : 2}
            />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">
          {isFavorite ? "取消收藏" : "添加到收藏"}
        </TooltipContent>
      </Tooltip>

      {/* 图标容器 */}
      <div
        className={cn(
          "flex size-11 shrink-0 items-center justify-center rounded-xl ring-1 transition-transform group-hover:scale-105",
          accent.container,
        )}
      >
        <Icon className={cn("size-5", accent.icon)} />
      </div>

      {/* 文本区 */}
      <div className="flex min-w-0 flex-col gap-1">
        <h3 className="truncate text-sm font-semibold text-foreground">
          {app.name}
        </h3>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
          {app.description}
        </p>
      </div>

      {/* 标签行：业务域角标 + 功能阶段徽章 */}
      <div className="mt-auto flex items-center gap-1.5 pt-1">
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
            accent.tag,
          )}
        >
          {domainLabel}
        </span>
        {stageLabel && (
          <span className="inline-flex items-center rounded-full border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {stageLabel}
          </span>
        )}
      </div>
    </Link>
  );
}

export const AppCard = memo(AppCardImpl);
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/components/AppCard.tsx
```

Expected: 无类型错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/components/AppCard.tsx
git commit -m "refactor(app-center): AppCard — 业务域标签 + stageTag 徽章，accent 自动分配"
```

---

### Task 6: 更新 CategoryTabs 组件

**Files:**
- Modify: `frontend/src/extensions/app-center/components/CategoryTabs.tsx`

- [ ] **Step 1: 类型重命名**

将 `components/CategoryTabs.tsx` 的第 5 行和第 11 行中的 `CategoryFilterOption` 替换为 `DomainFilterOption`：

```typescript
"use client";

import { cn } from "@/lib/utils";

import type { DomainFilterOption } from "../hooks/useApps";

interface CategoryTabsProps {
  options: DomainFilterOption[];
  active: string;
  onChange: (key: DomainFilterOption["key"]) => void;
}
```

> 其余代码不变（`aria-label="按分类筛选"` 等文案保持，组件名不变以最小化 diff）。

- [ ] **Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit src/extensions/app-center/components/CategoryTabs.tsx
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/app-center/components/CategoryTabs.tsx
git commit -m "refactor(app-center): CategoryTabs — CategoryFilterOption → DomainFilterOption"
```

---

### Task 7: 更新 AppCenterToolbar + AppGrid + AppCenterPage

**Files:**
- Modify: `frontend/src/extensions/app-center/components/AppCenterToolbar.tsx`
- Modify: `frontend/src/extensions/app-center/components/AppGrid.tsx`
- Modify: `frontend/src/extensions/app-center/AppCenterPage.tsx`

- [ ] **Step 1: 更新 AppCenterToolbar.tsx**

将 `AppCenterToolbar.tsx` 中的 `CategoryFilter`/`CategoryFilterOption` 替换为 `DomainFilter`/`DomainFilterOption`，prop 名 `categoryOptions` → `domainOptions`，`activeCategory` → `activeDomain`：

```typescript
"use client";

import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { DomainFilterOption } from "../hooks/useApps";
import type { DomainFilter, SortMode } from "../types";

import { CategoryTabs } from "./CategoryTabs";
import { SortControl } from "./SortControl";

interface AppCenterToolbarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  domainOptions: DomainFilterOption[];
  activeDomain: DomainFilter;
  onDomainChange: (key: DomainFilter) => void;
  sortMode: SortMode;
  onSortChange: (mode: SortMode) => void;
}

export function AppCenterToolbar({
  searchQuery,
  onSearchChange,
  domainOptions,
  activeDomain,
  onDomainChange,
  sortMode,
  onSortChange,
}: AppCenterToolbarProps) {
  const hasQuery = searchQuery.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="relative">
        <Search
          className={cn(
            "pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground",
          )}
        />
        <Input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label="搜索应用"
          placeholder="搜索应用名称或功能..."
          className={cn(
            "h-11 rounded-xl border-border bg-muted/50 pl-10 pr-10 text-sm transition-colors",
            "placeholder:text-muted-foreground/70 focus-visible:bg-background",
          )}
        />
        {hasQuery && (
          <button
            type="button"
            onClick={() => onSearchChange("")}
            aria-label="清除搜索"
            className="absolute right-3 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CategoryTabs
          options={domainOptions}
          active={activeDomain}
          onChange={onDomainChange}
        />
        <SortControl value={sortMode} onChange={onSortChange} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 更新 AppGrid.tsx**

`AppGrid` 需要透传 `domainOrder` 给 `AppCard`。修改 `components/AppGrid.tsx`：

将第 6-16 行替换为：

```typescript
import type { AppDefinition } from "../types";

import { AppCard } from "./AppCard";

interface AppGridProps {
  apps: AppDefinition[];
  isLoading: boolean;
  isFavorite: (appId: string) => boolean;
  onToggleFavorite: (appId: string) => void;
  /** 业务域首次出现顺序（用于 accent 确定性分配） */
  domainOrder: string[];
}
```

将第 41-47 行的 `AppCard` 调用处添加 `domainOrder` prop：

```typescript
        <AppCard
          key={app.id}
          app={app}
          isFavorite={isFavorite(app.id)}
          onToggleFavorite={onToggleFavorite}
          domainOrder={domainOrder}
        />
```

- [ ] **Step 3: 更新 AppCenterPage.tsx**

修改 `AppCenterPage.tsx`，替换类型和 prop 名：

1. 第 23-31 行，解构 `useApps` 返回值时重命名：
```typescript
  const {
    apps,
    visibleApps,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeDomain,
    setActiveDomain,
    domainOptions,
    licenseLoading,
  } = useApps(favorites, hydrated);
```

2. 第 37 行 `activeCategory` → `activeDomain`：
```typescript
    if (activeDomain !== "all") return [];
```

3. 第 40 行 `favoriteApps` 依赖数组：
```typescript
  }, [hydrated, searchQuery, activeDomain, sortMode, visibleApps, favorites]);
```

4. 第 73-79 行，工具栏 props 更新：
```typescript
      <AppCenterToolbar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        domainOptions={domainOptions}
        activeDomain={activeDomain}
        onDomainChange={setActiveDomain}
        sortMode={sortMode}
        onSortChange={setSortMode}
      />
```

5. 第 88-95 行和第 113-119 行，`AppGrid` 添加 `domainOrder` prop。需要先计算 domainOrder：

在 `showFavorites` 之后添加：
```typescript
  // 业务域首次出现顺序（与 useApps 中 domainOptions 的派生逻辑一致，用于 AppCard accent 分配）
  const domainOrder = useMemo(() => {
    const seen: string[] = [];
    for (const app of visibleApps) {
      if (!seen.includes(app.businessDomain)) seen.push(app.businessDomain);
    }
    return seen;
  }, [visibleApps]);
```

然后两处 `<AppGrid` 都加上 `domainOrder={domainOrder}`。

- [ ] **Step 4: 验证**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 全局无类型错误。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/app-center/components/AppCenterToolbar.tsx
git add frontend/src/extensions/app-center/components/AppGrid.tsx
git add frontend/src/extensions/app-center/AppCenterPage.tsx
git commit -m "refactor(app-center): Toolbar/Grid/Page — category → businessDomain prop 全链路重命名"
```

---

### Task 8: 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 启动前端并检查页面**

```bash
docker compose -p eai-docker restart frontend
```

等待重启完成后，访问 `http://localhost:2026/app-center`，验证：

1. 分类 pills 显示：`全部(9)` `通用工具(3)` `系统管理(1)` `报告编撰(2)` `知识管理(2)` `采购管理(1)`
2. 点击每个业务域 pill，筛选正确
3. 卡片上显示业务域标签 + 功能阶段徽章（如工作台显示"通用工具"+"概览"）
4. 搜索、排序、收藏功能正常

- [ ] **Step 2: 检查控制台错误**

打开浏览器 DevTools Console，确认无 React 报错、无 TypeScript 运行时错误。

- [ ] **Step 3: Commit（如有微调）**

```bash
git add -A
git commit -m "chore(app-center): 分类重构端到端验证通过"
```
