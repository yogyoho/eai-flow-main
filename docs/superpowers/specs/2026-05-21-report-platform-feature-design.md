# AI智能工程报告写作平台 — 功能扩展设计

**日期**: 2026-05-21
**状态**: 已审核通过
**范围**: 在现有 DeerFlow 写作引擎 + 知识工厂基础上，新增四大功能模块

---

## 1. 背景与目标

### 1.1 现有系统能力

| 模块 | 状态 | 说明 |
|------|------|------|
| DeerFlow 写作引擎 | ✅ 已有 | AI对话式写作，流式输出 |
| 样例报告管理 | ✅ 已有 | 上传、分类、检索 |
| 模板抽取/编辑/发布 | ✅ 已有 | 从样例提取模板，可视化编辑 |
| 法规标准库 | ✅ 已有 | 法律/法规/标准管理，RAGFlow集成 |
| 合规规则管理 | ✅ 已有 | 规则引擎、合规检查、规则测试 |
| 模板质量评估 | ✅ 已有 | 针对模板的质量评分 |
| 模板版本管理 | ✅ 已有 | 模板版本对比、回滚 |
| 业务词典 | ✅ 已有 | 行业术语管理 |
| 网页爬虫 | ✅ 已有 | 法规采集 |
| 文档管理(docmgr) | ✅ 已有 | Tiptap编辑器、文件管理 |
| 用户/角色/部门 | ✅ 已有 | RBAC权限管理 |

**重要区分**：版本管理和质量评估是**模板级**功能，不适用于报告编写流程。报告层需要独立的版本和质量机制。

### 1.2 目标用户

- **单人模式**：工程师独立完成小型报告
- **团队协作**：多人分工编写大型报告，有审核、签发流程

### 1.3 报告类型覆盖

- 地质勘查类（煤炭、金属矿产等）
- 评价类（环评、安评、能评等）
- 设计/可研类（工程设计方案、可行性研究）
- 全行业扩展

### 1.4 设计原则

1. **流程驱动**：以「立项→采集→编写→审核→签发→归档」为主线
2. **严格分层**：模板层（知识工厂）与报告层（新增）职责分离
3. **可扩展**：插件框架支持外部数据源和专业软件集成
4. **标准化输出**：符合国标排版的 Word/PDF 输出

---

## 2. 模块一：报告项目管理

### 2.1 核心数据模型

```
ReportProject
  ├── id: UUID
  ├── name: string                  # 项目名称
  ├── report_type: enum             # 报告类型（环评/地质勘查/可研...）
  ├── client: string                # 委托方
  ├── target_standard: string       # 目标标准
  ├── status: enum                  # 项目状态（planning/writing/review/finalizing/archived）
  ├── template_id: FK               # 关联的报告模板
  ├── compliance_rule_set_id: FK    # 关联的合规规则集
  ├── law_ids: FK[]                 # 关联的法规
  ├── members: ProjectMember[]      # 项目成员
  ├── outline: ReportOutline        # 报告大纲（章节树）
  ├── milestones: Milestone[]       # 里程碑
  ├── created_at / updated_at
  └── created_by: FK(user)

ProjectMember
  ├── user_id: FK
  ├── project_id: FK
  ├── role: enum                    # manager/writer/reviewer/approver/issuer
  └── chapter_assignments: FK[]     # 负责的章节

ReportOutline (章节树)
  ├── id: UUID
  ├── project_id: FK
  ├── parent_id: FK(self)           # 支持多级嵌套
  ├── title: string
  ├── order: int
  ├── status: enum                  # not_started/writing/pending_review/approved/signed
  ├── assignee_id: FK(user)
  ├── word_count_target: int
  └── description: string

Milestone
  ├── id: UUID
  ├── project_id: FK
  ├── name: string                  # 开题/初稿/内审/送审/定稿
  ├── due_date: date
  ├── completed_at: date
  └── status: enum
```

### 2.2 功能清单

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 项目立项向导 | 选择报告类型→匹配模板→生成大纲→指定成员→创建 | P0 |
| 章节任务看板 | 看板视图展示所有章节状态，支持拖拽流转 | P0 |
| 进度仪表盘 | 完成率、审核通过率、逾期预警 | P1 |
| 成员工作台 | 每个成员看到自己负责的章节和待办 | P0 |
| 项目模板库 | 将成功的项目配置保存为可复用模板 | P2 |

