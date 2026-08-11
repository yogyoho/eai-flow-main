# 给排水单体计算书技能优化设计

- **日期**: 2026-08-11
- **状态**: Draft（待用户审阅 → 转 writing-plans）
- **范围**: `skills/public/water-drainage-report`（及其引用的 `app/extensions/formula_engine` 引擎）
- **作者**: brainstorming 会话产出
- **相关文件**: `SKILL.md`、`scripts/formula_runner.py`、`references/formulas.json`、`references/consistency_contracts.json`、`app/extensions/formula_engine/graph.py`、`backend/tests/test_formula_graph.py`

---

## 1. 背景与问题

### 1.1 用户反馈（7 条）

| # | 反馈 | 一句话 |
|---|---|---|
| 1 | 生成耗时过长 | 一份计算书 5–8 分钟，期望 30s–3min |
| 2 | 原始数据刚性 | 缺值即中断，缺容错/渐进；期望行业经验参考值库 + 分阶段输入 |
| 3 | 计算过程黑箱 | 只给结果，无中间步骤；期望逐条展开（公式来源/取值依据/代入/单位换算） |
| 4 | 缺结果校验 | 无法判断结果合理性；期望取值范围合理性自动检查 |
| 5 | 规范索引单一 | 只引一本主规范；期望多规范可勾选、逐参数跨标准比对、标注条款号 |
| 6 | 缺在线编辑/局部更新 | 改一个数要整篇重跑；期望依赖树热更新 + 差异高亮 |
| 7 | 多轮无上下文承接 | 二次修改答非所问；期望会话级项目快照 + 版本历史 |

### 1.2 现状盘点（关键：很多能力引擎层已有，只是未外显）

| 反馈 | 已有基建 | 真实缺口 |
|---|---|---|
| 1 提速 | 公式引擎纯 Python 瞬时 | 瓶颈在 LLM 整篇章节生成 |
| 2 数据刚性 | `lookup_table`/`code_requirement` 已内嵌默认值（KZF、有效水深、旁滤比）；但技能"最高铁律"禁用经验值 | 政策冲突 + 扩面 |
| 3 黑箱 | 步骤2 已 LaTeX 展示代入过程 | 未写进最终报告正文 |
| 4 校验 | `check` 命令 + 11 条 `consistency_contracts` 已有范围检查 | 校验项更多 + 汇总面板 |
| 5 规范单一 | 4 本 GB/HG 硬编码；合约只支持单标准限值 | 多规范可勾选 + 跨标准比对 |
| 6 热更新 | `FormulaGraph.update_param` 已实现 DAG 脏标记增量重算 + 变更摘要 | 报告正文侧无联动；无差异高亮 |
| 7 多轮承接 | `update` 的 `formula_state.json` 已是快照雏形 | 缺会话级快照重建 + 版本历史 |

> **结论**：本次优化的本质，大部分是"把引擎已具备的能力外显到最终报告与交互循环"，加上一次生成架构升级（提速 + 真增量）和一个数据层（经验值 + 多规范）。

---

## 2. 目标 / 非目标

### 2.1 目标
- **反馈1**：首版完整计算书生成 ≤3min（见非目标①对 30s 的说明）。
- **反馈2**：系数/经验类参数缺失时，按行业参考值库自动填入并标【待核实】；核心工艺参数仍必须用户提供。
- **反馈3**：最终报告每条公式含"摘要 + 折叠式详细步骤（公式来源/取值依据/代入分步/单位换算）"。
- **反馈4**：报告内含「校验面板」，自动执行范围合理性检查并给 ✅/⚠️/❌。
- **反馈5**：用户可勾选多本规范；每个关键参数给"围框式"跨标准比对表，标注条款号+版本。
- **反馈6**：改单个参数 → 仅重算受影响公式 → 仅重生成受影响章节；附变更日志（新旧值对比）。
- **反馈7**：会话级项目快照，跨轮次增量理解；保留版本号 + 修改历史轨迹。

### 2.2 非目标（明确顶回去 / 不在本 spec）
1. **不承诺 30s 下限**。即便章节并行，多章 LLM 生成 + 一致性校验也很难 <90s；目标 ≤3min。
2. **不建"条款级规范库"**。多规范走"扩展 contract + 人工入库"，不做全量条款知识工程。
3. **web_search 不驱动合规判定**。仅 discovery-only（见 §3.3 与附录 A 的实测证据）。
4. **不新建响应式前端文档编辑器**。差异 = 变更日志文本；版本历史复用 AIDocument 既有能力。若后续确需前端交互（赛道4），单独立项。
5. **不改 harness 核心**。新增集中在技能层 + `formula_engine` 的一个公共方法 + 两个 CLI 子命令。

