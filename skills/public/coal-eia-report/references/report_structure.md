# ⛔ 本文件已废止 — 请勿作为章节结构依据

**废止日期：2026-09-06（coal-eia-report v2，T8/D8）。** 保留本文件仅为防旧引用失效。
**章节结构唯一真源 = `references/stages/planning_eia.json`**（机器可读：章/节清单、必备/可选集、
条件开关、sections[].uses 结构化引用——由 ingest / chapter_planner / build_output / seed_gen 消费）。
项目环评（井工）结构走 `references/stages/project_eia_underground.json`（在编）；openpit / post_eia 二期立项。

## 废止原因（D8 实体污染）

本"通用"模板已被单一横城样例实体污染：白芨滩自然保护区、太中银铁路、明长城、鸭子荡水库、宝丰光伏等
横城专属敏感目标与地物被硬编码进通用章节定义，换任何矿区即失效。敏感目标专节改为实体卡片清单
数据驱动的小节槽位（设计 D8）；per-sample 实体注册表见 `references/sample_entities/`。

## KF 三偏差备注（D3）

KF 既有 published「煤炭_环评报告_模板」（13 章单模板）与 planning_eia 语料存在三处已知偏差，resolve 命中时
结构一律以 stages JSON 校正，勿以 KF 模板或本文件为准：

1. 风险评价应为第 6 章内小节，非独立章；
2. 缺回顾性评价 / 清洁生产与循环经济 / 跟踪评价三个高频章；
3. 13 章单模板仅适用规划环评（项目环评不同构）。

偏差数据修订走 KF 版本机制（一期末回写）。
