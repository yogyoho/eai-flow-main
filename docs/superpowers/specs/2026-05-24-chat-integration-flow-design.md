# PM ↔ DeerFlow Chat 深度集成流程设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在项目管理模块与 DeerFlow 对话页之间建立完整的双向导航与上下文传递，让用户在 PM 页面和 AI 对话之间无缝切换，且对话结果自动回写到项目章节。

**Architecture:** URL 参数传递上下文 + 面包屑组件 + 自动刷新机制。PM 页面通过增强 URL 参数将项目/章节信息传递给对话页；对话页渲染上下文感知的面包屑导航栏；返回时 PM 页面自动刷新数据。

**Tech Stack:** Next.js 16 App Router, React 19, URL searchParams, Shadcn UI, Lucide Icons, TanStack Query refetch

**依赖的已有设计：**
- `2026-05-23-ai-writing-deerflow-integration-design.md` — MCP Server + Skill 架构
- `2026-05-24-project-management-redesign.md` — PM 模块全面重设计

---

## 1. 问题分析

### 1.1 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| 跳转到对话页 | `?from=project` 布尔值 | 无法知道是哪个项目、哪个章节 |
| 返回导航 | 固定链接到 `/projects` | 无法返回到具体的 Stage 页面 |
| 对话结果回写 | MCP `write_chapter` 工具 | 用户看不到回写状态，需手动刷新 |
| 上下文感知 | 无 | 用户在对话页不知道自己在做什么任务 |
| 多入口统一 | 无 | 不同 PM 页面跳转到对话页后体验一致 |

### 1.2 目标状态

1. 用户从任何 PM 页面进入对话页，都能清楚看到上下文：「XX项目 > 第3章 > AI撰写」
2. 返回导航精确到 Stage 级别：直接回到 `/projects/{id}?stage=3`
3. 对话完成后回到 PM 页面，章节状态和内容已更新（自动刷新）
4. 所有 PM→Chat 入口使用统一的 URL 参数协议

---

## 2. URL 参数协议

### 2.1 参数定义

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `from` | string | 是 | 固定值 `"project"`，标识来源 |
| `projectId` | UUID | 是 | 项目 ID |
| `projectName` | string | 是 | 项目名称（URL-encoded） |
| `stage` | number | 是 | 当前 Stage 编号 (1-6) |
| `chapterId` | UUID | 否 | 章节 ID（Stage 4 和 AI Toolbox 有值） |
| `chapterName` | string | 否 | 章节标题（URL-encoded） |
| `mode` | string | 是 | 交互模式：`"writing"`, `"editing"`, `"ai-tool"`, `"review"` |

### 2.2 各场景 URL 示例

**Stage 3 AI 撰写（项目级）：**
```
/workspace/chats/{threadId}?from=project&projectId=abc123&projectName=XX环评报告&stage=3&mode=writing
```

**Stage 4 协作编辑（章节级）：**
```
/workspace/chats/{threadId}?from=project&projectId=abc123&projectName=XX环评报告&stage=4&chapterId=def456&chapterName=第3章+生态环境影响分析&mode=editing
```

**AI Toolbox（工具级）：**
```
/workspace/chats/{threadId}?from=project&projectId=abc123&projectName=XX环评报告&stage=3&chapterId=def456&chapterName=第3章&mode=ai-tool
```

**Approval Review（审核级）：**
```
/workspace/chats/{threadId}?from=project&projectId=abc123&projectName=XX环评报告&stage=5&chapterId=def456&chapterName=第3章&mode=review
```

---

## 3. 面包屑导航栏组件

### 3.1 组件规格

**名称：** `ProjectBreadcrumbBar`

**位置：** 对话页 header 下方，absolute 定位，高 36px

**视觉样式：**
- 背景：`bg-muted/50`（半透明）
- 边框：`border-b border-border`
- 文字：`text-xs text-muted-foreground`
- 图标：Lucide `ChevronRight` 分隔，`ArrowLeft` 返回

**三种布局：**

#### 布局 A：AI 撰写模式（mode=writing）

```
[← 返回] XX环评报告 > AI撰写中
         Stage 3 · 全部章节
```

面包屑路径：项目名称 → 固定文案 "AI撰写中"
右侧标签：Stage 编号 + 范围

#### 布局 B：协作编辑模式（mode=editing）

```
[← 返回] XX环评报告 > 第3章 生态环境影响分析 > 协作编辑
         Stage 4 · 编辑模式
```

