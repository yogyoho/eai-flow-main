# 文档空间 — AI Agent 编辑器协作设计

- **日期**: 2026-07-24
- **状态**: 待实现

## 1. 目标

AI 对话页 + 文档空间 = 两阶段流水线：

1. **Phase 1 (对话页)**: 写作 Skill 生成工程报告初稿 → outputs/
2. **Phase 2 (文档空间)**: AI Agent 助手精细化修改完善

AI 助手提供三大能力：内容修改、合规审查、格式规范，通过 MCP 工具驱动 Tiptap 编辑器实时渲染协作标记（增删改/批注/格式调整）。

**核心原则：不动 deer-flow 前后端代码。** 所有新增在 extensions 层。

## 2. 能力全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI 对话页 (Phase 1)                               │
│  写作 Skill "煤矿工程报告生成"                                        │
│  ├─ 根据需求描述生成初稿                                             │
│  ├─ 自动填充标准章节模板                                             │
│  └─ 输出 → outputs/xxx.md                                           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ 打开文档
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    文档空间 AI 助手 (Phase 2)                         │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 📝 内容  │  │ 🔍 合规  │  │ 📐 格式  │  │ 💬 自由对话      │   │
│  │   修改   │  │   审查   │  │   规范   │  │                  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
│                                                                     │
│  快捷 Pill: [章节扩展] [数据校验] [安全审查] [术语统一] [更多▼]       │
│                                                                     │
│  MCP 工具层                                                         │
│  ├─ edit_document  ── 驱动编辑器实时修改（增删改标记）               │
│  ├─ read_document  ── 读当前文档内容/指定章节                        │
│  └─ review_document── 合规审查标注（波浪线+批注弹窗+条款引用）      │
│                                                                     │
│  知识层                                                             │
│  ├─ Skill: 煤矿报告审查规则（检查清单、指标范围、结构模板、术语表）   │
│  └─ MCP 知识库: 煤矿安全规程、GB 标准条款原文                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 📝 内容修改

| 功能 | Agent 行为 | 编辑器表现 |
|---|---|---|
| 章节扩展 | 读取目标章节 → 补充技术细节/参数/计算 | 新增文字 = 绿色下划线 |
| 章节缩写 | 提炼核心内容，删除冗余 | 待删文字 = 红色删除线 |
| 数据修正 | 校验数据一致性 → 修正错误值 | 旧值删除线 + 新值下划线 |
| 表述优化 | 改善专业表达，消除歧义 | 替换区域可视化 diff |
| 结构重组 | 调整章节顺序/层级 | 标题层级变更高亮 |
| 计算补充 | bash 沙箱执行工程计算 → 插入结果 | `公式=结果` 绿色下划线 |

### 2.2 🔍 合规审查

| 审查项 | 依据来源 | Agent 行为 |
|---|---|---|
| 安全规程对照 | MCP 知识库 → 煤矿安全规程原文 | 逐条比对，不符处打波浪线标注 |
| 技术指标校验 | Skill 内置指标范围 | 数值超限标记，提供标准范围引用 |
| 术语规范检查 | Skill 内置术语表 | 不规范术语波浪线 + 建议替换词 |
| 缺失项检查 | Skill 内置章节清单 | 缺失的必需要素列表提醒 |
| 法规引用核实 | MCP 知识库 → 法规条款 | 错误引用标注 + 正确条款原文 |

### 2.3 📐 格式规范

| 功能 | Agent 行为 | 编辑器表现 |
|---|---|---|
| 标题层级标准化 | 检测并修正标题嵌套逻辑 | 变更标记 |
| 图表编号 | 自动编号 + 交叉引用链接 | 插入编号 |
| 术语统一 | 全文查找不一致术语 → 批量替换 | 逐个替换标记 |
| 引用格式规范化 | 标准 GB/T 7714 引用格式 | 修改标记 |
| 中英文排版 | 中英文间加空格、标点规范化 | 修改标记 |

## 3. 交互设计

