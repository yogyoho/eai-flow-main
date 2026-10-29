# 文档空间 · 右侧 AI 助手全文操作能力设计（M1–M3）

- **日期**: 2026-10-29
- **状态**: 设计已评审（用户确认），待实现
- **前序**: `2026-07-26-docmgr-ai-panel-redesign.md`（三模式 / 操作卡片 / 锚点 5 级匹配已落地）
- **核查**: 7 项承重假设经 8-agent 对抗性代码核查（结论已并入下文，file:line 均已验证）

## 1. 背景与现状

右侧 AI 助手（`DocAIAgentPanel.tsx`）挂载于个人文档 BlockNote 编辑器（`DocumentManagement.tsx:2841-2903`），现状能力：

| 能力 | 现状 | 位置 |
|---|---|---|
| 三模式 | Ask 逐条确认 / Auto 批量应用+批量撤销 / Plan 只分析 | `DocAIAgentPanel.tsx:61` |
| 操作原语 | replace / insert_after / delete / prepend / append | `PersonalBlockNoteEditor.tsx:94` |
| 锚点定位 | 5 级：exact→prefix→唯一 contains→Levenshtein<30%→null | `PersonalBlockNoteEditor.tsx:188` |
| 安全网 | 提交前 PUT 同步 + `createPersonalVersion("AI 编辑前快照")` + 版本历史恢复 | `DocAIAgentPanel.tsx:622-644` |
| 链路 | 全文+全锚点内嵌 prompt → `lead_agent`（useStream）→ `---OPERATIONS---` 解析 | `DocAIAgentPanel.tsx:71` |

对照「全文操作」定位的缺口：全文变换无直达路径（模型需逐块产 replace，长文不可行）；每轮全文+全锚点进 prompt（token 爆炸）；审查产出是散文非结构化清单；无 diff 对照；autoApply 按模式不按操作类型；Plan 产出无法转执行；选区能力闲置。

**分工不变**：BlockNote 内置 xl-ai 管选区局部操作；右侧面板管全文/多块。本设计只覆盖**个人文档**；项目协作文档（CollabEditor + Hocuspocus）不做。

## 2. 架构

```
   自由对话（不动）      lead_agent (useStream)           ← Ask/Auto/Plan 原样
   确定性任务（新增）    docmgr 扩展端点（ai_transform / ai_review）
 ┌──────────┐  NDJSON   · 模型装配走 create_chat_model（同 ai-edit 先例）
 │ 面板任务区 │ ←──────  · 分节引擎：markdown→节→逐节调模型
 │ 预设/审查/重写│        · 产出 = DocOperation[]（新增 replace_section）
 └──────────┘            · 服务端零读盘：content 请求体直传
        ↓
   结果回灌现有 applyOperations / 锚点匹配 / 快照撤销
```

**核心原则**：新能力只加「怎么生成 ops」，不加「怎么应用 ops」。产出永远是 `DocOperation[]`（本设计新增一个 `replace_section` 原语）。

## 3. 代码核查修订记录

| # | 核查发现 | 设计响应 |
|---|---|---|
| 1 | `replace` 只删 anchor 单块（`PersonalBlockNoteEditor.tsx:669`），整节回灌会节体重复 | `replace_section` 提前到 M1（原属 M3） |
| 2 | op.content 解析绕过数学/details 管线（:652 裸调 tryParse），`$$..$$` 独立公式回灌即变裸文本 | applyOperations 改走 `transformMathInBlocks(buildBlocksWithDetails(...))`（seed 同款管线，:472-481） |
| 3 | 切分按段再切会腰斩跨行 `$$..$$`、代码围栏、表格 | 原子段规则：代码围栏 / `$$..$$` 区间 / GFM 表格 / `<details>` 不可切 |
| 4 | 锚点 exact/prefix 级首中即返回无歧义检查（:197-213），重复标题静默错配 | exact/prefix 改扫全量、>1 命中返回 null（共享函数加固，静默错配→安全失败） |
| 5 | PUT 不检查 `res.ok`（:622-633），同步失败静默继续 | 任务通道补 res.ok 检查，失败中止提交 |
| 6 | 整卷回滚会吞掉用户手改（restoreBlocks 全文档替换 :707-712） | 撤销前脏检查：快照后文档变过→禁用整卷回滚，指路版本历史 |
| 7 | auto 模式 ops 每次渲染内联重解析（:872,:886-890）→ 重渲染重复应用+覆写快照点（既有 bug） | `parseAIMessage` 结果按 message.id useMemo 缓存；auto 批应用逐 op 捕获继续（弃首错即断） |
| 8 | 服务端读盘存在越权外带风险（_locate_thread_outputs 扫全部 user 桶）+ 读回竞态 | **content 请求体直传**，服务端零读盘——越权通道与竞态整类消失 |
| 9 | collab_ai_chat 裸 httpx 装配：无 model_name override、无 max_tokens（provider 默认 4096 静默截断）、错误静默吞（:275-280,:343-346） | 模型装配改走 **`create_chat_model`**（ai-edit 先例 `routers.py:636/705`）：支持模型下拉、max_tokens 显式下发、显式 `{error}` 事件（`routers.py:648-655` 先例） |
| 10 | 前端已有流读取骨架 `aiEditStream`（`extensions/api/index.ts:762-833`：withCsrf+getReader+行缓冲+AbortSignal） | NDJSON reader 克隆该骨架去 `data:` 前缀（~20 行） |

