# 协同编辑器 AI 功能整合与评论工具栏设计

日期: 2026-05-30
状态: 待实现

## 背景

协同编辑器存在两套 AI 功能重叠：行内工具栏的 AI 操作（润色/扩写/精简/头脑风暴/续写/生成大纲）和右侧 AI 面板的 AIToolbar 组件提供相同的四个操作（润色/扩写/精简/头脑风暴）。用户需要明确的心智模型来区分两个入口。此外，右侧面板体系包含评论、版本历史、AI、溯源四个面板，但溯源面板的切换机制与其他三个不同（独立浮动按钮），缺乏统一性。

## 设计目标

1. 消除 AI 功能重叠，给两个入口明确分工
2. 在行内工具栏添加评论入口，参照 BlockNode 官方 comments 模式
3. 统一右侧面板体系，将溯源纳入统一切换机制

## 职责划分

### 行内工具栏（选中即操作）

文字操作和评论的快捷入口，选中文字后弹出 FormattingToolbar：

```
[格式化工具...] | [MessageSquare 评论] | [Sparkles AI]
```

- **AI 操作**（不变）：润色、扩写、精简、续写、头脑风暴、生成大纲
- **评论操作**（新增）：点击后弹出 Popover 输入框，提交后保存评论并自动打开右侧评论面板
- 交互：就地编辑 → 接受/拒绝（AI）/ 提交并跳转（评论）

### 右侧面板（全文级功能）

统一为四个互斥面板，通过顶部工具栏按钮切换：

| 面板 | 图标（lucide） | 标题 | 功能 |
|---|---|---|---|
| 评论 | `MessageSquare` | 评论 | 评论列表、回复、标记已解决 |
| 版本历史 | `History` | 版本历史 | 版本列表、Diff 对比、恢复（不变） |
| AI 文档审查 | `Sparkles` | AI 文档审查 | 全面审查、风格检查、逻辑审查、完整性检查 + 评分 + 插入评论 |
| 溯源 | `BookOpen` | 溯源 | 内容来源追溯（从 CollabEditor 层下沉到统一面板） |

`SidePanel` 类型更新为：`"comments" | "versions" | "ai" | "traceability" | null`

## 变更清单

### 1. 行内工具栏增加评论按钮

**文件**: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- 在 `FormattingToolbar` 中，`<AIToolbarButton />` 左侧添加评论工具按钮
- 使用 BlockNote 的 `FormattingToolbar.Button` 组件，图标为 `MessageSquare`
- 点击后弹出 Popover（内含 Textarea + 提交按钮），提交调用 `handleCreateComment(blockId, content)`
- 提交后自动执行 `setSidePanel("comments")` 跳转到评论面板
- 获取当前选中文字所在 block 的 ID 作为评论锚点

### 2. AI 面板精简为纯审查

**文件**: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- 移除 `AIToolbar` 组件的 import 和渲染（约 15 行）
- 将 `import { AIToolbar } from "./AIToolbar"` 移除
- 面板标题从"AI 助手"改为"AI 文档审查"
- `AIDocumentReview` 组件保留不变，成为 AI 面板的唯一内容

**文件**: `frontend/src/extensions/collab/AIToolbar.tsx` — 可整体删除

### 3. 溯源面板纳入统一侧边栏

**文件**: `frontend/src/extensions/collab/CollabEditor.tsx`

- 移除 `showTrace` state 和右上角浮动的 `BookOpen` 按钮
- 将 `projectId` 透传给 `BlockNoteEditor`

**文件**: `frontend/src/extensions/collab/BlockNoteEditor.tsx`

- `BlockNoteEditorProps` 增加 `projectId?: string`
- `SidePanel` 类型增加 `"traceability"`
- 顶部工具栏增加第四个按钮（`BookOpen` 图标，title="溯源"），仅当 `projectId` 存在时渲染
- `sidePanel === "traceability"` 时渲染 `TraceabilityPanel`，使用与其他面板一致的容器样式（`w-80 border-l`）

### 4. 不变的部分

- `CommentThread.tsx` — 不变
- `CommentSidebar.tsx` — 不变
- `BlockCommentAnchor.tsx` — 不变
- `InlineCommentThread.tsx` — 不变
- `AIDocumentReview.tsx` — 不变
- `VersionPanel.tsx` — 不变
- `aiMenuItems.tsx` — 不变（行内 AI 菜单项保持原样）
- `aiTransport.ts` — 不变
- `useComments.ts` — 不变
- `useVersions.ts` — 不变

## 数据流

```
选中文字 → FormattingToolbar 弹出
  ├── 点击 [MessageSquare] → Popover 输入框 → handleCreateComment → 右侧评论面板
  ├── 点击 [Sparkles] → AIMenu → AI 就地编辑 → 接受/拒绝
  └── 格式化操作（不变）

顶部工具栏切换 → sidePanel state
  ├── "comments" → CommentSidebar
  ├── "versions" → VersionPanel
  ├── "ai" → AIDocumentReview
  └── "traceability" → TraceabilityPanel
```
