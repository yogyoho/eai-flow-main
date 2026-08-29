---
name: water-drainage-report
description: |
  为石化/化工项目生成给排水设计专篇（循环水装置工艺设计计算报告）。触发词："给排水设计专篇"、"循环水装置计算"、"给排水计算书"、"循环水场设计"等。

  公式驱动：设计参数 → 公式DAG计算 → 结果注入章节生成 → 一致性校验 → 合规检查。
  即使有上游设计说明书，也只提取设计参数，不摘抄文本段落。
---

# 给排水设计专篇技能

## 核心原则

1. **公式驱动**: 设计参数 → 公式计算 → 计算结果 → 注入章节生成 prompt。公式是核心环节，不是辅助。
2. **参数一致性**: 前后章数据必须一致。公式输出自动传播到下游公式，参数变更自动触发增量重算。
3. **多轮交互**: 参数确认 → 公式审核 → 章节生成 → 一致性校验 → 合规检查。每步等待用户确认后再进入下一步。
4. **⛔ 禁止无出处的值（最高铁律，贯穿全程）**: 精确化（2026-08-11）——原"禁止任何默认值"改为"禁止无出处的值"。**核心工艺参数**（Q、Δt、N、构筑物尺寸、装置用水量）缺失，仍必须用户提供（`[待用户提供]` + `ask_clarification`，绝不编造）。**系数/经验类参数**（蒸发系数 KZF、有效水深、旁滤比、反洗强度/时长）缺失时，可从 `references/reference_values.json` 取**有出处**的默认值并标注【待核实】，用户核实后晋升为项目定值。三个"绝不"：
   - 绝不联网搜索项目/工程内部数据（设计阶段项目网上不存在，搜了只会引入幻觉）
   - 绝不编造、推断、估算、补全任何具体数值（如消防水量、投资金额、管径、温度）
   - 绝不根据"行业常见值""经验数据"自行填入
   - **唯一正确做法**：缺失信息时标注 `[待用户提供: 信息名]`，并用 `ask_clarification` 向用户追问，等用户提供后才能继续。公式所需的参数缺失时，公式暂不计算，整章对应位置标注 `[待用户提供]`。

## ⛔ 执行铁律（最高优先级，先于一切步骤）

**实证教训（2026-08-12 页面验证）：** agent 即便被明确要求用规范工具，仍倾向"先自写整篇 Python 生成器 + 分块 `write_file` 拼接"，导致耗时从目标 ≤3min 飙到 7min+，还常丢失自身变量结构、需 grep/sed 取证自己的代码。以下铁律杜绝该模式——**违反任一条即视为流程失败**。

1. **公式数值的唯一来源 = `formula_state.json` / `traces.json`。** 严禁在任何自写代码、heredoc、或回复里硬编码或重算公式结果——禁止出现 `R = dict(Qe=292.20, ...)` 这类字面量赋值，也禁止自行 `Qe = Q * KZF * delta_t`。所有 Qe/Qw/Qb/Qm/V_pool/V_system/filter_count 等值，必须来自步骤2 的 `formula_runner.py execute`/`trace` 输出文件，由代码读文件取得。**向用户汇报/总结时原样引用** `consistency_check.json`/`traces.json` 的数值（如容积比直接引 `detail` 字段的 `0.196`），**严禁在 prose 里自行单位换算或重算**——自行换算会引入 `0.196→0.0545` 这类错误（2026-08-12 复验实测：agent 把 V_ratio 多除了 ×3.6，写出错误的 0.0545h）。

2. **必须先 execute，后生成。** 步骤2 的 `formula_runner.py execute` 必须是第一个计算动作并产出 STATE_READY；在它成功之前，**不得写任何报告内容或生成器代码**。execute 失败则按步骤2「失败处理」排查重试，**绝不绕过自算**。

3. **禁止"整篇文档生成器"脚本。** 不得编写一个循环拼装全报告的 `.py`（如 `gen_report.py`）。table 章的逐公式块由 `render_calc_blocks.py inject` 从 `traces.json` 注入（见步骤4，唯一例外：它只渲染公式片段、不拼装全报告；write_file 只放 `<!-- CALC:公式id -->` 占位符，公式块正文严禁手写）；narrative 章走 `task()` 子 agent。报告最终内容由 agent 在上下文内组装，一次 `write_file` 落盘（见步骤5）。渲染需要少量 helper 代码时，必须 `read_file` 读 `formula_state.json`/`traces.json` 取值，不得重算。

4. **禁止分块 `write_file` 拼接。** 全程只允许两类写盘：① 步骤2 的单个 `params.json` heredoc；② 步骤5 的单次报告 `write_file(append=false)`。不得用多次 `append` 拼长脚本或长文档——这会丢自身结构、制造重复段、且每次 append 都是一次工具调用，直接吃掉耗时预算。

5. **耗时自检（反馈1）：** 单轮工具调用累计超 ~90s 仍未拿到 `STATE_READY`/`TRACE_READY` → 已偏离正轨，立即停下、重读步骤2，**勿继续堆砌自写代码**。规范计算本身亚秒级；耗时全在编排，编排必须走规范工具链。

6. **⛔ 同一文件的读/写禁止并行 tool_call（bug-2202）。** 同一回合发出的多条 bash / str_replace 会被**并行执行**：两条 `update` 并行时各自读旧 state 后写回，后完成者覆盖先完成者（2026-08-28 实测：`N=5` 与 `pool_area=2700` 两条 update 并行，pool_area 更新丢失）；`check --params "$(cat params.json)"` 并行跑在 update 落盘前会拿到空参数直接 Traceback；两批 `str_replace` 并行打同一报告文件会 "String not found" 报错 + 重读重试循环（增量轮被拖到 15min+）。规则：**对同一文件的写、或依赖前一条命令落盘结果的读，必须用 `&&` 合并为一条命令，或拆到下一回合串行**；多个参数变更 = 多条 update 以 `&&` 串联，绝不并行发出。

## ⛔ 多轮承接铁律（反馈7，与执行铁律同级，先于一切步骤）

**实证教训（2026-08-13 页面验证）：** 线程 `1366cf6c` 第 2 轮明确要求"把 Q 改成 25000 做 impacted 定点重生成"，agent 读到了基准 state、确认了 CLI 可用，却**漂移回"重新交付 Q=20000 报告"**——根因是 `project_snapshot.json` 从未被写出，无"当前任务"锚点，agent 被线程首条历史消息 + 累积记忆拉回"生成"语义（bug-1171）。以下铁律杜绝该模式——**违反任一条即视为流程失败**。

**实证教训（2026-08-19 对话页验证）：** 全新线程（`7d58e494`）收到系统记忆注入的**另一项目**（吉林经开区，Q=20000/Δt=10/N=5/有效水深2.0超标）历史参数，agent 据此预填"设计参数确认表"并标来源"用户提供"，还引用旧线程对话细节"您提到正在调整容积比至0.4"发起澄清表单（bug-2191）——若用户直接点提交，旧项目参数将污染本项目。→ 铁律 #6。

