# eia 域模型设计

> 设计依据：环评样例四类目标抽取（章节结构 / 上下文逻辑链 / 标准阈值与法规条款 / 业务节点佐证需求），词汇与 registry `eia.yaml` 严格同名。

## 两条逻辑链

eia 域的本体围绕两类上下文逻辑链组织：

```
治理合规链：  污染源 ──treated_by──▶ 治理措施 ──governed_by──▶ 排放标准
                  │                                              ▲
                  └──monitored_by──▶ 监测 ──has_limit──┘
                                   （属性链推导 covered_by_standard）

影响链：      污染源 ──emitted_as──▶ 污染物 ──threatens/impact_to──▶ 敏感点
```

**治理合规链**回答「这个设施执行哪个标准」；**影响链**回答「谁影响了哪个敏感点」。两条链的要素全部来自确定性抽取器（regex/v1），谓词与 `eia.yaml` 枚举严格同名。

## 属性链公理（推理核心）

```yaml
axioms:
  property_chains:
    - { derived: covered_by_standard, chain: [monitored_by, has_limit] }
  transitive: [located_in]
```

`monitored_by ∘ has_limit ⇒ covered_by_standard` 由 OWL 2 RL 的 **prp-spo2** 规则在推理闭包中物化——治理合规链的「被标准覆盖」结论不是抽出来的，是**推出来的**。这使报告原文只需陈述「X 配施 Y、Y 监测指标 Z 限值按标准 S」，覆盖关系由内核推导。

::: warning 已知边界（prp-spo2）
属性链要求**链首谓词已有实例**——若 `monitored_by` 无任何实例，整条链静默零推断（不报错）。CQ 验收 FAIL 行会给出缺前提提示。
:::

## 数据流（抽取 → 人审 → 推理）

```
环评报告 ──regex/v1 抽取──▶ dg_entities/relations/mentions（pending_review）
                                │
                    消解审核：确认 → active ／ 驳回 → rejected
                                │（同步投影，状态强制翻转）
                                ▼
                        断言图（全行忠实投影）
                                │ POST /formal/infer
                                ▼
                    推理物化（covered_by_standard 等派生）
```

- 抽取结果置信度 < 0.7 落 `pending_review`，≥ 0.7 直落 `active`
- 重入库 promote-only：人工清理过的状态永不降级
- 全量装载 = 对账：重读 `dg_*` 全表强制重写图（degraded 自愈的执行者）

## 双透镜与图面判据

| 视角 | 对象类型 | 用途 |
|---|---|---|
| 环评域透镜 | `eia_entity` / `eia_relation`（domain=eia 过滤） | 环评专属浏览（etype 枚举齐全） |
| 通用透镜 | `graph_entity` / `graph_relation` | 全域数据 |

图面验收判据唯一：`GET /formal/export?graphs=asserted` 含目标 IRI 且状态正确。MCP 只读工具走 SQL 层，**不作为投影判据**。

## 重建与扩展

- 在**本体建模器**选 `eia.yaml` → 可视化画布查看真实类层次、表单编辑 label/definition、「＋新建类」追加、YAML 源码模式做结构编辑
- 新类保存后须过校验（schema/引用/环），SHA 热重载后下一次 infer 用新词表
