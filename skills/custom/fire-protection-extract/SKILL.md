---
name: fire-protection-extract
description: |
  ⛔ 当用户已上传设计说明书(.docx)并请求编写消防设计专篇时，应使用本技能，不使用 fire-protection-report-v2。
  本技能从设计说明书**逐字摘抄**重组出消防专篇（映射契约驱动 + 逐字溯源校验），而非从零生成。
  触发词：消防设计专篇/消防设计报告/消防设计篇章 + 有设计说明书。无说明书时改用 fire-protection-report-v2。
---

# 消防设计专篇 抽取技能

从已上传的**设计说明书**按映射契约精确摘抄出消防设计专篇。原则：**能抄尽抄，但不抄错**。

## 关键规则
0. 所有输出用中文（含 SESSION INTENT/SUMMARY/ARTIFACTS 等框架标签的中文替换）。
1. 仅用工具：read_file / bash / write_file / present_files / ask_clarification。禁调 text-to-cad_*/cad_*/word-document-server_*。
2. 上传的 docx 会在 uploads/ 自动生成同名 .md（markitdown）；但本技能需要**结构化**解析，用 bash 跑 parse_spec.py 生成 structure.json（见步骤2）。
3. 路径一律虚拟路径（/mnt/user-data/...、/mnt/skills/...）。禁容器物理路径。
4. 一次性 write_file 写完整报告到 outputs/，再 present_files（沿用 v2 写盘铁律，禁分块 append/str_replace 修补）。

## 工作流

### 步骤1：确认说明书
确认 uploads/ 下有 设计说明书.docx（或 .md）。缺项目名/编号用 ask_clarification 一次补齐。

### 步骤2：解析说明书为结构 JSON
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/parse_spec.py \
  "/mnt/user-data/uploads/<设计说明书>.docx" \
  "/mnt/user-data/workspace/<项目名>_struct.json"
```

### 步骤3：按契约抽取报告
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/extract.py \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json" \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md"
```
检查输出：有 `[⚠未找到...]` 说明契约锚与本项目说明书失配（结构差异）→ 走步骤3a。

### 步骤3a：失配处理（契约校准）
- 少量锚失配：read_file structure.json 找到对应内容的新锚，**临时**改一份 workspace 副本的 mapping 重跑（不直接改技能契约文件，除非用户要求沉淀）。
- 大面积失配：说明书结构与样本差异大 → ask_clarification 告知用户，考虑是否回退 fire-protection-report-v2 生成式。

### 步骤4：逐字溯源校验
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/grounding_check.py \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json"
```
退出码 0 = 通过(rate≥0.85 且无失配锚)；非 0 = 看输出修契约锚后重跑步骤3-4。最多 2 轮。

### 步骤5：合规检查（复用 v2 链路）
```bash
python /mnt/skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py \
  --report "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  --output "/mnt/user-data/outputs/<项目名>消防合规检查报告.md"
```

### 步骤6：落盘 + 展示
一次 write_file（append=false）写完整报告到 outputs/，立即 present_files 触发文档空间同步。§7 投资概算保持 `[需计算]` 不伪造。

## 参考文件
- references/fire_spec_mapping.json — 映射契约（8章×子节→源锚；本项目结构不同时按步骤3a校准）
- references/extractor_rules.md — 抽取/溯源/防抄错规则
- scripts/parse_spec.py / extract.py / grounding_check.py — 引擎三件（report-agnostic，给排水/抗震将来复用）