```
文档编辑器顶部工具栏
┌──────────────────────────────────────────────────────────────┐
│ ← 返回   [标题]                           [AI 助手] [导出▼] │
└──────────────────────────────────────────────────────────────┘

AI 助手面板 (右侧, 420px)
┌──────────────────────────┐
│ ✨ AI 助手     [新对话][×] │
├──────────────────────────┤
│ 📝内容 [🔍合规] [📐格式] [💬] │  ← pill 模式切换
├──────────────────────────┤
│                          │
│  对话消息区               │
│  (复用 MessageList)      │
│                          │
│  Agent 操作实时反馈:      │
│  ├─ "已完成第3章安全审查"  │
│  ├─ "发现2处术语不规范"    │
│  └─ "新增1处支护计算验证"  │
│                          │
├──────────────────────────┤
│ [接受全部] [拒绝] [逐条]   │
├──────────────────────────┤
│ [输入框...]        [发送] │
│ [模型选择▾]              │
└──────────────────────────┘
```

- 模式 pill 切换时，发送给 Agent 的 system context 自动调整（content/compliance/format/chat）
- 用户可在自由对话中随时切换任务，Agent 通过上下文 + 工具调用灵活响应

## 4. 技术架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        文档编辑页 (前端)                              │
│  ┌──────────────────────┐    ┌─────────────────────────────────────┐ │
│  │    Tiptap Editor      │    │        DocAIAgentPanel (新)          │ │
│  │                       │    │                                     │ │
│  │  · ai-insertion mark  │◄───│  拦截 SSE tool_call 事件            │ │
│  │    (绿色下划线)        │    │  → 解析 operation → 调用 editor API │ │
│  │  · ai-deletion mark   │    │                                     │ │
│  │    (红色删除线)        │    │  复用 MessageList (消息渲染)         │ │
│  │  · ai-review mark     │    │  复用 InputBox (输入+模型选择)       │ │
│  │    (橙色波浪虚线+弹窗) │    │                                     │ │
│  │  · ai-format mark     │    │  useStream() → LangGraph SDK        │ │
│  │    (蓝色下划线)        │    │  useDocAIThread (子thread 懒创建)    │ │
│  └──────────────────────┘    └──────────────┬──────────────────────┘ │
└─────────────────────────────────────────────┼────────────────────────┘
                                              │ SSE stream
┌─────────────────────────────────────────────┼────────────────────────┐
│                               LangGraph Runtime (Gateway, 不动)      │
│  ┌──────────────────────────────────────────┴──────────────────────┐ │
│  │  lead_agent (完整能力)                                           │ │
│  │  ├─ sandbox tools (read_file, write_file, str_replace, bash...) │ │
│  │  ├─ MCP tools → docmgr-editor-tools (新增)                       │ │
│  │  │   ├─ edit_document(operations, file_path)                     │ │
│  │  │   ├─ read_document(file_path, section?)                       │ │
│  │  │   └─ review_document(comments, file_path)                     │ │
│  │  ├─ MCP tools → coal-mine-regulations (知识库, 新增)             │ │
│  │  │   ├─ search_regulations(query)                                │ │
│  │  │   └─ lookup_clause(clause_id)                                 │ │
│  │  ├─ Skill: coal-mine-report-review (审查规则, 新增)              │ │
│  │  └─ memory, sub-agents, 18 middlewares...                       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 关键机制：SSE 双重消费

| 层 | 行为 |
|---|---|
| **后端 MCP 工具** | 实际读写线程 outputs/ 下的 .md 文件（保证数据持久化） |
| **前端拦截器** | 解析 SSE stream 中的 ToolMessage，提取 operation 参数，驱动 Tiptap 编辑器实时渲染协作标记 |

### 子 Thread 隔离

文档编辑器创建独立子 thread（`metadata.type = "docmgr-agent"`，`metadata.parent_thread_id` 指向文档所在线程），对话历史与主对话页完全隔离。首次发送消息时懒创建。

## 5. 文件变更清单

全部在 extensions 层，不碰 deer-flow：