### 2.3 与现有模块的交互

- **知识工厂**：项目立项时从模板库选择模板，自动生成报告大纲
- **合规规则**：项目绑定合规规则集，编写过程中实时检查
- **法规库**：项目关联适用法规，AI写作时自动参考
- **DeerFlow**：每个章节的编写任务触发一个 DeerFlow 写作会话

---

## 3. 模块二：报告协作与审批流

### 3.1 核心数据模型

```
CollaborationLock
  ├── chapter_id: FK
  ├── locked_by: FK(user)
  ├── locked_at: timestamp
  └── expires_at: timestamp         # 自动释放时间

Annotation
  ├── id: UUID
  ├── chapter_id: FK
  ├── author_id: FK(user)
  ├── position: JSON                # 文档内位置（offset/path）
  ├── content: string
  ├── parent_id: FK(self)           # 支持讨论串
  ├── status: enum                  # open/resolved
  └── created_at

Revision
  ├── id: UUID
  ├── chapter_id: FK
  ├── author_id: FK(user)
  ├── content_diff: JSON            # OT操作记录
  ├── created_at
  └── accepted: boolean

ApprovalWorkflow (审批流配置)
  ├── id: UUID
  ├── name: string
  ├── report_type: enum             # 按报告类型配置不同流程
  ├── steps: ApprovalStep[]
  └── is_default: boolean

ApprovalStep
  ├── id: UUID
  ├── workflow_id: FK
  ├── order: int
  ├── name: string                  # 内审/技术复核/签发
  ├── required_role: enum           # reviewer/approver/issuer
  ├── can_reject: boolean
  └── parallel: boolean             # 是否并行审批

ApprovalRecord (审批记录)
  ├── id: UUID
  ├── project_id: FK
  ├── step_id: FK
  ├── chapter_id: FK                # null=整报告审批
  ├── reviewer_id: FK(user)
  ├── action: enum                  # approve/reject/comment
  ├── comment: string
  └── acted_at: timestamp
```

### 3.2 功能清单

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 章节协作编辑 | 基于 Tiptap 的实时协作，章节粒度锁定/解锁 | P0 |
| 审批工作流引擎 | 可配置的多级审批，支持串行/并行 | P0 |
| 批注与讨论 | 在文档上添加批注，支持讨论串 | P1 |
| 修订追踪 | 显示修改痕迹，可按修订接受/拒绝 | P1 |
| 电子签章 | 对接第三方电子签章服务 | P2 |
| 报告版本快照 | 每次审批产生版本快照，支持 diff 对比 | P1 |
| 实时通知 | @提及、任务分配、状态变更通知 | P1 |

### 3.3 审批流程示例

```
编写完成 → 提交内审 → 内审员逐章/整报告审核 → 审核意见/通过/退回修改
  → 内审通过 → 技术负责人复核 → 复核通过 → 签发人签发
  → 签发完成 → 生成正式版 PDF（水印+电子签章）
```

---

## 4. 模块三：插件/开放平台

### 4.1 核心数据模型

```
Plugin
  ├── id: UUID
  ├── name: string
  ├── type: enum                    # data_connector/tool/output/custom
  ├── version: string
  ├── author: string
  ├── description: string
  ├── config_schema: JSON           # JSON Schema，动态生成配置表单
  ├── entry_point: string           # 插件入口（Python模块路径或API地址）
  ├── permissions: string[]         # 需要的权限
  ├── status: enum                  # registered/installed/enabled/disabled
  └── created_at

PluginInstance (已安装的插件实例)
  ├── id: UUID
  ├── plugin_id: FK
  ├── project_id: FK                # null=全局可用
  ├── config: JSON                  # 根据config_schema验证
  ├── status: enum                  # active/error/disabled
  └── last_sync_at: timestamp

ApiKey
  ├── id: UUID
  ├── name: string
  ├── key_hash: string              # 只存hash
  ├── scope: string[]               # 权限范围
  ├── project_id: FK                # null=全局
  ├── created_by: FK(user)
  ├── expires_at: timestamp
  └── last_used_at

WebhookSubscription
  ├── id: UUID
  ├── url: string
  ├── events: string[]              # project.status_changed/approval.completed/etc
  ├── secret: string                # HMAC签名密钥
  ├── retry_policy: JSON
  └── created_by: FK(user)
```

