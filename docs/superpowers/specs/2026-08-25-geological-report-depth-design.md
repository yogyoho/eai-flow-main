# 地质勘查报告章节深度对标优化设计（深度目标门 + 范式细化 + 多样例范式库）

> 2026-08-25 · geological-report 技能 · 承接 bug-2220/2221/2223/2225 修复线 · 方向 B 分两步（已批准）

## 1. 问题与证据

E2E 交付（线程 90c9d09d，2026-08-25）报告有效字符 24,236，样例同口径 71,795，**总体 31%**。逐章取证（eff=排除表格行/标题的叙述字符，与 build_output 深度门同口径）：

| 章 | 样例 eff | 生成 eff | 比值 | 样例表行 | 生成表行 | 待确认 |
|---|---:|---:|---:|---:|---:|---:|
| 1 绪论 | 7,320 | 2,873 | 39% | 23 | 0 | 5 |
| 2 区域地质 | 9,203 | 1,587 | 17% | 16 | 8 | 0 |
| 3 矿区地质 | 3,211 | 2,278 | 71% | 0 | 6 | 1 |
| 4 矿体特征 | 8,990 | 3,489 | 39% | 24 | 5 | 19 |
| 5 样品分析 | 3,785 | 1,125 | 30% | 96 | 0 | 23 |
| 6 资源量估算 | 17,370 | 2,655 | 15% | 54 | 0 | 0 |
| 7 水文工程 | 7,918 | 1,887 | 24% | 37 | 0 | 0 |
| 8 开采技术 | 7,904 | 3,202 | 41% | 32 | 9 | 23 |
| 9 经济评价 | 3,763 | 1,606 | 43% | 0 | 0 | 27 |
| 10 结论 | 2,331 | 1,561 | 67% | 0 | 0 | 7 |
| **计** | **71,795** | **22,263** | **31%** | **282** | **28** | **105** |

### 根因分解（三个独立杠杆）

1. **数据面**：表格族近乎全缺（28/282 行，ch5/6/7 整表缺失）+ 105 处 `[待确认]`。已确认真实用户**大多能供全量数据**（CSV/Excel 愿上传）——所以这是**引导时机问题**：用户开题时不知道第 5 章需要化验表，写到才发现缺。
2. **叙述面**（结构性短板）：即使同数据，叙述也只有样例 31%。三个子因：
   - 要素粒度：样例逐要素**成段**（每个地层组一段：岩性+厚度+接触关系+含矿性），生成版逐要素成句；
   - 解释层缺失：样例每表/每组数据后有「规律识别→成因解释→规范对比→勘查意义」，生成版表后即止；
   - 无体量反馈：深度门只有绝对下限（≥3句/节、1000字/章）——那是地板，不是目标，模型不知道该写多厚。
3. **范式面**（次要）：单样例参照。检索键本质是节号（同阶段报告结构同构），**确定性文件索引即可，无需向量/图谱检索**。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 方案 | B 分两步：Phase 1（深度目标门+范式细化+数据预告）立即落地；Phase 2（样例到位后）多样例范式库 |
| GraphRAG/PageIndex | **不考虑**（用户明确 defer）——检索键=节号，语义检索非对症 |
| 数据供给前提 | 真实用户大多能供全量数据；E2E 最小数据场景**不得被目标门误拦** |
| 时长/成本 | 质量优先，可接受单轮 40-60 分钟 |
| coverage_scale | 由 build_output 从**注入后文本自算**（agent 不可传参绕过），不用手工章节-数据族映射表 |
| 数据预告载体 | `references/data_expectations.json` 静态文件，手工一次写死 10 章映射 |

## 3. 架构与组件

改动**全部在 skill 层**（`skills/public/geological-report/`），不碰 harness/gateway。

```
skills/public/geological-report/
├── scripts/
│   ├── build_output.py        # 改：抽 effective_chars() 模块级函数；新增 validate_depth_target()
│   └── calibrate.py           # 新：样例 → references/depth_targets.json（确定性、无时间戳）
├── references/
│   ├── depth_targets.json     # 新（生成物）：每章 median eff/表行/段落 + 可调系数
│   ├── data_expectations.json # 新（手写）：章 → 所需数据族 → CSV 列样例
│   └── samples/               # 现行单样例（Phase 2 扩为 samples_bank/）
└── SKILL.md                   # 改：步骤1 数据预告 + 步骤4 范式升级 + 命令速查
```