## 4. M1 详设：端点 + 分节引擎 + 预设操作库

### 4.1 后端 `backend/app/extensions/docmgr/ai_transform.py`（新增）

- **路由**: `POST /api/extensions/docmgr/ai/transform`，router 注册进 `gateway/app.py` docmgr 挂载块（:1589-1618 先例）。鉴权随 gateway fail-closed middleware 自动覆盖，前端 `withCsrf`。
- **请求**: `{thread_id, rel_path, operation, model_name?, content, sections?}`
  - `content` = 面板当前 `getMarkdown()` 清洗后全文（请求体直传，同 ai-edit 先例 `routers.py:632,700`）；服务端**零读盘**——无越权读通道、无 PUT-read 竞态
  - `sections` = 可选节序号数组，部分重跑（切分是确定性纯函数，同 content 必得同节边界）
- **响应**: NDJSON 事件流
  - `{type:"section_start", index, total, title, skipped?}` — skipped:true = 结构节（含公式/表格/图片/details），不送模型
  - `{type:"ops", index, ops:[DocOperation...]}` — 每节一批
  - `{type:"section_error", index, message}` — 节级失败，**后续节继续**
  - `{type:"done", total, failed:[index], skipped:[index]}`
- **模型装配**: `create_chat_model(name=model_name)`（缺省走 Settings 默认模型，同 `routers.py:599` 语义）；`max_tokens` 显式下发（取 model config，缺省 8192——防 provider 默认 4096 截断节输出）；上游超时/异常 → 显式 `section_error`（ai-edit `:648-655` 模板），**不照抄 collab_ai_chat 的静默吞**。

### 4.2 分节引擎（纯函数，独立单测）

- 按 ATX 标题（`#`–`######`）切节，节 = 标题 + 至下一同级或更高级标题前全部内容；无标题文档 = 全文单节；空文档 = 0 节（`done` 事件 `total:0`）
- 单节 >4000 字按空行段再切；**原子段不可切**：代码围栏、`$$..$$` 区间、GFM 表格、`<details>` 块；单段仍超长在句号边界硬切
- **结构节跳过**：节内含 equation/表格/图片/details 块 → skipped（v1 不做块级穿引，见 §8）

### 4.3 预设操作目录（v1 六个）

| 操作 | 机制 | 产出 |
|---|---|---|
| 全文润色 | 逐节改写；术语/数字/公式/单位硬约束 | 逐节 `replace_section` ops |
| 全文校对 | 错别字/标点/单位符号，只产差异 | 同上 |
| 术语统一 | 两遍：①全文扫变体建术语表 ②携表逐节 replace_section | 同上 |
| 格式规范 | 标题层级/编号/中英文空格 | 同上（UI 提示可切 Auto 批量） |
| 生成目录 | 全文扫标题 | 单个 prepend op（文首目录节）；无标题文档返回空提示 |
| 全文摘要 | 全文一次性总结 | 仅展示 + 「插入文末」按钮（append op） |

### 4.4 前端