1. **启动第一件事 = 读快照锚点。** 进流程第一个动作：`bash` 跑 `snapshot.py show`（见步骤0）。拿到 `SNAPSHOT_LAST_TASK` → **这就是当前任务上下文**，理解用户本轮指令一律基于它，**绝不被对话历史首条消息主导**。`SNAPSHOT_NONE` 才按全新运行走步骤1。

2. **第 2 轮+ = 增量指令，绝不回退整篇重生成。** 本会话第 2 轮及以后的任何消息，默认是对当前基准的**增量/修改/追加**指令。**禁止**把"改参/补参数/调章节/追加校验"误读为"重新生成一份完整计算书"。判别：快照存在 + 用户消息含"改成/调整/补/换成/比选/增加/去掉"等变更动词 → 一律走增量路径（改参→步骤2 改参定点；补参数→步骤2 update；追加校验→步骤6/7），**不回步骤1 重新收集参数**。

3. **改参必走 impacted + update，禁回落 present 旧报告。** 用户说改参（"把 Q 改成 25000"/"方案比选"等）→ 必须执行步骤2「改参定点重生成」全流程（`formula_runner.py impacted` **先** → `update` **后** → 仅重生成受影响章节 → 单次 write_file 覆盖 → 步骤5 save）。**绝不**直接 `present_files` 一份未改参的旧报告充数。改参前后关键值对比必须给出（取 `impacted` 的 value_diff）。

4. **每轮收尾必须 `snapshot.py save`，且在 `present_files` 之前。** 首次交付与每一次改参/补参/追加，都必须在步骤5 调 `present_files` **之前**先 `snapshot.py save --task "<本轮一句话>"` 固化当前状态、`version++`、追加 changelog，拿到 `SNAPSHOT_READY` 才能收尾。**顺序颠倒（先 present_files 后 save）= 本轮未完成**，因为 agent 在 `present_files` 后即视为交付完成、不会回头执行 save——下一轮将因无 `last_task` 锚点而漂移（bug-1171 重现）。**⛔ 快照唯一合法产生方式 = `snapshot.py save`（bug-2198）：禁止用 `write_file` 手写/复制/改名生成任何 `project_snapshot*.json` 旁路文件**（如 `project_snapshot_N5.json`——2026-08-20 实跑中 agent 手搓旁路文件致正典锚点停留在 v1，bug-1171 复发）；`--output` 必须是正典 `$WORK/project_snapshot.json`（CLI 会拒绝其他文件名），且 stdout 必须出现 `SNAPSHOT_READY: version=N`（N = 上一版 +1，新线程首轮 =1）——version 没涨 = save 没走到正典上 = 本轮未完成。**⛔ 同样禁止 `python3`/heredoc/`str_replace` 直改正典文件本体**（bug-2198 变体，2026-08-28 线程 e8cf3d2f 实测：agent 手搓 `snap['version']=2` 后 last_task 仍停在 N=5.0、changelog 无 v2 条目、updated_at 未刷新——直改不维护任何锚点字段，锚点即废，bug-1171 复发条件）；增量轮 save 应带 `--diff`/`--affected`（取步骤2 记录的 value_diffs 与 impacted 输出）。

5. **数值汇报仍守执行铁律 #1。** 跨轮承接只承接"任务意图 + 参数基准"，公式数值仍唯一来自 `formula_state.json`/`traces.json`/`consistency_check.json`，原样引用、禁 prose 重算。

6. **⛔ 记忆污染防线（bug-2191）。** 本项目参数权威只有两个：**本线程用户消息明确给出的值** + **`project_snapshot.json` 锚点**。系统记忆可能注入**其他线程/其他项目**的历史参数（项目名、数值均可能不同）。对记忆中的参数：① 不得作为本项目参数参与计算或预填参数确认表；② 不得把来源标为"用户提供"——"用户提供"仅指**本线程**用户消息中明确给出的值，其他线程的"用户提供"对本项目无效；③ 记忆与当前请求对不上（项目名/参数不一致）→ 直接忽略，按参数缺失走步骤1 正常收集（核心参数缺失 → `ask_clarification`），**绝不基于记忆预填参数确认表或发起澄清表单**，更不得引用"您提到过…"等本线程未发生的历史对话细节；④ 唯一例外：用户本轮明确说"沿用上次/记忆中的参数"——此时也必须复述数值请用户逐项确认后才可用；⑤ 记忆值同样**不得作为澄清表单/追问的"建议值/参考值"**（含"基于同类/历史项目取值，因比例相近"等话术）——非库内参数缺失时，只做两件事：请用户提供，或按步骤1「分层放开」以行业常规值名义给出并标注【待核实】；绝不以其他项目的记忆数据充当建议值；⑥ **记忆不得引导文件读取（2026-08-20 增）**：不读取记忆/跨项目上下文提到的任何文件路径（"历史报告""上次的计算书"等）——本项目文件只认本线程 `/mnt/user-data/**` 与快照锚点 `report_path` 记录的路径，其他路径一律不存在、不尝试打开；⑦ **`present_files` 即本轮终点（2026-08-20 增）**：交付后**不得**再发起任何澄清/确认表单或追问——尤其禁止"要生成哪个项目的计算文档？"类问题，表单/追问选项**绝不含记忆中其他项目**（如其他线程的 Q=20000/Q=15000 项目）。交付完成就结束，等用户下一轮指令。

## 工具范围

本技能**仅用**以下工具：`read_file` / `bash` / `write_file` / `present_files` / `knowledge-factory_kf_resolve_template` / `ask_clarification` / `web_search`（仅限下述三类查询）。

**禁止**调用 `text-to-cad_*` / `cad_*` / `word-document-server_*` 等无关工具。

**配套脚本与数据（通过 bash/read_file 使用）：**
- `scripts/formula_runner.py` — 公式计算 CLI（execute / update / check / **trace** / **impacted**）
- `scripts/chapter_planner.py` — 章节规划（manifest 生成 / 受影响章节反查）
- `scripts/snapshot.py` — 会话快照 CLI（**save** / **show**，反馈7 跨轮承接 + 版本历史）
- `references/reference_values.json` — 系数/经验类行业参考值库（反馈2，缺失时取默认+【待核实】）
- `references/standards_index.json` — 可勾选规范清单（反馈5）
- `references/consistency_contracts.json` — 一致性 + 多规范围框合约（含 `code_constraint_multi`）

### ⛔ 联网搜索规则（重要）

**项目处于设计阶段，项目相关信息网上根本不存在，搜索纯属浪费且会引入幻觉。**

**禁止联网搜索的内容**（项目信息——必须由用户提供或从上传的设计说明书中提取）：
- ❌ 项目名称、建设单位、设计单位、投资金额、建设规模、产能
- ❌ 具体装置/设备清单（如"乙烷""丙烯腈""ABS装置"等工艺装置参数）
- ❌ 项目所在地以外的工程数据、工艺流程、物料平衡
- ❌ 用户已在对话中提供或可从上传文档提取的任何信息

缺失上述信息时，用 `ask_clarification` 向用户追问，**绝不联网搜索**。

