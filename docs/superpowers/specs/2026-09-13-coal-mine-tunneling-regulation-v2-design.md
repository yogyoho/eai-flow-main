# Design: coal-mine-tunneling-regulation v2 升级设计（掘进作业规程管线化 + 矿井档案层）

Date: 2026-09-13
Branch: main-dev-fork
Status: APPROVED（brainstorming 两节设计均经用户确认：§1 总体架构/两层状态模型/档案文件契约；§2 管线/门/12 合约/红线/测试/一期边界）
Mode: Builder
参照系：geological-report v2 → coal-eia-report v2 已验证管线（`docs/designs/coal-eia-report-v2.md`）

## 问题与目标

`skills/public/coal-mine-tunneling-regulation/` 现为纯提示词技能（251 行 SKILL.md，KF 模板 resolve 优先 + 内置 9 章回退），与已管线化的 geological-report v2 / coal-eia-report v2 相比缺整个机器层——eia v2 设计文档的差距表逐项适用：

| 能力 | geo/eia v2（参照） | 本技能现状 |
|---|---|---|
| 数字防护 | `{{SLOT:key}}`/`{{TABLE:族}}` 槽位，数字零过 LLM | `[XX]` 文字占位约定，数字直过 LLM |
| 数据层 | ingest.py 唯一写者 + 表单 schema + 门1 完备性 | 对话引导收集（10 类信息逐类问），无持久化 |
| 计算 | formula_runner 冻结 + trace + 改参反查 | 无（提示词要求"公式+代入"，LLM 手算） |
| 状态/续跑 | progress.py 状态机 + SHA-256 快照 | 无，断线即丢；且"整书内存生成一次写"在迭代修改时全量重生成 |
| 跨章一致性 | 合约集（XS/FC/CC/NR/SL 五类） | 无（仅提示词提醒"联动检查"） |
| 派发 | 控制器 + batch_task 子代理 + 波间要点包 | 单上下文整书生成（5.7 万字勉强可行，迭代/重生成脆弱） |
| 跨运行复用 | — | 无（**本技能独有缺口**：一矿一年上百份，矿井级常量每次重问） |

**领域特征**（与 geo/eia 的本质差异）：「一工程一规程、一变化一措施」——同一矿井反复编制，通风/供电/劳动组织/避灾体系/会审名单/编号规则是矿井级常量，地质/支护/工艺是工程级变量。**矿井档案层是本技能的核心增量，也是「一矿百份」场景的效率杠杆。**

## 证据基座（2026-09-13 样例解析）

