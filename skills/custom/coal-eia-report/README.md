# 煤炭矿区总体规划环评报告编写技能

## 概述

为煤炭矿区总体规划项目生成专业的环境影响评价报告书。采用项目工作流模式，按章节逐步生成，支持知识工厂模板驱动和多知识库 RAG 检索。

## 功能特性

- **模板驱动**：优先从知识工厂获取报告模板，利用 generation_hint / compliance_rules / content_contract 等元数据驱动生成
- **仿写而非照抄**：四重防护机制确保不复制样例报告的实体数据
- **多知识库支持**：样例报告库、法规标准库、技术导则库、地理环境库
- **三种计算模式**：内置 Python 脚本 / 占位符 / 外部 API
- **双重合规检查**：模板规则 + 法规知识库 RAG 对照
- **章节级生成**：每次生成一个章节，支持跨会话恢复

## 报告结构

标准13章结构：总则 → 规划概况 → 环境现状 → 回顾评价 → 影响识别 → 影响预测 → 承载力 → 综合论证 → 减缓措施 → 监测管理 → 清洁生产 → 公众参与 → 结论建议

## MCP 工具依赖

- `knowledge-factory`：kf_resolve_template, kf_list_domains
- `project`：list_chapters, get_chapter_spec, write_chapter, get_project
- 知识库 REST API：/{kb_id}/chat, /search

## 计算脚本

| 脚本 | 功能 |
|------|------|
| `scripts/calc/calc_subsidence.py` | 概率积分法沉陷预测 |
| `scripts/calc/calc_noise.py` | 噪声衰减计算 |
| `scripts/calc/calc_water_balance.py` | 水量平衡计算 |
| `scripts/calc/calc_air_screen.py` | AERSCREEN 简化大气估算 |
| `scripts/calc/calc_capacity.py` | 环境容量估算 |

## 参考文档

- `references/report_structure.md` — 13章完整结构
- `references/terminology.md` — 环评专业术语
- `references/content_guidelines.md` — 编写规范
- `references/compliance_checklist.md` — 合规检查条目
- `references/sample_entities.md` — 样例实体黑名单
- `references/calc_params_guide.md` — 计算参数说明
- `references/chapter_examples/` — 4个核心章节样例

## 设计文档

详见 `docs/superpowers/specs/2026-06-12-coal-eia-report-skill-design.md`
