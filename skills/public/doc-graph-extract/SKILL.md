---
name: doc-graph-extract
description: 从上传的投标/合同类文档抽取实体关系构建知识图谱（doc_graph 域）。当用户要求"构建图谱 / 抽取实体入库 / 更新投标图谱 / 图谱化这份文档"时使用。
---

# doc-graph 文档图谱抽取

把非结构化文档变成结构化图谱：抽取 → `ingest_extraction` 入库 → 待复核确认 → 汇报。

## 工作流

1. **读文档**：用户上传的文件在工作目录/上传目录中，先通读定位 投标项目/投标人/货物/资质 信息。
2. **抽取**：严格按下面 schema 组装 JSON（多余字段会被拒绝，关系只能引用 entities 里声明过的 name）。
3. **入库**：调用 doc-graph MCP 工具 `ingest_extraction` 传入 payload。幂等——同一文档重抽不会产生重复实体。
4. **复核**：若返回里提示有 pending_review，调 `list_pending_review` 列出，请用户确认；确认是同一实体的用 `merge_entities` 合并（可 `unmerge` 撤销）。
5. **汇报**：报告 实体数/关系数/证据数/待复核数，关键实体附 quote 原文引用。

## 抽取 schema

```json
{
  "domain": "bid",
  "thread_id": "<当前会话 id，可空>",
  "extracted_by": "llm",
  "entities": [
    {
      "etype": "project | bidder | goods | qualification",
      "name": "实体规范名（≤300字）",
      "attrs": {"自由键值": "如 金额/资质等级/货物规格"},
      "confidence": 0.0,
      "valid_from": null,
      "valid_to": null,
      "mention": {"document_id": "<文档标识>", "doc_span": {"page": 1}, "quote": "原文片段"}
    }
  ],
  "relations": [
    {
      "predicate": "bidder_of_project | bidder_supplies_goods | bidder_holds_qualification | project_won_by_bidder",
      "subject": "<entities 中的 name>",
      "object": "<entities 中的 name>",
      "confidence": 0.0,
      "mention": {"document_id": "<文档标识>", "quote": "原文片段"}
    }
  ]
}
```

## 纪律

- **只抽文档明确出现的信息**；quote 必须是原文逐字片段（这是溯源证据链，会被永久保留）。
- 置信度：原文明确 ≥0.95；需要推断 0.6~0.8；**<0.7 自动进人工复核**，不要虚高。
- 名称规范化：同一实体在不同段落的不同写法，选最完整正式的作为 name（消解靠归一化+复核兜底）。
- 查询图谱：用 ontology MCP 的 `graph_entity` / `graph_relation` / `graph_mention` 对象（list_objects / search_objects / get_links / traverse）。本技能的 MCP 只负责写。