面包屑路径：项目名称 → 章节名称 → 固定文案 "协作编辑"

#### 布局 C：AI 工具模式（mode=ai-tool）

```
[← 返回] XX环评报告 > 第3章 > 内容润色
         Stage 3 · AI辅助
```

面包屑路径：项目名称 → 章节名称 → 工具名称

### 3.2 返回导航行为

| 条件 | 返回目标 |
|------|---------|
| 有 `projectId` + `stage` | `/projects/{projectId}?stage={stage}` |
| 仅有 `projectId` | `/projects/{projectId}` |
| 仅有 `from=project` | `/projects`（向后兼容） |

返回时使用 `router.push()` 而非 `router.replace()`，保留浏览器历史。

### 3.3 组件接口

```typescript
interface ProjectBreadcrumbBarProps {
  projectId: string;
  projectName: string;
  stage: number;
  chapterId?: string;
  chapterName?: string;
  mode: "writing" | "editing" | "ai-tool" | "review";
}
```

---

## 4. PM 页面跳转逻辑增强

### 4.1 ChapterWritingPanel（Stage 3）

当前：
```typescript
router.push(`/workspace/chats/${result.threadId}?from=project`);
```

增强为：
```typescript
const params = new URLSearchParams({
  from: "project",
  projectId: projectId,
  projectName: projectName,
  stage: "3",
  mode: "writing",
});
router.push(`/workspace/chats/${result.threadId}?${params}`);
```

### 4.2 ChapterEditingPanel（Stage 4）

当前：
```typescript
router.push(`/workspace/chats/${result.threadId}?from=project`);
```

增强为：
```typescript
const chapter = flat.find(c => c.id === chapterId);
const params = new URLSearchParams({
  from: "project",
  projectId: project.id,
  projectName: project.name,
  stage: "4",
  chapterId: chapterId,
  chapterName: chapter?.title ?? "",
  mode: "editing",
});
router.push(`/workspace/chats/${result.threadId}?${params}`);
```

### 4.3 AI Toolbox（新增）

```typescript
const params = new URLSearchParams({
  from: "project",
  projectId: project.id,
  projectName: project.name,
  stage: "3",
  chapterId: selectedChapterId,
  chapterName: selectedChapterTitle,
  mode: "ai-tool",
});
router.push(`/workspace/chats/${result.threadId}?${params}`);
```

### 4.4 Approval（新增）

```typescript
const params = new URLSearchParams({
  from: "project",
  projectId: project.id,
  projectName: project.name,
  stage: "5",
  chapterId: chapterId,
  chapterName: chapterTitle,
  mode: "review",
});
router.push(`/workspace/chats/${result.threadId}?${params}`);
```

---

## 5. 返回刷新机制

### 5.1 自动刷新策略

当用户从对话页返回 PM 页面时，PM 页面需要自动刷新项目数据以反映 AI 回写的章节内容。

**方案：Visibility API + TanStack Query refetch**

```typescript
// ProjectWorkspace.tsx 中
useEffect(() => {
  const handleVisibility = () => {
    if (document.visibilityState === "visible") {
      // 页面重新可见时刷新数据
      loadProject();
    }
  };
  document.addEventListener("visibilitychange", handleVisibility);
  return () => document.removeEventListener("visibilitychange", handleVisibility);
}, [loadProject]);
```

同时在 `useEffect` 依赖中添加路由变化：
```typescript
// 当从对话页返回时，URL 变化触发刷新
useEffect(() => {
  loadProject();
}, [loadProject]);
```

### 5.2 章节状态轮询（Stage 3 AI 撰写中）

当项目处于 Stage 3 且有活跃的 AI 撰写 thread 时，前端可以轮询章节状态：

```typescript
// ChapterWritingPanel 中
useEffect(() => {
  if (currentStage !== 3) return;
  const interval = setInterval(() => {
    loadProject(); // 刷新章节状态
  }, 15000); // 每15秒轮询
  return () => clearInterval(interval);
}, [currentStage, loadProject]);
```

### 5.3 写入反馈指示

当 MCP `write_chapter` 回写成功时，后端可返回确认。但由于回写发生在 Agent 侧（后端），前端无法实时感知。使用轮询是当前最简方案。

---

## 6. 交互时序图

### 6.1 Stage 3 AI 撰写完整流程

