# Word 样例自动提取排版 + 报告输出/文档空间导出对话框补齐 — 设计文档

> 日期: 2026-08-06
> 状态: 待实施
> 前置规格: `2026-06-09-docmgr-word-export-layout-design.md`（其中 `import-layout` 端点仅写前端、后端未实现）

## 概述

报告输出模块（`output`）与文档空间模块（`docmgr`）共用同一套排版模板数据模型，但两处的导出/模板编辑能力存在缺口：

1. **报告输出 `LayoutTemplateEditor`（新建/编辑模板对话框）**：
   - 无法「上传文档样例自动提取排版模版」——本次核心功能
   - 数据模型有 `tocSettings`（目录设置）但无对应 UI，改不了存不了
   - 封面配置仅 4 个 checkbox，无预览
2. **文档空间 `ExportDocxDialog`（Word 导出对话框）**：
   - 「导入排版」按钮**损坏**：前端调 `POST /api/extensions/docmgr/import-layout`，后端从未实现（2026-06-09 规格只写前端），点击必 404
   - 勾选「保存为模板」时 `tocSettings` / `coverTemplate` 硬编码 `null`，对话框里选的目录/封面参数丢失

本次一次性补齐：共享 docx 排版提取后端 + 两个对话框接线。

## 需求

1. 上传 `.docx` 样例，后端确定性提取排版参数（基础 5 组 + 封面结构检测），填充到模板编辑器表单
2. 修好 docmgr 导出对话框的「导入排版」按钮
3. 报告输出模板编辑器补「目录设置」UI 与「封面预览」
4. 修复 docmgr「保存为模板」丢弃目录/封面参数

### 明确不做（YAGNI）

- `output/generate` 的 `source=project` 仍是 stub（返回占位内容），不碰
- 封面图/字体精确还原（即 2026-06-09 规格里的「方案 B」，模型装不下，否决）
- LLM 辅助提取（有 token 成本、不可复现，否决）
- docmgr 导入应用封面（docmgr 封面是预设驱动，与模板 5 开关模型不同）

## 架构

### 提取逻辑

**新文件 `backend/app/extensions/output/layout_import.py`** — 确定性 python-docx 提取，与生成器同用 python-docx，无新依赖。

输入 `UploadFile`（.docx，≤10MB），输出 LayoutTemplate 数据子集（snake_case，与 docmgr 前端既有期望一致）：

| 输出字段 | 提取来源 | 缺失时 |
|---|---|---|
| `page_settings` | `doc.sections[0]` 宽高 → 纸张（A4/A3/B5/letter）+ 方向；四边距 cm | 默认 A4 纵向 |
| `body_styles` | `doc.styles['Normal']`：字体（含 `w:eastAsia`）、字号、`line_spacing`、`paragraph_spacing`、`first_line_indent` | 默认值 |
| `heading_styles` | `doc.styles['Heading 1'..4]`：字体/字号/`bold`→fontWeight/颜色；`numbering` 无法检测 → 默认 `decimal` | 默认值 |
| `table_styles` | 首张表：表头行底纹 → `headerBg`、表头字色 → `headerColor`、边框色 → `borderColor`；`stripeRows` 无法检测 → `true` | 默认值 |
| `header_footer` | `sections[0].header` / `.footer`：段落文本 + 页码字段检测 → `showPageNumber` | 空文本 + 显示页码 |
| `cover_template` + `cover_detected` | **方案 A**：首节 `different_first_page`（`titlePg`）为强信号；否则取首标题前首页内容分析——顶部图片 → `showLogo`（按对齐推断 `logoPosition`）、大字号居中段 → `showTitle`、「业主/单位/日期/编号」关键词 + 日期正则 → `showClient`/`showDate`/`showProjectNumber` | 无封面结构 → `cover_detected:false`，调用方保持封面区原样（方案 C 兜底） |
| `figure_styles` | 不提取（图注样式不稳定） | `null`，UI 保持默认 |

### 共享端点（同一提取函数，两个路由，各自权限）

- **`POST /api/extensions/output/import-layout`**（`require_permission("system:access")`）— 报告输出模板编辑器使用
- **`POST /api/extensions/docmgr/import-layout`**（`require_permission("doc:upload")`，薄封装调用同一函数）— 修好 docmgr 坏按钮。不共用 output 端点是因为 docmgr 用户未必有 `system:access`，权限不能降级

