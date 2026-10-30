# docmgr AI 助手面板 v2 重构实施计划

> **For agentic workers:** 按 superpowers:subagent-driven-development 执行；两个实现块顺序派发（同一面板文件有依赖）。

**Goal:** DocAIAgentPanel 按 2026-10-30 v2 原型（`.wolf/tmp/docmgr-ai-panel-redesign-v2.html`）完全重构：eia-p2 视觉语言 + 三种交互模型统一为面板的三态（空态=快捷指令宫格；全文任务=工单+diff 卡；自由对话=消息流视觉升级）。

**原型:** `.wolf/tmp/docmgr-ai-panel-redesign-v2.html`（三案）；视觉令牌以应用现有 shadcn 语义 token 落地（primary=indigo、muted、destructive 等），不引原型 CSS 文件。

## 原型→真实数据源映射（范围裁决）

| 原型元素                                                  | 落地                                                                                                                                                                                                                                                                             | 依据                         |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| 六宫格动作卡（方案三）                                    | ✅ 复用 `PRESETS` 6 预设 + 图标/描述                                                                                                                                                                                                                                             | 既有                         |
| 执行预览条（目标 pills + 开始执行）                       | ✅ 目标=全部章节或指定节 → `startTask(op, sections)`；节列表来自新 `editorRef.getHeadings()`【2026-10-30 复审#1 勘误：`sections` 投递的是 `getHeadings().section`（后端 split_sections 桶下标），非块下标——原表述两空间混淆】                                                    | ai/transform 已收 `sections` |
| 最近操作列表                                              | ❌ 砍（无数据源，挂账 M2+）                                                                                                                                                                                                                                                      | —                            |
| 工单头（进度条 + 计划行）                                 | ✅ 进度=已完成节/总数；计划行三态由流事件推导（已完成 n → 正在处理 §x（最新 section_start）→ 待确认 n）                                                                                                                                                                          | NDJSON 事件                  |
| 逐节 diff 卡（展开/接受/拒绝）                            | ✅ 新 `sectionDiff.ts` 行级 diff；old=编辑器当前节文本（`getSectionText`），new=`op.content`；拒绝=新 reducer action（**保留该节 ops**——「恢复建议」反悔依赖 ops，且无 ops 的 ready 卡接受按钮会静默 no-op；只翻 status 不入 failed）【2026-10-30 复审裁决，原「丢弃 ops」作废】 | replace_section              |
| 批量栏（接受全部/撤销整批）+撤销提示                      | ✅ 既有 applyAll/undoAll，文案与布局照原型                                                                                                                                                                                                                                       | 既有                         |
| 消息流视觉（用户气泡/AI orb+meta）                        | ✅ 纯样式                                                                                                                                                                                                                                                                        | 既有                         |
| 停止按钮（发送中）                                        | ✅ `useStream.stop()`                                                                                                                                                                                                                                                            | SDK 既有                     |
| 回复操作条（复制/重试）                                   | ✅ 复制=剪贴板；重试=重发最后一条用户消息                                                                                                                                                                                                                                        | 既有                         |
| 思考折叠块 / 建议 chips / @上下文 pills / 👍👎 / 最近操作 | ❌ 砍（无数据源，挂账 M2：findings 契约/上下文注入）                                                                                                                                                                                                                             | —                            |

## Chunk 1 — 任务工单（先做：Chunk 2 依赖其编辑器新方法）

**Files:**

- Create: `frontend/src/extensions/docmgr/sectionDiff.ts`（~50 行 LCS 行 diff：`(oldText, newText) → Array<{type:'ctx'|'del'|'ins', text}>`，超大文本>500 行时退化为 [del 全旧, ins 全新]）
- Create: `frontend/tests/unit/docmgr/section-diff.test.ts`
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx` — ref 接口新增 `getHeadings(): {index:number, level:number, text:string}[]`（遍历 doc 取 heading 块）与 `getSectionText(anchorIndex:number): string`（`findSectionRange` 取文本）；实现放既有 useImperativeHandle。
- Modify: `frontend/src/extensions/docmgr/DocAITaskArea.tsx`：
  - reducer 增 `{type:"reject_section"; index:number}`（该节 status→"rejected"，**保留 ops**【复审裁决：恢复建议反悔依赖 ops；无 ops 的 ready 卡接受会静默 no-op】，不入 failed、不离列表；配套 `{type:"restore_section"}` 仅 rejected→ready）；`TaskSectionStatus` 增 `"rejected"`。
  - `SectionCard` → `DiffCard`：头部状态 pill（生成中/待确认/已接受/已拒绝/无变更/已跳过/失败）+ 节名 + chevron；展开区=行 diff（del 红底删除线 / ins 绿底 / ctx 灰，等宽字体）；ready 态底部 [接受][拒绝]；failed 保留错误+重试；rejected 可「恢复」。点击头部切换展开。
  - 新 `TicketHeader`：任务名 + `pill 执行中/已完成` + 进度条 + 三行计划（✓ 已完成 n 节 / ● 正在处理 §title / ○ 待确认 n）。
  - 批量栏照原型：`接受全部（n）` 主按钮（无待确认时 disabled）+ `撤销整批`；其下撤销提示行（版本快照文案）。
  - `DocAITaskArea` 组件整合：busy 时头部右侧停止钮。
- Tests: `frontend/tests/unit/docmgr/task-reducer.test.ts` 增 reject/恢复用例；`task-area.dom.test.tsx` 改造为 DiffCard 交互（展开/接受/拒绝/计数联动）。

## Chunk 2 — 面板空态 + 对话流（依赖 Chunk 1 的 getHeadings/getSectionText）

**Files:**

- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`：
  - **空态**：删旧欢迎文案组与预设 chips 行，改六宫格 `qgrid`（图标+名称+一行描述，点击选中→高亮 `box-shadow ring`）+ `launcher` 预览条（目标 pills：全部章节默认选中；各节 pill 来自 `getHeadings()` 前 8 个，多选互斥=全部 vs 任选节；`开始执行` → `startTask(op, sections)`）。图标用内联 SVG（润色笔/校对勾/术语 A|文/格式行/目录列/摘要页）。
  - **消息流**：用户消息右对齐 `bg-primary/10` 圆角气泡（右下小角）；AI 回复加 orb+「AI 助手」meta 行；回复底部操作条：复制（clipboard+2s「已复制」反馈）、重试（重发最后一条用户消息，仅最后一条回复显示）。流式发送中发送钮变停止方块（`useStream().stop`）。
  - 输入区照原型：`inrow`（focus ring primary/20）、Ask/模式下拉保留、占位文案「输入指令，@ 引用章节…」砍 @ 部分只留「输入指令…」。
  - 三态互斥：任务进行中宫格与输入禁用（既有 busy 锁），任务区卡片显示在消息流之上（既有挂载位不动）。
- Tests: 面板层如有既有 dom 测试则同步；无则不强加。

## 验收门（每 Chunk + 收尾）

- `cd frontend && pnpm test tests/unit/docmgr/` 全绿；`pnpm typecheck` 9→9；改动文件 eslint/prettier 清零
- 收尾：`docker compose -p eai-docker restart frontend` 后浏览器走查（空态宫格→选节执行→diff 卡接受→对话流停止/复制/重试→明暗两主题）
- 提交按域拆分，绝不 `git add -A`

## 挂账（不在本轮）

最近操作列表、@上下文 pills、思考折叠、建议 chips、👍👎 反馈、M2 findings 契约。