```
用户                  ChapterWritingPanel         ChatPage               Agent (DeerFlow)         MCP Server
 │                         │                         │                         │                       │
 │  点击"开始AI撰写"       │                         │                         │                       │
 │──────────────────────►  │                         │                         │                       │
 │                         │  POST /start-writing    │                         │                       │
 │                         │─────────────────────────────────────────────────►│                       │
 │                         │  {threadId, projectId}  │                         │                       │
 │                         │◄────────────────────────────────────────────────│                       │
 │                         │                         │                         │                       │
 │                         │  router.push             │                         │                       │
 │                         │  /chats/{tid}?           │                         │                       │
 │                         │  from=project&           │                         │                       │
 │                         │  projectId=...&          │                         │                       │
 │                         │  projectName=...&        │                         │                       │
 │                         │  stage=3&mode=writing    │                         │                       │
 │                         │────────────────────────►│                         │                       │
 │                         │                         │                         │                       │
 │                         │                         │  渲染面包屑:            │                       │
 │                         │                         │  "XX项目 > AI撰写中"    │                       │
 │                         │                         │                         │                       │
 │  发送"开始撰写第1章"    │                         │                         │                       │
 │─────────────────────────────────────────────────►│  提交消息到 thread      │                       │
 │                         │                         │────────────────────────►│                       │
 │                         │                         │                         │  get_chapter_spec(ch1) │
 │                         │                         │                         │──────────────────────►│
 │                         │                         │                         │  返回编写规格          │
 │                         │                         │                         │◄──────────────────────│
 │                         │                         │                         │                       │
 │                         │                         │                         │  生成内容...           │
 │                         │                         │                         │                       │
 │                         │                         │                         │  write_chapter(ch1,    │
 │                         │                         │                         │  content, "draft")     │
 │                         │                         │                         │──────────────────────►│
 │                         │                         │                         │  更新成功              │
 │                         │                         │                         │◄──────────────────────│
 │                         │                         │                         │                       │
 │  看到AI回复             │                         │                         │                       │
 │◄─────────────────────────────────────────────────│  流式展示               │                       │
 │                         │                         │                         │                       │
 │  点击面包屑"返回"       │                         │                         │                       │
 │─────────────────────────────────────────────────►│                         │                       │
 │                         │  /projects/{id}?stage=3 │                         │                       │
 │                         │◄────────────────────────│                         │                       │
 │                         │                         │                         │                       │
 │                         │  自动刷新项目数据        │                         │                       │
 │                         │  章节状态已更新为draft   │                         │                       │
 │                         │                         │                         │                       │
```

---

## 7. 设计约束

1. **不修改对话页核心代码** — 只在 header 区域新增面包屑组件，不影响 MessageList、InputBox、Artifact 等核心组件
2. **URL 参数而非 Context API** — 使用 URL searchParams 传递上下文，确保页面刷新不丢失状态，且支持分享链接
3. **向后兼容** — 旧的 `?from=project` URL 仍然有效，只是面包屑信息不完整
4. **中文 URL 编码** — `projectName` 和 `chapterName` 通过 `encodeURIComponent` 编码
5. **轮询而非 WebSocket** — 使用 Visibility API + 定时轮询刷新数据，不引入 WebSocket 复杂度
6. **所有 PM→Chat 入口统一** — `navigateToChat()` 工具函数统一处理 URL 构建

---

## 8. 新增/修改文件清单

### 8.1 新增文件

| 文件 | 说明 | 代码量 |
|------|------|--------|
| `frontend/src/extensions/project/ProjectBreadcrumbBar.tsx` | 对话页面包屑组件 | ~120 行 |
| `frontend/src/extensions/project/navigateToChat.ts` | 统一跳转工具函数 | ~30 行 |

### 8.2 修改文件

| 文件 | 修改内容 | 变更量 |
|------|---------|--------|
| `frontend/src/app/workspace/chats/[thread_id]/page.tsx` | 替换 `fromProject` 布尔判断为 `ProjectBreadcrumbBar` 组件 | ~20 行变更 |
| `frontend/src/extensions/project/ChapterWritingPanel.tsx` | 使用 `navigateToChat()` 替代硬编码 URL | ~10 行变更 |
| `frontend/src/extensions/project/ChapterEditingPanel.tsx` | 使用 `navigateToChat()` 替代硬编码 URL | ~10 行变更 |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | 添加 Visibility API 自动刷新 | ~15 行变更 |

### 8.3 不修改的文件

- DeerFlow 对话页核心组件（MessageList、InputBox、ArtifactPanel）
- DeerFlow Agent 系统
- 后端 API（URL 参数是纯前端传递）
- MCP Server 和 Skill 文件
