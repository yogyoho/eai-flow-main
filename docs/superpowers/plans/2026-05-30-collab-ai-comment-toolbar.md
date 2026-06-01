# 协同编辑器 AI 功能整合与评论工具栏 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 整合协同编辑器 AI 功能重叠（行内工具栏为主、侧边栏纯审查），在行内工具栏添加评论入口，统一右侧面板体系。

**Architecture:** 行内 FormattingToolbar 增加 MessageSquare 评论按钮（Popover 输入框），侧边栏移除 AIToolbar 组件保留纯审查，溯源面板从 CollabEditor 层下沉到 BlockNoteEditor 统一面板切换机制。

**Tech Stack:** React 19, BlockNote (@blocknote/react, @blocknote/shadcn, @blocknote/xl-ai), lucide-react, Tailwind CSS 4

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/extensions/collab/BlockNoteEditor.tsx` | 主编辑器：增加评论工具按钮、移除 AIToolbar、接入溯源面板、统一 SidePanel 类型 |
| Modify | `frontend/src/extensions/collab/CollabEditor.tsx` | 移除溯源浮动按钮和状态，透传 projectId |
| Delete | `frontend/src/extensions/collab/AIToolbar.tsx` | 侧边栏 AI 文字操作组件（润色/扩写/精简/头脑风暴），已由行内工具栏替代 |

---

### Task 1: 移除侧边栏 AIToolbar 组件

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`
- Delete: `frontend/src/extensions/collab/AIToolbar.tsx`

- [ ] **Step 1: 移除 AIToolbar import 和渲染**

在 `BlockNoteEditor.tsx` 中：

删除 import：
```tsx
// 删除这一行
import { AIToolbar } from "./AIToolbar";
```

替换 `sidePanel === "ai"` 面板内容（原第 396-433 行），移除 AIToolbar 渲染块，只保留 AIDocumentReview：

```tsx
        {sidePanel === "ai" && (
          <div className="w-80 border-l border-border bg-background flex flex-col h-full">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="font-medium text-sm">AI 文档审查</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <AIDocumentReview
                docId={documentId}
                documentContent={editor.blocksToMarkdownLossy()}
                onInsertComment={(blockId, comment) => {
                  handleCreateComment(blockId || selectedBlockId || "", `[AI 审查] ${comment}`);
                  setSidePanel("comments");
                }}
              />
            </div>
          </div>
        )}
```

- [ ] **Step 2: 删除 AIToolbar.tsx 文件**

```bash
rm frontend/src/extensions/collab/AIToolbar.tsx
```

- [ ] **Step 3: 更新顶部按钮 title**

将 AI 按钮的 `title` 从 `"AI 助手"` 改为 `"AI 文档审查"`：

```tsx
              <Button size="icon" variant={sidePanel === "ai" ? "secondary" : "ghost"}
                onClick={() => setSidePanel(sidePanel === "ai" ? null : "ai")} title="AI 文档审查">
                <Sparkles className="w-4 h-4" />
              </Button>
```

- [ ] **Step 4: 验证编译**

```bash
cd frontend && pnpm typecheck
```