- **`replace_section`**（`PersonalBlockNoteEditor.tsx`）: `DocOperation` union 扩展；定位节标题块（5 级匹配）→ 向下扫至下一 `props.level <= anchor 标题级` 的标题前 → `replaceBlocks(sectionIds, parsed)`（复用 :638-642 level 读取与 :707-712 多 id 替换，均已验证存在，~20 行）
- **applyOperations 管线修复**: :652 改经 `transformMathInBlocks(buildBlocksWithDetails(...))`
- **锚点加固**: `findBlockByAnchor` exact/prefix 级改扫全量、>1 命中返回 null（共享函数，自由对话路径同受益：静默错配→卡片安全失败；补回归测试）
- **任务区**（**不进 thread 消息流**、不伪造 assistant 消息、不污染 lead_agent 线程历史）: 面板内独立状态。每节一张 SectionCard（节标题 + 新内容预览 + 应用/跳过；skipped 节明示「含公式表格已跳过」；failed 节 [重试本节]）+ 顶层 [全部应用][全部放弃]（流毕可用）。M3 升级为 diff 对照。
- **任务通道流程**: `getMarkdown` → PUT 同步（**补 res.ok 检查**）→ `createPersonalVersion("AI 全文操作前快照")` → `aiTransformStream`（content 直传）→ 逐节卡片。
- **取消**: AbortSignal 接线（`aiEditStream` 骨架已支持 signal）；取消时**未确认 ops 丢弃**（不产生部分应用），已应用部分保持、提示可整批回滚。
- **撤销**: 任务批撤销 = 任务前快照 `restoreBlocks` + **脏检查**（快照后文档指纹变过 → 禁用整卷，指路版本历史）。
- **互斥**: 面板级 busy 锁（transform 进行中禁任务与自由对话提交）；跨 tab 不设防（挂账，同现有写端点水位）。
- **既有 bug 修复**: auto 模式 `parseAIMessage` 按 message.id useMemo 缓存；auto 批应用逐 op 捕获继续 + 失败清单（弃首错即断+单横幅）。
- **NDJSON reader**: `extensions/api/index.ts` 新增 `aiTransformStream`，克隆 `aiEditStream` 骨架（:762-833）去 `data:` 前缀分支。

## 5. M2 详设：审查 → findings → 修复

- **端点**: `POST /api/extensions/docmgr/ai/review`，同装配同 NDJSON：`{section_start}` → `{finding}`（逐条流出，边审边看）→ `{done, summary:{counts by severity}}`
- **请求**: `{thread_id, rel_path, review_type, instruction?, model_name?, content}`；review_type v1 = `consistency`（术语一致性，**两遍法**：第一遍全文建术语表/变体清单，第二遍逐节审查携全局表——跨节不一致不漏）/ `numbering`（编号连续性，同样先全文扫编号清单）/ `units`（公式单位规范）/ `custom`（instruction 透传）
- **findings 契约**（仓库根 `contracts/docmgr_findings.v1.json`，沿 `contracts/knowledge_sources.v1.json` 先例）:
  `{id, severity: error|warn|info, anchor, excerpt, problem, suggestion, fix_op?}`
  - `fix_op` = DocOperation（replace / replace_section）——修复 = 现有 applyOperations 原样复用，零新应用机制
  - 锚点失败 = 安全报错卡片（v1 不做 fix_op 失效预检测，挂账 §8）
- **FindingsCard**: 按严重度分组，每条 [定位][修复][忽略]；顶部 [全部修复] = 顺序 apply + 开始前快照 + 脏检查；忽略仅当前会话生效（finding id 跨会话不稳定，明确不做记忆）

## 6. M3 详设：全文重写 + diff + 翻译

- **diff**: 行级 LCS 自写（~40 行 TS，**不加依赖**——加包需重建前端镜像）；SectionCard 升级为旧文（删行红）/新文（增行绿）上下对照，max-height 滚动；diff 基准 = 任务开始时该节原文 vs 模型新文（content 直传中自带）
- **翻译** = 重写预设（prompt = 目标语言 + 术语表机制复用 M1 术语统一）；「翻译为英文」进操作库
- **渐进确认**: NDJSON 逐节到 → 逐节出 diff 卡 → 边生成边审，不等全文
- **失败节重试**: `sections:[i]` 复用 M1 部分重跑

## 7. 关键决策记录