---

## 3. 关键决策

### 3.1 默认值策略：分层放开（已确认）
- **系数/经验类参数**（蒸发系数 KZF、有效水深、旁滤比、反洗强度、飘水损失率等）：允许**有出处**的默认值，填入后标【待核实】。
- **核心工艺参数**（Q、N、Δt、构筑物尺寸、装置用水量等）：仍必须用户提供或从说明书提取，缺失则 `ask_clarification`。
- 铁律文字同步精确化：**从"禁止任何默认值"改为"禁止无出处的值"**。本质是把现有 `lookup_table`/`code_requirement` 的既有做法正规化 + 扩面。

### 3.2 生成架构：计算与生成分离 + 章节级并行/增量（Approach A，已确认）
- 公式引擎先算出全部数值 + 步骤轨迹 + 依赖图（瞬时）。
- 报告 = 一组独立章节单元；每章打标 `table`（机械渲染，不走 LLM）/ `narrative`（LLM 生成）。
- 首版：table 章瞬时渲染，narrative 章并行子 agent 生成（每个子 agent 拿同一份**冻结公式快照** → 数字不跨章漂移）→ 合并 → 单次 `write_file`。
- 改参：`update` 增量重算 → 仅重生成受影响章节 → 变更日志。

### 3.3 规范数据：两层模型（替换原"web_search 兜底"，详见附录 A）
- **Tier 1 · 人工入库**（`standards_index.json` + `code_constraint_multi`）：随包附常用规范关键限值，人工按规范原文录入，带条款号+版本号。**唯一驱动自动 pass/fail 的来源。**
- **Tier 2 · 未入库参数**：标【需人工对照规范: GBxxxx-yyyy §z】，面板显示"未自动校验"，不给 pass/fail；工程师核实后可写入项目快照晋升为该项目 Tier-1。
- **web_search = discovery-only**：仅用于"规范是否存在/范围/版本年"（实测 6/6 可靠），绝不作为合规限值/条款号自动引用。

---

## 4. 总体架构

```
参数(+说明书) ──► [Formula DAG 引擎] ──► 数值结果 + 步骤轨迹 + 依赖图   (瞬时, 纯Python)
                         │
                  [章节规划器] ──► chapter_manifest.json
                         │   每章: type=table|narrative, formula_ids=[...], hint, contract
                         ▼
            ┌────────────┴────────────┐
      table章: 模板机械渲染        narrative章: 并行子agent生成
       (参数表/计算表/设备表)        (每agent拿同一份冻结公式快照+步骤+contract)
            └────────────┬────────────┘
                         ▼
                   [合并] → 单次 write_file → present_files → 文档空间
                         ▼
              [多规范一致性校验] → 校验面板 + 多规范比对表附加到报告
                         ▼
              写 project_snapshot.json (version++, change_log 追加)
```

**核心不变量**：所有数值在第一段固化进一份**冻结快照**；所有生成单元（机械或 LLM）只读该快照——并行不会引入跨章数值漂移，改参不会污染未受影响章节。

---

## 5. 章节单元模型与生成管线

### 5.1 `chapter_manifest.json`（execute 时生成，是反馈6 定点重生成的中枢）

```json
{
  "version": 1,
  "chapters": [
    {"id": "ch3_params",    "title": "设计参数",         "type": "table",
     "formula_ids": [],                       "render": "param_table"},
    {"id": "ch5_calc",      "title": "循环水工艺计算",   "type": "table",
     "formula_ids": ["Qe","Qw","Qb","Qm"],   "render": "calc_steps"},
    {"id": "ch6_pool",      "title": "塔底水池/吸水池",   "type": "narrative",
     "formula_ids": ["V_pool","V_system","V_ratio_check"], "hint": "...", "contract": {}},
    {"id": "ch7_pumphouse", "title": "循环水泵房",       "type": "narrative",
     "formula_ids": ["pump_foundation_L"],   "hint": "...", "contract": {}},
    {"id": "ch9_equiplist", "title": "设备一览表",       "type": "table",
     "formula_ids": ["filter_count"],         "render": "equipment_table"}
  ]
}
```

