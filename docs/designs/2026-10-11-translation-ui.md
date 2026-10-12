# Design: 翻译工作台 UI（应用中心入口 + 子页面）

Generated 2026-10-11 · 分支 main-dev-fork
Status: DRAFT（待用户确认后实施）
上游设计: docs/designs/2026-10-11-jv-mining-translation-kb.md（APPROVED，T1-T9 已销账）
范式参照: contract-price（子路由+layout+组件目录）、knowledge-factory（9 tabs）、应用中心 app_definitions 注册
风格基准: docs/designs/ui-style-spec.md（三层 token/字号四角色/shadcn 组件 only/cn()）

## 范围裁定

- **本期建**：应用中心入口 + 总览 + 任务管理 + 复核工作台 + 术语库 + 设置（KB 开关）
- **二期不建**（既有裁定，触发器见 TODOS）：批量导入向导、MTPE 内联编辑器（v1 复核=裁决+批注）、TM 记忆库、报告能力入口
- 权限：页内按 `translation:read`（可见）/`translation:transition`（裁决按钮）过滤；应用中心条目对无 translation:read 者隐藏

## 1. 应用中心入口

`app_definitions` 插一行（管理 API 或 seed）：

| 字段 | 值 |
|---|---|
| app_id | `translation` |
| name | 文档翻译工作台 |
| description | EN/FR 文档翻译入库：任务管理、机检复核、术语库 |
| icon_name | `languages` |
| business_domain | 知识文档域（既有 domain key，实施时对齐） |
| path | `/translation` |
| admin_only | false（权限点过滤） |

## 2. 主页面结构（/translation）

`frontend/src/app/translation/layout.tsx`：**顶栏页签承载子页面切换**（2026-10-11 裁定，不用左侧子导航）——页头 `h-12 bg-background/80 backdrop-blur`：左侧应用名「文档翻译工作台」+ 页签排（**资产库** / 任务管理 / 复核工作台〔待复核数徽章〕/ 术语库 / 设置），右侧环境 chip（语言对统计 / 当前模型 / 用户）。子路由照 contract-price 目录模式：

```
/translation              文档资产库（page.tsx = 首页，双语资产库双栏视图）
/translation/tasks        任务管理
/translation/review       复核工作台
/translation/glossary     术语库
/translation/settings     设置
```

组件目录：`frontend/src/extensions/translation/{api.ts, types.ts, hooks.ts, components/}`（Route B，零上游改动）。

## 3. 子页面设计

### 3.1 资产库（原「总览」，/translation 首页）

**定位重定义**：总览 = 双语资产库（Windows 资源管理器双栏结构）。左栏原文库（用户自建文件夹树 + 多文件/整文件夹上传 + 勾选批量翻译），右栏译文库（左树只读镜像投影，译本由管线产出，无独立上传）。指标卡/状态分布移至任务管理页头部压缩条；检索质量展示归设置页。

**左列表列**：`勾选 | 文件名 | 状态 | 类型 | 大小 | 修改时间 | 操作▾`（操作下拉：翻译/删除/下载/预览——预览按类型分档：PDF 内嵌，office 下载）
**右列表列**：`文件名 | 状态 | 类型 | 大小 | 创建时间 | 操作▾`（操作下拉：下载/预览）
状态列保留理由：批量翻译的动作依据（仅未翻译/已失败可译）；右侧在途行显示「翻译中 N% / 待复核 →」灰色占位。

**交互**：两侧树独立导航（右树=只读镜像）；配对定位按需（行级「定位译本/定位原文」）；勾选列仅左列表（Shift 连选/本夹全选→批量翻译 ≤100 即时入队，更大走 scheduled_tasks）；拖拽移动；三档宽度态；删除=R3-3 归档语义+确认框；统计底栏=总数/已交付/翻译中/待复核→/EN/FR。

**文案红线**（全 UI 强制，工程语禁入）：

| 工程语（禁止出现在 UI） | 用户语（UI 一律用右侧） |
|---|---|
| hit@k / 评测夹具 / 检索链路闸 / 样例闸 | 检索准确率（前 5 条命中） / 验收测试 |
| 机检数值轴 / 数值轴 | 数字准确性（译文与原文逐字核对） |
| 术语轴 / force / forbid / keep | 指定译法（术语库要求） / 保留原文 |
| 结构轴 | 格式完整性（段落表格无遗漏） |
| 质量档 draft / reviewed | 标准版 / 人工校对版 |
| 双份索引 | 中文与原文都可被检索 |
| exceeded | 待复核 |
| EAI_TRANSLATION_MODEL | 翻译模型（只显示模型名） |

**交互补充**：左右区域间有可拖拽分隔条（拖动改宽度，25%-75% 夹取）；两侧文件列表均带横向滚动条（窄屏/列多时 overflow-x-auto，不挤压列）。
### 3.2 任务管理 `/translation/tasks`

```
┌──────────────────────────────────────────────────────────────┐
│ 筛选: [状态▾(多选)] [知识库▾] [语言▾] [质量档▾] [sha/文件名🔍] │
├──────────────────────────────────────────────────────────────┤
│ 文档名            │KB      │语言│状态        │进度│更新时间    │
│ annual-report.docx│铁矿知识│EN→ZH│● delivered│100%│10-11 18:02│
│ contract-fr.pdf   │铁矿知识│FR→ZH│⚠ exceeded │ 70%│10-11 17:40│
│ balance.xlsx      │财务知识│EN→ZH│● running  │ 45%│10-11 17:22│
│ …                          [行点击 → 右侧详情 Drawer]        │
└──────────────────────────────────────────────────────────────┘
```