docmgr 前端 URL 不变（`/api/extensions/docmgr/import-layout`），后端补上即活。

**响应**（`LayoutTemplate` 数据子集，snake_case）：
```json
{
  "page_settings": { "paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17 },
  "body_styles": { "fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 6, "firstLineIndent": 2 },
  "heading_styles": [ { "level": 1, "fontFamily": "黑体", "fontSize": 16, "fontWeight": 700, "color": "#333333", "numbering": "decimal" } ],
  "table_styles": { "headerBg": "#2B579A", "headerColor": "#FFFFFF", "borderColor": "#CCCCCC", "stripeRows": true },
  "figure_styles": null,
  "header_footer": { "headerText": "", "footerText": "", "showPageNumber": true, "showLogo": false },
  "cover_template": { "showLogo": true, "logoPosition": "center", "showTitle": true, "showClient": false, "showDate": false, "showProjectNumber": false },
  "cover_detected": true
}
```

## 前端

### 报告输出 `LayoutTemplateEditor.tsx`

- 「基本信息」区新增 **「从样例导入排版」** 按钮（`.docx` 上传）→ 调 `/api/extensions/output/import-layout` → 按 snake_case→camelCase 映射填充各 section state → toast 成功/失败
- 新增 **「目录设置」区块**（折叠 Section）：
  - 包含目录开关（无目录时禁用手下控件）
  - 收录级别 `maxDepth`（1~4）
  - 显示页码 `showPageNumbers`
  - 点线 `leaderDots`
- **封面预览**：封面配置区内嵌极简 CSS mock（按 5 开关渲染：logo 占位 / 标题 / 客户 / 日期 / 项目编号行），约 40 行，无图上传、纯展示
- `cover_detected=false` 或提取失败时，封面区不做任何改动

### 报告输出 `api.ts`

新增 `importLayout(file: File): Promise<LayoutTemplateImportResult>`（POST multipart，携带 CSRF token，与 docmgr 现有做法一致）。

### 文档空间 `ExportDocxDialog.tsx`

- 「导入排版」按钮：后端修好即活，现有 `handleFileSelected` 已能应用 5 组数据（snake_case）；封面为预设驱动，忽略 `cover_template`
- **修「保存为模板丢参」**：保存时持久化
  - `tocSettings`：`{ maxDepth: tocDepth, showPageNumbers: true, leaderDots: true }`（`withToc=true` 时）否则 `null`（当前硬编码 `null`）
  - `coverTemplate`：把活动封面预设字段映射为 5 开关（尽力映射；预设的具体值仍在导出时按 `default_from` 填）

## 测试

- **后端** `backend/tests/test_output_layout_import.py`（TDD）：
  - 内存用 python-docx 建已知排版样例 → 提取 → 断言 page_settings/body_styles/heading_styles/table_styles/header_footer 各值
  - 无封面样例 → `cover_detected:false`
  - 有独立封面页（`different_first_page` + 图片 + 大标题）样例 → `cover_detected:true` + 各开关
  - 非 docx / 损坏文件 → 400 或可读错误
- **前端**：typecheck + lint（本次变更均为表单接线，不新增单测）

## 文件变更清单

| 文件 | 变更 |
|---|---|
| `backend/app/extensions/output/layout_import.py` | **新建** — 提取函数 |
| `backend/app/extensions/output/routers.py` | **修改** — 新增 `POST /import-layout` |
| `backend/app/extensions/docmgr/routers.py` | **修改** — 新增 `POST /import-layout` 薄封装 |
| `backend/tests/test_output_layout_import.py` | **新建** — 提取单测 |
| `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx` | **修改** — 导入按钮 + 目录设置区 + 封面预览 |
| `frontend/src/extensions/output/api.ts` | **修改** — 新增 `importLayout` |
| `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` | **修改** — 修保存为模板丢参 |

## 运行验证

- 后端改代码 → `docker compose -p eai-docker restart gateway`
- 前端改代码 → `docker compose -p eai-docker restart frontend`
- 回归：`cd backend && make lint && make test`；`cd frontend && pnpm typecheck && pnpm lint`