- **table 章**（参数表/工艺计算表/设备表）= 纯公式输出，机械渲染不走 LLM：最快、最准、天然带步骤轨迹（直接解反馈3、4）。
- **narrative 章** = 并行子 agent 生成。每个子 agent prompt = `该章 formula 注入值 + 步骤轨迹 + generation_hint + content_contract + compliance_rules`，只返回该章 Markdown。合并按 manifest 章节顺序拼接。
- 跨章一致性由"共享冻结快照" + 既有 `cross_section` 合约保证。

### 5.2 生成并发与速度预算
- 子 agent 池：3 执行并发（既有 harness 限制）。
- 10 章典型报告：~3 table 章瞬时 + ~7 narrative 章分 3 批并行 → **目标 ≤3min**。
- 流式：narrative 章按完成顺序流式呈现进度（非硬性，HMR 不可靠时降级为批处理提示）。

---

## 6. 改参热更新流程（反馈6 落地）

```
用户 "Q 改成 25000"
  → formula_runner update   (DAG 增量重算, 已有)  → 受影响公式 [Qe,Qw,Qb,Qm,Qsf,filter_count,...]
  → formula_runner impacted --param Q --manifest   → 受影响章节 [ch3_params, ch5_calc, ch7, ch9_equiplist]
  → 仅重生成这些章节 (table重渲染 / narrative子agent重生成), 其余章节原样保留
  → 内存内整体覆盖 → 单次 write_file(append=false) → present_files
  → 变更日志追加: "v3: Q 20000→25000 ⇒ 第3/5/7/9章重生成, Qe:292.2→365.2, Qm:385.3→481.6"
```

- 不做像素级差异高亮 UI（顶回去）；"差异"以变更日志文本落地，复用文档空间既有版本能力。
- 公式侧增量重算（`FormulaGraph.update_param`）已存在并测试覆盖；本流程新增的是"受影响章节映射 + 定点重生成"。

---

## 7. 数据层改动

### 7.1 `references/formulas.json`（扩展现有）
每个 input 增可选字段：
```json
"KZF": {"type": "lookup_table", "value": 0.001461, "unit": "1/℃",
        "source": "GB/T 50746-2012 表3.3.3 内插",
        "needs_verification": false,
        "description": "蒸发损失系数"}
```
- `needs_verification: true` → 输出标【待核实】（新填入的经验值默认 true；人工核实过的入库值 false）。
- 把更多系数类 param 从 `user_input` 转为 `lookup_table` 带出处（扩面，反馈2）。

### 7.2 `references/reference_values.json`（新，小）— 行业经验参考值库
```json
{
  "description": "给排水/循环水 行业经验参考值（仅系数/经验类，不含核心工艺参数）",
  "values": [
    {"key": "backwash_intensity", "default": 15.0, "unit": "L/(s·m²)",
     "source": "GB/T 50050-2017 §4.0.4 条文说明 / 工程经验 12~16",
     "applies_when": "用户未提供反洗强度", "needs_verification": true},
    {"key": "effective_depth", "default": 2.0, "unit": "m",
     "source": "GB/T 50746-2012 §4.3.13（1.0~1.5m 为有效水深，本项目取值需核实）",
     "applies_when": "用户未提供塔底水池有效水深", "needs_verification": true}
  ]
}
```
- **核心工艺参数（Q/N/Δt/构筑物尺寸/装置用水量）一律不进此库** → 缺失即 `ask_clarification`。

### 7.3 `references/consistency_contracts.json`（扩展，新增多规范类型）
```json
{
  "id": "N-multi-standard",
  "type": "code_constraint_multi",
  "param": "N",
  "standards": [
    {"code": "GB 50648-2011",  "clause": "§4.1.1", "min": 3.0, "severity": "fail", "note": "不应低于3.0"},
    {"code": "GB 50648-2011",  "clause": "§4.1.1", "min": 5.0, "severity": "warn", "note": "宜≥5.0"},
    {"code": "GB/T 50050-2017","clause": "§3.1.x", "min": 3.0, "severity": "fail"}
  ]
}
```
- 既有 `code_constraint`（单标准）保留向后兼容；`check` 优先识别 `_multi`。

