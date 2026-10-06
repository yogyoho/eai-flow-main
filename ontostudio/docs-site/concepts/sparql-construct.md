# SPARQL 与 CONSTRUCT 派生

> 对齐：CONSTRUCT 派生规则（per-rule named graph）+ `evaluate_rules`（doc-graph MCP）@ 2026-10-06

## 一句话类比

SPARQL 之于图 = SQL 之于表。其中 **CONSTRUCT** 最特别——它不是"查出现有数据"，而是 **`CREATE VIEW`**：按模板把匹配到的数据"造"成新三元组。本系统把它用作**自定义业务规则的推理引擎**。

## 在 OntoStudio 里对应什么

**双层推理，各司其职**：

| 层 | 引擎 | 回答的问题 | 结果落点 |
|---|---|---|---|
| 标准规则 | owlrl 闭包（见 [owlrl 闭包](./owlrl)） | 逻辑上**必然**有什么（子类传递等） | `graph:entailment` 命名图 |
| 业务规则 | CONSTRUCT 派生 | 本系统**规定**推出什么（业务启发式） | `graph:derived:*`（每条规则一个命名图） |

**per-rule named graph**：每条 CONSTRUCT 规则的派生结果落在自己的命名图里——这是刻意设计：规则 A 的产物与规则 B 互不污染，"这条结论是哪条规则推的"可以精确溯源，停用规则时精确摘除。

**引擎安全约束**：CONSTRUCT 模板在服务端受安全检查（防注入式规则构造）；规则启停是受治理动作，有审计留痕。

## 你在哪能看到/操作它

- **ontology MCP 的 `ontology_reason`**：一次调用同时跑闭包层 + 派生层，返回各规则派生计数（[MCP 工具总表](../reference/mcp-tools)）
- **doc-graph MCP 的 `evaluate_rules`**：在真库数据上现算现返（零落库），带**触发轨迹**——哪条源事实触发了哪条规则；适合 Agent 做规则验证与解释（注意：`max_derived_reached` 等标志=true 表示到达推理工作预算，不必然截断）
- **06 推理工作台**：人工验证规则效果的界面

## 常见坑

- **CONSTRUCT 错得安静**：模板写错不会报错，只会安静地产出错误的"事实"，且带着"规则结论"的名义出现——比查不出数据更危险。改规则必须：先 `evaluate_rules` 小样本看触发轨迹 → 确认派生合理 → 再上真图。
- **两层的"真相等级"不同**：断言图是人审过的最硬；entailment 是逻辑必然；derived 是业务规定——引用 derived 结论给用户时说明"这是规则推的"，别包装成原始事实。
- **预算标志不是错误**：`max_iterations_reached=true` 只是说"到工作预算了"，结果可能仍完整——看数据本身，别见标志就当失败。
