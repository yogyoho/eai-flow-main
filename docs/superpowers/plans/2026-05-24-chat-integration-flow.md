# PM ↔ DeerFlow Chat 集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现项目管理模块与 DeerFlow 对话页的双向导航与上下文传递，包括统一跳转函数、面包屑组件、返回导航和自动刷新。

**Architecture:** URL 参数协议 + ProjectBreadcrumbBar 组件 + Visibility API 自动刷新。纯前端变更，无后端修改。

**Tech Stack:** Next.js 16, React 19, TypeScript, Shadcn UI, Lucide Icons, TanStack Query

**Design Spec:** `docs/superpowers/specs/2026-05-24-chat-integration-flow-design.md`

---

## File Structure

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Create | `src/extensions/project/navigateToChat.ts` | 统一跳转 URL 构建函数 |
| Create | `src/extensions/project/ProjectBreadcrumbBar.tsx` | 对话页上下文面包屑组件 |
| Modify | `src/extensions/project/ChapterWritingPanel.tsx:47-57` | Stage 3 使用新跳转函数 |
| Modify | `src/extensions/project/ChapterEditingPanel.tsx:43-53` | Stage 4 使用新跳转函数 |
| Modify | `src/app/workspace/chats/[thread_id]/page.tsx:60,151-160` | 替换布尔面包屑为新组件 |
| Modify | `src/extensions/project/ProjectWorkspace.tsx` | 添加 Visibility API 自动刷新 |

---

### Task 1: 统一跳转工具函数

**Files:**
- Create: `src/extensions/project/navigateToChat.ts`

- [ ] **Step 1: 创建 navigateToChat 工具函数**

```typescript
// src/extensions/project/navigateToChat.ts

import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";

export type ChatNavigateMode = "writing" | "editing" | "ai-tool" | "review";

export interface NavigateToChatOptions {
  router: AppRouterInstance;
  threadId: string;
  projectId: string;
  projectName: string;
  stage: number;
  chapterId?: string;
  chapterName?: string;
  mode: ChatNavigateMode;
}

export function navigateToChat({
  router,
  threadId,
  projectId,
  projectName,
  stage,
  chapterId,
  chapterName,
  mode,
}: NavigateToChatOptions) {
  const params = new URLSearchParams({
    from: "project",
    projectId,
    projectName,
    stage: String(stage),
    mode,
  });

  if (chapterId) {
    params.set("chapterId", chapterId);
  }
  if (chapterName) {
    params.set("chapterName", chapterName);
  }

  router.push(`/workspace/chats/${threadId}?${params.toString()}`);
}
```

- [ ] **Step 2: 验证类型正确**

Run: `cd frontend && pnpm typecheck`
Expected: PASS（无类型错误）

- [ ] **Step 3: Commit**

```bash
git add src/extensions/project/navigateToChat.ts
git commit -m "feat(project): add navigateToChat URL builder utility"
```

---

### Task 2: ProjectBreadcrumbBar 面包屑组件

**Files:**
- Create: `src/extensions/project/ProjectBreadcrumbBar.tsx`

- [ ] **Step 1: 创建面包屑组件**

```tsx
// src/extensions/project/ProjectBreadcrumbBar.tsx

"use client";

import { ArrowLeft, ChevronRight, FileText, PenLine, Sparkles, CheckSquare } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import type { ChatNavigateMode } from "./navigateToChat";

interface ProjectBreadcrumbBarProps {
  projectId: string;
  projectName: string;
  stage: number;
  chapterId?: string | null;
  chapterName?: string | null;
  mode: ChatNavigateMode;
}

const MODE_CONFIG: Record<ChatNavigateMode, { label: string; tag: string; icon: typeof Sparkles }> = {
  writing: { label: "AI撰写中", tag: "全部章节", icon: Sparkles },
  editing: { label: "协作编辑", tag: "编辑模式", icon: PenLine },
  "ai-tool": { label: "AI辅助", tag: "AI工具", icon: Sparkles },
  review: { label: "审核反馈", tag: "审核模式", icon: CheckSquare },
};

const STAGE_LABELS: Record<number, string> = {
  1: "Stage 1",
  2: "Stage 2",
  3: "Stage 3",
  4: "Stage 4",
  5: "Stage 5",
  6: "Stage 6",
};

export function ProjectBreadcrumbBar({
  projectId,
  projectName,
  stage,
  chapterId,
  chapterName,
  mode,
}: ProjectBreadcrumbBarProps) {
  const config = MODE_CONFIG[mode];
  const Icon = config.icon;
  const returnHref = `/projects/${projectId}?stage=${stage}`;

  return (
    <div className="absolute top-12 right-0 left-0 z-30 flex h-9 items-center border-b border-border bg-muted/50 px-4 text-xs">
      <Link
        href={returnHref}
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
      >
        <ArrowLeft className="h-3 w-3" />
        <span>返回</span>
      </Link>

      <ChevronRight className="h-3 w-3 text-muted-foreground/50 mx-1.5 shrink-0" />

      <Link
        href={returnHref}
        className="text-foreground hover:text-primary transition-colors truncate max-w-[200px]"
      >
        {projectName}
      </Link>

      {chapterName && (
        <>
          <ChevronRight className="h-3 w-3 text-muted-foreground/50 mx-1.5 shrink-0" />
          <span className="text-muted-foreground truncate max-w-[200px]">
            {chapterName}
          </span>
        </>
      )}

      <ChevronRight className="h-3 w-3 text-muted-foreground/50 mx-1.5 shrink-0" />

      <div className="flex items-center gap-1 text-primary shrink-0">
        <Icon className="h-3 w-3" />
        <span>{config.label}</span>
      </div>

      <div className="ml-auto flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground/70">{STAGE_LABELS[stage]}</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="text-muted-foreground/70">{config.tag}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 验证类型和 lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/extensions/project/ProjectBreadcrumbBar.tsx
git commit -m "feat(project): add ProjectBreadcrumbBar component for chat context"
```