### 7.4 `references/standards_index.json`（新，小）— 可勾选规范清单
```json
{
  "standards": [
    {"code": "GB/T 50746-2012", "title": "石油化工循环水场设计规范", "scope": "循环水场", "tier1_curated": true},
    {"code": "GB 50648-2011",    "title": "化学工业循环冷却水系统设计规范", "scope": "化工循环水", "tier1_curated": true},
    {"code": "GB/T 50050-2017",  "title": "工业循环冷却水处理设计规范", "scope": "循环水处理", "tier1_curated": true},
    {"code": "GB 50974-2014",    "title": "消防给水及消火栓系统技术规范", "scope": "消防给水", "tier1_curated": false,
     "note": "部分条文 2023-03-01 废止；Tier-1 入库前需按现行条文核对"},
    {"code": "GB 50014-2021",    "title": "室外排水设计标准", "scope": "排水", "tier1_curated": false},
    {"code": "GB/T 50378-2019",  "title": "绿色建筑评价标准", "scope": "绿建", "tier1_curated": false}
  ]
}
```
- 步骤1 用户多选 → 存入 `project_snapshot.standards_selected`。
- `tier1_curated: false` 的规范 → 其参数走 Tier-2（标【需人工对照】，不自动判定）。

### 7.5 `project_snapshot.json`（新）— 会话级快照（反馈7）
```json
{
  "version": 3,
  "created_at": "<ISO>",
  "updated_at": "<ISO>",
  "params": {"Q": 25000, "delta_t": 10, "N": 5},
  "formula_state": { /* formula_runner execute/update 的完整输出 */ },
  "chapter_manifest": { /* §5.1 */ },
  "standards_selected": ["GB/T 50746-2012", "GB 50648-2011", "GB/T 50050-2017"],
  "report_path": "/mnt/user-data/outputs/<项目名>给排水设计专篇.md",
  "change_log": [
    {"version": 1, "action": "init", "ts": "<ISO>"},
    {"version": 2, "action": "update_param", "param": "Q", "old": 20000, "new": 25000,
     "affected_formulas": ["Qe","Qw","Qb","Qm","Qsf","filter_count"],
     "affected_chapters": ["ch3_params","ch5_calc","ch7_pumphouse","ch9_equiplist"],
     "value_diffs": {"Qe": "292.2→365.2", "Qm": "385.3→481.6"}, "ts": "<ISO>"}
  ]
}
```
- 技能**步骤0**：workspace 有快照 → 加载恢复（不重复问全局参数），后续指令默认基于基准状态增量理解。
- 版本历史 = `version` 序列 + `change_log`；前端展示复用文档空间，不新建。

---

## 8. 引擎与 runner 新增（复用 `FormulaGraph` + `formula_runner.py`）

### 8.1 `FormulaGraph.get_step_trace(formula_id)` （新公共方法）
返回单公式完整步骤轨迹，供反馈3 折叠渲染：
```python
{
  "id": "Qe",
  "expression": "Q * KZF * delta_t",
  "source": "GB/T 50746-2012 表3.3.3",
  "substituted": "20000 * 0.001461 * 10",
  "result": 292.2,
  "unit": "m³/h",
  "inputs": [
    {"name": "Q",     "value": 20000,   "unit": "m³/h", "source": "user_input",        "needs_verification": false},
    {"name": "KZF",   "value": 0.001461,"unit": "1/℃",  "source": "GB/T 50746 表3.3.3","needs_verification": false},
    {"name": "delta_t","value": 10,     "unit": "℃",    "source": "user_input",        "needs_verification": false}
  ]
}
```
- 实现复用引擎已有的表达式求值与参数表；新增的是"结构化轨迹导出"。
- 属 `app/extensions/formula_engine`（harness 公共包），非 app 私有；按项目 EAI-CUSTOM 规范加三重注释：docstring 声明 + START/END 包裹 + bug 编号/升级注意（harness 核心改动统一规矩）。

### 8.2 `formula_runner.py` 新增子命令
| 子命令 | 作用 | 输出标记 |
|---|---|---|
| `execute` / `update` / `check` | 既有 | `STATE_READY` / `CHECK_READY` |
| **`trace`**（新） | 输出全公式步骤轨迹（供报告渲染） | `TRACE_READY: <path>` |
| **`impacted`**（新） | 给定 `--param` + `--manifest`，输出受影响 formula_id + chapter_id | `IMPACTED_READY: <path>` |
| `check`（扩展） | 消费 `code_constraint_multi`，输出 每参数×每规范 结果矩阵 | `CHECK_READY` |

- 全部沿用现有 CLI + `STATE_READY` 标记 + bash 调用模式。
- `impacted` 算法：复用 `FormulaGraph.update_param(param, value)` 已返回的受影响 formula_id 集合（与 `update` 命令同源，保证一致）→ 用 `chapter_manifest` 反查含这些 formula_id 的 chapter_id。`impacted` 可实现为 `update` 的"只算不写盘"变体（dry-run）。

---