```
新增:
  backend/app/extensions/docmgr/
    └─ editor_mcp.py               # MCP Server: 3个编辑器工具

  skills/custom/coal-mine-report-review/
    └─ SKILL.md                     # 煤矿报告审查规则 Skill

  frontend/src/extensions/docmgr/
    ├─ DocAIAgentPanel.tsx          # 核心面板: useStream + tool call拦截 + 模式切换
    ├─ useDocAIThread.ts            # 子thread懒创建hook
    └─ tiptap/
        ├─ ai-insertion.ts          # Tiptap mark: 绿色下划线(新增文字)
        ├─ ai-deletion.ts           # Tiptap mark: 红色删除线(待删文字)
        ├─ ai-review.ts             # Tiptap mark: 橙色波浪虚线+点击弹窗(含条款引用)
        └─ ai-format.ts             # Tiptap mark: 蓝色下划线(格式调整)

修改:
  extensions_config.json            # 注册 docmgr-editor-tools + coal-mine-regulations MCP
  frontend/src/extensions/docmgr/DocumentManagement.tsx
    └─ AIEditPanel 替换为 DocAIAgentPanel (传 thread_id + editorRef + docFilePath)

删除:
  frontend/src/extensions/docmgr/DocumentManagement.tsx → 旧 AIEditPanel 组件
  frontend/src/extensions/api/index.ts → aiEdit / aiEditStream 方法
  backend/app/extensions/docmgr/routers.py → ai_edit_text / ai_edit_text_stream 端点
```

### 与 deer-flow 的边界

| 复用 (只读引用) | 不修改 |
|---|---|
| `MessageList` 组件 | deer-flow 任何代码 |
| `InputBox` 组件 | `core/threads/hooks.ts` |
| `useStream()` from `@langchain/langgraph-sdk` | `backend/app/gateway/` |
| LangGraph Runtime (Gateway) | `backend/packages/harness/` |
| `getAPIClient()` from `core/api` | `config.yaml` |

## 6. MCP Server 设计

3 个工具，注册为 `docmgr-editor-tools`。

**编辑操作映射**：

| action | 修改文件? | Tiptap mark |
|---|---|---|
| `insert` | ✓ | `ai-insertion` (绿色下划线) |
| `delete` | ✓ | `ai-deletion` (红色删除线) |
| `replace` | ✓ | 旧:deletion + 新:insertion |
| `format` | ✓ | `ai-format` (蓝色下划线) |
| `review` | ✗ | `ai-review` (橙色波浪虚线+弹窗) |
| `compute` | ✗ | `ai-insertion` (计算结果) |

```python
# 工具1: edit_document
@mcp.tool()
async def edit_document(
    operations: list[dict],   # [{action, from?, to?, position?, text?, comment?, clause_ref?}]
    file_path: str,           # 绝对路径
) -> dict:
    """批量编辑操作。insert/delete/replace/format 实际写文件；review/compute 不修改文件仅透传。"""

# 工具2: read_document
@mcp.tool()
async def read_document(
    file_path: str,
    section: str = None,      # 可选：章节标题，如 "2.安全技术措施"
) -> dict:
    """读文档全文或指定章节。返回 {content, line_count, char_count}"""

# 工具3: review_document
@mcp.tool()
async def review_document(
    comments: list[dict],     # [{from, to, comment, severity, clause_ref}]
    file_path: str,
) -> dict:
    """批量合规审查标注。severity: "info"|"warning"|"error"。clause_ref: 引用条款。"""
```

### 设计决策
- **edit_document 实际写文件** — insert/delete/replace/format 确保数据持久化
- **review 不改文件** — 仅返回结构化数据供前端渲染波浪批注
- **file_path 使用绝对路径** — 前端构造完整沙箱路径传入
- **计算走 bash 沙箱** — agent 用已有 `bash` 工具执行计算，再用 `edit_document(action:"compute")` 插入结果
- **操作顺序执行** — 数组顺序即执行顺序

## 7. Tiptap 协作标记

4 个 Prosemirror mark 扩展：

### `ai-insertion` — AI 新增文字
- 渲染：绿色下划线 `text-decoration-color: #22c55e`
- 接受：移除 mark，文字保留

### `ai-deletion` — AI 标记删除
- 渲染：红色删除线 `text-decoration: line-through; color: #9ca3af`
- 接受：真删除对应文字

### `ai-review` — AI 合规审查
- 渲染：橙色波浪虚线 `text-decoration-style: wavy; text-decoration-color: #f97316`
- 点击 → NodeView Popover 显示 comment + severity + clause_ref 链接

### `ai-format` — AI 格式调整
- 渲染：蓝色下划线 `text-decoration-color: #3b82f6`
- 接受：移除 mark

### 接受/拒绝操作
- **[接受全部]**：移除所有 mark，保留内容变更
- **[拒绝全部]**：移除所有 mark，恢复原文字
- **[逐条审阅▼]**：展开每条变更，逐条接受/拒绝

## 8. DocAIAgentPanel 设计

