# 审阅闭环

> 对齐：ResolutionPanel + doc_graph service @ 2026-10-06

抽取产物不是进图就完——本系统强制"人审闸门"（force_review）。这篇讲清状态机、每步操作、以及最常见的疑问："我抽的实体怎么图上没有/Agent 查不到？"

## 状态机

```
抽取入库
  → pending_review   （force_review=true 默认全量置待审，D11/11A）
      ├─ 确认 confirm → active     （投影入 kernel 图，全系统可见）
      ├─ 驳回 reject  → rejected   （不入图）
      └─ 合并 merge   → merged     （归入规范实体，dg_merges 留痕，可 unmerge 撤销）
```

设计意图：LLM 抽取必有噪声，宁可多一道人工确认，不让脏事实污染账本。确认后的实体才成为"断言图"一员——后续推理、校验、导出、Agent 查询都以它为基础。

## 待审队列怎么读

- **按置信度升序**：最不可信的排最前，先处理最可疑的
- force_review 批次（置信度 0.85+）在列表**后段**——量大时用搜索或逐条确认处理，别等它自己浮上来
- 待审计数与侧栏红点同源（工作台总览瓦片同 key 共享缓存）

## 每步操作（在「04 消解审核」）

| 动作 | 做什么 | 后果 |
|---|---|---|
| 确认 | 核对实体名/属性/证据 quote 无误 → confirm | 置 active 并投影入图 |
| 驳回 | 判定为抽取噪声 → reject | 置 rejected，不入图 |
| 合并 | 同一实体的不同写法（"煤矸石山1号"/"1号煤矸石山"）→ candidate 归入 canonical | candidate 置 merged，dg_merges 留痕 |
| 撤销合并 | merge 错了 → unmerge（拿 merge_id） | 删留痕行，candidate 回 active 待审 |

## 与 Agent 的关系（高频疑问）

**未确认的实体不投影进 kernel 图，Agent 经 MCP 查不到。**"刚抽完怎么搜不到"不是 bug——先来这里确认。反过来这也是安全设计：Agent 引用的图谱事实全部经过人审（深读：[Agent 集成指南](../reference/agent-integration)）。

## 权限与边界

- **第一版仅超管可审**（消解面板横幅自述）；多人化审阅角色授权在主系统 TODOS（与操作审计一起）
- **relation 审批通道未建**：实体有状态机，关系边暂无独立审批（治理链关系现随实体整链确认）；主系统 TODOS 在册
