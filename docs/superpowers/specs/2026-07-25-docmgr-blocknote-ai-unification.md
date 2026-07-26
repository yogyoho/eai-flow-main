# 文档空间 AI 助手重构 — BlockNote 统一方案

- **日期**: 2026-07-25
- **状态**: 待实现

## 1. 目标

将「我的文档」编辑页从 Tiptap 迁移到 BlockNote，统一 AI 编辑体验：
- BlockNote 内置 AI 处理内联编辑操作（润色/扩写/精简/续写）
- DocAIAgentPanel 保留为文档对话助手（分析、建议、审查）
- 删除自建的 function calling 工具链和 Tiptap AI 标记

## 2. 架构

```
┌─────────────────────────────────────────────────────────┐
│                   DocumentEditor                         │
│                                                         │
│  ┌─────────────────────────┐  ┌──────────────────────┐ │
│  │   BlockNoteEditor        │  │  DocAIAgentPanel     │ │
│  │                          │  │                      │ │
│  │  AIExtension (内联)      │  │  useStream (LangGraph)│ │
│  │  DefaultChatTransport    │  │  lead_agent          │ │
│  │  /api/collab/ai-chat     │  │  模式 pill           │ │
│  │                          │  │  消息面板            │ │
│  │  选中文字 → 润色/扩写等  │  │  对话历史持久化     │ │
│  └─────────────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 3. 文件变更

### 新增
- （无新增文件，复用现有 BlockNote 基础设施）

### 修改

| 文件 | 变更 |
|---|---|
| `DocumentManagement.tsx` | DocumentEditor: TiptapEditor → BlockNoteEditor |
| `DocAIAgentPanel.tsx` | 移除 editor bridge，保留聊天功能 |

### 删除

| 文件 | 原因 |
|---|---|
| `tiptap/ai-insertion.ts` | BlockNote 内置 accept/reject |
| `tiptap/ai-deletion.ts` | 同上 |
| `tiptap/ai-review.ts` | 同上 |
| `tiptap/ai-format.ts` | 同上 |
| `editor_tools.py` | 不再需要 function calling |
| `editor_mcp.py` | 不再需要 MCP |

### 配置清理

| 文件 | 变更 |
|---|---|
| `config.yaml` | 删除 3 个 docmgr 工具注册 |
| `extensions_config.json` | 删除 docmgr-editor-tools MCP（已删除） |

### TiptapEditor 清理

| 方法 | 处理 |
|---|---|
| `insertAtPosition` | 删除 |
| `markRange` | 删除 |
| `clearAllAIMarks` | 删除 |
| `acceptAllChanges` | 删除 |
| `rejectAllChanges` | 删除 |
| `acceptChange` | 删除 |
| `rejectChange` | 删除 |
| `getReviewComments` | 删除 |
| `setContent` | 删除 |

## 4. BlockNote 集成细节

### 4.1 AI Transport

```typescript
const aiTransport = new DefaultChatTransport({
  api: "/api/collab/ai-chat",
  credentials: "include",
});
```

复用现有 `collab_ai_chat.py` 后端，无需修改。

### 4.2 无协作模式

BlockNote 在「我的文档」中不使用 Yjs 协作：

```typescript
const editor = useCreateBlockNote({
  dictionary: { ...coreEn, ai: aiEn },
  extensions: [AIExtension({ transport: aiTransport })],
  // 不传 collaboration 参数
});
```

### 4.3 内容加载/保存

```typescript
// 加载: BlockNote JSON ↔ Markdown
const blocks = await editor.tryParseMarkdownToBlocks(markdownContent);
editor.replaceBlocks(editor.document, blocks);

// 保存: BlockNote → Markdown
const markdown = await editor.blocksToMarkdownLossy(editor.document);
```

## 5. DocAIAgentPanel 简化

| 移除 | 保留 |
|---|---|
| `applyEditorOperations` | 模式 pill（内容/合规/格式/对话） |
| `EDITOR_TOOL_NAMES` | StreamMessageList |
| `interceptToolResults` | useDocAIThread |
| `appliedToolResults` | handleSubmit（纯对话 prompt） |
| `threadMsgCache`（editor 操作相关） | resetThread / handleNewChat |
| `reloadEditorEffect` | 模型选择器 |

### Prompt 简化

```typescript
const contextByMode = {
  content: `当前文档《${docTitle}》全文:\n\`\`\`markdown\n${docContent}\n\`\`\`\n\n用户指令: ${message}`,
  // ... 其他模式类似，不要求工具调用
};
```

## 6. 实施顺序

1. DocumentEditor: TiptapEditor → BlockNoteEditor
2. BlockNote 内容加载/保存适配
3. DocAIAgentPanel 简化（移除 editor bridge 代码）
4. TiptapEditor AI 方法清理
5. 删除不再需要的文件（4 AI marks, editor_tools.py, editor_mcp.py）
6. config.yaml 清理
7. 端到端验证
