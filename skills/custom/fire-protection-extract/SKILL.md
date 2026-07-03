---
name: fire-protection-extract
description: |
  ⛔ 当用户已上传设计说明书(.docx)并请求编写消防设计专篇时，应使用本技能，不使用 fire-protection-report-v2。
  本技能从设计说明书**逐字摘抄**重组出消防专篇（映射契约驱动 + 逐字溯源校验），而非从零生成。
  触发词：消防设计专篇/消防设计报告/消防设计篇章 + 有设计说明书。无说明书时改用 fire-protection-report-v2。
---

# 消防设计专篇 抽取技能

从已上传的**设计说明书**按映射契约精确摘抄出消防设计专篇。原则：**能抄尽抄，但不抄错**。

本技能是**执行式**技能，不是分析式技能。报告由脚本自动生成，不是通过阅读文件后手动编写。

## ⛔ 禁止事项（必须阅读 — 违反将导致技能失败）

### 关于设计说明书
- ❌ **禁止手动 read_file 读取设计说明书 .md 来挑选/查找/理解内容。** 这不是手动编写报告，脚本会自动完成所有摘抄。
- ❌ **禁止逐章节阅读设计说明书**来判断"这部分内容该放到消防专篇哪里"——映射契约已经定义了全部映射关系。

### 关于脚本
- ❌ **禁止 read_file 读取 parse_spec.py / extract.py / grounding_check.py 脚本来"理解其逻辑"**——直接通过 bash 执行它们。脚本是执行件，不是参考文档。
- ❌ **禁止 read_file 读取 fire_spec_mapping.json**——它是机器读的契约文件，extract.py 会自动加载它。

### 关于报告生成
- ❌ **禁止在内存中手动起草报告内容。** 报告由 extract.py 一步生成，你只需检查它的输出。
- ❌ **禁止跳过步骤 2-3-4 的 bash 流水线**——这三个步骤是强制性、不可跳过的。

### 允许读取的文件
- ✅ SKILL.md（本文件）—— 技能指令
- ✅ extractor_rules.md —— 防抄错规则和术语参考（可选，补充知识）
- ✅ structure.json 或 report.md 的局部内容 —— 仅在失配处理（步骤 3a）时需要
- ✅ 合规检查报告（步骤 5 的输出）

## 关键规则
0. 所有输出用中文（含 SESSION INTENT/SUMMARY/ARTIFACTS 等框架标签的中文替换）。
1. 仅用工具：read_file / bash / write_file / present_files / ask_clarification。禁调 text-to-cad_*/cad_*/word-document-server_*。
2. 上传的 docx 会在 uploads/ 自动生成同名 .md（markitdown）；但本技能需要**结构化**解析（{paras, tables}），通过 bash 跑 parse_spec.py 直接从 .docx 生成 structure.json。不要用 markitdown 的 .md 替代。
3. 路径一律虚拟路径（/mnt/user-data/...、/mnt/skills/...）。禁容器物理路径。
4. 一次性 write_file 写完整报告到 outputs/，再 present_files（沿用 v2 写盘铁律，禁分块 append/str_replace 修补）。

## 工作流（严格执行，每个 bash 步骤不可跳过或替代）

> 整个工作流由三个 bash 命令组成一个流水线：**解析 → 抽取 → 校验**。你的角色是执行这个流水线，检查结果，处理失配和失败，最后落盘。你不是报告的作者——extract.py 是。

### 步骤1：确认说明书
确认 uploads/ 下有 设计说明书.docx。缺项目名/编号用 ask_clarification 一次补齐。注意文档路径。

### 步骤2：解析说明书为结构 JSON（⚠️ 不可跳过，不可用 read_file 替代）
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/parse_spec.py \
  "/mnt/user-data/uploads/<设计说明书>.docx" \
  "/mnt/user-data/workspace/<项目名>_struct.json"
```
确认输出 `OK [backend] paras=... tables=...` 表示解析成功。不要 read_file 打开 structure.json（它很大，是给 extract.py 用的机器文件）。

### 步骤3：按契约抽取报告（⚠️ 不可跳过，不可手动替代）
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/extract.py \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json" \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md"
```
检查步骤 3 的终端输出：有 `[⚠未找到...]` 说明契约锚与本项目说明书失配 → 走步骤 3a。没有则继续步骤 4。

### 步骤3a：失配处理（契约校准）
- 少量锚失配：read_file structure.json 找到对应内容的新锚，复制一份 mapping.json 到 workspace 修改锚点后重跑步骤 3（不直接改技能契约文件，除非用户要求沉淀）。
- 大面积失配：说明书结构与样本差异大 → ask_clarification 告知用户，考虑回退 fire-protection-report-v2。

### 步骤4：逐字溯源校验（⚠️ 不可跳过）
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/grounding_check.py \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json"
```
退出码 0 = 通过(rate≥0.85，无失配锚，无冲突失败)；非 0 = 阅读 JSON 输出找到失败项（`missing_anchors` / `conflict_failures` / `failed_samples`），修契约锚后重跑步骤 3-4。最多 2 轮。

### 步骤5：合规检查（复用 v2 链路，可选但推荐）
```bash
python /mnt/skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py \
  --report "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  --output "/mnt/user-data/outputs/<项目名>消防合规检查报告.md"
```

### 步骤6：落盘 + 展示
先 read_file 快速浏览 `/mnt/user-data/outputs/<项目名>消防设计专篇.md` 的开头和结尾（确认标题、章节结构完整，无大量 `[⚠` 标记）。然后一次 write_file（append=false）写完整报告到 outputs/，立即 present_files 触发文档空间同步。§7 投资概算保持 `[需计算]` 不伪造。

## 参考文件
- references/fire_spec_mapping.json — 映射契约（8章×子节→源锚，机器文件）
- references/extractor_rules.md — 抽取/溯源/防抄错规则（可选参考）
- scripts/parse_spec.py / extract.py / grounding_check.py — 引擎三件（执行件，不读直接跑）