语料：真实样例《3218运输顺槽掘进作业规程.docx》（`D:\18 辽宁创元\03 项目策划\01 中煤科工\`），用户确认少量样例（1–3 份），本期以 3218 为结构基准。

- **总量**：1253 段 / 57,468 有效字符（≈5.7 万字，geo 的 1/3、环评的 1/12）/ 22 表格 190 行 / 仅 2 内嵌图（附图为外部图纸）
- **章集**：9 章（Heading 1 实测）——概况 / 地面位置及地质情况 / 巷道布置及支护说明 / 施工工艺 / 生产系统 / 劳动组织及主要技术经济指标 / **安全风险辨识与管控（独立章）** / 安全技术措施 / 灾害应急措施及避灾路线
  - ⚠️ 与《煤矿作业规程编制指南》8 章框架的差异：样例把「安全风险辨识与管控」独立成章（双重预防机制新要求），且灾害应急章含「职业病防治」节——**stage 结构以真实样例为准，非指南框架**
- **样式混乱实证**：节标题混用 Subtitle，条级混用 Title/Normal/Heading 缺失——eia「编号正则+序号连续性双通道、目录区跳过」教训直接适用
- **计算域实测**：正文公式行命中极少——风量计算以「表格参数 + 公式代入」呈现（T458/T460：日最大 3.4 / 月平均 2.45 m³/min，Khg=1.39 / Khc=1.95 系数表）；**支护章无显式设计计算**（锚杆/锚索参数直接给定）→ formula 一期域 = 通风（四法 + 局扇选型 + 通风阻力 + 风筒距迎头 L=5√A）
- **表单族直接来源**（22 表 → 11 族）：工作面参数（水平/采区/标高）、煤层指标、顶底板岩性、工程质量允许偏差、支护材料与设备、矿压观测、施工设备（EBZ160 掘进机 / CMM2-15 锚杆钻车）、管线敷设（Φ1000 风筒 120 节）、瓦斯涌出量、防尘设施（水幕/喷雾/洒水周期）、传感器设置（甲烷 T≥1.0/≥1.5/<1.0 断电表）、劳动组织出勤、技术经济指标（**施工长度 902.236m——三位小数，SLOT 必要性实证**）、安全风险管控清单（风险类型/描述/等级/管控措施/责任人）
- **前置区 = 矿井档案金矿**：封面（矿名/编号 `掘ZJED-3218YSSC/01号`/编制单位 综掘二队/编制人/施工负责人/批准日期）+ 会审纪要表 + 审批栏（审批单位/人员/意见/日期）——会审单位名单是矿井级常量

## 决策记录（本会话已拍板）

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| D1 | 一期范围 | **掘进作业规程单场景先行**；采煤规程 / 二十余种专项安全技术措施（「一变化一措施」小型文档）二期扩 stage | 用户拍板；沿 eia D2 分层分期先例（管线风险与语料资产风险分离） |
| D2 | 升级路径 | **全管线移植**：geo 9 件套（ingest/formula_runner/chapter_planner/consistency/build_output/snapshot/progress/calibrate/bank_compile，4033 行）+ eia 增强（mapping/seed_gen 思路）**自包含副本适配，禁跨技能 import** | 用户拍板方案一；复制适配以删代写（删节级/删大半合约），全部失败模式已有解（bug-3040/3048/3049 内嵌） |
| D3 | 矿井档案层 | **一期做，形态 = 档案文件契约**：首跑建档案（mine_forms + ask_clarification 单回合一张）→ `profile.py` 校验 → 档案 md 随规程 present_files 进 docmgr（用户可见可编辑可下载）；**后续每跑 = 用户带档案文件进线程**，ingest 像吃地质说明书一样吃它。二期演进 = `mine_profile` 数据扩展 MCP（沿 contract-price 先例，schema 沿用 profile.json 零改动换存储）；spike = 验证 docmgr 文档能否作线程附件（若可，摩擦归零） | 用户拍板一期做档案层。实测约束：docmgr 对 chat agent 是只写通道（present_files 后端回调同步；editor_tools 为编辑器 UI 专用），运行时无 per-user KV。带 1 文件替代答 30+ 问，杠杆成立 |
| D4 | stage 结构 | **3218 样例实测定稿 9 章**（含「安全风险辨识与管控」独立章 + 职业病防治节），样例 > 指南框架；**双源归一**：stages/tunneling.json 唯一真源，report_structure.md 退役为派生说明 | 样例含指南没有的监管新增章；eia D12 教训（结构源污染/语义匹配承重墙）前置规避 |
| D5 | 计算域 | **formula_runner 一期只做通风域**：风量四法（瓦斯涌出量/人数/柴油机车/风速验算）+ 风筒距迎头 L=5√A + 局扇选型 + 通风阻力；**支护域不做设计计算**（样例实证无公式）——参数表走 SLOT + 审查红线阈值校验 | 样例全量解析实证；支护设计计算若更多样例出现公式再扩域（Open Question） |
| D6 | 派发粒度 | **章级**（9 章，波 ≤4 章），无节级；batch_task 注入 stage 要素链 + 冻结值表 + 深度目标；波间要点包 = 冻结值投影（章间无正文依赖，值表即事实源）；每波后落盘 progress+snapshot，停车契约全套移植 | 5.7 万字 = 环评 1/12，最大章 ~1.5 万字子代理装得下；比 eia 节级简单一档 |
| D7 | 一致性合约 | **12 条轻量集**（见下表），**阈值与 `coal-mine-report-review` 审查技能数字同源**（锚杆≥1.8m/间排距≤1.0m/风速 0.25–8m/s 等直接取审查技能数值）——写出的规程天然可过审查，两技能单一事实源；条件激活沿 eia（依赖章按语义标题在场才激活，缺席记 skip 非 fail） | 用户确认；审查技能已存在且阈值表完备，复用而非另立 |
| D8 | 红线 | geo P1–P5 全套移植 + 本域两条：①**强制条款不得放宽**（「有掘必探先探后掘」/断电值/防尘间隔等须引条款号；`standards_index` 限值 tier1 人工核实分级——websearch 不可靠教训适用，`reference_values` 全部【待核实】）；②**口径标签**：涌出量日最大/月平均双口径绑定（3.4/2.45 实证） | 法定安全文件；memory websearch-unreliable-for-gb-compliance |
| D9 | 交付 | **单文档 docmgr**：md（封面→会审页→目录→正文 9 章→附表→附图清单 `[需附图]`→贯彻记录）→ present_files → AIDocument。**不做** KF 章树/项目通道（单文档够）；**不做 Word 精排**（字体字号页边距由 docmgr 编辑器排版解决，技能保证结构语义与表格完备）；附图不生成（`[需附图]` 占位，cad-dxf 远期可选） | 用户确认；50 页单文档合理，文档空间编辑排版是既定路径 |
| D10 | 语料策略 | n=1–3：结构从 3218 定稿（confidence=low-单样本标注，防过拟合）；深度基线 = 绝对地板 ×1.2 留量；calibrate 深度校准与 samples_bank 切片库**二期**，回填触发 = 掘进规程样例 ≥5 份 | 用户确认少量样例；eia D7/D2 同纪律 |

## 一致性合约清单（12 条，数值实证自 3218 样例）

| # | 合约 | 跨章触点 | 实证 |
|---|---|---|---|
| C1 | 断面尺寸三元组（掘进/净断面）exact | ch3 支护 ↔ ch4 工艺 ↔ ch5 通风验算 | 5.0×3.6m，掘进 18m² |
| C2 | 巷道名称全称 exact | 全文（传感器表/避灾路线均点名） | 3218运输顺槽 |
| C3 | 设计长度 SLOT | ch1 概况 ↔ ch6 技术经济指标 | 902.236m |
| C4 | 支护参数组（锚杆/锚索/间排距/预紧力/锚固剂） | ch3 设计 ↔ ch3 工艺 ↔ ch8 措施 | 同组数值三处 |
| C5 | 风量链：Q需→局扇选型→风筒规格 | ch5 内闭环 + 风筒节数↔巷长校验 | Φ1000×120 节 |
| C6 | 瓦斯涌出量（口径标签绑定） | ch2 数据 ↔ ch5 计算 | 3.4/2.45，Khg 1.39/Khc 1.95 |
| C7 | 涌水量 | ch2 水文 ↔ ch5 排水 ↔ ch9 水灾 | 三章联动 |
| C8 | 设备型号 ↔ 措施条目匹配 | ch4 设备表 ↔ ch8 对应设备措施必须在场 | EBZ160/CMM2-15 |
| C9 | 限员 ↔ 自救装置数量与距离 | ch6 ↔ ch9 | 25–40m、3 个 ZYJ-M6 |
| C10 | 传感器阈值 = AQ1029 红线值 | ch5 表格 | ≥1.0/≥1.5/<1.0 |
| C11 | 规程编号格式 ↔ 封面 ↔ 会审页 | 编号正则 | `掘ZJED-YYYYSSC/NN号` |
| C12 | 矿井级字段 echo（**档案漂移检测**） | 档案 ↔ ch1/ch2 声明一致 | 瓦斯等级/水文类型 |

## 总体架构

```
skills/public/coal-mine-tunneling-regulation/
├── SKILL.md                       # 重写：角色/红线/管线步骤0-6/两道门/派发协议/停车契约/档案协议/命令速查
├── scripts/                       # geo 9 件套自包含副本适配（calibrate/bank_compile 随套件携带、二期启用）
│   ├── ingest.py                  # 表单唯一写者 + 门1完备性（吃 forms.json，含 mine_forms 档案族）
│   ├── formula_runner.py          # 通风域冻结计算（值+display+source+口径标签）
│   ├── chapter_planner.py         # 章级派发计划 + deps 编译
│   ├── consistency.py             # 12 合约校验（表格感知 + 条件激活）
│   ├── build_output.py            # 单文档组装（封面/会审/目录/正文/附图清单/贯彻记录）+ --chapter 章门
│   ├── snapshot.py / progress.py  # 快照续跑 + 章级状态机（PENDING→DRAFTED→VERIFIED）
│   └── profile.py                 # 🆕 矿井档案 schema 校验 + merge + 版本 + 漂移检测
└── references/
    ├── stages/tunneling.json      # 9 章骨架（3218 实测定稿，样例>指南；confidence=low 标注）
    ├── forms.json                 # 表单族 ~11 族 + mine_forms 档案族
    ├── formulas.json              # 风量四法/局扇选型参数与舍入策略（计算体在 formula_runner）
    ├── consistency_contracts.json # C1–C12
    ├── standards_index.json       # 煤矿安全规程2022/GB35056/AQ1029/AQ1020/防治水细则/地质工作细则/防突细则…；限值 tier1 人工核实分级
    ├── reference_values.json      # 通风经验参数（风筒漏风率/K 值/风阻…全部【待核实】）
    ├── data_expectations.json     # 按章数据预告（开题三件套③）
    ├── depth_targets/tunneling.json  # 绝对地板 ×1.2（n=1，confidence=low）
    ├── terminology.md             # 沿用现有
    ├── content_guidelines.md      # 沿用现有（章节编写规范/19 附图说明/扩展点）
    └── report_structure.md        # 退役：改写为「结构唯一真源=stages/tunneling.json」的派生说明