| 决策 | 理由 | 弃选方案 |
|---|---|---|
| 模型装配走 `create_chat_model` | 天然支持 model_name override（UI 有模型下拉）、LangChain 生态、max_tokens 透传、显式错误先例 | 克隆 collab_ai_chat 裸 httpx（无 override/无 max_tokens/错误静默） |
| content 请求体直传 | 服务端零读盘：越权外带通道、PUT-read 竞态、CRLF 归一三类问题整类消失；同 ai-edit 先例 | 盘上读回+一致性令牌（需 mtime/version_id 加固）；version_id 读回（多一次依赖） |
| `replace_section` 提前 M1 | plain replace 单块删除会倍增节体，逐节改写不成立；实现仅 ~20 行全用现有内部函数 | 服务端逐块拆 ops（锚点匹配次数×N，失败面扩大） |
| 产出不进 thread 消息流 | 独立任务区不污染 lead_agent 线程历史；避免伪造 assistant 消息 | 伪造消息进 MessageList |
| 逐节卡片、取消=丢弃未确认 | 取消永不产生部分应用；快照兜底已应用部分 | 流中实时应用（取消=部分应用，需逐节快照） |
| 前端面板级互斥 | 零后端新增；跨 tab 风险同现有写端点水位（挂账） | 服务端 per-doc 单飞注册表 / mtime 乐观锁（基础设施为零，纯新增） |
| 一致性审查两遍法 | 全文单次投喂长文档不可行；逐节独立审漏跨节不一致 | 全文投喂 / 逐节+状态传递 |
| 锚点加固改共享函数 | 静默错配→安全失败对自由对话同受益 | transform 专用匹配入口（分裂匹配语义） |

## 8. 明确不做（YAGNI）

项目协作文档面板 / 结构节块级穿引（v1 整节跳过）/ findings 跨会话记忆 / 字符级 diff / 操作库配置化（v1 硬编码 6 个）/ fix_op 失效预检测 / 服务端单飞与乐观锁 / Plan 产出一键转执行（后议）

## 9. 测试与验收

**后端**（`make test`）: 分节引擎单测（标题层级 / 超长再切 / 原子段不切 / 空文档 0 节 / 无标题单节 / sections 部分重跑幂等）；6 预设 fake-model 单测（固定响应 → ops 断言）；NDJSON 事件序列 TestClient（含 section_error 后续节继续）；review findings schema 校验。
**前端**（rstest，tests/unit 镜像 src）: `replace_section` dom 测试（同级/跨级标题边界）；applyOperations 数学管线回归（`$$..$$` 内容产出 transform 后 blocks）；锚点歧义加固回归（重复标题→null）；SectionCard/任务区 dom（应用/跳过/重试/全部应用/取消）；auto ops 身份稳定回归（重渲染不重复应用）；`aiTransformStream` NDJSON 解析单测。
**契约**: `docmgr_findings.v1.json`。
**验收场景**: 2 万字级含公式+表格的计算书跑「全文校对」全链——进度逐节、结构节明示跳过、逐节确认、整批撤销（含脏检查）、失败节重试、取消中途无部分应用。

## 10. 涉及文件

| 层 | 文件 | 变更 |
|---|---|---|
| 后端 | `backend/app/extensions/docmgr/ai_transform.py` | 新增（transform + review 端点、分节引擎、预设 prompt 模板） |
| 后端 | `backend/app/gateway/app.py` | docmgr 挂载块注册（~:1589-1618） |
| 前端 | `PersonalBlockNoteEditor.tsx` | replace_section、applyOperations 管线、findBlockByAnchor 加固 |
| 前端 | `DocAIAgentPanel.tsx` | 预设 chips、任务区/SectionCard、auto bug 修复、busy 锁 |
| 前端 | `extensions/api/index.ts` | aiTransformStream（NDJSON） |
| 契约 | `contracts/docmgr_findings.v1.json`（仓库根） | 新增 |
| 测试 | 后端 `tests/`、前端 `tests/unit/` 镜像位 | 如上 §9 |

## 11. 开工前置（T0）

1. **规模盘点**（只读脚本）: 扫 `outputs/` 个人文档节数/节长分布，校准 4000 字切分阈值与单任务节上限
2. **round-trip 对应性单测**: 取 3-5 份真实保存的个人文档 markdown，验证 split→tryParseMarkdownToBlocks 块序列与原文档节内块一一对应（列表/引用/嵌套 children 节归属）
3. **核实** `deerflow.models.create_chat_model` 对 `ModelConfig.max_tokens` 的透传行为（`factory.py`）
