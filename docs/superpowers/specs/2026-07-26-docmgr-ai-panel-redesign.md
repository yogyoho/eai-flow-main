# 文档空间 — 右侧 AI 助手重新定位设计

- **日期**: 2026-07-26
- **状态**: 待实现

## 1. 背景

「我的文档」已从 Tiptap 迁移到 BlockNote 编辑器。BlockNote 自带 `@blocknote/xl-ai` 的 `AIExtension`，覆盖了选中文本的局部 AI 操作（润色/扩写/精简/续写/头脑风暴/大纲）。右侧 AI 助手此前通过 LangGraph `lead_agent` 实现全文对话，但定位模糊——4 个 pill（内容/合规/格式/对话）本质上只是 system prompt 前缀差异。

本设计重新定义右侧 AI 助手的定位、能力和交互方式。

## 2. 定位与分工

| | BlockNote 内置 AI | 右侧 AI 助手 |
|---|---|---|
| **操作粒度** | 选中文字 → 局部替换 | 全文 / 多 block |
| **能力** | 润色/扩写/精简/续写/头脑风暴/大纲 | 内容协作、文档审查、格式修正 |
| **交互方式** | 选中→内联预览→接受/拒绝 | 对话 + 结构化操作卡片 |
| **授权** | 逐次确认 | Agent 自判：格式修正 autoApply，内容修改逐条确认 |
| **后端** | `/api/collab/ai-chat` | LangGraph `lead_agent` via `useStream` |

两者**互补**，不重叠：
- 选中一段文字想润色 → 用 BlockNote 内置 AI（右键或 `Ctrl+J`）
- 全文级分析/多段修改/审查 → 用右侧 AI 助手

## 3. 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DocumentManagement                             │
│                                                                      │
│  ┌──────────────────────────┐  ┌───────────────────────────────────┐│
│  │  PersonalBlockNoteEditor  │  │  DocAIAgentPanel                  ││
│  │                          │  │                                   ││
│  │  AIExtension (内联 AI)    │  │  useStream ← lead_agent           ││
│  │  选中→润色/扩写/精简/续写 │  │                                   ││
│  │                          │  │  MessageList (复用对话页)        ││
│  │  暴露:                    │  │   分析文本 + 操作卡片             ││
│  │  · getMarkdown()         │  │   欢迎页（无对话时）              ││
│  │  · getBlockAnchors()     │──┤                                   ││
│  │  · applyOperations()     │  │  [输入框] [模型▼] [发送]          ││
│  │  · scrollToAnchor()      │  │                                   ││
│  └──────────────────────────┘  └───────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户输入指令
  ↓
handleSubmit():
  1. editorRef.getMarkdown()         → 全文 markdown
  2. editorRef.getBlockAnchors()     → anchor 索引
  3. 构建 prompt (system + markdown + anchors + 指令)
  4. streamState.submit(prompt)
  ↓
Agent 流式返回 SSE
  ↓
解析 SSE 消息:
  文本部分 → 渲染为 Markdown
  ---OPERATIONS--- 分隔符后 → 解析 JSON 操作数组
  ↓
autoApply: true  → 自动应用 + 通知卡片（可撤销）
autoApply: false → 逐条确认卡片（预览/应用/跳过）
```

## 4. UI 简化

**删除**：4 个模式 pill（内容/合规/格式/对话）

**保留**：模型选择器、新对话、关闭按钮

**新增**：欢迎页（无对话时）、操作卡片（autoApply 通知 / 逐条确认）

`autoApply` 由 Agent 在 system prompt 指导下自主判断，不需要额外开关。

### 欢迎页文案

```
🤖 文档 AI 助手

我能帮你做什么？

📝 内容协作
· "给第3节加一段安全措施"
· "把设计参数表格改成文字描述"
· "在文档末尾补充结论"

🔍 文档审查
· "检查公式编号是否连续"
· "这段计算逻辑有没有问题"
· "全文的术语使用是否统一"

✨ 格式修正（自动应用）
· "统一中英文之间的空格"
· "修正标题层级"

