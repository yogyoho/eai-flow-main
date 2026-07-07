# 文档空间编辑器：两栏可拖 + AI 助手按钮 + AI 助手缺陷记录

- **日期**: 2026-07-07
- **状态**: 审查完成，范围锁定 #1+#2（实现），#3 仅记录

## 本轮实现范围

### #1 两栏可拖（目录树 ↔ 编辑器）
编辑器页面（`view=editor`）保留左侧目录树，目录树宽度可横向拖动。

- `DocumentManagement.tsx:88-101`：`view=editor` 时不再 `hidden` `DocumentList`，改为目录树（`sidebarWidth` 可拖，已实现 `handleSidebarDragStart`）+ `DocumentEditor`（`flex-1`）并列
- `DocumentEditor` 去掉 `absolute inset-0` 覆盖语义，改 flex 子项
- 复用已有拖动手柄
- 注意：view 切换时 DocumentList 挂载状态保留（已 always-mounted，CSS 切换）

### #2 AI 润色 → AI 助手按钮
`DocumentManagement.tsx:1330` 文案 `AI 润色` → `AI 助手`。一行。对齐面板 header（已叫「AI 助手」line 1538）。

## #3 AI 助手缺陷（本轮不修，记录备查）

当前实现是「披着对话 UI 的单次文本工具」。

### P0 — 撞击核心体验
1. **无流式**（`routers.py:488` `await model.ainvoke`）— 长文本 10–60s 只显示 spinner，无 token 逐字流出
2. **假对话/无多轮上下文**（`routers.py:481` 每次独立 `prompt.format(text=...)`）— UI 有消息历史，但 API 不传前文，追问「再正式点」AI 不知前次结果

### P1 — 数据安全 / 正确性
3. **替换无 diff、无撤销确认**（`DocumentManagement.tsx:1516` `handleReplace` → `replaceSelection`）— 盲覆盖选区，仅靠 Tiptap Ctrl+Z 救
4. **全文操作无长度保护**（`AIEditPanel:1506` `getFullText()` 整篇传）— 30–80KB 规程超 context window 静默截断/500
5. **brainstorm 替换语义错** — 思路列表不该覆盖原文，当前 `handleReplace` 直接替换选区

### P2 — 健壮性
6. 错误信息笼统（`routers.py:500-504` 统一 500）
7. 并发 race（`AIEditPanel:1488` `running` state 异步拦不住，需 ref）
8. 对话不持久化（刷新丢失）

### 修复路线（未来如要完备）
- 流式 SSE + 前端 stream 渲染
- 多轮：后端接 messages 历史，前端传完整对话
- diff 替换（接受/拒绝）
- 全文长度检查 + 分块
