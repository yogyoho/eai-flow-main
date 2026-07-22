---
name: markdown-to-docx
description: 当用户想要将 Markdown 内容转换为 Microsoft Word (.docx) 文档时使用此技能。该技能可以解析 Markdown 并创建具有正确标题、段落、表格、列表和基本格式的专业 Word 文档。
---

# Markdown 转 Word 文档技能

## 概述

此技能可将 Markdown 内容转换为专业格式的 Microsoft Word (.docx) 文档。它使用 python-docx 库创建具有正确格式的 Word 文档，包括标题、段落、表格、列表和基本文本样式。

## 核心功能

- 将 Markdown 转换为 Word 文档 (.docx)
- 支持具有正确层级结构的标题 (H1-H9)
- 将表格转换为 Word 格式
- 支持无序列表和有序列表
- 应用基本文本格式（粗体、斜体）
- 支持分页符
- 可自定义文档元数据（标题、作者）

## 使用场景

在以下情况下使用此技能：
- 用户请求将内容导出为 Word 文档
- 用户想要将 Markdown 报告转换为 .docx
- 用户需要从 Markdown 源创建专业格式的 Word 文档
- 用户想要从 AI 生成的内容创建 Word 文档

## 工作流程

### 步骤 1：了解需求

当用户请求生成 Word 文档时，需要确定：
- **内容来源**：Markdown 内容或文件路径
- **输出位置**：保存 .docx 文件的位置（通常在 `/mnt/user-data/outputs/`）
- **文档标题**：用于元数据的文档标题
- **作者**：作者姓名（可选）

### 步骤 2：准备 Markdown 内容

如果用户提供 Markdown 文件，请读取其内容：

```bash
cat /mnt/user-data/uploads/filename.md
```

或者如果用户直接提供 Markdown 内容，则直接进行转换。

### 步骤 3：转换为 Word

使用转换脚本将 Markdown 转换为 Word：

```bash
python /mnt/skills/public/markdown-to-docx/scripts/convert.py \
  --markdown "/mnt/user-data/uploads/input.md" \
  --output "/mnt/user-data/outputs/report.docx" \
  --title "文档标题" \
  --author "作者姓名"
```

或使用内联 Markdown 内容：

```bash
python /mnt/skills/public/markdown-to-docx/scripts/convert.py \
  --content "# 你好世界\n\n这是一个段落。" \
  --output "/mnt/user-data/outputs/document.docx" \
  --title "我的文档"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--markdown` | 否* | Markdown 输入文件路径 |
| `--content` | 否* | 内联 Markdown 内容 |
| `--output` | 是 | 输出 Word 文档路径 (.docx) |
| `--title` | 否 | 文档标题（元数据） |
| `--author` | 否 | 作者姓名（元数据） |

*必须提供 `--markdown` 或 `--content` 之一。

### 步骤 4：展示结果

转换成功后，告知用户：
- Word 文档保存的文件路径
- 文件可供下载
- 格式说明（如适用）

## 支持的 Markdown 特性

### 标题
- H1 - 文档标题
- H2 - 章节标题
- H3 - 小节标题
- H4-H9 - 子小节

### 段落
- 具有适当行距的常规段落

### 列表
- 无序列表（项目符号）
- 有序列表（编号）

### 表格
- 带表头的基本表格支持
- 多行/多列单元格

### 文本格式
- **粗体** 文本
- *斜体* 文本
- ~~删除线~~

### 其他
- 分页符（单独一行使用 `---` 或 `***`）
- 水平线

## 输出位置

将 Word 文档保存到：
- `/mnt/user-data/outputs/` - 适用于用户下载
- `/mnt/user-data/workspace/` - 适用于工作副本

## 示例提示词

- "将此 Markdown 报告转换为 Word"
- "将研究报告导出为 .docx 文件"
- "从此 Markdown 内容创建 Word 文档"
- "把这份 Markdown 报告转换成 Word 文档"

## 注意事项

- 此技能需要已安装 python-docx 库
- 复杂的 Markdown 特性（嵌入图片、脚注、带语法高亮的代码块）可能支持有限
- 为获得最佳效果，请使用简洁、结构良好的 Markdown
- 生成的 Word 文档可以在 Microsoft Word 或 WPS 中打开查看