操作有预览，你可以逐条确认或拒绝。
格式修正类操作会自动应用，可一键撤销。
```

### 消息渲染：复用对话页 MessageList

当前 `DocAIAgentPanel` 使用自定义的轻量 `StreamMessageList`（仅渲染纯文本）。改为复用对话页的消息渲染体系：

**直接复用**：
- `MessageList` / `MessageItem` — 消息分组、Markdown 渲染、代码高亮
- `SafeStreamdown` — 公式（remark-math + rehype-katex）、表格、引用
- `human-input-card` — Agent 通过 `ask_clarification` 向用户追问时展示结构化卡片

**适配点**：
- 面板宽度 420px（对话页是全宽），但现有消息组件本身是响应式的
- 线程标题、分支、goal 状态等功能不适用 — 通过 props 关闭
- 操作卡片（`autoApply` 通知 / 逐条确认）作为新的消息类型嵌入 `MessageList`

**涉及组件**：
- `MessageList` — `src/components/workspace/messages/message-list.tsx`
- `SafeStreamdown` — `src/core/streamdown/components.tsx`
- `human-input-card` — `src/components/workspace/messages/human-input-card.tsx`

## 5. System Prompt 设计

Agent 收到的完整 prompt 结构：

```
你是一个文档助手。当用户提出请求时，按以下规则输出：

**输出格式**：你的回复由两部分组成，用分隔符 `---OPERATIONS---` 隔开：

[你的分析/建议/回答文本，Markdown 格式]

---OPERATIONS---
[可选的 JSON 操作数组，如不需要操作则省略此行及之后所有内容]

**操作类型**：
• replace:   替换匹配文本所在的 block
• insert_after: 在匹配文本后插入新 block
• delete:    删除匹配的 block(s)
• prepend:   在文档开头插入
• append:    在文档末尾追加

**操作定位**：使用 `anchor` 字段匹配文本（标题文字或段落开头前20字），不要用 block ID。

**格式修正类操作**：如果修改纯属格式规范化（中英文空格、标点统一、标题层级、列表缩进），设置 `autoApply: true`。涉及内容增删改的，设置 `autoApply: false`。

**审查/分析类请求**：输出分析文本即可，不需要 operations 块。

示例输出：
```
发现以下问题：

1. 第3节标题"实际参数"不够准确，建议改为"设计参数分析"
2. 中英文之间应加空格

---OPERATIONS---
[{"op":"replace","anchor":"实际参数","content":"## 设计参数分析","autoApply":false},{"op":"replace","anchor":"## 设计参数分析","content":"## 设计参数分析\\n\\n根据GB/T 50746-2012...","autoApply":true}]
```

**文档锚点索引**（定位用，不要输出这些内容）：
{anchors plain text}

**当前文档全文**：
```markdown
{markdown content}
```