### 数据流（Phase 1）

```
样例 chN_sample.md ──calibrate.py──> depth_targets.json
用户开题（步骤1）──> 呈现数据预告清单（data_expectations.json）──> 引导上传 CSV/Excel
wave1 逐章生成：动笔前读该章目标值 + 范式规则（逐要素成段/表后五步解读）→ 写 chN.md
build_output：validate_chapter → validate_depth（地板，保留）→ validate_toc → inject
           → validate_depth_target（新，作用于注入后文本）→ FAIL exit 1 点名差距
```

## 4. 深度目标门（核心机制）

### 公式（作用域：assemble 内 inject 之后的章节文本）

```
signals    = text.count("[待确认]") + missing_table_weight × text.count("数据未提供")
scale      = max(scale_floor, 1 − per_signal_penalty × signals)
target_eff = median_eff(ch) × coefficient × scale
FAIL ⟺ effective_chars(text) < target_eff
```

**参数默认值**（写入 depth_targets.json，可调无需改码）：`coefficient=0.6`、`scale_floor=0.25`、`per_signal_penalty=0.05`、`missing_table_weight=8`。

- `[待确认]` 是 LLM 按红线写的缺数占位（注入前即在文本中）；「数据未提供」是 render_family 对缺失数据族的占位表串（注入后出现）——两者都只在注入后文本同时可见，故门在 inject 后执行。占位表一张 ≈ 8 个散点缺数（一表多行数据），权重折算。占位表串本身同时含两信号（`数据未提供——[待确认] 槽位`）→ 同一缺数被双计，方向保守（scale 更低、更不易误拦缺数场景），有意为之。
- **参数已用 E2E 实测数据校准**：当前 E2E 产物（最小数据场景）下，仅 ch2 类「数据全供但叙述薄」的章会 FAIL（正是要逼补的）；ch5/6/7/9 等缺数章全部落到 scale 下限附近、PASS 不误拦。全量数据场景下（signals≈0）各章目标≈样例 60%，全面逼升叙述。Phase 1 落地后以重生成 E2E 复核两组场景。

### targets 定位

build_output 新增 `--targets` 可选参数（SKILL.md 命令速查显式传 `references/depth_targets.json`）；未传时在 stage 文件同目录与其 `../`、`../../`（即 references/ 下）探测 `depth_targets.json`，探测不到 → 退回地板门（§8 第一行）。

### FAIL 输出（stderr，exit 1）

```
chN.md 深度目标门 FAIL：eff X < 目标 Y（样例 median Z × 0.6 × 覆盖缩放 s）
最薄节：3.2（2句/缺要素段）、…——参照 samples/…/chN_sample.md 逐要素成段扩写；表后五步解读（陈述→规律→成因→规范对比→勘查意义）
```

### 门层级（三层递进，互不替代）

| 层 | 门 | 状态 |
|---|---|---|
| L0 地板 | validate_depth（≥3句/节、1000字/章） | 既有，保留不动 |
| L1 结构 | toc 覆盖/章节卫生/槽位完整性 | 既有，保留不动 |
| L2 目标 | validate_depth_target | 新增 |

交付面（bug-2225 契约标记/manifest/present_files/artifacts 三门）**零改动**。

## 5. calibrate.py

- 输入：`--samples-dir references/samples/<stage>/`（Phase 2 为 samples_bank 下 N 份）
- 逻辑：按 `## N.M` 节号切章切节（HEADING_NO_RE 与 build_output 同源），逐章统计 eff/表行/段落数；N 份时取 median（1 份时 median=值，字段名从第一天就叫 `median_*`，Phase 2 兼容）
- `effective_chars` 从 build_output import（同口径单源，脚本同目录 import 成立）
- 输出 `references/depth_targets.json`（含上节参数默认值 + samples 清单 + per_chapter median）；sort_keys、无时间戳（确定性幂等，与 delivery_manifest 同哲学）
- 样例文件无节号 → 报错退出（rc≠0），绝不静默产出空 targets