## 9. 会话快照协议（反馈7）

1. 技能启动（步骤0）：`/mnt/user-data/workspace/project_snapshot.json` 存在 → 加载 → `params`/`formula_state`/`standards_selected`/`report_path` 全部恢复 → 跳过全局参数重问，直接进入用户当前指令的增量理解。
2. 每次 `execute`/`update`/章节重生成/规范增删后，更新快照（`version++`、`change_log` 追加、`updated_at` 刷新）。
3. 快照损坏/缺失 → 降级为全新运行，不崩溃（try/except 包裹加载）。

---

## 10. 报告内呈现（反馈3/4/5/6 落到最终文档）

- **反馈3**：工艺计算章每公式 = 摘要行（结果）+ `<details><summary>计算过程</summary>…</details>` 折叠块（公式来源 / 各参数取值依据 / 代入分步 / 单位换算）。导出 Word 时折叠退化为"摘要 + 详细附录"（Markdown `<details>` 不被 Word 保留，机械渲染时同步产出展开版附录章节）。
- **反馈4**：报告末尾「校验面板」表：检查项 / 当前值 / 规范区间 / 结论（✅/⚠️/❌）/ 条款引用。
- **反馈5**：每个关键参数的「围框式多规范比对」小表：规范号+条款 / 限值 / 当前值 / 是否满足；Tier-2 参数显示"未自动校验（规范未入库，需人工对照）"。
- **反馈6**：报告顶部「本次变更」块（取 `change_log` 最新一条），列改动参数 + 受影响章节 + 数值新旧对比。

---

## 11. 错误处理

| 情形 | 处理 |
|---|---|
| 核心工艺参数缺失 | `ask_clarification`（保持既有铁律行为） |
| 系数/经验参数缺失 + 在 `reference_values.json` | 自动填入 + 标【待核实】 |
| 系数/经验参数缺失 + 不在参考值库 | `ask_clarification` |
| 子 agent 章节生成失败 | 重试 1 次 → 退化为单 agent 生成该章 → 仍失败标 `[待补充: 章节名]` |
| 合并后跨章不一致 | `cross_section` 合约检出 → 定点重生成违规章（≤2 轮） |
| 合规 FAIL >2 轮 | 既有"人工复核"路径不变，报告可导出并标注未修复项 |
| 快照损坏/缺失 | try/except → 降级全新运行 |
| `formula_runner` 报错 | 检查 params.json 格式/路径 → 修正重试 1 次 → 仍失败输出错误日志并告知用户 |

---

## 12. 测试策略（ponytail：每块一个 assert 级自检）

扩展 `backend/tests/test_formula_graph.py`：
- `get_step_trace` 正确性：给定 fixture 公式+参数，轨迹的 `substituted`/`result`/`inputs.source` 与预期一致。
- `impacted` 受影响集：改 `Q` → 返回的 formula_id 集合与 DAG 反查一致；chapter_id 与 manifest 反查一致。
- `code_constraint_multi` 求值：多规范矩阵中每条 severity 判定正确。
- `reference_values` 兜底：缺失系数类 → 填入默认 + `needs_verification=true`；缺失核心参数 → 不填入（返回"需用户提供"）。
- 机械渲染器：一个 fixture demo，断言 table 章从公式结果正确渲染（含步骤块）。
- 快照 round-trip：`execute` → 写快照 → 重新加载 → 恢复后的 `all_params` 与原一致。

不引入新测试框架；沿用 `assert` + pytest 既有风格。

---

## 13. 复用对账

| 既有件 | 复用方式 |
|---|---|
| `FormulaGraph`（DAG 引擎） | `execute`/`update_param`/`dependencies` 原样；新增 `get_step_trace` |
| `formula_runner.py` CLI | 既有 3 子命令 + 新增 `trace`/`impacted` |
| `consistency_contracts.json` | 既有单标准合约 + 新增 `code_constraint_multi` |
| `formulas.json` | 扩 input 字段（`source`/`needs_verification`） |
| knowledge-factory 模板 | `kf_resolve_template` 不变；`found=false` fallback 结构不变 |
| 子 agent 池（harness） | narrative 章并行生成 |
| `present_files` + 文档空间 AIDocument | 报告落盘 + 版本历史 |
| KaTeX（remark-math/rehype-katex） | 公式渲染不变 |

**新增代码集中在**：2 个小数据 json（`reference_values.json`/`standards_index.json`）、2 个 runner 子命令、1 个引擎方法、1 个章节规划+机械渲染辅助脚本（`scripts/chapter_planner.py`）、SKILL.md 流程改写。

