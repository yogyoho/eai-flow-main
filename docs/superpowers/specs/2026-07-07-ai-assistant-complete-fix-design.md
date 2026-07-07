# AI 助手完备化：P0+P1+P2 全量修复

- **日期**: 2026-07-07
- **状态**: 设计确认，待实现
- **关联**: `2026-07-07-docmgr-editor-resizable-ai-button-design.md`（缺陷清单来源）
- **架构决策**: 不复用 deerflow Agent；前端负责多轮上下文 + 历史持久化，后端无状态流式

## 目标

把文档编辑器右侧 AI 助手从「披着对话 UI 的单次文本工具」升级为完备的流式多轮文档助手，修复 P0/P1/P2 全部缺陷。

## 现状（问题）

- `AIEditPanel`（`DocumentManagement.tsx:1406+`）：UI 像聊天，但 `sendMessage` 每次只发 `{text, operation}`
- `POST /documents/ai-edit`（`routers.py:468+`）：`await model.ainvoke(prompt)` 单次无状态
- 缺陷：无流式、假对话（无多轮）、替换无 diff、全文无长度保护、brainstorm 替换语义错、错误笼统、并发 race、历史不持久

## 架构决策

- **多轮上下文**：前端 `messages` 数组，每次请求带完整历史；后端无状态
- **历史持久化**：localStorage（key `ai-chat-{docId}`），per-document
- **流式**：后端 SSE（`model.astream` + StreamingResponse），前端 fetch stream
- **不复用 deerflow Agent**：在现有 ai-edit 框架上增强

## 设计

### P0-1: 流式响应

**后端**（新增 `POST /documents/ai-edit-stream`）：
- body: `{messages: [{role, content}], operation, model_name}`
- `model.astream(messages)` 逐 token yield，FastAPI `StreamingResponse(media_type="text/event-stream")`
- SSE 格式：`data: {token}\n\n`，结束 `data: [DONE]\n\n`
- 保留原 `/documents/ai-edit`（非流式，兼容）

**前端**：
- `AIEditPanel.sendMessage` 改用 fetch + ReadableStream 解析 SSE
- token 逐字追加到 assistant 消息气泡（实时渲染，不卡 spinner）

### P0-2: 多轮上下文（真对话）

**前端**：
- `messages` state 保留完整对话（user + assistant）
- `sendMessage` 请求体改为 `{messages: buildApiMessages(), operation, model_name}`
- `buildApiMessages()`：system prompt（operation 指令）+ 历史消息 + 当前消息
- localStorage 持久化：key `ai-chat-{docId || personalKey}`，刷新恢复
- 「新对话」清空 messages + localStorage

**后端**：
- 接收 `messages` 数组，转 LangChain messages（SystemMessage/HumanMessage/AIMessage），`model.astream(messages)`

### P1-3: diff 替换预览

**前端**（新组件 `DiffPreviewDialog`）：
- 点「替换」弹 modal：左侧原文（选区文字）/ 右侧 AI 改写，红绿行级 diff（用 `diff` 库或简易逐行对比）
- 「接受」→ `replaceSelection(aiText)`；「拒绝」→ 不动
- 操作按钮从「替换」改为「对比替换」

### P1-4: 全文长度保护

**前端**：
- `getFullText()` 后检查长度，超阈值（20K 字符）弹确认框「文档较长（N 字），AI 可能截断或超时，是否继续？」
- 确认才发；取消则不发

### P1-5: brainstorm 语义修正

**前端**：
- assistant 消息若 `operation === "brainstorm"`，标记「💡 思路参考」
- 只显示「复制」按钮，**不显示「替换」**（思路不该覆盖原文）

### P2-6: 错误细化

**后端**：
- `asyncio.TimeoutError` → 504「AI 处理超时，请缩短文本或换更快的模型」
- context window 超限（捕获 model 特定异常 / 检测 token 估算）→ 400「文档过长，超出模型上下文，请缩短或分段」
- 模型连接失败 → 503「AI 模型暂不可用，请稍后重试」
- 其他 → 500「AI 处理失败，请重试」

**前端**：显示后端 detail（具体原因 + 建议），不再通用「AI 处理失败」

### P2-7: 并发 ref

**前端**：
- `AIEditPanel` 加 `runningRef = useRef(false)`
- `sendMessage` 开始 `runningRef.current = true`，结束（finally）`= false`
- 入口检查 `if (runningRef.current) return`（同步拦截，不靠 `running` state）

### P2-8: 历史持久化

P0-2 的 localStorage 已覆盖。补充：
- key 规范：`ai-chat-{docId || "personal-" + threadId + "-" + relPath}`
- 存 `{messages, activeOp, modelName}`
- 「新对话」清空 key

## 改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/docmgr/routers.py` | 新增 `POST /documents/ai-edit-stream`（SSE）；细化错误码 |
| `frontend/src/extensions/api/index.ts` | 新增 `aiEditStream`（fetch + ReadableStream） |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | `AIEditPanel` 重构：多轮 messages、fetch stream、localStorage、diff 预览、长度检查、brainstorm 标记、ref 拦截 |
| `frontend/src/extensions/docmgr/DiffPreviewDialog.tsx` | 新建 diff 预览组件 |

## 边界处理

1. **空选区 + 自定义指令**：正常发（无选中文字拼接）
2. **流式中断**（用户切走/关面板）：AbortController 取消 fetch
3. **localStorage 满**：try/catch，失败降级（仅内存）
4. **超长历史**：messages 超 20 条时，前端裁剪保留最近 10 轮（防 token 爆）
5. **diff 库**：用轻量 `diff` npm 包（行级）或自实现逐行对比（避免新依赖则自实现）

## 不变部分

- 4 个操作（polish/expand/condense/brainstorm）+ OPERATION_PROMPTS 保留
- 模型选择、建议 prompt、复制、新对话按钮保留
- 编辑器集成（getSelectedText/getFullText/replaceSelection）不变