### 4.2 功能清单

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 插件注册中心 | 插件元数据管理，上传/发现/安装 | P1 |
| 插件配置面板 | 根据 JSON Schema 动态生成配置表单 | P1 |
| 数据连接器管理 | 连接状态监控、同步日志、定时拉取 | P0 |
| API Key 管理 | 创建、轮换、吊销、权限范围设置 | P1 |
| Webhook 管理 | 订阅事件、配置回调、重试策略 | P2 |
| 插件沙箱运行 | 隔离执行，不污染核心系统 | P1 |

### 4.3 预置插件（首批）

| 插件 | 类型 | 说明 |
|------|------|------|
| 地质数据连接器 | data_connector | 对接地质钻孔数据库，拉取地层信息 |
| 环境监测连接器 | data_connector | 对接在线监测平台，获取实时数据 |
| CAD 文件预览 | tool | 解析 DWG/DXF，生成预览图和元数据 |
| GIS 数据可视化 | tool | 加载 Shapefile/GeoJSON，在报告中嵌入地图 |

---

## 5. 模块四：数据集成 + 专业工具 + 报告输出

### 5.1 外部数据集成层

#### 数据模型

```
DataSource
  ├── id: UUID
  ├── name: string
  ├── type: enum                    # database/api/file/gis
  ├── connection_config: JSON       # 加密存储的连接信息
  ├── auth_type: enum               # none/basic/oauth/api_key/certificate
  ├── sync_mode: enum               # manual/scheduled/event
  ├── sync_config: JSON             # 定时配置或事件规则
  ├── status: enum                  # connected/error/disconnected
  ├── last_sync_at: timestamp
  └── created_by: FK(user)

DataReference (报告中的数据引用块)
  ├── id: UUID
  ├── chapter_id: FK
  ├── source_id: FK
  ├── query: JSON                   # 数据查询参数
  ├── display_config: JSON          # 展示配置（表格/图表/文本）
  ├── cached_data: JSON             # 缓存的查询结果
  ├── refreshed_at: timestamp
  └── position: JSON                # 在文档中的位置
```

#### 行业数据适配器

| 适配器 | 数据类型 | 说明 |
|--------|----------|------|
| 地质数据适配器 | 钻孔数据、地层信息、矿物分析 | 标准化钻孔柱状图数据 |
| 环境数据适配器 | 大气/水/噪声监测、排放指标 | 时间序列数据，自动统计 |
| 工程数据适配器 | 设计参数、施工记录、检测报告 | 结构化表格数据 |

### 5.2 专业软件集成

#### AutoCAD 集成

- DWG/DXF 文件上传和预览（服务端解析）
- 图纸元数据提取（标题、比例、图层列表）
- 在报告中引用图纸：插入缩略图 + 链接到原始文件
- 图纸版本管理：同一图纸的多版本关联

#### GIS 集成

- 支持 Shapefile、GeoJSON、KML 格式
- 在线地图底图叠加（OpenStreetMap/天地图）
- 空间数据可视化：矿区范围、监测点位、等值线
- 生成报告附图：地图截图自动插入报告

#### 专业制图

- 数据驱动的图表生成：柱状图、折线图、饼图、散点图
- 地质剖面图生成（基于钻孔数据）
- 等值线图/等高线图生成（基于空间数据）

### 5.3 报告排版与输出引擎

#### 排版规则

```
LayoutTemplate (排版模板)
  ├── id: UUID
  ├── name: string                  # 如 "GB/T 7713 环评报告"
  ├── report_type: enum
  ├── page_settings: JSON           # 纸张大小、方向、边距
  ├── cover_template: JSON          # 封面布局规则
  ├── toc_settings: JSON            # 目录生成规则
  ├── body_styles: JSON             # 正文字体、字号、行距、段距
  ├── heading_styles: JSON[]        # 各级标题样式
  ├── table_styles: JSON            # 表格样式
  ├── figure_styles: JSON           # 图片样式（编号、标题位置）
  ├── header_footer: JSON           # 页眉页脚模板
  ├── reference_style: enum         # 参考文献格式（GB/T 7714）
  └── appendix_rules: JSON          # 附录编排规则
```

