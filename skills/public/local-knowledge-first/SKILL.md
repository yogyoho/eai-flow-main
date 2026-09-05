---
name: local-knowledge-first
description: 本地知识库优先检索规则——查询标准/规范/法规/行业标准（GB、DZ/T、HG/T、DL/T、TB 等编号或名称）、历史报告、样例报告、项目资料、合同条款时，必须先调用 MCP 工具 knowledge-factory_kf_search_knowledge 检索本地 RAGFlow 知识库（含法规标准库等），本地无命中或确需最新官方发布信息时才改用 web_search。
license: proprietary
---

# 本地知识库优先检索

## 何时遵守（每个回合自动生效，无需读取本文件）

用户询问以下内容时，**第一动作**是调用 MCP 工具 `knowledge-factory_kf_search_knowledge`：

- 标准 / 规范 / 法规 / 行业标准（如"中华人民共和国地质矿产行业标准"、"GB/T 13908"、"DZ/T 0033"）
- 历史报告、样例报告、报告模板相关资料
- 项目资料、内部文档、合同条款

## 工具用法

- `query`：检索问题或关键词；标准查询可直接用标准名称或编号
- `kb_name`：可选，知识库名模糊过滤（如"法规标准"）
- `top_k`：默认 5；`similarity_threshold`：默认 0.2，命中少可降低

返回每个命中块的 所属知识库 / 文档名 / 相似度 / 原文内容，引用时注明出自哪个知识库与文档。

**本地来源没有网页链接**：本地知识库命中项在 Sources/引用列表中只写 `知识库名 — 文档名`（可附相似度），**禁止编造 URL 或虚构域名**（如 `knowledge-factory.internal`）。只有 web_search/web_fetch 的结果才允许带 url。

## 与 web_search 的分工

1. 先本地检索；命中即可直接作答，标注本地来源。
2. 本地无命中（换关键词重试一次后仍为空）或用户明确要"最新/官方发布/在线"信息时，再用 web_search。
3. 两者都用了时，回答中分开标注 [本地知识库] 与 [网络] 来源。
