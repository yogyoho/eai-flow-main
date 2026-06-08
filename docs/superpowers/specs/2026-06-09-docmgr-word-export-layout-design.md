# 文档空间 Word 导出排版设置 — 设计文档

> 日期: 2026-06-09
> 状态: 待审核

## 概述

在文档空间（docmgr）的文档编辑器中，点击「导出 → Word 文档」时弹出排版设置对话框，用户可以选择已有排版模板、从上传的 Word 文件导入排版、微调排版参数后导出。支持水印（初稿/送审稿/正式稿）和将排版保存为新模板。

## 需求

1. **排版设置对话框**：点击 Word 导出时弹出，包含页面设置、正文样式、标题样式、表格样式、图表样式、页眉页脚、水印等排版参数
2. **模板选择**：从已有的 `LayoutTemplate` 列表中选择一个作为基础
3. **轻量覆盖**：选择模板后可临时调整关键参数，不修改原模板
4. **导入排版**：上传 Word 文件，后端提取排版信息并填充到对话框表单
5. **保存为模板**：导出时可勾选将当前排版设置保存为新的 `LayoutTemplate`
6. **水印**：支持初稿/送审稿/正式稿水印标记

## 架构

### 整体流程

```
用户点击「Word 导出」
    → 打开 ExportDocxDialog
    → 选择模板 或 导入排版 或 使用默认
    → 微调排版参数（可选）
    → 设置水印（可选）
    → 点击「导出 Word」
        → [勾选保存?] → outputApi.createTemplate()
        → POST /docmgr/documents/{id}/export (body: layout_template + watermark)
        → 浏览器下载 .docx 文件
```

### 数据流

```
ExportDocxDialog
  ├── outputApi.listTemplates()  → 模板下拉列表
  ├── POST /docmgr/import-layout → 导入排版提取
  ├── outputApi.createTemplate() → 保存为模板（可选）
  └── docmgrApi.export(id, "docx", layout, watermark) → 生成并下载
```

## 前端组件

### ExportDocxDialog

**文件**: `frontend/src/extensions/docmgr/ExportDocxDialog.tsx`