**允许联网搜索的内容**（仅三类辅助信息）：
- ✅ **地理信息**：项目所在城市/区域的经纬度、周边环境（如"吉林市 龙潭区 地理位置"）
- ✅ **气象信息**：项目所在地的气象参数（如"吉林市 年平均气温 降水量 风速 气压"）——用于报告第4节（设计参数）
- ✅ **标准规范**：GB/HG 标准的具体条款、版本、适用范围（如"GB/T 50746-2012 浓缩倍数 条款"）

判断标准：**能查到的客观地理/气候/法规信息 → 可搜；属于某个具体工程项目的内部数据 → 绝不搜，问用户。**

## 执行流程

### 步骤0：会话快照恢复（反馈7 跨轮承接）

**进流程第一动作（多轮承接铁律 #1）——读快照锚点：**
```bash
python /mnt/skills/public/water-drainage-report/scripts/snapshot.py show \
  --input /mnt/user-data/workspace/project_snapshot.json
# → SNAPSHOT_VERSION / SNAPSHOT_LAST_TASK / SNAPSHOT_LAST_CHANGE / SNAPSHOT_REPORT
# 或 SNAPSHOT_NONE（无快照，全新运行）
# ⛔ --input 必须显式写：默认路径在脚本源码里，不出现在命令文本中就不会被沙箱
#    路径翻译层替换，裸调用必然误报 SNAPSHOT_NONE（2026-08-20 线程 9509c508 实证）
```

- **`SNAPSHOT_LAST_TASK` 存在** → **这就是当前任务上下文**（防漂移锚点）。向用户展示「当前基准状态」（v{version} + 最近一次变更 + report_path），后续指令默认基于该基准增量理解，**不重复追问全局参数、绝不被对话历史首条消息主导**。直接跳到用户本轮指令对应的步骤（改参→步骤2 改参定点；补参数→步骤2 update；追加校验→步骤6/7）。
- **`SNAPSHOT_NONE` 或损坏** → 降级为全新运行（脚本已 try/except，不崩），从步骤1 开始。

快照字段（由 `snapshot.py save` 在每轮收尾维护，`version++` + `changelog` 追加）：
```
{"version", "last_task"(⬅ 防漂移锚点), "created_at", "updated_at",
 "params", "formula_state_path", "chapter_manifest_path",
 "standards_selected", "report_path",
 "changelog": [{"version","task","timestamp","value_diffs","affected","note"}]}
```

**版本历史** = `version` 序列 + `changelog`；前端展示复用文档空间，不新建。

### 步骤1：收集设计参数

**输入:** 用户请求 + 可能上传的说明书 (.docx/.pdf)
**工具:** `read_file`（读上传文件）、`ask_clarification`（追问缺失参数）
**输出:** 完整的参数表（用户确认后）

**若用户上传了设计说明书(.docx/.pdf)：**
系统配置 `uploads.auto_convert_documents=true`，上传的 docx/pdf 会自动在 `uploads/` 下生成同名 `.md` 文件。用 `read_file /mnt/user-data/uploads/<文档名>.md` 读取并提取以下参数：
- Q: 循环水设计水量 (m³/h) — 从水量统计表中取合计值
- Δt: 冷却塔进出水温差 (℃) — 从设计参数章节取
- N: 浓缩倍数 — 从设计参数章节取（宜≥5.0，且不应低于3.0）
- 气象条件: 干球温度、湿球温度、大气压力
- 各装置用水量: 从水量统计表逐行提取

**若用户未上传说明书：** 用 `ask_clarification` 一次性追问所有缺失参数。"已提供"仅指**本线程**用户消息/上传文件/快照锚点中出现——系统记忆注入的跨线程参数**视为缺失**，不算已收集（多轮承接铁律 #6）。

**⛔ 用户确认门禁 — 在用户确认前禁止进入步骤2：**

步骤1收集到的参数必须向用户展示并等待确认。展示格式如下：

```
已收集以下设计参数：

| 参数 | 符号 | 值 | 单位 | 来源 |
|------|------|-----|------|------|
| 循环水设计水量 | Q | {值} | m³/h | {说明书/用户提供} |
| 进出水温差 | Δt | {值} | ℃ | {来源} |
| 浓缩倍数 | N | {值} | — | {来源} |
| 干球温度 | θ | {值} | ℃ | {来源} |
| ... | | | | |

公式计算将使用以上参数。请确认是否正确。如需修改请说明，确认后开始计算。
```

只有在用户回复"确认"/"没问题"/"开始"或等价肯定答复后，才能进入步骤2。

**「来源」列仅限四种合法值：** `本线程用户提供`、`说明书提取`、`参考值库（【待核实】）`、`厂家返资资料`。系统记忆注入的跨线程参数不属于任何一种——**不得填入本表、不得标"用户提供"、不得据此发起参数确认或澄清表单**（多轮承接铁律 #6，bug-2191）。

**分装置水量统计（样例 3.1 工艺装置循环水量表 定式）：** Q 的来源要落成「循环水水量统计表」——7 列（序号/用水单位/生产连续用水量 正常、最大 m³/h/进界区压力 MPa/出界区压力 MPa/温度 ℃），逐行列各装置水量、合计行=Q；统计表后紧跟两条定水量依据句（HG/T 20690-2000 3.1.2、GB/T 50746-2012 3.2.2）。用户给不出分项明细时允许只报 Q 总量，但第3节（设计规模）标注 `[待补充: 用水单位明细]`。

**气象参数（样例第4节"设计参数"五行，KZF 内插的输入）：** 干球温度 θ、湿球温度 τ、相对湿度 φ、大气压、风速必须入参数表——缺气象参数则 KZF 取值无法按 GB/T 50746-2012 表3.3.3 内插溯源。缺失按核心工艺参数同策略 `ask_clarification`。

**双工况对比（样例定式，可选）：** 默认按 N=5（主工况）计算；用户要求校核时加算 N=3 工况——用独立状态文件，禁止污染主工况 state：
```bash
python $SCRIPTS/formula_runner.py execute --formulas $FORMULAS \
  --params "$(cat $WORK/params.json | python -c "import json,sys; p=json.load(sys.stdin); p['N']=3; print(json.dumps(p))")" \
  --output $WORK/formula_state_N3.json   # STATE_READY
```
报告配管节并排双工况（样例：补充水 366 m³/h→1.39 m/s 与 439 m³/h→1.66 m/s（N=3）），管径按包络选取；校核值不回写主工况结论。

**设备选型规格叙述契约（并入计算节，样例不单设设备表章）：** 各计算节内的设备选型叙述必须回填可计算结果（DN/单罐水量/台数/组数等，取自 traces.json 公式输出，样例"DN1500吸水喇叭口 D=1200/D1=1620/H=1150"形态），**禁止写"待定"**；设备选型来源合法值含 `厂家返资资料`（样例：单罐 40m³/h、每5罐1组共5组即出自厂家返资）。落点：滤网/起吊设备规格写 7.2.4（滤网起吊设备），泵/喇叭口/起重机规格写 8.2.1（循环水泵），旁滤罐组写第9节。

**⛔ 参数缺失策略：** 参数必须在用户提供或设计说明书中明确标出，两者都没有 → 标注 `[待确认: 参数名]` → 暂不进入步骤2，等用户补充。

