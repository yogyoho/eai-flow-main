# 文档空间「我的文档」BlockNote 编辑器 — 代码 Review 与功能补全

- **日期**: 2026-08-02
- **状态**: 已实施（A/B/C10 + 数学修复）
- **范围**: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`、`DocumentManagement.tsx`、`DocAIAgentPanel.tsx` + 后端 `app/extensions/docmgr`（C10）

## 1. 背景

「文档空间 → 我的文档」点击 AI 生成的文档进入 BlockNote 编辑器页面。本文档记录对编辑器的**代码 review、功能盘点、缺口分析与已实施补全**，作为后续 D 组（AI 集成）的设计依据。

## 2. 现状功能盘点

### 2.1 编辑器内核 `PersonalBlockNoteEditor.tsx`
- BlockNote（shadcn）+ 数学公式（内联 `$...$`→latex、整段 `$$...$$`→equation、表格内公式、多段 `$$` 合并、Markdown 往返导出）
- 代码块语法高亮（lowlight 同步）、代码文件 light 主题覆盖
- BlockNote 内联 AI（润色/扩写/精简/续写/头脑风暴/生成大纲，accept/reject/retry）
- 斜杠菜单（默认 + math 项）、左侧 TOC 目录（标题点击滚动）
- 自动保存（1500ms 防抖 → markdown）
- Agent 操作锚点机制：`getBlockAnchors` / `matchAnchor`（5 级模糊）/ `applyOperations`（replace/insert_after/delete/prepend/append）/ `scrollToAnchor` / `snapshot+restore`

### 2.2 宿主页面 `DocumentManagement.tsx`（DocumentEditor）
- 加载：个人文档直读线程 `outputs/` 文件；项目文档用 `CollabEditor`；其他走 `docmgrApi`
- 代码文件 ` ```lang ` fence 包裹/剥离、保存状态指示、AI 助手可拖面板、复制、导出 .md/.docx

### 2.3 AI 助手面板 `DocAIAgentPanel.tsx`
- LangGraph 子线程聊天 + 模型选择器、3 模式（Ask 确认卡片 / Auto 自动应用 / Plan 纯分析）
- `---OPERATIONS---` JSON 操作协议 + `parseOperations` 容错
- 用户消息 localStorage 持久化、新对话

## 3. 缺口分析（综合基准：完整编辑器 + CollabEditor 兄弟能力）

### A 组 Bug（已修复）
1. Auto 模式「撤销全部」空操作（`onUndo=TBD`）
2. Auto 模式 `applyOperations` 无 try/catch，失败静默中断整批
3. `scheduleSave` 保存失败静默（丢数据风险）
4. 1500ms 防抖窗口内关闭/切档丢内容
5. 遗留 debug `console.log`
6. **Rules-of-Hooks 违规**（`useRef` 在 `mode==="auto"` 提前 return 之后调用 → ask↔auto 切换崩溃）

### B 组 编辑体验（已实现）
7. 无撤销/重做 UI 按钮 → 已加
8. 无字数统计 → 已加
9. 无查找/替换 → 已加（块级）
10. 无全屏/专注模式 → 已加（Fullscreen API）

### C10 版本历史（已实现）
11. 个人文档无版本历史，AI 反复改稿无法回退 → 已加（后端表 + API + 前端对话框 + AI 自动快照）

### D 组 AI 集成（遗留）
12. 双 AI 系统并存（BlockNote 内联 AI 无状态 `/api/collab/ai-chat` + DocAIAgentPanel 有状态 LangGraph 子线程），行为割裂
13. 每次消息注入全文+全部锚点，无压缩 → 大文档 token 爆炸
14. 面板无法引用编辑器当前选区
15. 锚点仅顶层块（嵌套/表格行不可定位）
16. 操作非流式（整轮结束才出卡片）

## 4. 已实施修复/功能

### 4.1 数学修复（bug-811）
- 根因：`TEXT_BLOCK_TYPES` 缺 `"heading"` → 标题内联公式 `$V_s$` 不渲染
- 修法：三个纯转换函数抽到 `utils/mathBlocks.ts`（可单测），集合补 `heading`；新增 `EQUATION_CAPABLE_TYPES` 限制「整段 `$$...$$`→equation」仅对 paragraph 类，防标题被替换成公式块丢层级

### 4.2 A 组（bug-817）
- `DocAIAgentPanel.tsx` OperationCards 重写：hooks 无条件上移、auto 前 `snapshotBlocks`、undo=`restoreBlocks`、`applyOperations` 包 try/catch 展示错误
- `DocumentManagement.tsx`：`scheduleSave` 拆 `doSave` 闭包 + catch 设 `saveError` + 顶部栏 AlertCircle 展示；unmount `flushPendingRef` 立即保存 + `beforeunload` 未保存警告；删除 debug log

### 4.3 B 组
- 编辑器 ref 新增 `undo`/`redo`/`findText`/`replaceInBlock`/`scrollToBlock`；顶部栏撤销/重做/查找/全屏按钮 + 常驻字数统计；查找条（实时搜索、上下、替换、全部替换）
- 新增 `utils/docEditorUtils.ts`：`computeDocStats`（字数统计）+ `replaceTextInContent`（块内文本重写，保留 latex 节点）

### 4.4 C10 版本历史
- 后端：`PersonalDocVersion` 表（`create_all` 启动自动建表）+ 4 API（create/list/get/restore）+ service 方法（cap 20）
- 前端：`VersionHistoryDialog.tsx`（列表/预览/恢复/保存当前版本）+ 顶部栏入口 + 恢复后 `editorKey` 重挂载 + `DocAIAgentPanel` 发 AI 消息前自动「AI 编辑前快照」

## 5. 验证

| 项 | 结果 |
|---|---|
| 后端 `test_docmgr_versions.py` | 5/5 通过（路由、restore 写文件、cap 裁剪） |
| 前端 docmgr 单测 | 81/82（唯一失败 `tiptap-editor-paste` 为 HEAD 既有，与本次无关） |
| 新增单测 | `mathBlocks.test.ts` 10/10、`docEditorUtils.test.ts` 6/6 |
| 前端 typecheck | 修改文件零新增错误（既有错误均为未触碰代码） |
| ruff | 新增代码零错误（既有 13 个 F401/UP 等为 HEAD 既有） |

**HEAD 既有失败（与本次无关，建议单独修）**：`test_personal_outputs.py`（陈旧测试期望 list，服务已改分页 dict）、`test_sync_outputs_to_docmgr.py::TestIsTextMime`。

## 6. 部署注意

- C10 新表 `personal_doc_versions` 需重启 gateway 自动建表：`docker compose -p eai-docker restart gateway`
- 前端改动若 HMR 不生效需重启 frontend：`docker compose -p eai-docker restart frontend`

## 7. 遗留（D 组设计方向）

1. **统一 AI 入口**：二选一 —— (a) 收敛到 DocAIAgentPanel（LangGraph 有状态，含历史），BlockNote 内联 AI 隐藏；(b) 收敛到 BlockNote AIExtension（轻量、选区感知），面板改为纯分析/审查。倾向 (a) + 保留内联 AI 的选区快捷操作。
2. **提示词压缩**：不注入全文，改为「TOC + 用户指涉段落 + 锚点表」，必要时按块分片。
3. **选区引用**：面板 prompt 注入 `getSelectedText()` 选区文本。
4. **锚点递归**：`getBlockAnchors`/`findBlockByAnchor` 支持嵌套块（列表子项、表格行）。
5. **流式操作**：操作卡片随 SSE `---OPERATIONS---` 增量出现。