#### 输出能力

| 格式 | 说明 | 优先级 |
|------|------|--------|
| Word (.docx) | 完整排版输出，可直接编辑修改 | P0 |
| PDF | 正式版，支持水印、电子签章 | P0 |
| 在线预览 | 网页内嵌入报告阅读器 | P1 |

#### 签章与水印

- 电子签章：对接第三方 CA/签章平台（如 e签宝、法大大）
- 水印：根据报告阶段自动添加（初稿/送审稿/正式稿）
- 页眉页脚：公司 LOGO、报告编号、密级标识
- 附件打包：自动汇总附件清单，打包下载（正文+附图+附表+附件）

---

## 6. 模块间关系总览

```
                        ┌─────────────────┐
                        │   报告项目管理   │
                        │  (立项/分工/进度) │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────▼──────┐  ┌───────▼───────┐  ┌───────▼───────┐
    │  协作与审批流   │  │  DeerFlow     │  │  合规规则     │
    │ (编辑/审核/签发)│  │  写作引擎     │  │  实时检查     │
    └─────────┬──────┘  └───────┬───────┘  └───────────────┘
              │                  │
    ┌─────────▼──────────────────▼───────────────────────┐
    │              数据集成 + 专业工具                     │
    │  (地质数据 | 环境数据 | CAD | GIS | 制图)          │
    └──────────────────────┬─────────────────────────────┘
                           │
                ┌──────────▼──────────┐
                │   报告排版输出引擎   │
                │ (Word | PDF | 签章) │
                └─────────────────────┘

    ┌─────────────────────────────────────────────────────┐
    │              插件/开放平台（贯穿所有模块）            │
    │  (插件框架 | API网关 | Webhook | 数据连接器)        │
    └─────────────────────────────────────────────────────┘

    ─ ─ ─ ─ 已有模块（只读，不修改）─ ─ ─ ─ ─ ─ ─ ─ ─ ─
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ 知识工厂     │  │ 法规库       │  │ 文档管理     │
    │ (模板级)     │  │              │  │ (docmgr)     │
    └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 7. 技术要点

### 7.1 前端新增页面

| 路由 | 说明 |
|------|------|
| `/projects` | 项目列表 |
| `/projects/[id]` | 项目详情（看板+大纲） |
| `/projects/[id]/chapter/[chapterId]` | 章节协作编辑 |
| `/plugins` | 插件市场和管理 |
| `/plugins/[id]/config` | 插件配置 |
| `/data-sources` | 数据源管理 |
| `/output` | 输出模板管理 |

### 7.2 后端新增扩展模块

| 模块路径 | 说明 |
|----------|------|
| `app/extensions/project/` | 报告项目管理 |
| `app/extensions/approval/` | 审批工作流 |
| `app/extensions/plugin/` | 插件框架 |
| `app/extensions/data_source/` | 数据源管理 |
| `app/extensions/output_engine/` | 排版输出引擎 |

### 7.3 第三方依赖预估

| 用途 | 候选库/服务 |
|------|-------------|
| Word生成 | python-docx |
| PDF生成 | reportlab / weasyprint |
| CAD解析 | ezdxf |
| GIS处理 | geopandas, fiona |
| 图表生成 | plotly, matplotlib |
| 实时协作 | Tiptap Collaboration / Yjs |
| 电子签章 | 第三方 SaaS（e签宝/法大大） |

---

## 8. 优先级与实施建议

### P0 — 核心流程（MVP，2个月）

1. 报告项目管理（立项、大纲、成员分配）
2. 章节任务看板（状态流转）
3. 章节协作编辑（基于现有 Tiptap）
4. 审批工作流引擎（串行审批）
5. Word 输出（基础排版）

### P1 — 增强能力（+2个月）

1. 进度仪表盘和通知系统
2. 批注与修订追踪
3. 审批版本快照和 diff
4. 数据连接器框架 + 地质数据适配器
5. PDF 输出 + 水印
6. 插件注册与配置

### P2 — 完整平台（+2个月）

1. 并行审批、加急通道
2. 电子签章集成
3. CAD/GIS 预览集成
4. API Key 和 Webhook 管理
5. 项目模板库
6. 高级排版模板编辑器