**分层放开（反馈2）：** 系数/经验类参数缺失时，读 `references/reference_values.json`：命中 → 填入默认值并在参数表「来源」列标 `参考值库（【待核实】）`；未命中 → `ask_clarification`。核心工艺参数缺失一律 `ask_clarification`，**绝不**从参考值库取。

**规范勾选（反馈5）：** 步骤1 同时请用户从 `references/standards_index.json` 勾选本项目适用的规范（默认勾选 3 本 tier1_curated=true 的循环水规范）。选中集写入 `project_snapshot.standards_selected`。

### 步骤2：运行公式计算

**输入:** 步骤1确认的参数表
**工具:** `bash` + `formula_runner.py`
**输出:** 公式计算结果（STATE_READY）+ 公式状态文件

```bash
FORMULAS=/mnt/skills/public/water-drainage-report/references/formulas.json
SCRIPTS=/mnt/skills/public/water-drainage-report/scripts
WORK=/mnt/user-data/workspace

# 构建参数JSON（只填步骤1确认的核心参数；流速/DN/滤网规格/泵房高度分量等选型参数
# formulas.json 已带默认值——可不填，缺省自动生效并在计算块标【待核实】；
# total_filters 已改为公式输出（=filter_count），禁止手工填入）
cat > $WORK/params.json << 'PARAMS'
{"Q": 20000, "delta_t": 10, "N": 5, "pool_area": 912, "V_suction": 2099.5, "pump_motor_spacing": 5.2, "filter_unit_capacity": 40, "filter_area": 1.13, "concurrent_backwash": 5}
PARAMS

python /mnt/skills/public/water-drainage-report/scripts/formula_runner.py execute \
  --formulas $FORMULAS \
  --params "$(cat $WORK/params.json)" \
  --output $WORK/formula_state.json
```

**⛔ params.json 文件必须真实落盘（bug-2203）：** execute 必须如上引用 `cat $WORK/params.json`，**禁止把参数 JSON 内联进命令行绕过文件**——步骤2 的 check 与步骤5 的 `snapshot.py save --params` 都依赖该文件存在（2026-08-28 实测内联绕过 → 快照 params={} 静默降级 + 增量轮 check 首跑即 Traceback 重试）。

**生成步骤轨迹 + 章节清单（供后续折叠渲染与定点重生成）：**
```bash
python $SCRIPTS/formula_runner.py trace \
  --formulas $FORMULAS --state $WORK/formula_state.json \
  --output $WORK/traces.json   # TRACE_READY
python $SCRIPTS/chapter_planner.py manifest \
  --formulas $FORMULAS --output $WORK/chapter_manifest.json   # MANIFEST_READY
```
`traces.json` 含每公式的 `substituted`/`result`/`inputs.source`/`needs_verification`（反馈3 折叠块的数据源）。

**失败处理：** 如果 `formula_runner.py` 报错 → 检查 `params.json` 格式和 `formulas.json` 路径 → 修正后重试 1 次 → 仍失败则输出错误日志并告知用户具体错误原因。

**展示计算结果摘要，格式如下（公式使用 LaTeX 数学格式，前端 KaTeX 渲染）：**

```
公式计算完成。46个公式，5个执行批次。

水量平衡链:
  [6.1.1] 蒸发水量 $$Q_e = Q \times K_{ZF} \times \Delta t = 20000 \times 0.001461 \times 10 = 292.20\ \text{m}^3/\text{h}$$
  [6.1.2] 风吹损失 $$Q_w = Q \times 0.1\% = 20.00\ \text{m}^3/\text{h}$$
  [6.1.3] 排污水量 $$Q_b = \frac{Q_e}{N-1} = \frac{292.20}{5-1} = 73.05\ \text{m}^3/\text{h}$$
  [6.1.4] 补充水量 $$Q_m = Q_e + Q_w + Q_b = 292.20 + 20.00 + 73.05 = 385.25\ \text{m}^3/\text{h}$$

水池容积:
  [7.1.1] 有效容积 $V_{pool} = 1824\ \text{m}^3$, 系统总容积 $V_{system} = 3923.5\ \text{m}^3$
  容积比 $\frac{V_{system}}{Q} = 0.196$ (⚠ 低于 GB/T 50746 要求 1/3~1/2)

泵房+旁滤:
  [8.2.1] 基础尺寸 $L = 5.7\ \text{m}$
  [9.1.1] 旁滤水量 $Q_{sf} = 1000\ \text{m}^3/\text{h}$, 过滤器 $n = 25$ 台

执行批次（以 execute 输出的 execution_order 为准，v3 共5批46式）:
  批0: Q_connect,Qe,Qsf,Qw,V_pool,backwash_flow,backwash_single_volume,bell_mouth_ratio,bell_mouth_velocity,lift_rope_len,pipe_v_outlet,pipe_v_suction,pump_foundation_B,pump_foundation_L,pump_min_spacing,screen_drag,screen_lift_height
  批1: Qb,V_system,filter_count,pipe_v_connect,pipe_v_sidefilter,pumphouse_h1,screen_area,screen_lift_weight,screen_velocity_actual
  批2: Qm,V_ratio_check,backwash_volume,pipe_d_blowdown,pipe_v_blowdown,pumphouse_height
  批3: backwash_daily_volume,backwash_pool_volume,pipe_d_makeup,pipe_v_makeup
  批4: backwash_pump_flow
```

**⛔ 公式审核门禁 — 在用户确认前禁止进入步骤3：**

展示计算结果后，等待用户审核。用户可：
- 要求修改参数："Q改成25000" → 重新运行 update 命令
- 确认无误："没问题，继续"、"确认" → 进入步骤3

**参数修改（增量重算）：**
```bash
python /mnt/skills/public/water-drainage-report/scripts/formula_runner.py update \
  --formulas $FORMULAS \
  --state $WORK/formula_state.json \
  --param <参数名> --value <新值> \
  --output $WORK/formula_state.json
```

修改后重新展示变更摘要："Q 20000→25000, Qe: 292.2→365.2, Qm: 385.3→481.6, filter_count: 25→32"。再次等待用户确认。