## 6. SKILL.md 三处改动

1. **步骤 1 · 数据预告**：开题第一轮（kf_resolve_template 之后）向用户呈现「本报告各章所需数据清单」（读 data_expectations.json：第 5 章需要基本分析表 CSV，列为样品编号/工程号/起止深度/品位…；第 6 章需要块段表…），首次交互即引导备料上传——把 bug-2221 根因④的「写到才发现缺」前移为「开题即预告」。
2. **步骤 4 · wave1 范式升级**：
   - **逐要素成段**（原「逐要素成句」升级）：要素链每节点 ≥1 段完整专业叙述（定性描述+空间关系+工程意义）；数值仍只走 `{{SLOT:key}}`，缺数写 `[待确认]` 不砍段。ch2 类知识章按样例的地层组/构造单元**逐单元成段**——定性内容凭通用地质知识，数值一律 SLOT/待确认，禁联网（红线不变）。
   - **表后五步解读**（原「表后解读段」升级）：陈述→规律识别→成因解释→规范对比（引 standards_index 实有编号，禁编造条款号）→勘查意义。
   - **动笔前读目标**：读该章 depth_targets（median eff/表行/段落），写后自检对照（build 门兜底）。
3. **命令速查**：加 `calibrate.py` 行（用途/输出/错误码）；build_output 退出码说明补「深度目标门」。

## 7. Phase 2 · 多样例范式库（样例到位后）

- 入库：N≥3 份真实报告脱敏 → `samples_bank/<stage>/<report_id>/source.md`
- `bank_slice.py`：按节号切片 → `samples_bank/<stage>/slices/chN/<section>/<report_id>.md` + `bank_index.json`（节号→片段列表，**纯文件索引，零检索服务**）
- calibrate.py 升级读 N 份 → 真 median
- SKILL.md 参照升级：动笔前按节号经 index 取 2-3 份不同报告同节片段（读本地文件）
- 红线不变：片段数值/矿名/地名禁入正文（P2/P5）
- bank_index 缺失 → 自动退化为现行单样例模式

## 8. 错误处理汇总

| 场景 | 行为 |
|---|---|
| depth_targets.json 缺失/损坏 | stderr「退回地板门」，继续跑不阻断（兼容旧线程/其他 stage） |
| coverage_scale 触底 | 下限 0.25，缺数再多也留地板（约样例 15%） |
| calibrate 遇无节号样例 | rc≠0 报错，不产空 targets |
| Phase 2 bank_index 缺失 | 参照退化单样例 |
| 交付面 | 零改动；L2 是 build 内部门 |

## 9. 测试策略（TDD）

`backend/tests/test_geological_report_v2_scripts.py` 扩展：

- **calibrate**：mini fixture 样例 → targets 字段断言（median_eff/表行/参数默认值）；无节号样例 rc≠0。
- **effective_chars 抽取**：既有 validate_depth 测试数字回归不变。
- **validate_depth_target** 5 例：薄文本 FAIL（stderr 含差距与「覆盖缩放」字样）/ 达标 PASS / 缺 targets 回退地板门 / E2E 缺数场景缩放后 PASS（防误拦复现）/ signals 极多时 scale 触底 0.25。
- `test_geological_report_skill.py` presence 断言：五步解读、逐要素成段、数据预告、calibrate 速查行。

## 10. 验收标准

- **真实全量数据场景**重生成：每章 eff ≥ 样例×0.6，总量 ≥ ~43,000（现 22,263）；ch5/6/7 表行非零（数据预告生效）。
- **E2E 最小数据场景**（现有线程产物 host 重跑 build 验证）：不被目标门误拦（缩放生效），仅数据全供的薄章被拦。

## 11. 分期与范围

- **Phase 1（本计划范围）**：calibrate.py、effective_chars 抽取、validate_depth_target、data_expectations.json、SKILL.md 三处、全部测试。每任务一提交（explicit pathspec，main-dev-fork）。
- **Phase 2（样例到位后另立计划）**：脱敏入库、bank_slice.py、median、SKILL.md 参照升级。
- **不做**：GraphRAG/PageIndex（用户明确不考虑）；KF 检索链路改动；harness/gateway 改动；红线任何松动。
