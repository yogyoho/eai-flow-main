# 合同分项价格分析 — 前端管理页面实现计划 (Plan 3/3)

> **For agentic workers:** 直接实现,Steps 用 checkbox 跟踪。

**Goal:** 在主前端新增 `/contract-price` 路由,6 个管理页面,调用 Plan 2 的 `/api/extensions/contract-price/*` API。

**Architecture:** 遵循现有扩展模式:`src/extensions/contract-price/`(api.ts + types.ts + 页面组件)+ `src/app/contract-price/`(路由)+ Sidebar 注册。复用 `authFetch`、`ShellLayout`、Shadcn、TanStack Query。

**Tech Stack:** Next.js 16、React 19、TS、Tailwind 4、Shadcn、lucide-react、TanStack Query

---

## 文件结构

```
src/extensions/contract-price/
├── types.ts                          # TS 类型(镜像后端 schemas)
├── api.ts                            # authFetch API 客户端
├── hooks.ts                          # TanStack Query hooks
├── components/
│   ├── DashboardView.tsx             # 功能区6 看板
│   ├── ContractsView.tsx             # 功能区1 合同清单
│   ├── ClustersView.tsx              # 功能区2 聚类审核 ⭐(左右分栏)
│   ├── ItemsView.tsx                 # 功能区3 分项明细
│   ├── TasksView.tsx                 # 功能区4 任务历史
│   ├── SettingsView.tsx              # 功能区5 配置
│   └── StatCard.tsx                  # 复用统计卡片
src/app/contract-price/
├── layout.tsx                        # ShellLayout + 子导航 tabs
├── page.tsx                          # → Dashboard
├── contracts/page.tsx
├── clusters/page.tsx
├── items/page.tsx
├── tasks/page.tsx
└── settings/page.tsx
```

---

## Task 1: types.ts + api.ts + hooks(可测)
## Task 2: layout + Dashboard(功能区6)+ StatCard
## Task 3: Contracts(功能区1)
## Task 4: Clusters(功能区2)⭐ 左右分栏
## Task 5: Items(功能区3)
## Task 6: Tasks(功能区4)
## Task 7: Settings(功能区5)
## Task 8: Sidebar 注册 + typecheck + lint