**改参定点重生成（反馈6，替代整篇重跑）：**
```bash
# 0. 刷新章节映射（bug-2199：manifest 必须含 ch10_compliance 合规附录章——它由 check 结果渲染，永远随改参受影响）
python $SCRIPTS/chapter_planner.py manifest --formulas $FORMULAS --output $WORK/chapter_manifest.json
# 1. 查受影响章节（⛔ 必须先于 #2 的 update：impacted 对磁盘上的旧状态 dry-run 改参做
#    值差分——若 update 已把新值落盘，差分为空 → affected_formulas/chapters 全空，
#    受影响章节反查失效（2026-08-20 线程 9509c508 实证）。
#    ch10_compliance 必在结果中——附录整表依赖全量公式）
python $SCRIPTS/formula_runner.py impacted --formulas $FORMULAS --state $WORK/formula_state.json \
  --param <参数名> --value <新值> --manifest $WORK/chapter_manifest.json   # IMPACTED_READY
# 2. 增量重算落盘（--params-output 同步刷新 params.json，供第 3 步 check 用）
python $SCRIPTS/formula_runner.py update --formulas $FORMULAS --state $WORK/formula_state.json \
  --param <参数名> --value <新值> --output $WORK/formula_state.json \
  --params-output $WORK/params.json   # STATE_READY + PARAMS_READY
# 3. ⛔ 重跑一致性校验（bug-2199：合规附录的数据源，禁止沿用改参前的旧 check 结果——
#    否则交付"参数表 N=5 / 合规表 N=4"并存的自相矛盾报告）
python $SCRIPTS/formula_runner.py check \
  --formulas $FORMULAS \
  --params "$(cat $WORK/params.json)" \
  --output $WORK/consistency_check.json   # CHECK_READY
# 4. 仅重生成受影响章节（含 ch10 合规附录+调整建议区，数值取新 consistency_check.json；table 重渲染 / narrative 子 agent 重生成），
#    其余章节原样保留 → 内存内整体覆盖 → 单次 write_file（步骤5）
# 5. 记录本轮 value_diffs（{参数:{old,new}}）+ affected_formulas/chapters（取自上面 impacted 输出），
#    供步骤5 末尾的 snapshot.py save --diff/--affected 固化（不在本步 save；每轮收尾只在步骤5 save 一次）
```
不做像素级差异高亮 UI（顶回去）；「差异」以变更日志文本落地，复用文档空间版本能力。

### 步骤3：获取报告模板

**输入:** 步骤2确认的公式计算结果
**工具:** `knowledge-factory_kf_resolve_template`
**输出:** 模板元数据（generation_hint, compliance_rules, content_contract）或 fallback 标记

调用 `knowledge-factory_kf_resolve_template`：

```
knowledge-factory_kf_resolve_template(
    domain_keywords=["给排水设计专篇", "循环水装置计算", "给排水计算书"],
    industry="化工",
    min_completeness_score=60
)
```

**⛔ 报告体例契约（严格对齐吉林院样例，2026-08-29 定案，优先于一切模板）：**
- **标题体例 = 数字+空格+标题**：一级节 `## 1 设计依据`，子节 `### 6.1.1 蒸发水量`。**禁止"第X章/第一章"式标题**。
- **formulas.json 的 section 编号即报告编号**：公式 section `6.1.1` → 报告 `6.1.1` 节，`chapter_manifest.json` 的章节号与公式 section 天然一致，不要重排错位。
- **不设设备一览表、图纸清单章**：设备选型规格叙述并入 7.2.4（滤网起吊设备）/8.2.1（循环水泵）与第9节正文（样例即此体例）。
- **知识工厂模板不决定结构与编号**：拿到 `found=true` 时，模板**只提供**各节 `generation_hint` / `compliance_rules` / `content_contract` / `example_snippet` 写作约束；章节结构与标题编号一律按下方体例结构执行（避免模板结构覆盖样例体例）。

**拿到 `found=true` 时：**
- 每个章节独立拥有 `generation_hint`、`compliance_rules`、`content_contract`、`example_snippet`——按体例契约映射到对应编号节
- 输出提示：`✅ 已从知识工厂获取模板：{name} v{version}（完整度: {completeness_score}/100）`

**拿到 `found=false` 时：**
- 输出提示：`⚠️ 知识工厂返回 found=false，使用内置参考结构`
- 结构仍按下方体例结构执行
- 使用全局 GB 标准列表替代逐节 compliance_rules

**fallback 章节结构（样例 9 节 + 合规附录，标题=数字+空格+标题）：**
1. 设计依据 ← **只写**设计委托书/工程统一规定（样例第1节仅此2项，标准不得混入）
2. 设计范围
3. 设计规模 ← 工艺装置循环水量统计表（7列，合计行=Q）+ 两条定水量依据句（样例 3.1 定式）
4. 设计参数 ← 气象5参数 + 核心工艺参数表（样例第4节定式）
5. 设计中采用的主要标准及规范 ← 两列表逐项列规范号+名称（样例12项：GB50013/GB50014/GB50050/GB50648/GB50016/GB50160/GB50265/GB/T50102/GB/T50746/HG/T20690/HG/T20524/SH3099），标准依据只此一节
6. 循环水装置工艺计算 ← 公式计算结果注入此节（6.1.1 蒸发水量 ~ 6.1.4 补充水量、6.1.5 配管设计）
7. 塔底水池、吸水池、滤网及滤网井（7.1.1 塔底水池 / 7.1.2 管线 / 7.2 滤网与滤网井 / 7.2.4 滤网起吊设备）
8. 吸水池及循环水泵房工艺计算（8.1.1 规范要求 / 8.1.2 本项目设计 / 8.2.1 循环水泵 / 8.2 泵房高度）
9. 旁滤设备
- 合规校验结果与调整建议（附录，**不编号**）

### 步骤4：生成报告（章节并行，冻结快照驱动）

**输入:** 步骤1 参数 + 步骤2 公式结果 + 步骤2 的 `traces.json`（冻结快照）+ 步骤3 模板
**架构（计算与生成分离，Approach A）:**
- **table 章**（参数表/工艺计算表/设备表）= 纯公式输出 + `traces.json` 机械渲染，**不走 LLM**：最快、最准、天然带步骤轨迹。计算过程块必须脚本注入不得手写（历史：R4/R5/R6 三轮实测 agent 手写从不产 `<details>` 折叠；R6 即便生成了片段也不逐字粘贴——6K 字符复制对 LLM 不可靠；**R8 实测 agent 把 12 块全文手写进 write_file 并跳过 inject**，故 2026-08-29 起由快照门禁强制）：
  1. `write_file` 报告时，计算节**每个公式的小节**（标题编号 = 公式 section 编号，体例对齐后天然一致，如 `#### 6.1.1 蒸发水量`）标题下写**该公式的占位符** `<!-- CALC:公式id -->`（id 取自 `traces.json`，每个公式**恰好一个**）——write_file 的 content 里**严禁出现** `<details>` 或 `$$`（手写块与注入块叠加会重复，且快照门禁必打回）。注入块**不带标题**——小节标题由你的 TOC 承担，禁止写 `### [6.1.1]` 之类公式登记表编号标题（与报告 TOC 双编号，2026-08-29 用户定案去除）。（旧式单一占位符 `<!-- CALC_BLOCKS -->` 仍兼容——全部块顺序堆到一处，不推荐）；
  2. 落盘后立刻注入：`python $SCRIPTS/render_calc_blocks.py inject --traces $WORK/traces.json --report $OUT/报告.md   # CALC_INJECT_READY`（对已注入报告重跑返回 `CALC_INJECT_SKIP`，幂等不重复注入；未知 id / 公式缺占位符 / 重复占位符 → `CALC_INJECT_ERROR` 打回，修正报告后重注）
  3. 注入后自检：`grep -c '<details>' 报告.md` 必须**恰好等于公式数**（traces.json 公式总数，v3 为 46）——大于也是违约（多出的必是手写块）。
  ⛔ 禁止手写 KaTeX 公式块/计算过程折叠块替代脚本注入——**全文任何位置**（含 narrative 章的水池/泵房/旁滤小节）都不许写 `<details>` 或 `$$` 公式块；narrative 章引用数值用纯文本并标注"计算见第X章"。**快照门禁（R8+R9）**：`snapshot.py save --report ...` 校验报告——① 含未注入占位符；② 含无签名手写 `<details>`；③ `<details>` 总数 ≠ 注入签名块数（R9 实测：注入 12 块后又在第6-8章手写 8 块、其中 V_ratio 单位抄错成"0.202 h"）→ 一律 `SNAPSHOT_ERROR` 退出 1。打回后必须删除全部手写折叠块（保留唯一占位符注入产物）再 save。
