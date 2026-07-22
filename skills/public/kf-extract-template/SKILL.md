---
name: kf-extract-template
description: |
  从 Word/PDF 报告文件中自动提取报告模板。运行 5 阶段抽取流水线，
  生成包含章节结构、内容契约和富元数据（表格/公式/计算脚本/章节剖面）的模板。
  通过 MCP 工具 knowledge-factory_kf_extract_template 触发。
  触发场景：用户需要从样例报告中抽取模板、创建新的报告模板、
  或为知识工厂增加新的领域模板时。
---

# 知识工厂 — 模板提取技能

## 概述

此技能将 Word/PDF 报告文件自动解析为结构化的报告模板。模板包含：
- **章节树**：完整的章节层级结构（章→节→条）
- **内容契约**：每节的写作规范（关键要素、结构类型、风格规则）
- **富元数据**：表格定义、图片需求、公式引用、计算脚本绑定、章节剖面

提取的模板存入知识工厂数据库，后续通过 `kf_resolve_template` 消费（如 `coal-eia-report` 技能用于生成报告）。

## 5 阶段流水线

```
文档解析 → 章节推断 → 元数据抽取 → 模板融合 → 合规校验
 (Step 0)   (Step 1)    (Step 2)     (Step 3)    (Step 4)
```

### Step 0: 文档解析

直接解析 Word (.docx) 或 PDF 文件：

- **Word**：用 `python-docx` 读取 Heading 样式识别章节层级；用 `doc.tables` 提取表格结构
- **PDF**：用 `pymupdf` 读取字体大小/加粗推断标题；用 `page.find_tables()` 提取表格
- **兜底**：无样式 Word / 扫描版 PDF → 回退到正则扫描 + RAGFlow OCR

### Step 1: 章节推断

从文档内容推断标准章节结构。优先使用领域的 `standard_chapters` 作为骨架。

**LLM Prompt（可编辑）**：

```
你是一个专业的文档结构分析专家。

任务：从给定的样例文档中，推理出该类文档的标准章节结构。

要求：
1. 分析文档的章节标题，识别层级结构（一级章节、二级章节等）
2. 归纳章节的共性规律，提取标准章节模板
3. 每个章节给出：
   - id: 唯一标识（如 sec_01, sec_01_01）
   - title: 章节标题
   - level: 层级（1=一级, 2=二级, ...）
   - required: 是否必需
   - purpose: 章节目的/作用（50字以内）
4. 输出一棵树形结构，代表该类文档的标准模板
5. 章节层级不超过 {max_depth} 级

优先骨架规则：
- 如果提供了参考章节结构（reference_chapters），优先使用它作为骨架
- 必须覆盖参考结构中的所有 H1 章节（不可缺省）
- 章节顺序与参考结构对齐
- 如果实际文档结构不同（如报告类型不匹配），保留参考章节但标记 required=false
- 对未匹配的参考章节输出 deviation_note 说明原因

注意：
- 不同类型的报告（环评、可研、水保、安全评价等）章节结构完全不同
- 要基于实际文档内容推断，不要猜测
```

### Step 2: 元数据抽取

逐节调用 LLM，一次输出内容契约 + 富元数据。

**LLM Prompt（可编辑）**：

```
你是一个专业的文档抽取专家。

任务：为一篇报告模板的某个章节，生成完整的内容契约和结构化元数据。

## 输出字段

### content_contract（内容契约）
- key_elements: 章节必须包含的关键要素列表
- structure_type: 内容结构类型
  - narrative_text: 叙述性文本
  - table: 表格形式
  - formula: 公式/计算
  - diagram: 图表
  - mixed: 混合形式
- style_rules: 写作风格规范
- min_word_count: 最小字数要求
- forbidden_phrases: 禁止出现的表述

### compliance_rules: 涉及的法规/标准引用列表

### rag_sources: 推荐的知识库检索来源

### generation_hint: 生成时的提示

### example_snippet: 典型文本片段（100-200字）

### completeness_score: 完整度评分（0-100）

### 富元数据（仅当章节中存在对应内容时输出，无则省略）

- table_schemas: 表格定义列表
  每项：table_id, caption, columns[{header, width, type, unit}], data_source, required

- figure_requirements: 图片需求列表
  每项：figure_id, caption, suggested_type, placement_section, required, fallback

- formula_references: 公式引用列表
  每项：formula_id, name, applicable_section, expression, input_vars

- calc_script_bindings: 计算脚本绑定列表
  每项：script（脚本路径）, section, input_params[{name, unit, source}], output_table, trigger

- sub_section_profile: 子章节深度指导
  expected_h2_count, expected_h3_count, volume_estimate, notes

重要：只输出章节中确实存在的内容。如果某类元数据不存在，直接省略该字段，不要输出空数组。
这可以避免 prompt 膨胀和 token 超载。
```

### Step 3: 模板融合

多份报告合并为一份标准模板（去重、补充、排序）。