状态徽章（语义 token，禁裸色）：pending=muted / running=info+pulse / check_failed·retrying=warning / exceeded=amber-600 深调 / indexed=info / delivered=success / failed=destructive / superseded·cancelled=muted+删除线。

**详情 Drawer**（右侧 480px）：
- 溯源区：来源文件、sha256 前 12、语言、内容语义 tag、质量档、任务版本
- 三轴机检卡：numeric/structure/terminology 各自 PASS✅/FAIL❌ + violation 明细（missing/extra 数字列表、force 术语缺失、block 漂移）
- 不确定段：LLM low_confidence_spans 列表（黄点标记）
- 交付物：`deliverable_uri` 下载按钮（local path 文本展示 + s3:// 时直链）
- RAGFlow：中文版文档 id + 原件 sha
- 操作（按权限/状态显隐）：failed → 重跑；pending/running → 取消；exceeded → 跳复核

### 3.3 复核工作台 `/translation/review`（核心页）

```
┌──────────────┬───────────────────────────────────────────────┐
│ exceeded 队列│ annual-report.docx · FR→ZH · exceeded         │
│ ┌──────────┐ ├─────────────────────────┬─────────────────────┤
│ │contract  │←│ 源文（FR）              │ 译文（ZH）           │
│ │ 17:40 ⚠ │ │ "Le concentré…1 234,56"│  "铁精矿…1,234.56"  │
│ │annual    │ │        [数字对齐标绿]   │  [违例数字标红]      │
│ │ 18:02 ⚠ │ ├─────────────────────────┴─────────────────────┤
│ │…         │ │ 机检明细: numeric❌(缺 500 / 多 32024)         │
│ └──────────┘ │            terminology❌(force 缺「铁精矿」)    │
│              │ 不确定段: "…tonnes…" 🟡                        │
│              ├───────────────────────────────────────────────┤
│              │ [✅ 通过并交付]  [✏ 批注]  [⛔ 驳回归档]        │
│              │ (translation:transition 权限)                  │
└──────────────┴───────────────────────────────────────────────┘
```

- 左列：exceeded 任务队列（时间序），键盘 J/K 切换（v1 可后置）
- 右侧对照：源 block / 译文 block 并排逐块渲染；数字 token 对齐高亮（绿色=一致，红色=数值轴违例项）；术语违例下划线 + 期望译法气泡；不确定段黄底
- 裁决：通过 → `POST /tasks/{id}/transition {target:"indexed"}`（review_approved→双份索引更新→delivered）；驳回 → `{"target":"archived"}` + 批注（notes 写入 error_detail）
- v1 不做内联编辑（MTPE 编辑器=二期 OQ8）；批注为纯文本追加

### 3.4 术语库 `/translation/glossary`

- 表格：源词 / 动作（force=指定译法 · forbid/keep=原样保留）/ 目标译法 / 备注 / 更新时间
- 新增/编辑 Drawer：动作三选联动字段（force→必填译法；forbid/keep→仅源词）
- 导入：粘贴 yaml（`terms:` 块，与 glossary.py 同 schema）原子替换——术语内容=样例闸产出（≥100 条），导入是搬运动作
- 顶部提示条：机制生效点 = worker 翻译注入 + 机检术语轴；空表=机制空转
- **后端配套（新，小）**：glossary CRUD 路由（GET/PUT 原子写 yaml，参照 roles_custom overlay 模式：临时文件+rename+409 冲突）

### 3.5 设置 `/translation/settings`

- KB 列表 + `translation_enabled` 开关（逐行，写 `PUT /api/extensions/knowledge-bases/{id}`）
- 只读展示：当前翻译模型（EAI_TRANSLATION_MODEL）、轮询/并发旋钮值、机检阈值（「样例闸产出」占位说明）
- **后端配套（微）**：`KnowledgeBaseUpdate` schema 补 `translation_enabled` 字段 + service 透传

## 4. 后端配套缺口（UI 依赖，均已探明）

| 缺口 | 规模 | 方案 |
|---|---|---|
| KB 开关进 update schema | 微 | `KnowledgeBaseUpdate` + service 透传一行 |
| glossary CRUD API | 小 | 新路由 GET/PUT 原子写 yaml（overlay 模式） |
| metrics 聚合 | 免 | 前端聚合 `GET /tasks`（v1） |

## 5. 实施顺序

1. 后端配套两缺口（schema 字段 + glossary CRUD）
2. 骨架：app/translation 路由 + layout + 子导航 + extensions/translation 前端模块（api/types/hooks）
3. 总览 + 任务管理（列表+Drawer）
4. 复核工作台（对照视图+裁决）
5. 术语库 + 设置
6. 应用中心入口 seed + canPage 权限过滤

估：human ~3-4 天 / CC ~1 天（Route B 纯拼装，后端缺口半日内）。

## Open Questions

1. 应用中心 business_domain 用既有哪个 key（实施时对齐 app_domains 表）
2. 复核对照视图的分块对齐粒度（v1 逐 block 上下并排；滚动联动二期）

## 已知边界（2026-10-12 实施记录）

- 资产库上传的原件**未入 RAGFlow 原文索引**（走 translation 独立存储，与 knowledge 上传链独立）——原文即刻检索（前提 3）对资产上传件暂缺，二期接 bridge 时补「原件入索引」步骤。
- 文件夹上传 v1 保留一层目录结构（相对路径首段建夹）；更深层级二期。
- 任务管理页头部压缩指标条未做（旧总览指标去向前），任务页本身未改（用户裁定暂不动）。