- **narrative 章** = 并行子 agent 生成（`task()` 工具）。每个子 agent prompt 注入**同一份冻结快照**（`traces.json` 的数值 + 该章 `generation_hint`/`content_contract`/`compliance_rules`），只返回该章 Markdown。按 `chapter_manifest` 顺序合并。

**核心不变量：** 所有数值在步骤2 固化进 `traces.json`；所有生成单元只读该快照——并行不引入跨章数值漂移。

**提速预算：** 9 节（+合规附录）典型报告 = ~3 table 节瞬时 + ~6 narrative 节分批并行（子 agent 池 3 并发）→ 目标 ≤3min。

**⛔ 禁止生成目录：** 报告中**不要包含目录页（TOC）**。原因：Markdown 里手写的目录在导出 Word 后既不能自动更新页码、也不能联动跳转，反而是死文本占篇幅。Word 的目录应在文档空间排版阶段由 Word 的"引用→目录"功能自动生成（基于标题样式）。本技能只生成正文（封面 + 各章正文 + 附录），目录交给 Word。

**每节生成时注入公式结果：**

| 章节 | 注入的公式结果 |
|------|-------------|
| 第3节 设计规模 | 分装置水量统计表（7列，合计行=Q）+ 定水量依据句 |
| 第4节 设计参数 | 全部用户输入参数（Q, Δt, N, 气象5参数） |
| 第6节 工艺计算 | Qe/Qw/Qb/Qm 水量平衡链 + 补充水/排污水管选径与流速校核（pipe_d_makeup/pipe_v_makeup/pipe_d_blowdown/pipe_v_blowdown，含水力坡降叙述） |
| 第7节 水池·滤网 | V_pool/V_system/V_ratio_check（含规范校核）；连通管 Q_connect/pipe_v_connect；放空管 pipe_v_drain；滤网族 screen_area/screen_velocity_actual/screen_drag/screen_lift_weight/screen_lift_height + 滤网/起吊设备规格叙述（禁"待定"） |
| 第8节 泵房 | pump_foundation_L/pump_foundation_B/pump_min_spacing；吸出水管 pipe_v_suction/pipe_v_outlet + 坡降 pipe_i_suction/pipe_i_outlet（配 pipe_compare 比选表）；吸水池容积 V_suction_pool；喇叭口 bell_mouth_velocity/bell_mouth_ratio + 安装几何 bell_clearance/bell_submerge/bell_rear_wall/bell_side_wall（§5.4.3 ②~⑥ 逐项在规范要求小节引出）；起重机选型（查表契约）+ 泵/喇叭口规格叙述（禁"待定"）；泵房高度 lift_rope_len/pumphouse_h1/pumphouse_height |
| 第9节 旁滤 | Qsf/filter_count/pipe_v_sidefilter + 坡降 pipe_i_sidefilter（旁滤水管比选表）+ 悬浮物≤20→≤5mg/L/浅层砂叙述 + 反洗链 backwash_flow/backwash_single_volume/backwash_volume/backwash_daily_volume/backwash_pool_volume/backwash_pump_flow |

**多泵组口径（样例 8.2 定式）：** 样例含泵A（7000×3台，基础5700x2150、吸水DN1200、喇叭口D1=1620）与泵B（3000×2台，基础5000x1850、吸水DN900、喇叭口D1=1220）两型。公式库以**主泵组**（水量最大的泵A）为单值式载体；第二泵组的比选表/流速/喇叭口用 `pipe_compare` 与 02S403 选型值成表叙述（"b）循环水泵B…基础尺寸：5000x1850"形态），不重复建式。

**使用模板时，每章按以下元数据约束生成：**

| 元数据字段 | 作用 |
|-----------|------|
| `generation_hint` | 该章的 LLM 生成提示词 |
| `content_contract.key_elements` | 必须覆盖的要素清单，逐项检查 |
| `content_contract.min_word_count` | 字数下限约束 |
| `content_contract.forbidden_phrases` | 禁止出现的用语（如"大约""可能""暂定"） |
| `content_contract.structure_type` | 输出格式：`narrative_text` / `table` / `mixed` |
| `compliance_rules` | 该章必须遵循的具体 GB/HG 规范条款 |
| `example_snippet` | 样例内容片段 |

**⛔ 信息缺失策略（防止编造）：**

对于 `content_contract.key_elements` 中的每个要素：
- 有信息来源（用户参数、公式结果、规范条款）→ 准确写入
- 无信息来源 → 标注 `[待补充: 要素名]`
- `min_word_count` **不适用于无信息可写的章节**——宁可字数不足，不可编造填充
- `forbidden_phrases` 中的词（"大约""可能""暂定"）表明值不确定，应改为 `[待确认]` 标注

**公式计算步骤展示格式（LaTeX 数学渲染）：**

公式章节（第6/7/8/9节）中，每个公式使用 LaTeX 数学格式呈现。前端已集成 KaTeX（`remark-math` + `rehype-katex`）：

- **行内公式**：使用 `$...$` 包裹，如 `$Q = 20000\ \text{m}^3/\text{h}$`
- **块级公式（独占一行）**：使用 `$$...$$` 包裹，如：
  ```
  $$Q_e = Q \times K_{ZF} \times \Delta t$$
  ```
- **带代入数值的完整步骤**（推荐用于关键公式）：
  ```
  $$Q_e = Q \times K_{ZF} \times \Delta t = 20000 \times 0.001461 \times 10 = 292.20\ \text{m}^3/\text{h}$$
  ```

**计算章逐公式块的目标形态**（由 `render_calc_blocks.py inject` 注入：`$$公式+结果$$` 正文可见、计算过程折叠；**块不带标题**——小节标题是你的报告 TOC，2026-08-29 用户定案 A）：

```
#### 9.1.1 旁滤处理水量        ← 你写的小节标题（编号跟随报告 TOC）
<!-- CALC:Qsf -->              ← 你写的占位符（id 取自 traces.json）

（inject 后占位符处变为：）
$$Q_{sf} = Q \times sf_{ratio} = 20000 \times 0.05 = 1000\ \text{m}^3/\text{h}$$

<details><summary>计算过程</summary>

- 公式：$Q_{sf} = Q \times sf_{ratio}$
- 取值：Q = 20000 m³/h；旁滤比 sf_ratio = 5%【待核实】
- 代入：$20000 \times 0.05$
- 结果：**1000 m³/h**

</details>
```

取值行的【待核实】来自 `traces.json` 的 `needs_verification`（参考值库参数）。计算章手写的叙述、⚠️ 合规提示照常写在公式块之间；逐公式块本身交给脚本，禁止手写。