### Props
```typescript
interface DocAIAgentPanelProps {
  threadId: string;
  docFilePath: string;
  editorRef: Ref<TiptapEditorRef>;
  onClose: () => void;
}
```

### useDocAIThread
首次发送消息时懒创建子 thread（`metadata.parent_thread_id`），之后复用。

### 模式系统
```typescript
type AIMode = "content" | "compliance" | "format" | "chat";

const MODE_CONFIG = {
  content:     { label: "📝 内容", context: "请帮助修改和完善文档内容" },
  compliance:  { label: "🔍 合规", context: "请使用 review_document 工具标注审查结果, 每条标注附带 clause_ref" },
  format:      { label: "📐 格式", context: "请使用 edit_document 工具调整文档格式, 使用 action:'format'" },
  chat:        { label: "💬 对话", context: "" },
};
```

### Tool Call 拦截器
```typescript
const EDITOR_TOOLS = new Set(["edit_document", "review_document"]);

useEffect(() => {
  const lastAI = [...stream.messages].reverse().find(m => m.type === "ai");
  if (!lastAI?.tool_calls) return;
  
  for (const tc of lastAI.tool_calls) {
    if (!EDITOR_TOOLS.has(tc.name)) continue;
    const ops = tc.args.operations || tc.args.comments;
    applyEditorOperations(ops, editorRef.current);
  }
}, [stream.messages]);
```

### TiptapEditorRef 新增方法
```typescript
interface TiptapEditorRef {
  // 已有: getMarkdown, getSelectedText, replaceSelection, insertAtCursor
  // 新增:
  insertAtPosition(pos: number, text: string, opts?: { mark: string }): void;
  markRange(from: number, to: number, mark: string, attrs?: Record<string, any>): void;
  clearAllAIMarks(): void;
  acceptAllChanges(): void;
  rejectAllChanges(): void;
}
```

### 消息注入
每条消息根据当前模式自动注入文档全文 + 模式相关 context。

## 9. Skill: 煤矿报告审查规则

```yaml
# skills/custom/coal-mine-report-review/SKILL.md
name: 煤矿工程报告合规审查
description: 对照煤矿安全规程审查工程报告

审查维度:
  安全规程:
    - 通风系统: 风量计算 ≥ 设计需风量 × 1.2
    - 瓦斯防治: 必须包含瓦斯抽采设计章节
    - 防尘措施: 必须包含综合防尘措施
    - 防灭火: 必须包含自然发火防治措施
    - 防治水: 必须包含水文地质分析
    - 顶板管理: 支护强度 ≥ 设计载荷 × 1.5
    - 机电运输: 设备选型须有MA标志
    - 监测监控: 须明确传感器布置方案
    - 应急救援: 须包含避灾路线图

  技术指标:
    - 巷道断面: ≥ 设计值 × 1.05 (考虑变形)
    - 支护参数: 锚杆长度 ≥ 1.8m, 间排距 ≤ 1.0m
    - 通风风速: 0.25~8 m/s (掘进巷道)

  必备章节:
    - 工程概况
    - 地质条件分析
    - 施工工艺
    - 安全技术措施
    - 劳动组织
    - 应急预案

  术语规范:
    - 统一使用"掘进工作面"(不用"掘进头")
    - 统一使用"锚杆支护"(不用"锚杆")
```

## 10. 错误处理

| 场景 | 处理 |
|---|---|
| 文件不存在 | `read_document` 返回 `{error: "FILE_NOT_FOUND"}` |
| offset 越界 | `edit_document` 返回 `{error: "INVALID_OFFSET", detail}` |
| 编辑器未保存 | 发送消息前自动 flush save |
| 子 thread 创建失败 | toast 提示 |
| SSE 流中断 | `useStream` 内置重连 |
| 并发 tool call | 按 SSE 到达顺序执行，offset 失效静默跳过 + console.warn |

## 11. 实施顺序

1. Tiptap 4 个自定义 mark + TiptapEditorRef 新增 5 个方法
2. MCP Server `editor_mcp.py` + `extensions_config.json` 注册
3. Skill `coal-mine-report-review` + MCP 知识库 `coal-mine-regulations`
4. `useDocAIThread` hook
5. `DocAIAgentPanel` 核心组件
6. `DocumentManagement.tsx` 集成 + 清理旧代码
7. E2E 验证