---

### Task 3: 增强对话页集成面包屑

**Files:**
- Modify: `src/app/workspace/chats/[thread_id]/page.tsx`

- [ ] **Step 1: 在对话页中读取完整 URL 参数并渲染面包屑**

在 `page.tsx` 中：

1. 替换第 60 行的 `const fromProject = searchParams.get("from") === "project";` 为完整参数读取：

```typescript
const fromProject = searchParams.get("from") === "project";
const projectContext = fromProject
  ? {
      projectId: searchParams.get("projectId") ?? "",
      projectName: decodeURIComponent(searchParams.get("projectName") ?? ""),
      stage: Number(searchParams.get("stage")) || 3,
      chapterId: searchParams.get("chapterId"),
      chapterName: searchParams.get("chapterName")
        ? decodeURIComponent(searchParams.get("chapterName")!)
        : null,
      mode: (searchParams.get("mode") as "writing" | "editing" | "ai-tool" | "review") ?? "writing",
    }
  : null;
```

2. 添加 import:
```typescript
import { ProjectBreadcrumbBar } from "@/extensions/project/ProjectBreadcrumbBar";
```

3. 替换第 151-160 行的面包屑渲染：

将原来的：
```tsx
{fromProject && (
  <div className="absolute top-12 right-0 left-0 z-30 flex h-8 items-center border-b border-border bg-muted/50 px-4 text-xs">
    <Link
      href="/projects"
      className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="h-3 w-3" />
      返回项目列表
    </Link>
  </div>
)}
```

替换为：
```tsx
{projectContext && (
  <ProjectBreadcrumbBar
    projectId={projectContext.projectId}
    projectName={projectContext.projectName}
    stage={projectContext.stage}
    chapterId={projectContext.chapterId}
    chapterName={projectContext.chapterName}
    mode={projectContext.mode}
  />
)}
```

4. 因为不再直接使用 ArrowLeft + Link 的组合（由 ProjectBreadcrumbBar 内部处理），如果 `fromProject` 相关的 `ArrowLeft` import 不再被其他地方使用，可以移除。但检查发现 `ArrowLeft` 在第 157 行使用——替换后由 `ProjectBreadcrumbBar` 接管，所以 `page.tsx` 中不再需要 `ArrowLeft` 的 import。移除 `import Link from "next/link"` 和 `import { ArrowLeft } from "lucide-react"`（如果这些仅被 `fromProject` 面包屑使用的话）。

- [ ] **Step 2: 验证类型和 lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/app/workspace/chats/[thread_id]/page.tsx
git commit -m "feat(project): integrate ProjectBreadcrumbBar into chat page"
```

---

### Task 4: 更新 ChapterWritingPanel 跳转

**Files:**
- Modify: `src/extensions/project/ChapterWritingPanel.tsx`

- [ ] **Step 1: 使用 navigateToChat 替代硬编码 URL**

添加 import：
```typescript
import { navigateToChat } from "./navigateToChat";
```

替换 `handleStartWriting` 函数（第 47-57 行）：

将原来的：
```typescript
const handleStartWriting = useCallback(async () => {
  setLoading(true);
  try {
    const result = await projectApi.startWriting(projectId);
    router.push(`/workspace/chats/${result.threadId}?from=project`);
  } catch {
    toast.error("启动 AI 撰写失败");
  } finally {
    setLoading(false);
  }
}, [projectId, router]);
```

替换为：
```typescript
const handleStartWriting = useCallback(async () => {
  setLoading(true);
  try {
    const result = await projectApi.startWriting(projectId);
    navigateToChat({
      router,
      threadId: result.threadId,
      projectId,
      projectName,
      stage: 3,
      mode: "writing",
    });
  } catch {
    toast.error("启动 AI 撰写失败");
  } finally {
    setLoading(false);
  }
}, [projectId, projectName, router]);
```

- [ ] **Step 2: 验证类型**

Run: `cd frontend && pnpm typecheck`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/extensions/project/ChapterWritingPanel.tsx
git commit -m "feat(project): use navigateToChat in ChapterWritingPanel"
```

