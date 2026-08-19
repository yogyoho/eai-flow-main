# 给排水计算书技能 —— 7 项反馈建议技术解决方案汇总

- **日期**: 2026-08-19
- **对象**: `skills/public/water-drainage-report/`
- **验证**: 2026-08-19 对话页三轮实跑（线程 `7d58e494`，Agnes-2.5-Flash），报告 `.gstack/qa-reports/qa-report-localhost-2026-2026-08-19.md`
- **总体**: 6 项 PASS，反馈1 PARTIAL；过程中发现并修复 bug-2191（跨线程记忆污染，已加防线）

---

## 总览

| # | 反馈 | 方案核心 | 关键文件 | 验证 |
|---|------|----------|----------|------|
| 1 | 生成耗时 | 计算与生成分离（Approach A）+ 增量重算 | `formula_runner.py` | ⚠️ PARTIAL |
| 2 | 容错渐进 | 参数分层放开：核心硬门槛 / 系数默认值+【待核实】 | `reference_values.json` | ✅ |
| 3 | 过程透明 | READY 标记链 + 流式中间段落 | SKILL.md 执行流程 | ✅ |
| 4 | 结果校验 | 合约化一致性检查 + 多档约束 | `consistency_contracts.json` | ✅ |
| 5 | 多规范 | 两层模型：Tier-1 人工入库驱动 / Tier-2 标注不结论 | `standards_index.json` | ✅ |
| 6 | 局部热更新 | DAG 增量重算 + 受影响章节反查 | `formula_runner.py` / `chapter_planner.py` | ✅ |
| 7 | 跨轮承接 | 会话快照锚点 + 多轮承接铁律 | `snapshot.py` / SKILL.md 铁律 | ✅ |

---

## 反馈1：生成耗时 —— 计算与生成分离（Approach A）

**问题**: 全量生成一份 10 章计算书耗时过长；改一个参数也要整篇重生成。

**方案**: 把"算"与"写"拆成两段管线：

1. **公式引擎先出全部数值**（瞬时）：`formula_runner.py execute` 沿 FormulaGraph DAG 一次算出所有公式值，产出 `formula_state.json` + `traces.json`（每步含代入数值、引用条款、依赖关系）。
2. **报告章节按单元渲染**：章节清单由 `chapter_planner.py` 生成 manifest，数值表章节机械渲染（直接引用 state，零 LLM 重算），叙述章节引用同一份冻结公式快照。
3. **改参只走增量**：`update` → `impacted`（见反馈6），仅重生成受影响章节。

**关键决策**:
- 不承诺 30s——目标定为 ≤3min 量级（30s 不现实，写进方案即假承诺）。
- 公式数值唯一来源 = state/traces JSON，禁止 LLM 在 prose 里自行计算（执行铁律 #1）。

**验证结论（PARTIAL）**:
- 全量轮端到端 2min26s（含 bug-2191 记忆回显损耗 1min16s，净生成 ~1min10s）✅
- 增量轮 turn_duration=320s，**反慢于全量** ❌——增量内容确实更少（只重生成第 5 章），但瓶颈在 LLM 调用链：snapshot save 之后仍发生 3×write_file + 67K-token 最终调用（cache_read=60928 已命中仍慢）。
- **优化方向**（未实施）: 收敛 save→present 之间的多余写文件与最终消息上下文，不在章节量上。

---

## 反馈2：容错渐进 —— 参数分层放开

**问题**: 全参数齐备才肯跑（用户体验差）vs 缺参数就瞎猜（工程风险大），需要渐进容错。

**方案**: 按"谁有权定值"把参数分两层：

| 层 | 参数 | 缺失策略 |
|----|------|----------|
| 核心工艺参数 | Q、Δt、N、构筑物尺寸 | **硬门槛**：`ask_clarification` 一次性追问，绝不取默认值 |
| 系数/经验类 | KZF、有效水深、旁滤比、反洗强度/时长、飘水率 | 读 `reference_values.json` 取**有出处**默认值，标注【待核实】 |

