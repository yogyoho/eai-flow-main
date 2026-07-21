# 文档空间（我的文档）— 右侧 AI 助手功能完善设计

日期: 2026-07-21
状态: 待实现

## 背景

「我的文档」入口使用 Tiptap 编辑器（`DocumentManagement.tsx` → `TiptapEditor.tsx`），右侧 AI 助手由 `AIEditPanel` 组件实现。当前功能较为基础，仅支持 4 种快捷操作（润色/扩写/缩写/头脑风暴）+ 自由对话，且均为一次性请求-响应模式。用户期望覆盖三大人群需求：个人写作辅助、文档质量把控、知识型写作。

## 当前架构

```
┌─────────────────────┐  ┌──────────────────────┐
│    Tiptap 编辑器     │  │    AIEditPanel (360px) │
│                     │  │                      │
│  [目录] [正文区]     │  │  [润色][扩写][缩写][头脑风暴] ← 需选中才可用
│                     │  │                      │
│                     │  │  自由对话区           │
│                     │  │  · 总结要点           │
│                     │  │  · 优化结构           │
│                     │  │                      │
│                     │  │  [输入框] [模型▼] [发送] │
│                     │  │                      │
│                     │  │  每条回复: [替换] [复制] │
└─────────────────────┘  └──────────────────────┘
```

**涉及文件**：
- 前端: `frontend/src/extensions/docmgr/DocumentManagement.tsx` — `DocumentEditor` + `AIEditPanel`
- 前端: `frontend/src/extensions/docmgr/TiptapEditor.tsx` — 编辑器本体
- 前端 API: `frontend/src/extensions/api/index.ts` — `docmgrApi.aiEdit()`
- 后端: `backend/app/extensions/docmgr/routers.py` — `POST /documents/ai-edit`

**数据流（现状）**：
```
选中文字/输入指令 → fetch POST /api/docmgr/documents/ai-edit
  → docmgr routers ai_edit_text()
    → create_chat_model().ainvoke(prompt)
      → 返回 { result: "..." }
        → AIEditPanel 追加 assistant 消息 → 显示 [替换] [复制]
```

## 功能蓝图

### P0 — 核心体验缺陷（4 项）

| # | 功能 | 现状 | 目标 |
|---|------|------|------|
| 1 | **流式输出** | 一次性返回 | SSE 逐字输出 |
| 2 | **无选中也能用快捷操作** | 4 pill 全部置灰 | 作用于全文或光标段落 |
| 3 | **插入到光标** | 只有"替换" | 增加"插入"按钮 |
| 4 | **对话持久化** | 切文档清空 | 按 docId 内存缓存 |

### P1 — 写作增强（5 项）

| # | 功能 | 说明 |
|---|------|------|
| 5 | **更多快捷操作** | 翻译、续写、总结、语气调整 |
| 6 | **文档审查** | 移植 `AIDocumentReview`：审查 + 评分 + 逐条意见 |
| 7 | **上下文感知建议** | 根据文档类型动态推荐提示词 |
| 8 | **结果 Diff 预览** | 替换前显示 before/after |
| 9 | **撤销 AI 编辑** | 替换/插入后可一键撤销 |

### P2 — 文档质量把控（3 项）

| # | 功能 | 说明 |
|---|------|------|
| 10 | **全文一键润色** | 分段处理大文本 |
| 11 | **格式规范化** | 标题/列表/中英文空格/标点 |
| 12 | **可读性报告** | 统计 + 改进建议 |

### P3 — 项目集成 / 远期（3 项）

| # | 功能 | 说明 |
|---|------|------|
| 13 | **引用项目文档** | 文档检索 + 上下文注入 |
| 14 | **逐段批量处理** | 批量执行同一 AI 操作 |
| 15 | **对话导出** | Markdown 导出 |

## 实施路线

```
第1轮 (P0): 流式输出 → 无选中快捷操作 → 插入到光标 → 对话持久化
第2轮 (P1): 更多操作 + 文档审查 → 上下文建议 → Diff预览 → 撤销
第3轮 (P2): 全文润色 → 格式规范 → 可读性
第4轮 (P3): 项目引用 → 批量处理 → 导出
```

## 第1轮详细设计 (P0)

### 1. 流式输出

**后端变更** (`backend/app/extensions/docmgr/routers.py`):
- 新增 `POST /documents/ai-edit/stream` 端点，返回 `text/event-stream`
- 使用 `create_chat_model().astream()` 替代 `ainvoke()`
- SSE 格式: `data: {"token": "..."}\n\n` + 结束信号 `data: [DONE]\n\n`
- 保留原 `/ai-edit` 端点兼容旧版

**前端变更** (`AIEditPanel`):
- `sendMessage` 中检测是否支持流式（优先用 stream 端点）
- 使用 `fetch` + `ReadableStream` 读取 SSE
- 逐 token 追加到最新 assistant 消息
- 流式完成后追加 [替换][复制] 操作按钮
- 流式期间显示光标闪烁动画

### 2. 无选中也能用快捷操作

**前端变更** (`AIEditPanel`):
- 移除 pill 的 `disabled` 状态
- 无选中时：
  - 润色/扩写/缩写/续写：作用于"光标所在段落"（通过 `editorRef` 获取当前段落文本）或"全文"
  - 头脑风暴：作用于全文
- pill 下方加一行小字提示当前作用范围："将对全文执行润色" / "将对选中文字执行润色"
- `handleQuickAction` 中 `getSelectedText()` 为空时，改用光标段落或全文作为输入

### 3. 插入到光标

**前端变更** (`AIEditPanel`):
- 每条 assistant 消息下方增加第三个按钮：`[替换] [插入] [复制]`
- 替换：`editorRef.current?.replaceSelection(content)`（现有）
- 插入：`editorRef.current?.replaceSelection(content)` 但当无选中时等同于插入到光标位置
- 需要在 `TiptapEditorRef` 中新增 `insertAtCursor(text: string)` 方法
- `TiptapEditor` 实现：`editor.chain().focus().insertContent(text).run()`

### 4. 对话持久化

**前端变更** (`AIEditPanel`):
- 用 `useRef<Map<string, ChatMessage[]>>` 缓存按 docId 的对话历史
- 切换文档时保存当前对话到缓存，加载目标文档的缓存对话
- 最多保留每个文档最近 50 条消息
- 会话级别缓存（不跨页面刷新，够用且简单）
- ponytail: 不做后端持久化，内存缓存满足切文档场景。需要跨刷新时再加。

## 不变的部分

- `TiptapEditor` 本身不修改
- `DocumentManagement.tsx` 的整体布局不变
- `AIEditPanel` 的 UI 框架（头部/快捷操作/消息区/输入框）保持现有结构，渐进增强
- 后端 `POST /documents/ai-edit` 端点保留，新增 stream 端点作为增强
- 模型选择器保持现有实现