**⛔ 写作契约（样例定式，narrative 章逐小节强制）：** 每个计算小节按「引条款 → 计算 → 收口」三段式——
1. **先引条款号+限值原文**：`根据《石油化工循环水场设计规范》GB/T 50746-2012 第3.3.3条：<限值原文>`。条款号与限值只准取自注入块的「依据」行与 `standards_index.json` 入库原文，**禁止凭记忆编条号**（样例 16 处"根据"句中 13+ 处为此形态）；
2. **计算**交给占位符注入块（禁手写 $$）；
3. **"本项目按X设计"一句收口**：如"本项目浓缩倍数按5设计"、"过水断面流速按1.0m/s设计"、"本项目根据统一规定取5%"（样例"本项目"14 处）；
4. **标高/高度/起升类结果必须跟设计取整收口**（样例定式："H=5.21m 梁底标高按5.50m计"、"起升高度按6m设计"、"泵房吊车工字钢顶标高按6.0m设计…起升高度按10.00m设计"、"连通管管顶标高按-0.90设计，则管底标高-2.30"）——计算原值之后，凡用于施工设计的标高、梁底、起升高度、池顶高度，按 0.5m（或工程档位）向上取整并写"按X计/按X设计"。

规范要求密集的节（水池/滤网/吸水池）再加 `#### 规范要求` 小节逐条引用原文（样例 7.1.1 引 GB/T 50746-2012 4.3.13 逐条 (1)~(7) 形态），随后 `#### 本项目设计`（或直接接计算）。

**样例正文中数值叙述的锚点形态（叙述须与注入块数值一致）：**
- 管径+流速成对出现："补充水水量366m³/h，管径DN300，流速1.39m/s"（配管表带水力坡降 i 列：7000|DN1200|1.72|0.0025）
- **配管比选表必须用 `formula_runner.py pipe_compare` 生成**（禁手算）：`pipe_compare --q 7000 --dns 900,1000,1200 --mode suction` → JSON（DN/v/i/verdict），渲染为样例式候选表（|输送水量|管径|流速(m/s)|i|），吸水管 `--mode suction`、出水管 `--mode outlet`（GB 50013 分档自动判定），旁滤/连通管用 `--min-v/--max-v` 显式给区间；选定行在叙述中收口（"单个吸水管选用DN1200、DN900管，满足要求"）
- 连通管条数口径：`n_connect` 按**全部塔组的过水管道总数**计（样例：每组塔2条×2组=4条，单条流量=总流量/4，DN1400 时 v=0.90 满足 0.8~1.0）；只按单组2条会得 v=1.80 触发流速偏高警告
- 图集引用落地到具体规格："查阅标准图90S503，格栅净重为G1=705.9kg"、"参考《钢制管件》02S403，DN1500吸水喇叭口（D=1200/D1=1620/H=1150）"
- 瞬时流量双单位："84.75L/s=305.1m³/h"（注入块结果行已自动带换算，叙述沿用同值）
- 旁滤设备选型叙述（样例定式）：旁滤水量之后必须写进/出水悬浮物浓度与设备型式——"进水悬浮物浓度：≤20mg/L；出水悬浮物浓度：≤5mg/L；旁滤设备选择浅层砂过滤器"，再接厂家返资分组叙述（"每5个罐为1组，共设5组"）
- 滤网选型细节（样例定式）：选型先给规格再给有效面积——"参考90S503，选择2200x2000滤网，其中过水面积为1900x2000，格网有效过水面积Fw=1.75，设3道"；吸水喇叭口同理附 02S403 选型三件套（D=1200/D1=1620/H=1150）
- 起重机选型（样例 8.2.1 定式）：泵房高度计算前先选起重机——最重部件（如"循环水泵6.5t"）向上取标准吨位档（1/2/3/5/10/16/20t）写"起重量按10t设计"，并给跨度（"跨度13.50m"）与电动单梁/桥式型式；档位查找是查表不是计算，禁止跳过

**插图契约（样例三处设备示意图，参数驱动生成，禁 LLM 文生图/禁外链图片/禁自造文件名）：** 样例在 7.2.3 滤网起吊设备节末、8.2.1 喇叭口 02S403 选型文字下、8.2.3 泵房高度计算处各有一张示意图。落图流程：
1. 交付前（present_files 之前、写报告 md 的同一轮）运行：`python render_diagrams.py --state <formula_state.json> --outdir <outputs>/images`（state=本轮冻结公式快照；图上标注数值自动取自 state，本脚本不做任何计算）。
2. 输出含 `DIAGRAMS_READY: 3` → 把 `DIAGRAM_FILE:` 行给出的引用**独立成行**写进对应章节（文件名逐字复制脚本输出，禁止手改）：
   - 7.2.3 节末：`![滤网起吊示意图](images/08bb824f44bb.png)`
   - 8.2.1 喇叭口选型段后：`![吸水喇叭口安装示意图](images/35115cff8642.png)`
   - 8.2.3 泵房高度计算后：`![泵房剖面示意图](images/b1cfb1ccb5a3.png)`
3. 出现 `DIAGRAM_SKIP` 或 `FONT_MISSING` → 该图不写图片行，改写占位标记一行（数值取 traces 实际值），留给 Word 阶段人工贴图：
   `【插图待人工补充：滤网起吊示意图——请按 H=5.21m（a=0.86+b=0.45+c=2.20+d=1.00+e=0.70）贴标准图或剖面简图】`
4. 图片行必须独占一行（Word 导出仅解析整行 `![alt](url)` 形态，行内混排不识别）；图片文件在 threads 的 outputs/images/ 下随文档空间同步，导出 Word 时由服务端按相对引用嵌图。

**LaTeX 数学格式规范：**
- 变量使用下标：`Q_e`, `Q_w`, `Q_b`, `Q_m`, `K_{ZF}`, `\Delta t`
- 分数使用 `\frac{分子}{分母}`：`\frac{Q_e}{N-1}`
- 单位使用 `\text{}`：`\text{m}^3/\text{h}`, `\text{℃}`, `\text{mm}`
- 乘号使用 `\times`，百分号 `\%`
- 希腊字母：`\Delta`, `\theta`, `\tau`, `\rho`, `\eta`, `\lambda`
- 简单公式（单个变量赋值）使用行内 `$...$`，有代入步骤的完整公式使用块级 `$$...$$`

### 步骤5：一次性写入 outputs

**报告顶部「本次变更」块（反馈6，仅改参重生成时）：** 若本次是 `update` 触发的定点重生成，报告顶部插入变更摘要块（取 `project_snapshot.change_log` 最新一条）：
```
> 本次变更（v{version}）：{param} {old}→{new} ⇒ 重生成章节 {affected_chapters}；{value_diffs}
```

**输入:** 步骤4在内存中完整生成的 Markdown 报告
**操作（严格顺序，三步缺一不可）:** ① `write_file` 写报告 → ② `snapshot.py save` 固化快照（拿到 `SNAPSHOT_READY`）→ ③ `present_files` 收尾
**输出:** 同步到文档空间的 AIDocument

**① 一次 write_file 写入完整报告：**
```
write_file(
    path="/mnt/user-data/outputs/{项目名称}给排水设计专篇.md",
    content=<步骤4 完整生成的全部 Markdown>,
    append=false
)
```