---

## 14. 妥协与未决项

1. **提速目标 ≤3min**，不承诺 30s（见 §2.2①）。
2. **多规范 = 扩展 contract + 人工入库**，不建条款级规范库（见 §2.2②）。
3. **web_search 不驱动合规**，仅 discovery（见 §3.3、附录 A）。
4. **不新建响应式前端**；差异=变更日志文本，版本历史复用 AIDocument（见 §2.2④）。
5. **Tier-1 入库前需按规范原文重审现有硬编码值**（见附录 B）：`§6.1.9`、`0.1% 飘水`、`1%~5% 旁滤`、`GB 50050 → GB/T 50050-2017`。
6. **未决**：机械渲染的 table/narrative 分类是否做成渐进式（v1 全并行、v2 再机械优化）——若并行已达标则 v2 可缓。实施计划阶段定。

---

## 附录 A：web_search 可靠性验证证据（2026-08-11 实测）

**方法**：6 个真实 GB 条款检索（4 个技能已硬编码 + 2 个新规范），每个带权威源核验（WebFetch openstd.samr.gov.cn 等）+ 失败模式审计。工作流：`verify-websearch-standards-reliability`（7 agent，435k tokens，52 tool calls）。

**结论**：6/6 `citable=不可引用`，6/6 `source=非权威`。审计裁定 **discovery=中、精确限值=低**。

**最硬证据**：
1. **跨标准污染**：查 `GB/T 50746` 容积比，web 返回的原文"系统容积宜小于小时循环水量的三分之一"实际来自 **GB 50050 §3.2.2**；查飘水损失返回 **GB/T 50102-2014 §2.0.6**。真条款挂到错标准号——最危险的精度失效。
2. **算符方向翻转**：同一查询两次运行，`不宜大于 1/3` ↔ `不宜小于 1/3`，搜索引擎自承"通常要求/或类似限值/经验范围"的合成。pass/fail 引擎键在此则非确定。
3. **图表数字取不到**：GB 50974 室外消火栓 L/s 值在表3.3 图片表里，web 只拿到公式 `V=V1+V2`——无可引用数字。
4. **权威源全堵 + 串号**：`openstd.samr.gov.cn` 6/6 够不着；100% 来自聚合站，其中一次把 **GB 50648 查成 GB 50464**。

**裁定推荐**：web_search **不得**驱动自动合规 pass/fail；降级为 discovery-only + 人工核实门禁（规范原文 PDF / mohurd.gov.cn），核实工程师签章记录。

**环境局限说明**：本环境 WebFetch 对中文域被安全策略阻断，"无权威源"部分是网络所致；但跨标准污染、算符翻转、兜底子款简化、版本漂移是搜索引擎+LLM 综合的固有毛病，换网络也救不回——结论与网络无关。

---

## 附录 B：现有硬编码值重审清单（Tier-1 入库前必做）

实测检索翻出的存疑项（**注意：web 冲突 ≠ 技能必错**，技能值可能来自正版 PDF 是对的；但必须回规范原文核对）：

| 参数 | 现值（技能） | web 浮出 | 动作 |
|---|---|---|---|
| 系统容积比 | `1/3~1/2 @ §6.1.9`（GB/T 50746） | web 完全定位不到该条款；返回的是 GB 50050 §3.2.2 | 回 GB/T 50746-2012 原文核对条款号与方向 |
| 飘水损失率 | `0.1%`（Q×0.001） | web 浮出 `0.05%`（带收水器塔），归到 GB/T 50102-2014 | 核对塔型/是否带收水器，按条件取值 |
| 旁滤比例 | `1%~5% @ §4.0.4` | 实为"当缺乏空气含尘量数据时"的**兜底子款**，仅限间冷开式，沙尘区可上调 | 改为条件化判定，勿机械套"必须 1%~5%" |
| 规范版本 | `GB 50050` | 现行为 `GB/T 50050-2017`（强制→推荐） | 标签更正为 GB/T 50050-2017 |

> 这 4 项的重审属于 Tier-1 数据治理，应在实施计划的"数据层"阶段最先完成，其结论回写 `formulas.json`/`consistency_contracts.json`/`standards_index.json`。

---

## 后续

本 spec 经用户审阅通过后 → 调用 `writing-plans` skill 产出实施计划（按 §7 数据层 → §8 引擎/runner → §5/§6 管线 → §10 呈现 → §12 测试 的依赖顺序拆分阶段）。