`reference_values.json` 每项含 `default / unit / source（条款号或工程经验）/ applies_when / needs_verification`。执行铁律 #4 同步精确化："禁**无出处**的值"，而不是禁所有默认值。

**用户核实闭环**: 报告中 16 处【待核实】标注保留到终稿，用户核实后可晋升为项目定值。

**验证结论**: Run1 缺 Q/Δt/N → 停下澄清（问题 chips + 结构化表单），未硬跑未幻觉；Run2 扣住全部 6 系数 → 全部取库默认（effective_depth=1.5 修正值、drift_rate=0.001 等）并逐项标【待核实】。

---

## 反馈3：过程透明 —— READY 标记链

**问题**: 生成 2~3 分钟黑盒，用户不知道卡没卡。

**方案**: 每个里程碑工具输出显式成功标记，agent 在流式回复中复述：

```
公式计算成功 → TRACE_READY（轨迹就绪）
一致性校验完成 → CHECK_READY
快照固化 → SNAPSHOT_READY（才允许 present_files）
```

配合步骤器（每次 tool 调用 + token 输入/输出 + 单步耗时）与流式中间段落（"参数汇总"→"公式计算成功"→"继续生成轨迹文件和章节清单"）。

**验证结论**: 三轮运行标记链完整可见；最终消息含完整结果表 + 合规表 + 调整建议 + 文件路径。

---

## 反馈4：结果校验 —— 合约化一致性检查

**问题**: LLM 自查自报"符合规范"不可信。

**方案**: 校验不靠 LLM 判断，靠**机器执行的合约**：

- `consistency_contracts.json` 定义一致性合约（数值间交叉关系）+ 多规范约束 `code_constraint_multi`——同一指标按多本标准多档校验（如 N：GB 50648 ≥3.0 为强制 fail 档、≥5.0 为推荐 warn 档）。
- `formula_runner.py check` 执行合约，产出 `consistency_check.json`（每条：指标/实际值/限值/标准条款/档位/结论）。
- 报告附录与聊天合规表都从该 JSON 原样引用。

**验证结论**: 真实抓错 2 条——容积比 0.045 < 1/3（GB/T 50746 §6.1.9）⚠️；N=4 宜≥5.0 ⚠️ → N 改 5 后自动转 pass。12 个公式结果全部手算核对无误。

---

## 反馈5：多规范 —— 两层模型

**问题**: 不同项目适用规范组合不同；靠 web 搜索查条款号不可靠（跨标准污染、算符翻转，实测 6/6 不可引用）。

**方案**:
- **Tier-1（人工入库）**: `standards_index.json` 维护 `tier1_curated=true` 的循环水主规范清单；步骤1 请用户勾选，选中集写入 `project_snapshot.standards_selected`。入库条款驱动 pass/fail。
- **Tier-2（未入库）**: 校验时标注【需人工对照规范】，**不给结论**。
- **web_search 仅限三类**：地理/气象/标准版本信息，且仅 discovery 不驱动合规判定。

**验证结论**: 报告引用 5 本标准（GB/T 50746-2012×7、GB 50648-2011×3、GB/T 50050-2017×2、GB 50974-2014、GB 50014-2021）；N 双档校验生效；snapshot 记录 3 本主标准。

---

## 反馈6：局部热更新 —— DAG 增量重算

**问题**: "把 N 从 4 改成 5"不应重算/重写整份报告。

**方案**: 依赖图驱动的定点更新：

1. `formula_runner.py update --set N=5` —— 沿 FormulaGraph 只重算 N 的下游链，产出 `value_diffs`（old/new 对照）。
2. `formula_runner.py impacted` —— 给出受影响公式集（如 `Qb,Qm`）。
3. `chapter_planner.py` 用 impacted 集反查**受影响章节**（如第 5 章水量平衡），只重生成它们；未受影响章节原样保留。
4. 报告头部声明本次变更："N 4→5 ⇒ 重生成第 5 章"；聊天以变更对照表呈现（原值/新值/变化%）。

