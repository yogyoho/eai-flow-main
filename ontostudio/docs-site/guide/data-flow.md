# 端到端数据流

> 对齐：IngestPage/ResolutionPanel/kernel 管线 @ 2026-10-06

一条文档从进入系统到被 Agent 消费，完整走这条链。每站只讲"输入→做什么→产物→下一站"；操作细节链到对应模块分页。

## 全链路

```
文档/样例
  → ① 抽取导入（双通道）
  → ② 待审队列（force_review）
  → ③ 消解审核（确认/合并/驳回）
  → ④ 投影入 kernel 图
  → ⑤ 推理（owlrl 闭包 + CONSTRUCT 派生）
  → ⑥ 校验（SHACL + 国标 C1-C5）
  → ⑦ 沉淀与出口（TriG 快照 / Turtle·JSON-LD 导出 / Agent 消费）
```

## ① 抽取导入 → [08 抽取导入](./08-ingest)

两条通道进同一张任务队列：

- **选择已有样例**：消费 kf_samples 已提取产物（离线批量管线的 outline_json）入图
- **上传新文件**：拖拽 txt/docx 直连规则抽取（G3 一体流：上传→解析→抽取→建任务）

产物：实体/关系/证据（mention 带原文 quote），**默认 `force_review=true` 全量置待审**——不直接入图。

## ② 待审队列 → [04 消解审核](./04-resolve)

任务完成后实体进入 `pending_review` 状态，队列按置信度升序。**这一站是质量闸门**：没过闸的实体不存在于图上（Agent 也查不到，见 [审阅闭环](./review-loop)）。

## ③ 消解审核

逐条处理：确认（→active）/ 驳回（→rejected）/ 合并（同名异写归一，candidate 置 merged 留痕可撤销）。第一版仅超管可审。

## ④ 投影入 kernel 图

确认后的实体投影进 kernel 图（pyoxigraph）。从此它是"断言图"的一员——图上最硬的事实，[SHACL](../concepts/shacl) 校验它，[owlrl 闭包](../concepts/owlrl) 基于它推理。

## ⑤ 推理 → [06 推理工作台](./06-reasoning)

两层：标准规则闭包落 `graph:entailment`；业务规则 CONSTRUCT 派生落 `graph:derived:*`（[双层推理](../concepts/sparql-construct)）。推理是重操作，按钮触发。

## ⑥ 校验 → [07 校验中心](./07-validation)

pyshacl 全图形状校验 + 国标 C1-C5 符合性套件 + 数据治理（孤儿实体/零边 mention）。约 20 秒，按钮触发，历史自动留痕。

## ⑦ 沉淀与出口 → [09 导出互操作](./09-export) / [Agent 集成](../reference/agent-integration)

- **TriG 快照**：每日 06:00 自动 + 手动，30 天滚动，审计/回滚
- **导出**：Turtle（all / 含派生）/ JSON-LD schema，C2 往返同构兜底
- **Agent 消费**：ontology MCP（查）+ doc-graph MCP（写），技能包装层给纪律

## 一图记忆

> 抽取是**进料**，审核是**闸门**，图是**账本**，推理是**推演**，校验是**体检**，快照导出是**存档**，Agent 是**读者**。