Expected: 无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx frontend/src/extensions/collab/AIToolbar.tsx
git commit -m "refactor(collab): remove AIToolbar from sidebar, keep only AIDocumentReview"
```

---

### Task 2: 行内工具栏添加评论按钮

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- [ ] **Step 1: 添加评论 Popover 组件**

在 `BlockNoteEditor.tsx` 顶部添加 import：

```tsx
import { MessageSquare, History, Sparkles, MessageCircle } from "lucide-react";
```

在 `EditorErrorBoundary` 类之后、`BlockNoteEditor` 组件之前，添加 `CommentPopoverButton` 组件：

```tsx
function CommentPopoverButton({ editor, onSubmit }: {
  editor: ReturnType<typeof useCreateBlockNote>;
  onSubmit: (blockId: string, content: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      const cursorBlock = editor.getTextCursorPosition().block;
      await onSubmit(cursorBlock.id, text.trim());
      setText("");
      setOpen(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormattingToolbar.Button
      onClick={() => setOpen(!open)}
      isSelected={open}
      mainTooltip={"评论"}
    >
      <MessageCircle className="w-4 h-4" />
    </FormattingToolbar.Button>
  );
}
```

- [ ] **Step 2: 将 CommentPopoverButton 插入 FormattingToolbar**

在 `FormattingToolbarController` 的 `formattingToolbar` 渲染中，在 `<AIToolbarButton />` 之前添加评论按钮：

```tsx
                  <FormattingToolbarController
                    formattingToolbar={() => (
                      <FormattingToolbar>
                        {...getFormattingToolbarItems()}
                        <CommentPopoverButton
                          editor={editor}
                          onSubmit={handleCreateComment}
                        />
                        <AIToolbarButton />
                      </FormattingToolbar>
                    )}
                  />
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && pnpm typecheck
```

Expected: 无类型错误。如有 `FormattingToolbar.Button` 类型问题，改用 BlockNote 的 `useComponentsContext` 获取 `Components.FormattingToolbar.Button`。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx
git commit -m "feat(collab): add comment button to inline formatting toolbar"
```

---

### Task 3: 评论提交后自动跳转评论面板

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- [ ] **Step 1: 修改 CommentPopoverButton 的 onSubmit 回调**

在 CommentPopoverButton 的使用处，将 `onSubmit` 改为同时跳转评论面板：

```tsx
                        <CommentPopoverButton
                          editor={editor}
                          onSubmit={async (blockId, content) => {
                            await handleCreateComment(blockId, content);
                            setSidePanel("comments");
                          }}
                        />
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && pnpm typecheck
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx
git commit -m "feat(collab): auto-open comment sidebar after submitting inline comment"
```

---

### Task 4: 溯源面板纳入统一侧边栏

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`
- Modify: `frontend/src/extensions/collab/CollabEditor.tsx`

- [ ] **Step 1: 更新 SidePanel 类型**

在 `BlockNoteEditor.tsx` 中：

```tsx
type SidePanel = "comments" | "versions" | "ai" | "traceability" | null;
```

添加 import：

```tsx
import { BookOpen } from "lucide-react";
```

合并 lucide import 为一行：

```tsx
import { MessageSquare, History, Sparkles, BookOpen, MessageCircle } from "lucide-react";
```

添加 TraceabilityPanel import：

```tsx
import { TraceabilityPanel } from "@/extensions/workflow/TraceabilityPanel";
```

更新 `BlockNoteEditorProps` 接收 `projectId`：

```tsx
interface BlockNoteEditorProps {
  documentId: string;
  initialContent?: string;
  projectId?: string;
}
```

更新组件参数解构：

```tsx
  function BlockNoteEditor({ documentId, initialContent, projectId }, ref) {
```

- [ ] **Step 2: 添加溯源工具栏按钮和面板渲染**

在顶部工具栏按钮组中，AI 按钮之后添加溯源按钮（仅当 `projectId` 存在时渲染）：

```tsx
              {projectId && (
                <Button size="icon" variant={sidePanel === "traceability" ? "secondary" : "ghost"}
                  onClick={() => setSidePanel(sidePanel === "traceability" ? null : "traceability")} title="溯源">
                  <BookOpen className="w-4 h-4" />
                </Button>
              )}
```

在 AI 面板之后添加溯源面板渲染（与其他面板使用一致的容器样式）：

```tsx
        {sidePanel === "traceability" && projectId && (
          <div className="w-80 border-l border-border bg-background flex flex-col h-full">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="font-medium text-sm">溯源</span>
              <Button size="icon" variant="ghost" onClick={() => setSidePanel(null)}>
                ×
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <TraceabilityPanel projectId={projectId} chapterId={null} />
            </div>
          </div>
        )}
```

- [ ] **Step 3: 修改 CollabEditor 透传 projectId**

在 `CollabEditor.tsx` 中：

移除 `showTrace` 状态和浮动按钮，将 `projectId` 透传给 `BlockNoteEditor`：

```tsx
"use client";

import { forwardRef } from "react";

import { BlockNoteEditor } from "./BlockNoteEditor";
import type { BlockNoteEditorRef } from "./BlockNoteEditor";

export type { BlockNoteEditorRef as CollabEditorRef };

interface CollabEditorProps {
  documentId: string;
  initialContent?: string;
  projectId?: string;
  onChange?: (content: string) => void;
  placeholder?: string;
  className?: string;
}

export const CollabEditor = forwardRef<BlockNoteEditorRef, CollabEditorProps>(
  function CollabEditor({ documentId, initialContent, projectId, className }, ref) {
    return (
      <div className={className} style={{ minHeight: 0, display: "flex", flexDirection: "row" }}>
        <div className="flex-1 flex flex-col overflow-hidden relative">
          <BlockNoteEditor
            ref={ref}
            documentId={documentId}
            initialContent={initialContent}
            projectId={projectId}
          />
        </div>
      </div>
    );
  },
);
```

- [ ] **Step 4: 验证编译**

```bash
cd frontend && pnpm typecheck
```

Expected: 无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx frontend/src/extensions/collab/CollabEditor.tsx
git commit -m "feat(collab): unify traceability panel into sidebar, remove floating button"
```

---

### Task 5: 验证完整功能

**Files:** 无新变更

- [ ] **Step 1: 启动前端开发服务器**

```bash
cd frontend && pnpm dev
```

- [ ] **Step 2: 验证行内工具栏评论按钮**

在浏览器中打开协同编辑页面，选中一段文字，确认工具栏显示：`[格式化...] [MessageCircle 评论] [Sparkles AI]`。

- [ ] **Step 3: 验证评论流程**

点击评论按钮，输入文字提交，确认右侧评论面板自动打开并显示新评论。

- [ ] **Step 4: 验证 AI 面板**

点击顶部 Sparkles 按钮，确认只显示 AIDocumentReview（无润色/扩写/精简/头脑风暴按钮），标题为"AI 文档审查"。

- [ ] **Step 5: 验证溯源面板**

在有 projectId 的文档中，确认顶部工具栏显示 BookOpen 按钮，点击后溯源面板在右侧显示。确认 CollabEditor 原右上角浮动 BookOpen 按钮已移除。

- [ ] **Step 6: 验证版本历史和评论面板无回归**

确认版本历史和评论面板功能不受影响。