**⛔ 写盘铁律（防止死循环）：**
- ✅ 一次 `write_file` 写入完整内容，`append=false`；有误则在内存整体重生成后再整体覆盖
- ❌ 禁止分多次 `append` 拼章节（会制造重复段落）
- ❌ 禁止写完再用 `str_replace` 修改落盘文件（会误删相邻内容）
- ❌ 禁止"先写 workspace 再 `cp`/`mv` 复制到 outputs"——直接写到 `outputs/`
- 报告文件落盘只允许上面这一次 `write_file`

**② ⛔ 固化会话快照（写盘后、present_files 前，多轮承接铁律 #4，不可跳过）：** 快照**只能**由下面的 `snapshot.py save` 产生——⛔ 禁止用 `write_file` 手写/复制/改名任何 `project_snapshot*.json` 旁路文件（bug-2198）。
```bash
python /mnt/skills/public/water-drainage-report/scripts/snapshot.py save \
  --task "首次生成 {项目名称} 给排水计算书（Q=<值> m³/h）" \
  --params /mnt/user-data/workspace/params.json \
  --state /mnt/user-data/workspace/formula_state.json \
  --manifest /mnt/user-data/workspace/chapter_manifest.json \
  --report /mnt/user-data/outputs/{项目名称}给排水设计专篇.md \
  --standards '["<步骤1勾选的规范>"]' \
  --output /mnt/user-data/workspace/project_snapshot.json
# 必须 stdout 出现 SNAPSHOT_READY: version=1 才算快照固化成功
```
**改参轮** 把 `--task` 换成改参摘要并追加 `--diff '{"<参数名>":{"old":<旧值>,"new":<新值>}}' --affected "<affected_formulas> / <affected_chapters>"`（取自步骤2 impacted 输出）→ `SNAPSHOT_READY: version=N`。这一步保证下一轮用户回来时，步骤0 能读到 `last_task` 锚点、不漂移、不重问全局参数（bug-1171 防线）。
- 工具失败不盲目重试——最多修正一次（如纠正路径）再试，连续失败 2 次必须停止并如实告诉用户

**③ 最后调 present_files（⚠️ 必须在 ② 打印 SNAPSHOT_READY 之后才调）：**
```
present_files(filepaths=["/mnt/user-data/outputs/{项目名称}给排水设计专篇.md"])
```
> 没拿到 ② 的 `SNAPSHOT_READY` 就调 present_files = 本轮未完成（下一轮必漂移）。present_files 是收尾动作，必须是步骤5 的最后一个工具调用。

### 步骤6：一致性校验

**输入:** 步骤5落盘的报告
**工具:** `bash` + `formula_runner.py check` + `consistency_contracts.json`
**输出:** 校验结果（CHECK_READY）

```bash
FORMULAS=/mnt/skills/public/water-drainage-report/references/formulas.json
SCRIPTS=/mnt/skills/public/water-drainage-report/scripts
CONTRACTS=/mnt/skills/public/water-drainage-report/references/consistency_contracts.json
WORK=/mnt/user-data/workspace

# 公式规范性校验（容积比、浓缩倍数等）
python $SCRIPTS/formula_runner.py check \
  --formulas $FORMULAS \
  --params "$(cat $WORK/params.json)" \
  --output $WORK/consistency_check.json   # CHECK_READY
```

展示校验结果：
```
一致性校验结果:

✅ 浓缩倍数 N=5 满足要求 (≥5.0)
⚠ 系统容积比 0.196 低于 1/3 (GB/T 50746 §6.1.9)
ℹ 旁滤比例 5% 在 1%~5% 范围内

1项警告 — 建议增大水池容积或减少循环水量。
```

**校验面板（反馈4）：** 报告末尾附「校验面板」表：检查项 / 当前值 / 规范区间 / 结论（✅/⚠️/❌）/ 条款引用。

**多规范围框比对（反馈5）：** 对 `code_constraint_multi` 合约（如 N-multi-standard），输出每参数×每规范矩阵；Tier-2（`tier1_curated=false` 的规范）参数显示「未自动校验（规范未入库，需人工对照）」，不给 pass/fail。web_search 仅用于 discovery（规范是否存在/范围/版本年），**绝不**驱动合规 pass/fail。

### 步骤7：合规检查

**输入:** 步骤5落盘的报告
**输出:** 合规检查结果

运行给排水相关 GB/HG 规范的合规检查。检查项包括：
- GB/T 50746-2012 石油化工循环水场设计规范（水池有效水深、容积比、连通管流速）
- GB 50648-2011 化学工业循环冷却水系统设计规范（浓缩倍数 ≥3.0，宜≥5.0）
- GB/T 50050-2017 工业循环冷却水处理设计规范（旁滤比例 1%~5%）
- HG/T 20690-2000 化工企业循环冷却水处理设计技术规定（拦污滤网、格栅）

**检查结果处理：**
- 全部 PASS → 合规检查通过，向用户展示合规摘要
- 有 WARN/FAIL → 回到步骤4，在内存中修正报告内容，整体重写落盘，然后重新运行检查。**最多修正 2 轮**。
- **超过 2 轮仍有 FAIL**：生成合规报告并展示 `以下项目需人工修正`（列出每项 FAIL 的具体条款和当前状态）。报告仍可导出（文档空间自动同步），提示用户："以下合规项未能自动修正，建议在提交审批前由专业工程师复核。"

**步骤5+6+7 串联：** 步骤5写盘后，立即执行步骤6一致性校验 → 步骤7合规检查。如果两轮修正后仍有 FAIL，告知用户"报告已生成但含未修复合规项"。用户可决定是否继续修正或直接导出。

---

## 参考文件

- `references/formulas.json` — 46 个公式定义（v2：配管选径/滤网起吊/泵房高度/喇叭口/反洗配套链；v3：+喇叭口安装几何4式/吸水池几何容积/放空管流速校核/水力坡降3式；symbol/citation 字段驱动式中图例与依据行；系数/经验类 input 带 source + needs_verification）
- `references/reference_values.json` — 行业经验参考值库（反馈2）
- `references/standards_index.json` — 可勾选规范清单（反馈5）
- `references/consistency_contracts.json` — 一致性 + 多规范围框合约（含 code_constraint_multi）
- `scripts/formula_runner.py` — 公式 CLI（execute / update / check / trace / impacted）
- `scripts/chapter_planner.py` — 章节规划（manifest / impacted 反查）
- 知识工厂模板（仅提供写作约束） > 内置 fallback 9 节 + 合规附录结构（样例体例）

---

## 多轮交互模式

本技能的交互循环已内嵌到步骤门禁中：

| 交互 | 对应步骤 | 门禁条件 |
|------|---------|---------|
| 参数确认 | 步骤1→2 | 用户确认参数表后才能进入公式计算 |
| 公式审核 | 步骤2→3 | 用户确认公式结果后才能进入模板获取 |
| 报告审阅 | 步骤4→5 | 步骤4生成后，用户可在步骤5写盘前审阅 |
| 修正重算 | 步骤2内 | 用户调参数 → `formula_runner.py update` → 增量重算 → 重新确认 |
| 最终定稿 | 步骤7 | 合规检查通过（或用户接受未修复项）→ `present_files` 定稿 |
