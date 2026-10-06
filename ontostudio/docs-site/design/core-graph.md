# core_graph 骨架设计

> 对齐：`core_graph.yaml`（原 doc_graph.yaml，2026-10-06 更名）+ ingest_tasks @ 2026-10-06

`core_graph.yaml` 是图谱底座的**结构骨架**——它不描述业务语义（那是各业务域 yaml 的事），而声明支撑消解审核、实体库、图谱浏览的底座：

## 三类对象（双透镜体系）

```
dg_entities ──投影──▶ graph_entity（通用透镜）
            ──投影──▶ eia_entity  （eia 域透镜，声明于 eia.yaml）
dg_relations ─投影─▶ graph_relation
dg_mentions ─投影──▶ graph_mention（证据链，永不删）
```

同一物理表可被多个对象类型透镜投影（全域视角 vs 域过滤视角），属设计语义非数据重复。

## 审核动作管线

```
点「确认/驳回」──▶ POST /actions/invoke
  ├─ 权限：ontology:action:review（网关 JWT）
  ├─ 范围：ontology 模块 scope（/api/permissions/scope 下发）
  ├─ 事务：FOR UPDATE 锁行 → 前置校验(status=pending_review) → UPDATE → 审计行
  └─ 提交后投影：行级装载（状态强制翻转）+ refresh() 重跑推理
```

- 投影失败不回滚业务状态：接口回 `projected:false + errors`（degraded），重跑全量装载即自愈
- 审计行（`dg_action_audit`，before/after JSONB）是追溯与重放投影的凭据

## 不变量

| 不变量 | 说明 |
|---|---|
| **mention 永不删** | 证据链是一等节点——实体可驳回/合并，原文引文永远保留（溯源依据） |
| **合并留痕可回放** | `dg_merges` 记录 + mergedInto 指针，unmerge 撤销原位还原 |
| **promote-only 重入库** | 同文档重抽不降级人工清理过的 active/merged |
| **Postgres 唯一真相源** | `dg_*` 表是事实层；内核图是可随时重建的投影（装载=对账） |

## 抽取任务化（B2 + G3 + G6）

抽取从"内部装载器"升级为可观测的任务流：

- **B2 任务表**（`dg_extraction_tasks`）：排队 / 抽取中 / 装载 / 完成 / 失败状态机；「08 抽取导入」页 2s 轮询消费
- **G3 直连通道**：`upload-and-extract` 端点——txt/docx 上传 → 规则抽取 → 建任务，一体流不依赖离线管线预产产物
- **G6 进度 stats**：loading 阶段实时百分比由独立连接写入（零 DDL），任务队列进度列消费

## 与主系统的关系

- `dg_*` 表由主系统抽取管线（eia_samples regex/v1 / G3 直连规则抽取）写入；OntoStudio 消费
- agent 经 MCP（ontology server 17 工具——只读为主，含受治理动作 / doc-graph server 5 工具）读写本体（契约：[MCP 工具总表](../reference/mcp-tools)）
- 协同文档编辑**不在** OntoStudio 范围——使用主系统 docmgr（EAI 文档子系统）