**验证结论**: v2 快照记录 `value_diffs={N:{old:4,new:5}}` + `affected="Qb,Qm"`（恰好是 N 的下游链）；未受影响值原样保留（抽查 Qe=116.88 不变）；只重生成第 5 章。

---

## 反馈7：跨轮承接 —— 会话快照锚点 + 铁律

**问题**: 第 2 轮说"把 Q 改成 25000"，agent 漂移回"重新交付 Q=20000 报告"（bug-1171）——无"当前任务"锚点，被线程首条历史消息 + 累积记忆拉回旧语义。

**方案**（三层）:

1. **快照 CLI** `scripts/snapshot.py`（stdlib-only，8 单测）：
   - `save --task "<本轮一句话>"`：`project_snapshot.json` 读改写，version++、changelog 追加（含 value_diffs/affected）、更新 last_task 防漂移锚点。
   - `show`：进流程第一动作，输出 `SNAPSHOT_VERSION / SNAPSHOT_LAST_TASK / SNAPSHOT_REPORT` 或 `SNAPSHOT_NONE`。
2. **多轮承接铁律**（SKILL.md，与执行铁律同级、先于一切步骤）：
   1. 启动第一件事 = 读快照锚点，绝不被对话历史首条消息主导；
   2. 第 2 轮+ = 增量指令，绝不回退整篇重生成；
   3. 改参必走 update + impacted，禁回落 present 旧报告；
   4. 每轮收尾 snapshot save 且在 present_files **之前**（顺序颠倒 = 本轮未完成——agent 在 present_files 后即视为交付完成不会回头，bug-1171 根因）；
   5. 数值汇报仍守执行铁律 #1；
   6. **⛔ 记忆污染防线（bug-2191，2026-08-19 增）**：本项目参数权威只有两个——**本线程用户消息明确给出的值** + **`project_snapshot.json` 锚点**。系统记忆注入的其他线程/项目参数：不得参与计算或预填确认表；不得标来源"用户提供"；对不上直接忽略按缺失走正常收集（核心缺失→ask_clarification），绝不基于记忆发起参数确认表/澄清表单；唯一例外是用户明确说"沿用上次参数"，且须复述数值逐项确认；记忆值同样不得作为澄清表单的"建议值/参考值"（含"基于同类/历史项目取值"话术）——非库内参数缺失只做两件事：请用户提供，或按分层放开以行业常规值名义给出并标【待核实】。配套：步骤1「来源」列限定三种合法值（`本线程用户提供`/`说明书提取`/`参考值库（【待核实】）`）。
3. **顺序铁律**: 步骤5 固化 ①write_file(报告) → ②snapshot save → ③SNAPSHOT_READY → ④present_files。

**验证结论**: v1→v2 全字段正确（version/last_task/changelog/value_diffs/affected）；顺序铁律两轮事件流实证（`write_file → save → SNAPSHOT_READY → present_files`）；bug-1171 不再复现。bug-2191 防线为 2026-08-19 新增（commit `c16e9bd34`）。

---

## 遗留与后续

| 项 | 状态 | 说明 |
|----|------|------|
| 反馈1 增量轮 wall-clock | 未做 | 增量内容更少但端到端 320s > 全量 146s；优化在收敛 save→present 间多余 write_file 与终调上下文 |
| B-档参考值库扩充 | 未做 | 现库 6 项系数；可按项目类型扩充 |
| 前端 version 角标 | 排除 | 用户范围外 |
| harness Memory 线程级隔离 | 不做 | 涉及 harness 核心（守 no-core-code-changes 约束），技能层铁律 #6 已挡住实际污染路径 |