```

## 两层状态模型

```
┌─ 矿井档案层（跨运行持久：档案文件契约）────────────────────┐
│ profile.json（schema 固定，profile.py 校验；带档案日期版本） │
│  ├ mine_id   矿名/集团/编号规则(掘ZJED-YYYYSSC/NN)          │
│  ├ hazards   瓦斯等级/涌出量等级/水文地质类型/自燃倾向/煤尘  │
│  ├ systems   开拓方式/通风方式/供电电压等级/监控系统型号/    │
│  │           压风/防尘供水/运输系统/六大系统配置             │
│  ├ equipment 掘进机/锚杆钻车/输送机/车辆等设备型号库         │
│  ├ org       队组/班制/限员制度/会审单位名单/审批栏职务表    │
│  └ refuge    避灾路线体系/自救装置配置                       │
│ 条目带 mine_scope 标记 → data/ 分区矿井级/工程级：          │
│ 改巷道长度不惊动矿名；改瓦斯等级触发全章重扫（C12 联动）     │
├─ 工程运行时（per-thread workspace，一次性）────────────────┐
│ /mnt/user-data/workspace/tunneling-regulation/              │
│  data/      表单 JSON（ingest.py 唯一写者；档案 merge 进）   │
│  state/     chapters/ + key_points/formula_state/           │
│             consistency_check.json                          │
│  outputs/   全书 md → present_files → docmgr AIDocument     │
└─────────────────────────────────────────────────────────────┘
```

progress.json 章条目（章级，无节子表——与 eia 的关键简化）：

```json
{"ch5": {"status": "IN_PROGRESS", "title": "生产系统", "dispatches": 1}}
```

## 生成管线（步骤 0–6）

- **步骤 0** 快照恢复（`snapshot show --verify`，rc=3 停）
- **步骤 0.5** 🆕 矿井档案装载：线程带档案文件 → `profile.py` 校验 + 摘要呈现（含档案日期；「矿井条件有变先更新档案」提示；变更则走档案更新再继续）；无档案 → 先建档案（mine_forms 逐族 ask_clarification，单回合一张铁律）
- **步骤 1** 数据收集：KF `kf_resolve_template` 真调用（found=false 声明，沿现行技能契约）+ `data_expectations` 按章数据预告；表单族 ~11 族；ask_clarification 单回合一张；批量数据引导上传走 ingest.py；**门1** 完备性（含档案存在与完备）
- **步骤 2** 冻结计算：formula_runner 通风域（D5），输出值+display+source+口径标签；**门2** anomalies 逐条呈现（涌出量缺失/风速越界/口径并存）
- **步骤 3** 章级派发：progress 状态机；chapter_planner 分波（≤4 章/波）；batch_task 注入要素链+冻结值表+深度目标；波间要点包=值表投影；**每波后落盘 progress+snapshot（停车契约）**
- **步骤 4** 组装：build_output 单次原子写全书 → `--chapter` 章门 rc=0 自动回写 VERIFIED（禁手动 mark，bug-3049）；目录覆盖门 = 必备/可选集匹配 + 章标题语义相符（序不校验）
- **步骤 5** 一致性合约 C1–C12（表格感知；条件激活：依赖章缺席记 skip 非 fail）
- **步骤 6** 交付：单文档 md → present_files → docmgr；交付说明列明已填数据 / `[待补充]` 项 / `[需附图]` 清单

**迭代修改**：改参 → formula_runner 重算 → impacted 反查受影响章 → 重派受影响章 → 组装 → 合约重跑（沿 geo 改参回路；C12 使矿井级变更自动触发全章重扫评估）。

## 测试矩阵（7 文件 + fixture）

- `test_ingest_forms.py` — 表单解析 + 完备性门（含 mine_forms）
- `test_formula_ventilation.py` — 风量四法数值回归（用样例值 3.4/2.45/Khg1.39 造例）
- `test_contracts.py` — C1–C12 正反例 + 条件激活
- `test_progress_gate.py` — 章状态机 + 章门自动回写（禁手动 mark）
- `test_profile.py` — 档案 schema/merge/版本/漂移检测
- `test_build_output.py` — 组装 + 目录覆盖门
- `test_snapshot.py` — 快照往返 + rc=3
- `tests/fixtures/` — 3218 解析产物脱敏 fixture
- 集成验收：一份完整掘进规程 E2E（对话→档案→数据→冻结→派发→门→交付），交付物须能过 `coal-mine-report-review` 审查（数字同源的实证闭环）

## 错误处理（沿 geo 停车契约）

工具失败不盲试（连败 2 停、如实上报）；断线 = snapshot 恢复续跑；门失败定位章重派；档案版本冲突 / 档案与工程数据矛盾 → 升用户确认（禁静默取舍）；每波停车点 + 磁盘续跑为默认生存方式。

## 一期边界（明确不做）

采煤规程 / 专项安全技术措施 stage（二期）｜附图生成（`[需附图]` 占位）｜calibrate 深度校准 / samples_bank（n<5）｜KF 章树 / 项目通道交付｜mine_profile MCP 扩展（二期，schema 已预留）｜Word 精排（docmgr 编辑器排版解决）。

## Open Questions

1. **spike**：docmgr 文档能否作为线程附件直接引用（若可，档案装载摩擦归零；实现期首日验证）
2. 支护域设计计算：更多样例若出现悬吊理论等公式 → 扩 formula 域（当前 n=1 无公式实证）
3. 编号规则集团差异：`掘ZJED-*` 为样本矿格式，多集团编号规则进 mine_id 可配置项（一期单格式 + 正则宽松匹配）
4. KF 是否已有掘进作业规程 published 模板及其与 3218 结构的偏差（步骤 1 真调用时对账，偏差回写沿 eia D3 纪律）

## 证据工作文件

- 提取脚本与输出：`.wolf/tmp/gzgc-extract/`（extract_outline.py / extract_deep.py / outline.txt / deep.txt）