### Step 4: 合规校验

计算模板完整度评分（0-100）。

## 使用方式

### 方式 1：Agent 对话触发

```
用户：帮我从知识库的"环评报告-横城矿区"文档提取环评模板

Agent 调用 knowledge-factory_kf_extract_template：
  source_report_ids: ["<文档UUID>"]  ← 知识库中已上传的文档
  domain: "environmental_impact_assessment"
  industry: "coal"
  report_type: "环评报告"
```

### 方式 2：Web UI

知识工厂 → 模板抽取 → 创建提取任务 → 上传 Word/PDF → 查看结果

## 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `source_report_ids` | string[] | ✅ | 知识库中文档的 UUID 列表（需先在样例管理 tab 上传） |
| `file_paths` | string[] | | 服务器上的文件绝对路径（直接解析路径，后续支持） |
| `domain` | string | | 领域标识，默认 `"default"` |
| `industry` | string | | 行业分类代码 |
| `report_type` | string | | 报告类型，如 "环评报告" |
| `template_name` | string | | 模板名称，默认自动生成 |
| `max_depth` | integer | | 章节层级深度（1-6），默认 4 |
| `llm_model` | string | | 指定 LLM 模型，默认用系统设置 |

## 输出结构

```json
{
  "success": true,
  "template_name": "环评报告模板",
  "domain": "environmental_impact_assessment",
  "chapters": 14,
  "total_sections": 52,
  "completeness_score": 85,
  "sections": [
    {
      "id": "sec_01",
      "title": "总则",
      "level": 1,
      "required": true,
      "purpose": "说明任务由来、编制依据、评价标准等",
      "content_contract": {
        "key_elements": ["任务由来", "编制依据", "评价标准", "评价等级"],
        "structure_type": "narrative_text",
        "style_rules": "使用被动语态，引用法规标准编号，层次分明",
        "min_word_count": 500
      },
      "table_schemas": [
        {
          "table_id": "tbl_01_01",
          "caption": "表 1-1  评价标准一览表",
          "columns": [
            {"header": "标准名称", "width": "40%", "type": "string"},
            {"header": "标准编号", "width": "30%", "type": "string"},
            {"header": "执行级别", "width": "30%", "type": "string"}
          ],
          "data_source": "template",
          "required": true
        }
      ],
      "formula_references": [],
      "calc_script_bindings": [],
      "sub_section_profile": {
        "expected_h2_count": 5,
        "expected_h3_count": 12,
        "volume_estimate": "long",
        "notes": "总则是环评报告篇幅最大的章节之一"
      },
      "children": [
        {
          "id": "sec_01_01",
          "title": "任务由来",
          "level": 2,
          "required": true,
          "purpose": "说明项目背景和环评任务来源"
        }
      ]
    }
  ],
  "cross_section_rules": [],
  "step_summaries": [
    {"name": "文档解析", "status": "completed", "duration": "2s", "detail": "解析 1 份文档"},
    {"name": "章节推断", "status": "completed", "duration": "8s", "detail": "推断出 14 个章节"},
    {"name": "元数据抽取", "status": "completed", "duration": "45s", "detail": "已抽取 52 节元数据"},
    {"name": "模板融合", "status": "completed", "duration": "1s", "detail": "单文档，无需融合"},
    {"name": "合规校验", "status": "completed", "duration": "1s", "detail": "完整度 85%"}
  ]
}
```

## 调 prompt 指南

### 改进章节推断准确率

编辑上面的 `## Step 1` 中的 LLM Prompt。关键调试点：
- **领域术语**：在 prompt 中加入该领域报告的标准章节名称（如环评的"总则、工程分析、环境现状"）
- **噪音过滤**：增加 `排除项` 说明（如"目录页、附录、附表不算正文章节"）
- **层级信号**：明确告诉 LLM 如何区分章和节（如"一级章节通常以'第X章'或独立数字开头"）

### 改进元数据提取质量

编辑 `## Step 2` 中的 LLM Prompt。关键调试点：
- **输出省略规则**：当前已设置"无则省略"，如果 LLM 仍然输出空数组，加强该指令
- **表格提取**：如果表格列定义不准确，在 prompt 中增加示例
- **公式识别**：如果公式引用遗漏，在 prompt 中加入该领域常见公式名称

### 修改流水线阶段

流水线阶段顺序在 `backend/app/extensions/knowledge_factory/pipeline.py` 的 `run()` 方法中定义。
新增/删除/重排阶段需要修改代码。

## 边界与限制

- 仅支持 .docx 和 .pdf 格式
- 扫描版 PDF 通过 RAGFlow OCR 兜底（精度低于文字型 PDF）
- 表格合并单元格在 V1 中不完美支持（后续增强）
- 每文档 LLM 调用次数 ≈ 章节数 × 1（合并为一次 pass）
- 大文档（>100页）提取可能需要 2-5 分钟