---

### Task 5: 更新 ChapterEditingPanel 跳转

**Files:**
- Modify: `src/extensions/project/ChapterEditingPanel.tsx`

- [ ] **Step 1: 使用 navigateToChat 替代硬编码 URL**

添加 import：
```typescript
import { navigateToChat } from "./navigateToChat";
```

替换 `handleStartEditing` 函数（第 43-53 行）：

将原来的：
```typescript
const handleStartEditing = useCallback(async (chapterId: string) => {
  setLoadingChapterId(chapterId);
  try {
    const result = await projectApi.startChapterEditing(project.id, chapterId);
    router.push(`/workspace/chats/${result.threadId}?from=project`);
  } catch {
    toast.error("启动编辑失败");
  } finally {
    setLoadingChapterId(null);
  }
}, [project.id, router]);
```

替换为：
```typescript
const handleStartEditing = useCallback(async (chapterId: string) => {
  setLoadingChapterId(chapterId);
  try {
    const result = await projectApi.startChapterEditing(project.id, chapterId);
    const chapter = flat.find((c) => c.id === chapterId);
    navigateToChat({
      router,
      threadId: result.threadId,
      projectId: project.id,
      projectName: project.name,
      stage: 4,
      chapterId,
      chapterName: chapter?.title,
      mode: "editing",
    });
  } catch {
    toast.error("启动编辑失败");
  } finally {
    setLoadingChapterId(null);
  }
}, [project.id, project.name, flat, router]);
```

- [ ] **Step 2: 验证类型**

Run: `cd frontend && pnpm typecheck`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/extensions/project/ChapterEditingPanel.tsx
git commit -m "feat(project): use navigateToChat in ChapterEditingPanel"
```

---

### Task 6: 添加自动刷新机制

**Files:**
- Modify: `src/extensions/project/ProjectWorkspace.tsx`

- [ ] **Step 1: 添加 Visibility API 自动刷新**

在 `ProjectWorkspace` 组件中，在 `useEffect` 加载数据之后，添加 Visibility API 监听：

在现有的 `loadProject` `useEffect` 之后（第 72 行之后）添加：

```typescript
// Auto-refresh project data when returning from chat page
useEffect(() => {
  const handleVisibility = () => {
    if (document.visibilityState === "visible") {
      loadProject();
    }
  };
  document.addEventListener("visibilitychange", handleVisibility);
  return () => document.removeEventListener("visibilitychange", handleVisibility);
}, [loadProject]);
```

- [ ] **Step 2: 验证类型**

Run: `cd frontend && pnpm typecheck`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/extensions/project/ProjectWorkspace.tsx
git commit -m "feat(project): auto-refresh project data on visibility change"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 启动开发服务器**

Run: `cd frontend && pnpm dev`

- [ ] **Step 2: 验证 Stage 3 流程**

1. 打开项目列表 `/projects`
2. 进入 Stage 3 的项目
3. 点击「开始 AI 撰写」
4. 确认跳转到对话页，面包屑显示：「← 返回 > XX项目 > AI撰写中 > Stage 3 · 全部章节」
5. 确认返回按钮指向 `/projects/{id}?stage=3`
6. 点击返回，确认项目数据已刷新

- [ ] **Step 3: 验证 Stage 4 流程**

1. 进入 Stage 4 的项目
2. 点击某个章节的「开始编辑」
3. 确认面包屑显示：「← 返回 > XX项目 > 第3章 生态环境 > 协作编辑 > Stage 4 · 编辑模式」
4. 确认返回按钮指向 `/projects/{id}?stage=4`
5. 点击返回，确认数据已刷新

- [ ] **Step 4: 验证向后兼容**

1. 手动访问 `/workspace/chats/{threadId}?from=project`
2. 确认旧格式的 URL 不会崩溃（面包屑可能不完整，但不会报错）

- [ ] **Step 5: 最终 Commit**

```bash
git add -A
git commit -m "feat(project): complete PM-Chat integration with breadcrumb and auto-refresh"
```
