# 术语总览

OntoStudio 的术语与 registry YAML 声明**同名同义**——本文档中心由 registry 内容驱动，本体改了术语页跟着构建。术语按域组织：

| 域 | 文件 | 内容 |
|---|---|---|
| **eia**（环评） | `eia.yaml` | 环评业务本体：文档结构/治理合规链/影响链/法规佐证/组织活动（v2 扩容 +24 etype / +19 谓词，以 yaml 为准） |
| **core_graph**（图谱底座） | `core_graph.yaml` | 图谱底座骨架：图谱实体/关系/证据三类对象、审核动作与链接声明（原 doc_graph，2026-10-06 更名） |
| **market**（营销） | `market.yaml` | 营销域词汇 v1（天玛定制）：客户集团/矿井/工作面/商机/招投标/合同/已装机/证书——详见建模器 |

## 通用术语

| 术语 | 含义 | 深读 |
|---|---|---|
| **registry** | 本体注册表——本体声明的唯一真相源（YAML），保存后 SHA 热重载，下一次推理用新词表 | [本体地基](../concepts/foundations) |
| **三元组 / IRI** | 图的原子陈述句；IRI 是全局唯一资源名，机械可逆（C1 校验对象） | [本体地基](../concepts/foundations) |
| **Turtle / JSON-LD** | 图序列化双格式（导出正典 / REST 友好） | [Turtle 与 JSON-LD 1.1](../concepts/turtle-jsonld) |
| **SHACL** | 图上的质检规则清单；报告五要素 focusNode/path/message/severity/source | [SHACL](../concepts/shacl) |
| **断言图（asserted graph）** | 内核图的一层：`dg_*` 表全行的忠实投影（含状态三元组）。图面判据只有 `GET /formal/export?graphs=asserted` | — |
| **命名图** | 图中的"抽屉"：断言 / `graph:entailment` / `graph:derived:*` 按层隔离 | [SPARQL 与 CONSTRUCT 派生](../concepts/sparql-construct) |
| **装载（load）** | 把 `dg_*` 表行装进内核图；**装载即对账**（重写 DB 真相），投影失败后重跑即自愈 | — |
| **投影（projection）** | 确认/驳回动作提交后把行写入断言图——确认翻转 active、驳回翻转 rejected | [审阅闭环](../guide/review-loop) |
| **双透镜** | 同一张 `dg_entities` 表经 `graph_entity`（通用）与 `eia_entity`（环评域）两个对象类型投影——域透镜提供类型枚举过滤 | — |
| **状态机** | 实体行状态：`pending_review`（待审）→ 确认 `active` / 驳回 `rejected`；`merged`（合并入他实体）。驳回是翻状态非删除，实体与提及全保留 | [审阅闭环](../guide/review-loop) |
| **闭包 / 物化** | 把隐含三元组推出来写进图（`graph:entailment`） | [owlrl 闭包](../concepts/owlrl) |
| **CONSTRUCT 派生** | 业务规则造新三元组（`graph:derived:*`，每规则一图可溯源） | [SPARQL 与 CONSTRUCT 派生](../concepts/sparql-construct) |
| **TriG 快照** | 带抽屉的 Turtle 全图时点存档；每日 06:00 调度 + 30 天滚动 | [TriG 快照](../concepts/trig-snapshots) |

各域术语见左侧子页面。