**用户指令**：{user message}
```

### 设计要点

- **分隔符用文本而非 JSON 包装**：`---OPERATIONS---` 简单可靠，Agent JSON 格式错误时分析文本仍然可用
- **anchor 索引单独列出**：给 Agent 结构化的锚点列表（`[0] H2 "## 设计参数"`），Agent 引用最接近的文本
- **Few-shot 示例嵌入 system prompt**
- **`autoApply` 仅两条启发式规则**：格式修正=auto，内容修改=manual，由 Agent 自行判定

## 6. Operation 类型

| Op | 含义 | 必填字段 |
|----|------|---------|
| `replace` | 替换匹配文本所在的 block | `op`, `anchor`, `content`, `autoApply` |
| `insert_after` | 在匹配文本所在 block 后插入 | `op`, `anchor`, `content`, `autoApply` |
| `delete` | 删除匹配的 block(s) | `op`, `anchor`, `autoApply` |
| `prepend` | 文档开头插入 | `op`, `content`, `autoApply`（无需 anchor） |
| `append` | 文档末尾追加 | `op`, `content`, `autoApply`（无需 anchor） |

## 7. 锚点匹配策略

| 优先级 | 策略 | 说明 |
|--------|------|------|
| 1 | 精确匹配 | `anchor` 完全相同的一段文本 |
| 2 | 前缀匹配 | `anchor` 是某 block 文本内容的前缀 |
| 3 | 包含匹配 | `anchor` 作为子串出现，且仅匹配到 1 个 |
| 4 | 模糊匹配 | Levenshtein 距离 < 30% 的最接近 block |
| 5 | 匹配失败 | 卡片显示 "⚠️ 找不到匹配位置" + [跳过] |

多匹配时显示选项列表，让用户选择目标。

### anchor 索引格式

```typescript
type Anchor = {
  text: string;        // 截断到前 60 字符
  blockIndex: number;
  blockType: string;
  headingLevel?: number;
}
```

传给 Agent 的纯文本格式：
```
[0] H2 "## 设计参数分析"
[1] P "根据 GB/T 50746-2012 表3.3.3..."
[2] H3 "### 计算公式"
[3] P "$$K_{ZF} = 0.001461$$"
```

## 8. 操作卡片交互

### autoApply: true → 合并通知

```
┌────────────────────────────────────────┐
│ 🔧 已自动应用 2 项格式修正             │
│ 1. 统一中英文空格 (3处)                │
│ 2. 修正标题编号                        │
│ [撤销此次自动修正]                      │
└────────────────────────────────────────┘
```
- 同批次自动操作合并为一张卡片
- 提供一次撤销（前端保存逆操作）
- 2 分钟后撤销链接消失

### autoApply: false → 逐条确认

```
┌────────────────────────────────────────┐
│ ✏️ 替换 "# 实际参数"                     │
│ 旧: # 实际参数                          │
│ 新: ## 设计参数分析                     │
│ [预览定位📍]  [✅ 应用]  [✕ 跳过]      │
└────────────────────────────────────────┘
```
- 预览定位：滚动到 anchor 位置并高亮（不修改内容）
- 操作间独立
- 应用后卡片变为完成状态，底部显示 undo 链接（2分钟）

### 文档变更检测

应用前重新检查 anchor 匹配。如果匹配降级过多，显示 "⚠️ 文档已变更，此操作可能不准确" + [重试][跳过]。

## 9. 错误处理

| 场景 | 行为 |
|------|------|
| `---OPERATIONS---` 后 JSON 解析失败 | 分析文本正常显示，操作区 "⚠️ 操作指令解析失败" + [查看原始输出] |
| operation 缺必填字段 | 该条跳过，"⚠️ 操作格式不完整" |
| 操作执行失败 | "❌ 操作失败: {原因}"，不影响其他操作 |
| Agent 超时/流中断 | 已有文本正常显示，"⏱️ 响应中断，操作未生成" |
| Agent 输出 block ID 而非 anchor | 忽略，"请使用文本定位而非 ID" |

## 10. 涉及文件

### 修改

| 文件 | 变更 |
|------|------|
| `DocAIAgentPanel.tsx` | 删除 4 pill；删除 `StreamMessageList`；接入 `MessageList`（复用对话页）；新增欢迎页；新增操作卡片渲染；新增 `---OPERATIONS---` 解析 |
| `PersonalBlockNoteEditor.tsx` | `PersonalBlockNoteEditorRef` 新增 `getBlockAnchors()`、`applyOperations()`、`scrollToAnchor()` |
| `DocumentManagement.tsx` | DocAIAgentPanel props 简化（删除与 pill 相关属性，新增 `onApplyOperations` 回调）；传递 `MessageList` 所需 thread/message 数据 |

### 删除

| 文件/代码 | 原因 |
|-----------|------|
| `DocAIAgentPanel.tsx` 中 `MODE_CONFIG`、`mode` state、`handleModeSwitch` | pill 已删除 |
| `DocAIAgentPanel.tsx` 中 `modeRef`、`prompts[modeRef.current]` | system prompt 统一 |
| `DocAIAgentPanel.tsx` 中 `StreamMessageList` 及 `toDisplayText` | 替换为复用对话页 `MessageList` |

## 11. 实施顺序

1. `PersonalBlockNoteEditor.tsx` 新增 3 个方法（`getBlockAnchors` / `applyOperations` / `scrollToAnchor`）
2. `DocAIAgentPanel.tsx` 重构：删除 pill、新增操作卡片、新增 `---OPERATIONS---` 解析、新增欢迎页
3. `DocumentManagement.tsx` 对接新 props
4. 端到端验证
