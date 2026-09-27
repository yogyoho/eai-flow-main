# doc_graph 域术语（文档图谱骨架）

`doc_graph.yaml` 不是业务本体，而是**文档图谱的结构骨架**——它声明了证据链对象、审核动作与链接，是消解审核、实体库、图谱浏览的底座。

## 对象类型（透镜）

| api_name | 术语 | 物理表 | 说明 |
|---|---|---|---|
| `graph_entity` | 图谱实体（通用透镜） | `dg_entities` | 全域实体行的通用投影——图谱浏览/实体库的默认视角 |
| `graph_relation` | 图谱关系 | `dg_relations` | 实体间关系边（双端点齐备才入图） |
| `graph_mention` | 图谱证据 | `dg_mentions` | 证据链节点：原文引文 + 来源文档/会话定位，**永不删** |

::: warning 双透镜说明
`graph_entity`（doc_graph）与 `eia_entity`（eia）投影**同一张物理表** `dg_entities`——前者是全域通用视角，后者是环评域视角（etype 枚举过滤）。同一行可能在两个视图出现，属投影语义而非数据重复。
:::

## 审核动作

| 动作 | 前置条件 | 后象 | 说明 |
|---|---|---|---|
| `review_entity.confirm` | status = pending_review | status = active | 确认抽取实体——提交后**同步投影**进断言图（状态强制翻转） |
| `review_entity.reject` | status = pending_review | status = rejected | 驳回——状态翻转为 rejected（实体/关系/提及全保留，非删除） |

动作经权限（`ontology:action:review`）与数据范围（`ontology` 模块 scope）两层校验后，在事务内落库并记审计（`dg_action_audit`，撤销/追溯凭据）。

## 链接类型

| 链接 | 方向 | 含义 |
|---|---|---|
| `relation_subject` / `entity_as_subject` | graph_relation ↔ graph_entity | 关系主体侧 |
| `relation_object` / `entity_as_object` | graph_relation ↔ graph_entity | 关系客体侧 |
| `mention_of_entity` / `entity_has_mentions` | graph_mention → graph_entity | 实体证据链 |
| `mention_of_relation` / `relation_has_mentions` | graph_mention → graph_relation | 关系证据链 |

eia 域的对应证据链链接（`mention_of_eia_entity` 等）声明在 `eia.yaml`，机制同上。