**Props**:
```ts
interface ExportDocxDialogProps {
  docId: string;
  docTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

**布局结构**:
```
┌──────────────────────────────────────────────────┐
│  导出 Word 文档                              ✕  │
├──────────────────────────────────────────────────┤
│  📄 排版模板:  [▼ 选择模板...          ]         │
│  📥 [导入排版]  🔄 [重置为默认]                    │
├──────────────────────────────────────────────────┤
│  ▼ 页面设置    (纸张、方向、页边距)                │
│  ▼ 正文样式    (字体、字号、行距、段距、缩进)      │
│  ▼ 标题样式    (1~4级标题字体/字号/颜色/编号)      │
│  ▼ 表格样式    (表头背景、字色、边框、斑马纹)      │
│  ▼ 图表样式    (标题位置、编号方式、来源)           │
│  ▼ 页眉页脚    (页眉/页脚文本、页码、Logo)         │
│  ▼ 水印设置    (初稿/送审稿/正式稿/无)             │
├──────────────────────────────────────────────────┤
│  [☐ 保存为排版模板]  [模板名: ____]               │
│                        [取消]  [导出 Word]        │
└──────────────────────────────────────────────────┘
```

**关键实现**:
- 中部排版表单**复用** `LayoutTemplateEditor` 中的 `Section` + `FieldLabel` 组件和相同的表单字段
- 不包含「封面配置」和「参考文献与附录」（文档空间不需要）
- 新增「水印设置」Section，使用 `WATERMARK_LABELS` 映射
- 模板选择使用 shadcn `Select` 组件
- 内部状态管理：将选中的 `LayoutTemplate` 展开为独立的 state sections，修改时覆盖

### 修改 DocumentManagement.tsx

- `handleExport("docx")` 改为打开 `ExportDocxDialog`
- `handleExport("md")` 保持不变（直接下载）
- `ExportMenu` 中 Word 导出按钮的 `onClick` 改为 `setShowExportDialog(true)` 而非直接调用 `handleExport`

## 后端 API

### 1. 排版导入端点

**`POST /api/extensions/docmgr/import-layout`**

**请求**: `multipart/form-data`，字段 `file`（.docx 文件）

**处理逻辑** (使用 python-docx):
1. `Document(file)` 打开上传的文件
2. 从 `doc.sections[0]` 提取页面设置:
   - `page_width` / `page_height` → 推算纸张大小和方向
   - `top_margin` / `bottom_margin` / `left_margin` / `right_margin` → 页边距 (cm)
3. 从 `doc.styles['Normal']` 提取正文样式:
   - `font.name` / `font.size` → 字体、字号
   - `paragraph_format.line_spacing` → 行距
   - `paragraph_format.first_line_indent` → 首行缩进
4. 从 `doc.styles['Heading 1']` ~ `doc.styles['Heading 4']` 提取标题样式:
   - `font.name` / `font.size` / `font.bold` / `font.color.rgb` → 各级标题参数
5. 从 `doc.sections[0].header` / `.footer` 提取页眉页脚:
   - 遍历 paragraphs 获取文本
   - 检测是否包含页码字段
6. 从文档中的第一个 `Table` 提取表格样式:
   - 表头行的背景色（shading）
   - 边框颜色

**响应**: `LayoutTemplate` 的数据子集（不含 id/isBuiltin/createdAt/updatedAt）:
```json
{
  "name": "从文档导入",
  "reportType": "general",
  "pageSettings": { ... },
  "bodyStyles": { ... },
  "headingStyles": [ ... ],
  "tableStyles": { ... },
  "figureStyles": null,
  "headerFooter": { ... },
  "referenceStyle": "gb7714",
  "appendixRules": null
}
```

### 2. 改造导出端点

**新增 `POST /api/extensions/docmgr/documents/{doc_id}/export`**

保留原有 `GET` 端点用于 Markdown 导出。

**请求 body**:
```json
{
  "format": "docx",
  "layout_template": {
    "page_settings": { "paperSize": "A4", ... },
    "body_styles": { "fontFamily": "宋体", ... },
    "heading_styles": [...],
    "table_styles": {...},
    "header_footer": {...}
  },
  "watermark": "draft"
}
```

**处理**:
1. 获取文档内容（与 GET 端点逻辑相同）
2. 将 `layout_template` 传入改造后的 DOCX 生成函数
3. `watermark` 传入水印参数
4. 返回 .docx 文件流

### 3. 改造 DOCX 生成

**文件**: `backend/app/extensions/output/generator.py`

修改 `generate_docx_simple()` 签名:
```python
def generate_docx_simple(
    markdown_content: str,
    buf,
    template_data: dict | None = None,
    watermark: str | None = None,
) -> None:
```

- `template_data=None` 时使用默认值（当前行为）
- `template_data` 有值时，复用 `generate_docx()` 中的页面设置、正文样式、标题样式渲染逻辑
- 水印：复用已有的水印逻辑（页眉中插入 `【初稿】` 等）

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `frontend/src/extensions/docmgr/ExportDocxDialog.tsx` | **新建** — 导出对话框组件 |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | **修改** — Word 导出改为打开对话框 |
| `frontend/src/extensions/api/index.ts` | **修改** — docmgrApi.export 新增 POST 版本 |
| `backend/app/extensions/docmgr/routers.py` | **修改** — 新增 import-layout 端点 + 改造 export 为 POST |
| `backend/app/extensions/output/generator.py` | **修改** — generate_docx_simple 支持 template_data + watermark |

## 边界条件

- **大文件导入排版**：上传的 .docx 文件限制 10MB
- **无排版信息**：某些 Word 文件可能使用默认样式，导入时对缺失字段使用默认值
- **模板列表为空**：对话框显示「使用默认排版」选项
- **导入解析失败**：toast 提示「无法从该文件提取排版信息，请确保为 .docx 格式」

## 不在范围内

- 封面生成（文档空间导出不涉及封面）
- 目录生成（目录需要文档结构分析，不在本次范围）
- PDF 导出（本次只做 .docx）
- 参考文献格式化（文档空间内容不含引用管理）
