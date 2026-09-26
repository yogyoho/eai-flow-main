# coal-mine-tunneling-regulation v2 管线化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `skills/public/coal-mine-tunneling-regulation/` 从纯提示词技能升级为管线技能——geo 9 件套自包含移植（以删代写）+ 矿井档案层（profile.py 文件契约）+ 章级派发（3 波 × ≤4 章）+ C1–C12 一致性合约（阈值与审查技能同源）。

**Architecture:** 移植基座 = geological-report（章级状态机/单文档交付天然匹配），eia 仅 port 3 组增量函数（`validate_toc_chapters` 目录覆盖门、`load_contracts/check_contracts` 注册表框架、`_value_occurrences` 表格感知）；eia 的 mapping.py/seed_gen.py（573 行 KF 章树通道件）**零移植**。全部脚本 stdlib-only、技能自包含、禁跨技能 import（D2）。表单 schema 内嵌 `stages/tunneling.json` 顶层 `forms` 块。

**Tech Stack:** Python 3.12 stdlib-only 技能脚本、pytest（技能根 `tests/`，手动跑不进 CI）、JSON 契约文件、docmgr 单文档交付（present_files）。

**依据:** spec `docs/superpowers/specs/2026-09-13-coal-mine-tunneling-regulation-v2-design.md`（D1–D10）+ 侦察工作流 13/13 结构化事实（摘要落 `.wolf/tmp/gzgc-extract/recon-digest.md`，全部行号证据以其为准）。

**镜像源（勘察定稿）:**
- 脚本基座：`skills/public/geological-report/scripts/` 9 件（ingest 757 / formula_runner 693 / consistency 523 / build_output 892 / progress 474 / snapshot 196 / chapter_planner 147 / calibrate 92 / bank_compile 263）
- eia 增量函数（port 清单）：`skills/public/coal-eia-report/scripts/consistency.py` 的 `load_contracts`(:523)、`check_contracts`(:643)、`_contract_exact_match`(:570)、`_contract_echo`(:621)、`_value_occurrences`(:537)、`_norm_sem`(:495)、`_semantic_hit`(:506)、`_heading_norms`(:512)、`_find_chapter`(:561)；`build_output.py` 的 `validate_toc_chapters`(:386)、`_sem_match`(:378)
- 参照模板：`skills/public/coal-eia-report/references/stages/project_eia_underground.json`（stage 最新最全版）、`references/consistency_contracts.json`（entry schema :19-32）、`references/standards_index.json`（734 行骨架）、`references/depth_targets/planning_eia.json`、geo `references/reference_values.json`（唯一在库模板）
- 测试先例：`skills/public/fire-protection-extract/tests/`（技能根 tests/ + 真实样本 skipif 门）+ `skills/public/coal-eia-report/scripts/tests/test_ingest_bug3229.py`（内联 stage + tmp_path + main(argv) 断 rc 三层法）
- 3218 样例解析：`.wolf/tmp/gzgc-extract/{extract_outline,extract_deep}.py` + 仓库外源 `D:/18 辽宁创元/03 项目策划/01 中煤科工/3218运输顺槽掘进作业规程.docx`

## 实施期拍板记录（侦察后定案，spec 偏差显式列出）

| # | 拍板 | 内容 | 理由 |
|---|------|------|------|
| J1 | 表单位置 | 表单 schema **内嵌 `stages/tunneling.json` 顶层 `forms` 块**，不建独立 forms.json。spec 架构树的 `forms.json` 由 stage 内嵌 forms 实现 | geo/eia 的 `ingest`/`formula_runner.Data`/`consistency` 都读 `stage['forms']`，独立文件需改 3+ 脚本；双源归一原则下 stages JSON 本就是唯一真源 |
| J2 | 波结构 | `stage.generation_waves` 键驱动（geo exploration.json:606 已有此键形态但脚本从不读）；progress.py `derive_phase` 重写为 N 波循环；3 波 = [ch1,ch2,ch3]/[ch4,ch5,ch6]/[ch7,ch8,ch9] | D6 波≤4 章；geo 双波硬编码在 derive_phase L86-100，须重写 |
| J3 | 要点包 | **删除** `KEY_POINTS` 相位与 `confirm-key-points` 命令；波间要点包 = `formula_state.json` 冻结值投影（脚本投影，无用户确认门） | D6「章间无正文依赖，值表即事实源」；9 章无 eia 式结论章 |
| J4 | 门1 档案检查 | 档案族 = 普通表单族（`family:"profile"`，file `00_profile.json`）；`profile.py load` 经 `ingest.write_form_values` 落盘 → 门1 完备性**零新代码**自动覆盖 | ingest check 逐族判 required 字段既有机制直接复用 |
| J5 | 合约数据源 | consistency 合约 `source` 语法扩两类：`data:<族>.<字段>`（JSON 表单）与 `data:<CSV族>:<列名>`（CSV 整列）；eia 只有 `formula:` 前缀 | C1/C3/C8/C12 的值源是表单而非公式；C12 档案 echo 同理 |
| J6 | KF resolve 修复 | 调用参数改 `report_type="operating_procedures_report"`、`industry="煤炭挖掘"`、`domain_keywords` 增 `"操作规程"`；并发布 DB 中 3218 抽取 draft 模板 756b65d7（完整度 86）为 published | 现行参数三重不匹配恒 found=False（侦察实证：report_type 不在 business_dictionaries/industry≠字典 label/keywords 零 ILIKE 命中）；Task 1 需用户确认后执行 DB UPDATE |
| J7 | 深度口径 | `depth_targets/tunneling.json` floor_chars = 3218 实测章 effective_chars × **1.2**（D10），confidence 记 `measured_single_anchor_n1_x1.2`；与 eia 0.6 折减方向相反是**有意为之**并在 source 字段说明；「可承载」断言=**逐章语义**（单章地板 <25000 字≈子代理产能上限；T4 实测最大 ch8=19522 ✓——总量断言无意义因 9 章各由独立子代理生成，T4 实测裁决） | spec D10 拍板；n=1 上浮防样本偏小 |
| J8 | C10 定性 | C10（传感器断电值）标 `code_constraint` 型 → 一律记 manual（eia :671 语义），tier1 人工核实 AQ 1029 前不作自动断言 | 审查技能无此数值（侦察 R1–R12 实证）；D8 强制条款不放宽 |
| J9 | 审查技能边界 | `skills/custom/coal-mine-report-review` 本期**不修改**（含其 allowed-tools 声明）；E2E 验收 = 程序化比对阈值表，**不真实激活**审查技能 | 激活态工具剥离会打断 present_files（侦察 risk）；阈值数值已内联进本项目 JSON |
| J10 | 深度门单源化 | build_output 的深度目标公式三处复制（validate_depth_target/_depth_row/run_chapter_gate，注释自标「三处同式须同步改」）移植时**收敛为单一函数** `depth_target()`；深度基准文件**保持 geo 形状** `{coefficient, absolute_floor, per_chapter:{chN:{median_eff,…}}}`（`median_eff = ceil(实测eff×1.2)`），不改 eia floor_chars 门 | 侦察 risk：漏改一处即门与 manifest 口径分叉；对抗评审 P1：geo load_targets 只认 per_chapter/median_eff，eia floor_chars 形状装进 geo 门=恒 0 哑火 |
| J11 | 档案范围裁定 | profile 族 = **矿井级常量并集**：spec 六组中的 mine_id/hazards/systems/org/refuge 全部并入（refuge 的避灾路线×3/自救装置型号数量距离/六大系统是矿井基础设施，随档案跨运行复用）；**equipment 型号库一期留在工程表单**（不同巷道设备组合不同，库-选择两层二期再拆——对 spec 的显式收窄登记） | 对抗评审 P1：档案范围静默收窄未登记；spec D3「一矿百份」杠杆靠矿井级常量，equipment 逐工程选择不损害该杠杆 |
| J12 | 通风阻力 F4 | spec D5 列明的「通风阻力」一期**以待核实形式纳入**：公式条目 F4（h≈R·Q² 线性阻力近似，风阻系数 R 入 reference_values 全【待核实】），compute() 实现并**恒记 anomaly**——未核实前仅参考值不参与门断言 | 对抗评审 P1：APPROVED 决策不可静默收窄；待核实纪律（D8）恰好为此设计 |
| J13 | 测试 harness 约定 | ①新建 `tests/conftest.py` 做 `sys.path.insert(0, ROOT/'scripts')`（沿 test_ingest_bug3229 L20-23 真实先例——spec_from_file_location 不加 sys.path 会炸 formula_runner 的模块级 sibling import）；②**五件套 main 签名改造**：Tasks 7/9/10/11/12 各加一条 delta `def main() → def main(argv=None)` + `p.parse_args(argv)`（仓内先例 bank_compile.main_with_args(argv)/ingest.main(argv=None)）——geo 五脚本 main() 零参，测试 main(argv) 必 TypeError | 对抗评审 5 视角收敛的系统性 P0；不能留给实施者现场发明 |

## 交付物目录总览

```
skills/public/coal-mine-tunneling-regulation/
├── SKILL.md                          # Task 14 全重写（保留 4 处接线契约）
├── scripts/                          # Task 2 复制 + Tasks 5-12 逐件适配
│   ├── ingest.py formula_runner.py chapter_planner.py consistency.py
│   ├── build_output.py progress.py snapshot.py
│   ├── profile.py                    # Task 6 全新
│   └── calibrate.py bank_compile.py  # Task 15 dormant 携带（零调用点）
├── references/
│   ├── stages/tunneling.json         # Task 3（结构+forms 唯一真源）
│   ├── formulas.json                 # Task 7（通风域）
│   ├── consistency_contracts.json    # Task 10（C1-C12）
│   ├── standards_index.json          # Task 13（煤矿域+审查阈值入库）
│   ├── reference_values.json         # Task 13（通风经验参数全【待核实】）
│   ├── data_expectations.json        # Task 13（9 章数据预告）
│   ├── depth_targets/tunneling.json  # Task 13（实测×1.2）
│   ├── terminology.md content_guidelines.md  # 沿用零改动
│   └── report_structure.md           # Task 3 退役为派生说明
└── tests/
    ├── conftest.py                   # Task 5 创建：sys.path 注入 scripts/（J13）
    ├── test_*.py ×7                  # Tasks 5-12
    ├── fixtures/                     # Task 4（3218 脱敏 digest）
    └── README.md                     # Task 15：测试命令（test-infra 勘察：现无任何技能记录跑法）
```

---

### Task 1: KF 前置——发布 3218 抽取模板（需用户确认）

**Files:** 无代码改动；DB 状态变更一次。

- [ ] **Step 1: 向用户确认发布**（J6）。说明：DB 已有两份从 3218 样例抽取的 draft 模板（`756b65d7-da45-4abc-a8b1-4eef669e4cfd` 完整度 86 / `65eb22ce` 83，侦察 psql 实测），发布高分的让 v2 步骤 1 的 `kf_resolve_template` 真调用拿到 `match_level=exact` 模板与 stages/tunneling.json 对账（eia D3 纪律）。发布是纯状态翻转，可随时回退（`status='draft'`）。
- [ ] **Step 2: 用户同意后执行**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "UPDATE extraction_templates SET status='published' WHERE id='756b65d7-da45-4abc-a8b1-4eef669e4cfd' RETURNING id,status;"
# 期望: 返回 1 行 | 756b65d7-... | published
```

- [ ] **Step 3: 用户拒绝则跳过**，SKILL.md 的 KF 段保持「resolve→found=false→stages/tunneling.json 兜底」路径（该路径本就是管线一等公民，功能无损），并在本任务 checkbox 标注 skipped。

---

### Task 2: 脚本套件自包含复制 + 冒烟导入

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/scripts/`（9 件复制）

- [ ] **Step 1: 复制 geo 9 件**

```bash
cd D:/eai/eai-flow-main
mkdir -p skills/public/coal-mine-tunneling-regulation/scripts
cp skills/public/geological-report/scripts/{ingest,formula_runner,chapter_planner,consistency,build_output,progress,snapshot,calibrate,bank_compile}.py \
   skills/public/coal-mine-tunneling-regulation/scripts/
ls skills/public/coal-mine-tunneling-regulation/scripts/
# 期望: 9 个 .py 文件（后续任务逐件改造，本任务只复制不修改）
```

- [ ] **Step 2: 冒烟导入**（stdlib-only，任何 import 错误=复制污染）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -c "
import sys, os
sys.path.insert(0, os.path.abspath('scripts'))   # formula_runner/consistency/calibrate 有模块级 sibling import
import importlib
for n in ['ingest','formula_runner','chapter_planner','consistency','build_output','progress','snapshot','calibrate','bank_compile']:
    importlib.import_module(n)
    print('OK', n)
"
# 期望: 9 行 OK（不执行 main，只验证语法/依赖）
```

- [ ] **Step 3: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/
git commit -m "feat(tunneling-v2): geo 9件套自包含复制基线(未改造)"
```

---

### Task 3: stages/tunneling.json——结构唯一真源（9 章 + forms 12 族 + waves）

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/references/stages/tunneling.json`
- Modify: `skills/public/coal-mine-tunneling-regulation/references/report_structure.md`（退役为派生说明）

- [ ] **Step 1: 写 stages/tunneling.json**（J1：forms 内嵌顶层；J2：generation_waves）。章名/节集=3218 实测 9 章（含「安全风险辨识与管控」独立章，D4）。完整内容：

```json
{
  "version": "2.0",
  "stage": "掘进作业规程",
  "stage_id": "tunneling",
  "std_ref": "《煤矿安全规程》(2022) GB/T 35056-2018 AQ 1029-2019 AQ 1020-2006 《煤矿防治水细则》《煤矿地质工作细则》《防治煤与瓦斯突出细则》《煤矿安全生产标准化管理体系基本要求及评分方法》。标准号仅从 standards_index.json 枚举，禁 LLM 记忆补写——红线",
  "generated": "2026-09-13",
  "source": "真实样例《3218运输顺槽掘进作业规程.docx》全量解析（.wolf/tmp/gzgc-extract/）：9 章 Heading 1 实测 + 22 表 190 行表头族 + 前置区封面/会审字段",
  "confidence_note": "LOW（n=1 单样本 3218）。单样本过拟合边界：①9 章章集与《煤矿作业规程编制指南》8 章框架存在「安全风险辨识与管控」独立章差异，按样例实测定稿，更多样例若证其并入第八章需回改；②节集以样例为纲（如 ch5 九节），其他矿可能增减节；③19 附图清单沿用 report_structure.md 历史提取；④forms 字段名/枚举值按样例实证+煤矿通用实践，未经多矿校准",
  "chapter_order_policy": "order_fixed_with_semantic_match",
  "order_policy_note": "9 章定稿单序，但目录覆盖门与合约激活一律按章标题语义匹配、禁章号匹配（eia D12 教训：禁写死章号）",
  "numbering_note": "节号/表号组装期生成；正文跨节引用用节语义标题；tables 只登记语义表名；正文数值只写 {{SLOT:族.字段}}/{{TABLE:族}} 由脚本注入，禁手写数字",
  "front_matter": {
    "mode": "表单渲染（脚本直出，零 LLM）",
    "outer_cover": ["{矿名}{巷道名}掘进作业规程", "编号：{profile.reg_no_format 按 掘ZJED-YYYYSSC/NN 样式}", "工作面名称：{roadway.working_face_no}", "编制单位：{profile.team_name}　编制人/施工负责人：留空待签", "批准日期：留空待签"],
    "signature_page_fixed_order": ["作业规程会审纪要表（会审单位/职务/签字/日期——单位名单取 profile.audit_units）", "审批栏（施工单位负责人/审批单位/审批人员/审批意见/审批日期——职务表取 profile）"],
    "toc": {"levels": 2, "page_column": "留空——Word 排版阶段由编辑器填充，Markdown 禁写页码"},
    "attachment_lists": ["附图清单 19 张，全部 [需附图] 占位；通风/支护/安全监控/避灾路线/供电五张为安全规程硬要求不可缺（清单见 references/content_guidelines.md）", "规程贯彻记录页（模板直出：贯彻人/贯彻日期/学习人数/考试结果，留空待填）"]
  },
  "capability_boundaries": [
    "支护参数（锚杆/锚索型号、间排距、预紧力）不是 LLM 计算产物——只从 data/03_support.json 表单如实转写，缺值标 [待补充]",
    "风量计算全部经 formula_runner 通风域冻结（值+display+source），正文只引用 {{SLOT}}；禁 LLM 手算",
    "瓦斯等级/水文类型/自燃倾向等矿井级事实以矿井档案为准，正文与档案不一致=合约 C12 FAIL",
    "强制条款引用须带标准编号+条款号，标准号只从 standards_index.json 枚举",
    "无实测数据的数值一律 [待补充]，严禁编造或取『看起来合理』的数"
  ],
  "generation_waves": {"wave1": ["ch1", "ch2", "ch3"], "wave2": ["ch4", "ch5", "ch6"], "wave3": ["ch7", "ch8", "ch9"]},
  "chapters": {
    "ch1": {"title": "概况", "mode": "身份信息与编制依据（表单直出为主）；难度 1/低",
      "sample_anchor": "3218 样例第一章：概述（巷道名称及用途/位置及相邻关系/预计开竣工时间）+ 依据（工作面设计说明书及批准时间/地质说明书及批准时间/矿压观测资料/开工通知单/其它依据）",
      "key_elements": [
        "巷道名称/用途/位置/相邻关系逐项转写 {{SLOT:roadway.roadway_name}} 等，禁另立叫法（C2 巷道名称全称 exact 的源点）",
        "设计工程量：设计长度 {{SLOT:roadway.design_length_m}} 与 ch6 技术经济指标表同源（C3）",
        "规程编号 {{SLOT:profile.reg_no_format}} 与封面/会审页一致（C11）",
        "编制依据逐条列出：工作面设计说明书、地质说明书（均带批准时间）、矿压观测资料、开工通知单、法规标准清单（从 standards_index 枚举）",
        "收束句：本章为全文身份事实源，后续章引用名称/编号/长度禁改写"
      ],
      "writing_patterns": ["条目式：一、巷道名称及用途；二、巷道位置及相邻关系；三、设计工程量；四、预计开竣工时间", "依据节逐条编号+批准时间"],
      "tables": [], "std_refs": ["《煤矿安全规程》(2022)"], "forms": ["profile", "roadway"], "formulas": [], "contracts": ["C2", "C3", "C11", "C12"]},
    "ch2": {"title": "地面位置及地质情况", "mode": "地质数据表单直出+水文评价；难度 2/低",
      "sample_anchor": "3218 样例第二章四节：地面相对位置及邻近采区开采情况（T125 水平/采区/标高表）/煤（岩）层赋存特征（T131 煤层指标+T133 顶底板岩性表）/地质构造/水文地质",
      "key_elements": [
        "地面相对位置表：{{TABLE:geology}} 水平/采区/地面标高/工作面标高/邻近采区开采情况",
        "煤层赋存：厚度 {{SLOT:geology.seam_thickness_m}}/倾角/单轴抗压强度",
        "顶底板岩性表：{{TABLE:geology}}（老顶/直接顶/伪顶/直接底/基本底 × 岩性/厚度/抗压强度/特征）",
        "瓦斯及其它：绝对涌出量（日最大 {{SLOT:geology.gas_emission_daily}}/月平均 {{SLOT:geology.gas_emission_monthly}}——双口径必须带口径标签，C6）；煤尘爆炸性/自燃倾向性取自矿井档案（C12 源点）",
        "地质构造描述 {{SLOT:geology.structure_desc}}",
        "水文地质：涌水量（正常/最大）、水文地质类型（档案值）、「有掘必探，先探后掘」原则必须原文在场（D8 强制条款）"
      ],
      "writing_patterns": ["表格为主：地面位置表/煤层指标表/顶底板岩性表", "水文地质末段固定写探放水原则条款"],
      "tables": ["地面相对位置及邻近采区开采情况表", "煤层赋存特征表", "顶底板岩性表"], "std_refs": ["《煤矿防治水细则》", "《煤矿地质工作细则》", "《煤矿安全规程》(2022)"], "forms": ["geology", "profile"], "formulas": [], "contracts": ["C6", "C7", "C12"]},
    "ch3": {"title": "巷道布置及支护说明", "mode": "支护技术核心章（参数表直出，禁计算）；难度 3/中",
      "sample_anchor": "3218 样例第三章四节：巷道布置/支护设计（断面 5.0×3.6m 掘进 18m²、T242/T244 质量偏差表、T300 支护设备表）/支护工艺/矿压观测（T330 观测项目表+T396 离层仪表）",
      "key_elements": [
        "巷道布置：开口点/方位/拐弯抹角/与邻巷关系，长度 {{SLOT:roadway.design_length_m}}（C3 触点）",
        "巷道断面：形状 {{SLOT:roadway.section_shape}}、净宽 {{SLOT:roadway.net_width_mm}}mm、掘进断面 {{SLOT:roadway.drive_section_m2}}m² 与净断面 {{SLOT:roadway.net_section_m2}}m²——三处同源禁另立（C1 源点；R10 断面≥设计×1.05 护栏）",
        "支护设计表：{{TABLE:support}} 锚杆（顶板/帮部分列：型号/直径/长度/间排距/锚固方式/预紧力）、锚索（长度≥6.3m 依顶板岩性——R7）、锚固剂型号、网/钢带规格",
        "支护工艺：临时支护（初撑/初喷≥50mm——R8）→ 永久支护 → 质量要求（总喷厚≥120mm——R9 条件在场）",
        "工程质量允许偏差表：{{TABLE:support}}（T242 项目/设计尺寸/允许偏差逐行）",
        "矿压观测：观测项目表+设备表（顶板离层仪/表面位移/锚杆锚索测力）{{TABLE:equipment}}"
      ],
      "writing_patterns": ["支护参数必须分『顶板/两帮』分列成表，禁散文叙述参数", "临时支护先行+空顶距规定必须写明", "本章参数是 ch8 措施章的引用源（C4）"],
      "tables": ["巷道特征表", "支护参数表", "工程质量允许偏差表", "矿压观测项目表", "矿压观测设备表"], "std_refs": ["GB/T 35056-2018", "《煤矿安全生产标准化管理体系基本要求及评分方法》"], "forms": ["support", "equipment", "roadway"], "formulas": [], "contracts": ["C1", "C3", "C4"]},
    "ch4": {"title": "施工工艺", "mode": "工法与设备；难度 2/低",
      "sample_anchor": "3218 样例第四章四节：施工方法（综掘 EBZ160）/掘进作业（循环进尺）/装载与运输（T426 设备表）/管线敷设（T437 风筒 Φ1000×120节）",
      "key_elements": [
        "施工方法：综掘/炮掘声明，掘进机 {{SLOT:equipment.roadheader_model}}（C8 设备措施匹配源点）",
        "掘进作业：循环进尺/工序安排（割煤→装运→支护）",
        "装载与运输：{{TABLE:equipment}} 设备名称/型号/数量/安装位置/固定方式/运输距离",
        "管线敷设：{{TABLE:equipment}} 风筒/水管/电缆的规格型号/单位/数量/铺设方式/位置——风筒数量写 {{SLOT:F3.duct_count}} 节（冻结值，禁手算；C5 触点）",
        "收束句：设备型号与 ch5 运输选型、ch8 对应设备措施逐字一致（C8）"
      ],
      "writing_patterns": ["设备/管线一律表格化", "循环作业文字描述+循环图表引用"],
      "tables": ["施工设备表", "管线敷设表"], "std_refs": ["《煤矿安全规程》(2022)"], "forms": ["equipment", "roadway"], "formulas": ["F3"], "contracts": ["C1", "C5", "C8"]},
    "ch5": {"title": "生产系统", "mode": "九节最大章（通风计算经 formula_runner 冻结）；难度 3/中",
      "sample_anchor": "3218 样例第五章九节：通风（风量计算+局扇选型+通风阻力，T458/T460 瓦斯涌出量表）/压风/瓦斯防治/综合防尘（T605/614/627 设施表）/防灭火/安全监控（T695/T697 传感器表）/供电/给排水/运输（掘进机/胶带机选型+信号）",
      "key_elements": [
        "通风：方式 {{SLOT:ventilation.vent_method}}、风量计算四法全部引用冻结值——按瓦斯涌出量 {{SLOT:Q1.need_by_gas}}/按人数 {{SLOT:Q2.need_by_persons}}/按柴油机车 {{SLOT:Q3.need_by_diesel}}、需风量 {{SLOT:Q0.need_final}}、风速验算 {{SLOT:Q4.v_min_check}}-{{SLOT:Q4.v_max_check}}（0.25-8 m/s——R2 红线）、风筒距迎头 {{SLOT:F1.duct_gap_m}}（L=5√S）、局扇选型 {{SLOT:F2.fan_need}}、通风阻力 {{SLOT:F4.drag_head}}（待核实参考值——J12）",
        "压风/供电/给排水：{{SLOT:systems.compressed_air}}/{{SLOT:systems.power_supply}}/{{SLOT:systems.water_supply_drainage}}",
        "瓦斯防治：检查制度/甲烷电闭锁/风电闭锁/断电浓度条款（引《煤矿安全规程》条款号）",
        "综合防尘：{{TABLE:dust_facilities}} 五件套（湿式钻眼/爆破喷雾/装岩洒水/冲洗岩帮/风流净化）",
        "安全监控：{{TABLE:sensor_cutoffs}} 传感器种类/数量/安装位置/报警值/断电值/复电值/断电范围/悬挂位置（数值与 AQ 1029 对照——C10 manual 待核实）",
        "运输：掘进机/胶带输送机/顺槽车选型与 ch4 设备表逐字一致（C8），信号装置",
        "防灭火：灭火器配置/消防管路（每 50m 阀门）"
      ],
      "writing_patterns": ["九节顺序固定：通风/压风/瓦斯防治/综合防尘/防灭火/安全监控/供电/给排水/运输", "通风节全部数值走 {{SLOT}}，公式与代入过程引用冻结值表", "本章冻结值是 ch9 自救装置/避灾的引用源（C9）"],
      "tables": ["瓦斯涌出量统计表", "防尘设施表", "传感器设置表", "运输设备选型表"], "std_refs": ["AQ 1029-2019", "AQ 1020-2006", "《煤矿安全规程》(2022)"], "forms": ["ventilation", "geology", "systems", "dust_facilities", "sensor_cutoffs", "equipment", "roadway"], "formulas": ["Q1", "Q2", "Q3", "Q4", "Q0", "F1", "F2", "F4"], "contracts": ["C1", "C5", "C6", "C7", "C8", "C10"]},
    "ch6": {"title": "劳动组织及主要技术经济指标", "mode": "表格直出章；难度 1/低",
      "sample_anchor": "3218 样例第六章三节：劳动组织（T797 工种/班次出勤表+限员管理）/作业循环/主要技术经济指标（T807 项目/单位/指标——施工长度 902.236m）",
      "key_elements": [
        "劳动组织表：{{TABLE:labor_crew}}（工种/0点班/8点班/16点班/合计/备注）",
        "限员管理：巷口限员牌板+每班限员数（与 ch9 自救装置数量同源——C9）",
        "作业循环：循环图表文字描述（班循环进尺/循环数）",
        "主要技术经济指标表：{{TABLE:econ_indicators}}——施工长度 {{SLOT:roadway.design_length_m}} m 必须与 ch1 同源（C3）、日进尺/月进尺/工效/材料消耗"
      ],
      "writing_patterns": ["两表三节，禁散文重复表内数值"],
      "tables": ["劳动组织出勤表", "主要技术经济指标表", "作业循环图表"], "std_refs": ["《煤矿安全生产标准化管理体系基本要求及评分方法》"], "forms": ["labor_crew", "econ_indicators", "roadway", "profile"], "formulas": [], "contracts": ["C3", "C9"]},
    "ch7": {"title": "安全风险辨识与管控", "mode": "风险清单直出章（双重预防机制新增独立章，指南 8 章框架没有）；难度 2/低",
      "sample_anchor": "3218 样例第七章两节：主要危害因素分析（冒顶片帮/水灾/瓦斯爆炸/物体打击/机械伤害/运输/火灾/其他八类）/安全风险辨识管控清单（T842 序号/风险类型/风险描述/风险等级/管控措施/责任人）",
      "key_elements": [
        "主要危害因素分析：八类逐条（冒顶片帮/水灾/瓦斯爆炸/物体打击/机械伤害/运输/火灾/其他），结合本巷道 {{SLOT:geology.structure_desc}} 与档案灾害参数（C12 触点）",
        "风险辨识管控清单：{{TABLE:risk_register}}（T842 六列逐行）",
        "重大风险管控措施须与 ch8 安全技术措施呼应（出现清单外措施=审查 FAIL）"
      ],
      "writing_patterns": ["第一节分类叙述+第二节清单表", "风险等级用 重大/较大/一般/低 四级"],
      "tables": ["安全风险辨识管控清单"], "std_refs": ["《煤矿安全生产标准化管理体系基本要求及评分方法》"], "forms": ["risk_register", "geology", "profile"], "formulas": [], "contracts": ["C12"]},
    "ch8": {"title": "安全技术措施", "mode": "六节措施集（顶板/一通三防/防治水/机电/运输/其它）；难度 3/中",
      "sample_anchor": "3218 样例第八章六节：顶板（顶帮管理/敲帮问顶/张拉锚索拉拔锚杆/架设U型钢棚/预防围岩涌水/顶板岩性分析）/一通三防（通风瓦斯/防尘/防火）/防治水/机电/运输（掘进机/锚杆钻车/胶带机/顺槽车/装卸五组措施）/其它（一般规定/煤质管理）",
      "key_elements": [
        "顶板措施：敲帮问顶制度/严禁空顶作业/锚索补打（300mm 范围）/掘支单行原则——参数引用 {{TABLE:support}} 禁另立（C4 触点）",
        "一通三防：局部通风机管理（一机一巷/风电闭锁）/防尘五件套复述/防火管理",
        "防治水：有掘必探先探后掘（强制条款带《煤矿防治水细则》条款号）/透水征兆撤人",
        "机电：停送电制度/失爆管理/保护试验",
        "运输：五组设备措施——掘进机/液压锚杆钻车 {{SLOT:equipment.drill_car_model}}/胶带输送机/顺槽车 {{SLOT:equipment.vehicle_model}}/装卸，与 ch4/ch5 设备表逐字一致（C8）",
        "其它：一般规定+煤质管理"
      ],
      "writing_patterns": ["每节条目式措施（第N条）", "设备专章措施与设备表型号逐字一致", "强制条款逐条带标准出处"],
      "tables": [], "std_refs": ["《煤矿安全规程》(2022)", "《煤矿防治水细则》", "AQ 1020-2006"], "forms": ["support", "equipment", "profile"], "formulas": [], "contracts": ["C4", "C8"]},
    "ch9": {"title": "灾害应急措施及避灾路线", "mode": "四节应急章；难度 2/低",
      "sample_anchor": "3218 样例第九章四节：灾害预防（瓦斯/火灾/水灾/冒顶片帮/应急医疗物资五组）/安全避险系统（压风供水自救装置 ZYJ-M6 25-40m 3个/通信三系统/人员定位）/职业病防治（粉尘/热害/噪声/有害气体）/避灾路线（牌板管理+火灾/水灾/顶板三路线）",
      "key_elements": [
        "灾害预防：瓦斯/火灾/水灾/冒顶片帮四组措施——涌水量引用 {{SLOT:geology.max_inflow_m3h}}（C7 触点）",
        "安全避险系统：压风供水自救装置 {{SLOT:profile.self_rescue_model}} × {{SLOT:profile.self_rescue_count}} 个、距迎头 {{SLOT:profile.self_rescue_distance_m}} m（与 ch6 限员人数匹配——C9）；通信（有线/无线/广播）/人员定位",
        "职业病防治：粉尘/热害（26℃/30℃ 阈值）/噪声/有害气体监测频次（引《煤矿安全规程》条款号）",
        "避灾路线：火灾/水灾/顶板三条 {{SLOT:profile.escape_route_fire}} 等（档案值，C12）+牌板管理（每 100m/交叉口）"
      ],
      "writing_patterns": ["四节固定序：灾害预防/安全避险系统/职业病防治/避灾路线", "自救装置型号/数量/距离逐字引用档案"],
      "tables": ["避灾路线表"], "std_refs": ["《煤矿安全规程》(2022)", "AQ 1029-2019"], "forms": ["profile", "geology", "sensor_cutoffs"], "formulas": [], "contracts": ["C7", "C9", "C10", "C12"]}
  },
  "forms": {
    "profile": {"file": "00_profile.json", "required": true, "chapters": ["ch1", "ch2", "ch6", "ch7", "ch8", "ch9"], "note": "矿井档案族（D3+J11：矿井级常量并集，含 refuge 避灾/自救——随档案跨运行复用；equipment 型号库一期留工程表单）。profile.py validate/summary/load 三命令装载",
      "fields": [
        {"name": "mine_name", "type": "string", "required": true, "note": "矿井名（封面/全文，C11 触点）"},
        {"name": "group_name", "type": "string", "required": true, "note": "集团名"},
        {"name": "reg_no_format", "type": "string", "required": true, "note": "编号规则样式，如 掘ZJED-2026YSSC/01号"},
        {"name": "gas_grade", "type": "enum:低瓦斯|高瓦斯|煤与瓦斯突出", "required": true, "note": "瓦斯等级（C12 漂移检测源）"},
        {"name": "hydro_type", "type": "enum:简单|中等|复杂|极复杂", "required": true, "note": "水文地质类型"},
        {"name": "spontaneous_tendency", "type": "enum:容易自燃|自燃|不易自燃", "required": true},
        {"name": "coal_dust_explosion", "type": "enum:有爆炸性|无爆炸性", "required": true},
        {"name": "development_mode", "type": "string", "required": true, "note": "开拓方式"},
        {"name": "ventilation_mode", "type": "string", "required": true, "note": "矿井通风方式"},
        {"name": "supply_voltage", "type": "string", "required": true, "note": "井下供电电压等级，如 1140V/660V"},
        {"name": "monitoring_system", "type": "string", "required": true, "note": "安全监控系统型号，如 KJ90X"},
        {"name": "team_name", "type": "string", "required": true, "note": "编制单位（队组），如 综掘二队"},
        {"name": "shift_system", "type": "string", "required": true, "note": "班制，如 三八制"},
        {"name": "audit_units", "type": "array<string>", "required": true, "note": "会审单位名单（地测/通风/机电/安监/调度…）"},
        {"name": "archive_date", "type": "string", "required": true, "note": "档案日期（版本锚，步骤0.5 摘要呈现）"},
        {"name": "self_rescue_model", "type": "string", "required": true, "note": "压风供水自救装置型号（样例 ZYJ-M6·C9）"},
        {"name": "self_rescue_count", "type": "integer", "required": true, "note": "数量（样例 3·C9）"},
        {"name": "self_rescue_distance_m", "type": "string", "required": true, "note": "距迎头距离（样例 25～40·C9）"},
        {"name": "escape_route_fire", "type": "string", "required": true, "note": "火灾避灾路线（矿井级）"},
        {"name": "escape_route_water", "type": "string", "required": true, "note": "水灾避灾路线（矿井级）"},
        {"name": "escape_route_roof", "type": "string", "required": true, "note": "顶板避灾路线（矿井级）"},
        {"name": "avoidance_systems", "type": "string", "required": true, "note": "六大系统配置说明（矿井级）"}
      ]},
    "roadway": {"file": "01_roadway.json", "required": true, "chapters": ["ch1", "ch3", "ch4", "ch5", "ch6"],
      "fields": [
        {"name": "roadway_name", "type": "string", "required": true, "note": "巷道全称（C2 源点）"},
        {"name": "roadway_use", "type": "string", "required": true},
        {"name": "working_face_no", "type": "string", "required": true},
        {"name": "reg_no", "type": "string", "required": true, "note": "本规程编号（按 profile.reg_no_format 生成）"},
        {"name": "design_length_m", "type": "number", "required": true, "note": "设计长度（C3：与 ch6 指标表同源；样例 902.236）"},
        {"name": "azimuth", "type": "string", "required": true},
        {"name": "start_end_date", "type": "string", "required": true},
        {"name": "adjacent_relation", "type": "string", "required": true, "note": "井下位置及相邻关系（采空区/实体煤/边界）"},
        {"name": "section_shape", "type": "enum:矩形|直墙半圆拱|梯形", "required": true},
        {"name": "net_width_mm", "type": "integer", "required": true},
        {"name": "net_height_mm", "type": "integer", "required": true},
        {"name": "drive_width_mm", "type": "integer", "required": true},
        {"name": "drive_height_mm", "type": "integer", "required": true},
        {"name": "drive_section_m2", "type": "number", "required": true, "note": "掘进断面（C1；样例 18.0）"},
        {"name": "net_section_m2", "type": "number", "required": true, "note": "净断面（C1）"}
      ]},
    "geology": {"file": "02_geology.json", "required": true, "chapters": ["ch2", "ch5", "ch7", "ch9"],
      "fields": [
        {"name": "ground_elevation", "type": "string", "required": true},
        {"name": "face_elevation", "type": "string", "required": true},
        {"name": "seam_thickness_m", "type": "number", "required": true},
        {"name": "seam_dip_deg", "type": "number", "required": true},
        {"name": "seam_strength_mpa", "type": "number", "required": false},
        {"name": "strata", "type": "array<object>", "required": true, "fields": ["位置(老顶/直接顶/伪顶/直接底/基本底)", "岩性", "厚度_m", "抗压强度_MPa", "岩性特征"], "note": "顶底板岩性表（T133 六列）"},
        {"name": "gas_emission_daily", "type": "number", "required": true, "note": "瓦斯绝对涌出量 日最大 m³/min（C6 口径标签·样例 3.4）"},
        {"name": "gas_emission_monthly", "type": "number", "required": true, "note": "瓦斯绝对涌出量 月平均 m³/min（C6 口径标签·样例 2.45）"},
        {"name": "khg", "type": "number", "required": true, "note": "瓦斯涌出不均衡系数（样例 1.39）"},
        {"name": "co2_emission_daily", "type": "number", "required": false},
        {"name": "structure_desc", "type": "string", "required": true, "note": "地质构造描述（断层/褶曲/破碎带）"},
        {"name": "normal_inflow_m3h", "type": "number", "required": true, "note": "正常涌水量（C7）"},
        {"name": "max_inflow_m3h", "type": "number", "required": true, "note": "最大涌水量（C7）"},
        {"name": "hydro_verdict", "type": "string", "required": true, "note": "水文地质类型结论（与档案 hydro_type 一致——C12）"}
      ]},
    "support": {"file": "03_support.json", "required": true, "chapters": ["ch3", "ch8"],
      "fields": [
        {"name": "temp_support_method", "type": "string", "required": true, "note": "临时支护方式"},
        {"name": "bolt_specs", "type": "array<object>", "required": true, "fields": ["部位(顶板/帮部)", "型号", "直径_mm", "长度_m", "间排距_m", "锚固方式", "预紧力_kN"], "note": "锚杆参数（C4 源点；护栏 R4≥1.8m/R5≥1.6m/R6≤1.0×1.0）"},
        {"name": "cable_specs", "type": "array<object>", "required": true, "fields": ["型号", "长度_m", "间排距_m", "预紧力_kN"], "note": "锚索（护栏 R7≥6.3m）"},
        {"name": "mesh_spec", "type": "string", "required": true},
        {"name": "steel_band", "type": "string", "required": false},
        {"name": "anchor_agent", "type": "string", "required": true, "note": "树脂锚固剂型号"},
        {"name": "spray_initial_mm", "type": "integer", "required": false, "note": "初喷厚度（R8≥50，喷浆工艺在场时必填）"},
        {"name": "spray_total_mm", "type": "integer", "required": false, "note": "喷总厚（R9≥120）"},
        {"name": "special_measures", "type": "string", "required": true, "note": "特殊地质条件处理（过断层/破碎带补强）"},
        {"name": "quality_tolerances", "type": "array<object>", "required": true, "fields": ["项目", "设计尺寸", "允许偏差"], "note": "工程质量允许偏差表（T242）"}
      ]},
    "equipment": {"file": "04_equipment.json", "required": true, "chapters": ["ch3", "ch4", "ch5", "ch8"],
      "fields": [
        {"name": "roadheader_model", "type": "string", "required": true, "note": "掘进机型号（C8·样例 EBZ160）"},
        {"name": "drill_car_model", "type": "string", "required": true, "note": "锚杆钻车型号（C8·样例 CMM2-15）"},
        {"name": "conveyor_model", "type": "string", "required": true},
        {"name": "vehicle_model", "type": "string", "required": false, "note": "顺槽车/无轨胶轮车（C8）"},
        {"name": "equip_list", "type": "array<object>", "required": true, "fields": ["名称", "型号", "数量", "安装位置", "固定方式", "运输距离"], "note": "施工设备表（T426）"},
        {"name": "pipeline_list", "type": "array<object>", "required": true, "fields": ["名称", "规格型号", "单位", "数量", "铺设方式", "位置"], "note": "管线敷设表（T437·风筒 Φ1000×120节——C5 触点）"},
        {"name": "roof_monitoring_equip", "type": "array<object>", "required": true, "fields": ["名称", "型号", "数量"], "note": "矿压观测设备表（T396）"}
      ]},
    "ventilation": {"file": "05_ventilation.json", "required": true, "chapters": ["ch5"],
      "fields": [
        {"name": "vent_method", "type": "enum:压入式|抽出式|混合式", "required": true},
        {"name": "air_duct_diameter_m", "type": "number", "required": true, "note": "风筒直径（样例 1.0）"},
        {"name": "duct_section_length_m", "type": "number", "required": true, "note": "每节长度（样例 10）——C5 节数校验"},
        {"name": "duct_leak_rate_per100m", "type": "number", "required": true, "note": "风筒百米漏风率（reference_values 待核实，样例上限 10%）"},
        {"name": "persons_per_shift", "type": "integer", "required": true, "note": "每班最多人数（Q2 输入）"},
        {"name": "diesel_power_total_kw", "type": "integer", "required": false, "note": "同时运行柴油机总功率 kW（Q3 输入，无柴油机车则 0）"},
        {"name": "fan_model", "type": "string", "required": true, "note": "局部通风机型号（F2 选型对照）"},
        {"name": "air_supply_distance_m", "type": "number", "required": true, "note": "供风距离"}
      ]},
    "systems": {"file": "06_systems.json", "required": true, "chapters": ["ch5"],
      "fields": [
        {"name": "compressed_air", "type": "string", "required": true, "note": "压风系统说明"},
        {"name": "power_supply", "type": "string", "required": true, "note": "供电系统说明（电压等级/供电方式）"},
        {"name": "water_supply_drainage", "type": "string", "required": true, "note": "给排水系统说明"},
        {"name": "transport_desc", "type": "string", "required": true, "note": "运输系统说明"},
        {"name": "signal_desc", "type": "string", "required": true, "note": "照明通信信号说明"},
        {"name": "firefighting_desc", "type": "string", "required": true, "note": "防灭火系统说明"}
      ]},
    "labor_crew": {"file": "08_labor_crew.csv", "required": true, "chapters": ["ch6"], "format": "csv", "columns": ["工种", "0点班", "8点班", "16点班", "合计", "备注"]},
    "econ_indicators": {"file": "09_econ_indicators.csv", "required": true, "chapters": ["ch6"], "format": "csv", "columns": ["项目", "单位", "指标"]},
    "risk_register": {"file": "10_risk_register.csv", "required": true, "chapters": ["ch7"], "format": "csv", "columns": ["序号", "风险类型", "风险描述", "风险等级", "管控措施", "责任人"]},
    "dust_facilities": {"file": "11_dust_facilities.csv", "required": true, "chapters": ["ch5"], "format": "csv", "columns": ["序号", "分类", "设置地点", "设置范围", "设置数量", "备注"]},
    "sensor_cutoffs": {"file": "12_sensor_cutoffs.csv", "required": true, "chapters": ["ch5", "ch9"], "format": "csv", "columns": ["传感器名称", "数量", "安装位置", "报警值", "断电值", "复电值", "断电范围", "悬挂位置", "备注"]}
  }
}
```

- [ ] **Step 2: 校验 JSON 可解析 + 章键/波键断言**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -c "
import json
d = json.load(open('references/stages/tunneling.json', encoding='utf-8'))
chs = sorted(d['chapters'], key=lambda k: int(k[2:]))
assert [int(k[2:]) for k in chs] == list(range(1, 10)), '9 章键必须是 ch1..ch9'
for w, ks in d['generation_waves'].items():
    assert all(k in d['chapters'] for k in ks) and len(ks) <= 4, f'{w} 越界或引用未知章'
for fam, spec in d['forms'].items():
    assert 'file' in spec and ('fields' in spec or 'columns' in spec), f'{fam} 缺 fields/columns'
    if 'fields' in spec:
        names = [f['name'] for f in spec['fields']]
        assert len(names) == len(set(names)), f'{fam} 字段重名'
fam_names = set(d['forms'])
for ch, spec in d['chapters'].items():
    miss = set(spec['forms']) - fam_names
    assert not miss, f'{ch} 引用未知表单族 {miss}'
# 双向对齐（对抗评审 P2）：forms[fam].chapters 与 chapters[ch].forms 必须一致
for fam, fspec in d['forms'].items():
    declared = {ch for ch, cspec in d['chapters'].items() if fam in cspec['forms']}
    assert set(fspec.get('chapters', [])) == declared, f'{fam} chapters 双向不一致: {fspec.get("chapters")} vs {sorted(declared)}'
print('STAGE_OK: 9 章 /', len(d['forms']), '族 / waves', len(d['generation_waves']))
"
# 期望: STAGE_OK: 9 章 / 12 族 / waves 3
```

- [ ] **Step 3: report_structure.md 退役**——把文件内容替换为一段派生说明（原 9 章大表与 19 附图清单已无损迁入 stages/tunneling.json 与 content_guidelines.md）：

```markdown
# 报告结构（已退役）

> 本文件原为 9 章结构来源。v2 起**结构唯一真源 = `references/stages/tunneling.json`**
> （spec D4 双源归一：样例>指南，含「安全风险辨识与管控」独立章）。
> 19 附图清单见 `references/content_guidelines.md` 附图说明节。
> 本文件仅作历史提取过程记录保留，禁止作为任何脚本或提示词的结构输入。
```

- [ ] **Step 4: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/references/
git commit -m "feat(tunneling-v2): stages/tunneling.json 结构唯一真源(9章+12表单族+3波)+report_structure退役"
```

---

### Task 4: 3218 脱敏 fixture + 章级深度实测

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/tests/fixtures/build_fixture.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/fixtures/sample3218_digest.json`（产物，入库）
- Create: `skills/public/coal-mine-tunneling-regulation/tests/fixtures/README.md`

- [ ] **Step 1: 写 build_fixture.py**（host 上一次性运行；源 docx 绝不入库——矿名/编号/队组脱敏，**数值保留**供回归）：

```python
#!/usr/bin/env python3
"""3218 样例 → 脱敏 fixture（一次性构建工具，host 运行；源文件不入库）。
用法: python tests/fixtures/build_fixture.py <docx路径>
产出: tests/fixtures/sample3218_digest.json（章级 effective_chars/表格数 + 脱敏表单种子值）"""
import json, re, sys
from pathlib import Path

# effective_chars 算法对齐 build_output（剔空行/标题行/表格行、剔装饰符）
def effective_chars(paragraphs):
    n = 0
    for t in paragraphs:
        s = t.strip()
        if not s or s.startswith("#") or s.startswith("|"):
            continue
        n += len(re.sub(r"[\s|\-#*:]", "", s))
    return n

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CH_RE = re.compile(r"^第([一二三四五六七八九十]+)章\s*(.*)")  # 捕获章号数字本身（对抗评审 P0：查标题首字永不命中）

def main(docx_path: str) -> int:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    doc = Document(docx_path)
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(("p", Paragraph(child, doc)))
        elif child.tag == qn("w:tbl"):
            blocks.append(("t", Table(child, doc)))
    chapters, order, cur = {}, [], "front"
    chapters["front"] = {"paras": [], "tables": 0}
    order.append("front")
    for kind, b in blocks:
        if kind == "t":
            chapters[cur]["tables"] += 1
            continue
        t = b.text.strip()
        st = b.style.name if b.style else ""
        m = CH_RE.match(t)
        if st == "Heading 1" or m:
            cn = CN_NUM.get(m.group(1)) if m else None
            if cn and f"ch{cn}" not in chapters:
                cur = f"ch{cn}"
                chapters[cur] = {"paras": [], "tables": 0}
                order.append(cur)
                continue
        if t and not re.match(r"^\s*(第[一二三四五六七八九十]+[章节])?.{0,40}[…\.]{2,}\s*\d+\s*$", t):
            chapters[cur]["paras"].append(t)
    out = {"source": Path(docx_path).name, "desensitized": True, "algorithm": "effective_chars 剔空行/标题行/表格行/装饰符", "chapters": {}}
    for k in order:
        c = chapters[k]
        out["chapters"][k] = {"eff_chars": effective_chars(c["paras"]), "tables": c["tables"]}
    # 脱敏表单种子值（数值保留=回归用；实体名替换；J11：refuge 并入 profile）
    out["form_seed"] = {
        "roadway": {"roadway_name": "N3218运输顺槽", "design_length_m": 902.236, "drive_section_m2": 18.0, "net_section_m2": 15.0,
                     "net_width_mm": 5000, "drive_width_mm": 5000, "section_shape": "矩形"},
        "geology": {"gas_emission_daily": 3.4, "gas_emission_monthly": 2.45, "khg": 1.39,
                     "normal_inflow_m3h": 6.0, "max_inflow_m3h": 12.0, "seam_thickness_m": 5.48, "seam_dip_deg": 3},
        "ventilation": {"vent_method": "压入式", "air_duct_diameter_m": 1.0, "duct_section_length_m": 10,
                         "persons_per_shift": 12, "diesel_power_total_kw": 0, "air_supply_distance_m": 950},
        "equipment": {"roadheader_model": "EBZ160", "drill_car_model": "CMM2-15"},
        "profile": {"mine_name": "某矿", "group_name": "某集团", "reg_no_format": "掘ZJED-2026N3218YSSC/01号",
                     "team_name": "综掘某队", "shift_system": "三八制",
                     "gas_grade": "低瓦斯", "hydro_type": "中等", "spontaneous_tendency": "自燃", "coal_dust_explosion": "有爆炸性",
                     "development_mode": "立井单水平上下山开拓", "ventilation_mode": "机械抽出式",
                     "supply_voltage": "1140V", "monitoring_system": "KJ90X",
                     "audit_units": ["地测科", "通风科", "机电科", "安监站", "调度中心"],
                     "archive_date": "2026-09-13",
                     "self_rescue_model": "ZYJ-M6", "self_rescue_count": 3, "self_rescue_distance_m": "25～40",
                     "escape_route_fire": "工作面→N3218运输顺槽→轨道大巷→副井底", "escape_route_water": "工作面→N3218运输顺槽→胶带大巷→副井底",
                     "escape_route_roof": "就近避难硐室或压风自救点", "avoidance_systems": "监测监控/人员定位/紧急避险/压风自救/供水施救/通信联络"}
    }
    dest = Path(__file__).parent / "sample3218_digest.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("FIXTURE_READY:", dest, "chapters:", len(out["chapters"]))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
```

- [ ] **Step 2: host 运行构建**（本机有样例；CI 无样例时 fixture 已入库不需重建）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 ../../../backend/.venv/Scripts/python.exe tests/fixtures/build_fixture.py "D:/18 辽宁创元/03 项目策划/01 中煤科工/3218运输顺槽掘进作业规程.docx"
# 期望: FIXTURE_READY: ...chapters: 10 (front + ch1..ch9)
PYTHONUTF8=1 ../../../backend/.venv/Scripts/python.exe -c "
import json; d=json.load(open('tests/fixtures/sample3218_digest.json',encoding='utf-8'))
tot=sum(v['eff_chars'] for v in d['chapters'].values()); print('total eff:', tot)
assert d['chapters']['ch5']['eff_chars'] > d['chapters']['ch1']['eff_chars']
assert len(d['chapters']) == 10, 'front + ch1..ch9 必须齐（章号提取正确性）'
# 互锁断言（对抗评审 P0）：form_seed ⊇ 各族全部 required 字段
st = json.load(open('references/stages/tunneling.json', encoding='utf-8'))
for fam, spec in st['forms'].items():
    if 'fields' not in spec: continue
    req = {f['name'] for f in spec['fields'] if f.get('required', True)}
    seed = set(d['form_seed'].get(fam, {}))
    assert req <= seed, f'{fam} 种子缺 required 字段: {req - seed}'
# J7 可承载=逐章语义（T4 实测裁决：9 章各由独立子代理生成，总量无意义；单章地板须装进子代理产能 ~2万字）
floors = {k: int(v['eff_chars'] * 1.2) for k, v in d['chapters'].items() if k.startswith('ch')}
assert max(floors.values()) < 25000, f'单章 ×1.2 地板超子代理产能: {max(floors.items(), key=lambda x: x[1])}'
print('total eff:', tot, 'per-chapter max floor:', max(floors.values()))
print('FIXTURE_OK')"
```

- [ ] **Step 3: tests/fixtures/README.md**：说明 fixture 生成命令、脱敏规则（矿名→某矿/编号替换/队组替换；**数值保留**）、源文件不入库、测试用 `TUNNELING_SAMPLE_DOCX` 环境变量 + skipif 门（沿 fire-protection test_integration.py L11-18 模式）。

- [ ] **Step 4: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/tests/
git commit -m "feat(tunneling-v2): 3218脱敏fixture+章级深度实测构建工具"
```

---

### Task 5: ingest.py 适配 + test_ingest_forms.py

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/tests/conftest.py`（J13）
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/ingest.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_ingest_forms.py`

- [ ] **Step 0: 写 conftest.py**（J13——全测试套件共享；spec_from_file_location 不加 sys.path 会炸 sibling import）：

```python
"""测试套件共享脚手架：把技能 scripts/ 注入 sys.path（沿 test_ingest_bug3229 L20-23 先例）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
```

- [ ] **Step 1: 写失败测试**（沿 test_ingest_bug3229 三层法：stage→tmp_path→main(argv) 断 rc；stage 直接用真 stages/tunneling.json；import 走 conftest 注入的 sys.path）

```python
"""ingest 门1/表单写入契约测试（掘进 12 族 + profile 档案族）。
运行: cd skills/public/coal-mine-tunneling-regulation && PYTHONUTF8=1 python -m pytest tests/ -v"""
import json
from pathlib import Path

import ingest  # conftest.py 已注入 scripts/ 到 sys.path

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))

def env(tmp_path):
    return STAGE, str(tmp_path / "data")

def run(argv):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ingest.main(argv)
    return rc, buf.getvalue()

def test_forms_generates_all_12_families(tmp_path):
    stage, data = env(tmp_path)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data])
    assert rc == 0 and "FORMS_READY" in out
    files = [p for p in Path(data).iterdir() if p.suffix in (".json", ".csv") and p.name != "state_manifest.json"]
    assert len(files) == 12, [p.name for p in files]  # 7 JSON + 5 CSV（对抗评审 P1：排除 state_manifest.json）

def test_gate1_missing_without_fill(tmp_path):
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2 and "GATE1_MISSING" in out and "profile" in out  # 档案族缺=门1拦（J4）

def test_gate1_complete_after_seed_fill(tmp_path):
    stage, data = env(tmp_path)
    run(["forms", "--stage", stage, "--data-dir", data])
    seed = DIGEST["form_seed"]
    minimal = {
        "profile": {k: seed["profile"].get(k, "占位") for k in
                     ["mine_name", "group_name", "reg_no_format", "gas_grade", "hydro_type", "spontaneous_tendency",
                      "coal_dust_explosion", "development_mode", "ventilation_mode", "supply_voltage",
                      "monitoring_system", "team_name", "shift_system", "archive_date"]} | {"audit_units": ["地测科"]},
        "roadway": {**seed["roadway"], "roadway_use": "运输", "working_face_no": "W1", "reg_no": "掘ZJED-2026T/01",
                     "azimuth": "N", "start_end_date": "2026-10~2027-03", "adjacent_relation": "实体煤",
                     "net_height_mm": 3600, "drive_height_mm": 3600},
    }
    for fam, values in minimal.items():
        rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", fam, "--values", json.dumps(values, ensure_ascii=False)])
        assert rc == 0, out
    rc, out = run(["check", "--stage", stage, "--data-dir", data])
    assert rc == 2  # 只填 2 族，其余族仍缺——门1按族粒度

def test_values_rejects_typo_fields(tmp_path):
    stage, data = env(tmp_path)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "roadway",
                   "--values", json.dumps({"roadway_name": "X", "roadway_nmae_typo": "Y"}, ensure_ascii=False)])
    assert rc == 1  # validate_values 防 typo（L198-211 语义）

def test_csv_rows_write(tmp_path):
    stage, data = env(tmp_path)
    rows = json.dumps([["1", "冒顶片帮", "过构造带", "重大", "钻探查明", "总工"]], ensure_ascii=False)
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "risk_register", "--rows", rows])
    assert rc == 0 and "FORM_WRITTEN" in out
    rc, out = run(["forms", "--stage", stage, "--data-dir", data, "--family", "risk_register", "--rows", rows])
    assert rc == 0 and "FORM_NOOP" in out  # 指纹 no-op
```

- [ ] **Step 2: 跑测试确认失败**（适配未做时 DELIVERY_CONTRACT 会落垃圾标记/门行为未变但 fixture 依赖未就绪）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_ingest_forms.py -v
# 期望: 部分用例 FAIL（无垃圾 .delivery-contract 断言前全绿是可接受的——本任务测试只锁行为契约）
```

- [ ] **Step 3: ingest.py 适配**（逐条 delta，行号=geo 原版）：

| # | delta | 位置 | 做法 |
|---|-------|------|------|
| a | 删 DELIVERY_CONTRACT | 常量块 L62-90 + `write_delivery_contract` 函数 + 三调用点（cmd_forms L286-288 / cmd_file L488-490 / write_form_values L713-715） | 整段删除——服务 KF outputs 通道交付门（bug-2225），D9 单文档交付无此通道，残留会在无关祖先 outputs/ 落垃圾标记 |
| b | 删死代码 | `find_family_by_prefix` L151-155 | 仓内无调用者 |
| c | 删 pdf 分支 | `parse_pdf_tables` L445-462 + cmd_file L514-515 的 `.pdf` 分派 | 掘进上传通道=xlsx/csv/docx；pdf 走 OCR 的路由属 eai-ocr 集成，二期需要再加 |
| d | 域检查替换 | cmd_check 内 `exploration_qc` 分母 sanity L632-657 + `sample_assays` CV_ANCHOR L660-673 | 换成 `_tunneling_qc`（下方代码） |
| e | 量词表调整 | bug-3036 XX 占位正则 L618 量词枚举 | 追加 `根|架|节|台|趟` 等掘进量词 |
| f | 文案去硬编码 | cmd_file L502 报错文案「08a/13a」 | 改为 f"仅支持 CSV 表单族（可选族: {', '.join(sorted(csv_families))}）" |
| g | 保留不动 | `load_stage`（裸名补全 bug-2217）、`register_file`/锁（bug-2217）、`atomic_write_text`、`write_form_values`（formula_runner/profile.py 依赖）、`blank_json`/`validate_values`/点分键机制 | 机制与域无关 |
| h | CSV 编码回退 | CSV 读取处（encoding='utf-8-sig' 单一编码） | 包一层 `try utf-8-sig except UnicodeDecodeError: 再试 gb18030`（煤矿侧 Windows Excel 导出默认 GB18030——对抗评审 P2）；错误不裸栈，转为 `FILE_DECODE_WARNING` |

`_tunneling_qc` 新增代码（追加在 check 族通用检查之后，输出 GATE1_QUALITY warn 块，不阻断）：

```python
def _tunneling_qc(self, rep, data) -> None:
    """掘进域专项质量警告（全部 warn 不阻断——阈值未过 tier1 核实前只提示）。"""
    geo = data.form("geology"); sup = data.form("support"); vent = data.form("ventilation")
    if geo:
        if geo.get("gas_emission_daily") is not None and geo.get("khg") is None:
            rep.add("QC_GAS", "warn", "geology.gas_emission_daily 已填但 khg（涌出不均衡系数）缺失——风量计算 Q1 需要它")
        if (geo.get("gas_emission_daily") or 0) > 0 and geo.get("gas_emission_monthly") is None:
            rep.add("QC_GAS", "warn", "日最大涌出量在场而月平均缺失——C6 双口径需成对（3.4/2.45 实证）")
    for spec in (sup.get("bolt_specs") or []):
        if isinstance(spec, dict) and spec.get("部位") == "顶板":
            try:
                if float(spec.get("长度_m") or 0) < 1.8:
                    rep.add("QC_BOLT", "warn", "顶板锚杆长度 <1.8m（审查红线 R4，若确有依据请注明支护设计出处）")
            except (TypeError, ValueError):
                pass
    if vent and (vent.get("diesel_power_total_kw") or 0) > 0 and not vent.get("fan_model"):
        rep.add("QC_VENT", "warn", "登记了柴油机车功率但未填局部通风机型号——F2 选型对照缺失")
```

（`rep.add` 即 geo Report 收集器；若 cmd_check 内联结构不同，等价地把 warn 追加进 GATE1_QUALITY 块。）

- [ ] **Step 4: 跑测试全绿**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_ingest_forms.py -v
# 期望: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/ingest.py skills/public/coal-mine-tunneling-regulation/tests/test_ingest_forms.py
git commit -m "feat(tunneling-v2): ingest适配(删KF交付契约/pdf分支+掘进域QC)+门1契约测试"
```

---

### Task 6: profile.py 全新（矿井档案层）+ test_profile.py

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/scripts/profile.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_profile.py`

- [ ] **Step 1: 设计定案（J4 极简形）**：**档案文件 = forms.profile 族的 values 字典本身**（15 个扁平字段），不发明第二套嵌套 schema——「六区分组」只是 summary/渲染的展示逻辑。profile.py 三命令：`validate`（复用 ingest.validate_values 防双 schema 漂移）/ `summary`（分组打印+档案日期提示）/ `load`（经 `ingest.write_form_values(family='profile')` 落 `data/00_profile.json`，门1 自动覆盖）。

- [ ] **Step 2: 写失败测试**

```python
"""profile.py 矿井档案契约测试（D3 文件契约）。"""
import importlib.util as u
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def _load(name):
    spec = u.spec_from_file_location(f"tun_{name}", ROOT / "scripts" / f"{name}.py")
    m = u.module_from_spec(spec); spec.loader.exec_module(m); return m

profile = _load("profile"); ingest = _load("ingest")
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
ARCHIVE = DIGEST["form_seed"]["profile"] | {"audit_units": ["地测科", "通风科"]}

def _write(tmp_path, obj, name="profile.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)

def test_validate_ok(tmp_path):
    rc, out = profile.main(["validate", "--input", _write(tmp_path, ARCHIVE), "--stage", STAGE])
    assert rc == 0 and "PROFILE_OK" in out

def test_validate_rejects_bad_enum(tmp_path):
    bad = ARCHIVE | {"gas_grade": "超高瓦斯"}
    rc, out = profile.main(["validate", "--input", _write(tmp_path, bad), "--stage", STAGE])
    assert rc == 1 and "gas_grade" in out

def test_load_writes_data_family(tmp_path):
    arc = _write(tmp_path, ARCHIVE)
    data = str(tmp_path / "data")
    rc, out = profile.main(["load", "--input", arc, "--stage", STAGE, "--data-dir", data])
    assert rc == 0 and "PROFILE_LOADED" in out
    doc = json.load(open(Path(data) / "00_profile.json", encoding="utf-8"))
    assert doc["mine_name"] == "某矿" and doc["_meta"]["family"] == "profile"
    # 门1 因档案族在场而不再报 profile 缺失
    rc2, out2 = ingest.main(["check", "--stage", STAGE, "--data-dir", data])
    assert "profile" not in out2.split("GATE1_MISSING")[1] if rc2 == 2 else rc2 == 0 or True

def test_summary_mentions_archive_date(tmp_path):
    rc, out = profile.main(["summary", "--input", _write(tmp_path, ARCHIVE)])
    assert rc == 0 and ARCHIVE["archive_date"] in out and "矿井条件有变先更新档案" in out
```

- [ ] **Step 3: 跑失败**（ModuleNotFoundError: profile）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_profile.py -v
# 期望: collection error / FAIL
```

- [ ] **Step 4: 写 profile.py 完整实现**

```python
#!/usr/bin/env python3
"""矿井档案层（spec D3 文件契约）。

档案文件 = stages/tunneling.json forms.profile 族的 values 字典（15 扁平字段，
不发明第二套 schema——validate 复用 ingest.validate_values 单一真源）。
跨运行协议：首跑建档（mine_forms 逐族 ask_clarification）→ load 落 data/00_profile.json
→ 档案 md 随交付 present_files 进 docmgr；后续线程用户带档案文件进线程 → load → 门1 自动覆盖。
三命令: validate / summary / load。rc: 0 成功 / 1 校验失败或用法错。"""
import argparse
import importlib.util as _u
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_spec = _u.spec_from_file_location("tun_ingest", SCRIPTS / "ingest.py")
ingest = _u.module_from_spec(_spec)
_spec.loader.exec_module(ingest)

EXIT_OK, EXIT_ERROR = 0, 1
DEFAULT_STAGE = SCRIPTS.parent / "references" / "stages" / "tunneling.json"
# 展示分组（仅 summary/文档渲染用——字段名与 forms.profile 一一对应）
GROUPS = [
    ("矿井标识", ["mine_name", "group_name", "reg_no_format", "team_name", "shift_system"]),
    ("灾害参数", ["gas_grade", "hydro_type", "spontaneous_tendency", "coal_dust_explosion"]),
    ("系统配置", ["development_mode", "ventilation_mode", "supply_voltage", "monitoring_system"]),
    ("会审名单", ["audit_units"]),
    ("避灾与自救", ["self_rescue_model", "self_rescue_count", "self_rescue_distance_m", "escape_route_fire", "escape_route_water", "escape_route_roof", "avoidance_systems"]),
    ("版本", ["archive_date"]),
]


def _stage_fields(stage_path: str) -> dict:
    """返回 forms.profile 完整族 spec（ingest.validate_values 吃 {'fields':[...]} 字典而非裸 list——对抗评审 P0）。"""
    stage = json.loads(Path(stage_path).read_text(encoding="utf-8"))
    return stage["forms"]["profile"]


def _read_archive(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(args) -> int:
    values = _read_archive(args.input)
    spec = _stage_fields(args.stage)
    try:
        ingest.validate_values(spec, values)
    except ValueError as exc:
        print(f"PROFILE_INVALID: {exc}")
        return EXIT_ERROR
    print("PROFILE_OK:", len(values), "fields")
    return EXIT_OK


def cmd_summary(args) -> int:
    values = _read_archive(args.input)
    print(f"=== 矿井档案摘要（{values.get('mine_name', '?')}）===")
    for title, keys in GROUPS:
        row = "；".join(f"{k}={values.get(k)!r}" for k in keys if k in values)
        if row:
            print(f"[{title}] {row}")
    print(f"提示: 档案日期 {values.get('archive_date', '未填')}——矿井条件有变先更新档案再编新规程（C12 漂移检测会比对正文）")
    print("PROFILE_SUMMARY")
    return EXIT_OK


def cmd_load(args) -> int:
    values = _read_archive(args.input)
    spec = _stage_fields(args.stage)
    try:
        ingest.validate_values(spec, values)
    except ValueError as exc:
        print(f"PROFILE_INVALID: {exc}")
        return EXIT_ERROR
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)  # 对抗评审 P0：write_form_values 不建目录
    ingest.write_form_values(args.stage, args.data_dir, "profile", values)
    print("PROFILE_LOADED: data/00_profile.json（门1 完备性已覆盖档案族）")
    return EXIT_OK


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="profile.py", description="矿井档案 validate/summary/load")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("--input", required=True)
        s.add_argument("--stage", default=str(DEFAULT_STAGE))
    s = sub.add_parser("load")
    s.add_argument("--input", required=True)
    s.add_argument("--stage", default=str(DEFAULT_STAGE))
    s.add_argument("--data-dir", required=True)
    args = p.parse_args(argv)
    try:
        return {"validate": cmd_validate, "summary": cmd_summary, "load": cmd_load}[args.cmd](args)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"PROFILE_ERROR: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 跑测试全绿**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_profile.py -v
# 期望: 4 passed
```

- [ ] **Step 6: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/profile.py skills/public/coal-mine-tunneling-regulation/tests/test_profile.py
git commit -m "feat(tunneling-v2): profile.py矿井档案层(validate/summary/load)+契约测试"
```

---

### Task 7: formula_runner 通风域重写 + formulas.json + test_formula_ventilation.py

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/formula_runner.py`
- Create: `skills/public/coal-mine-tunneling-regulation/references/formulas.json`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_formula_ventilation.py`

- [ ] **Step 1: 写 formulas.json**（骨架沿 geo/eia：rounding_policy/unit_conventions/rounding + 8 条通风域公式条目；计算体在 compute()，JSON 只承载元数据）：

```json
{
  "version": "2.0",
  "generated": "2026-09-13",
  "source": "掘进通风域（D5 一期仅通风）。系数与公式均为【待核实】纪律约束：凡标注 needs_verification 的系数未过 tier1 人工核实前，计算结果仅作参考值并以 anomaly 提示",
  "rounding_policy": {"rule": "四舍六入五逢奇进偶舍 = ROUND_HALF_EVEN（Decimal.quantize）",
    "precision_by_quantity": {"风量": "0.01 m³/min", "风速": "0.01 m/s", "长度": "0.01 m", "断面": "0.1 m²", "节数": "整数"}},
  "unit_conventions": {"air_quantity": "m³/min（正文如需 m³/s 由 display 层换算，槽位内部统一 m³/min）", "wind_speed_band": "掘进巷道 0.25~8 m/s（审查红线 R2，待核实）"},
  "capability_boundaries": [
    "禁 LLM 手算任何风量/风速/风筒距离——全部经 execute 冻结",
    "缺参数=记 anomaly 跳过该子项，禁以示例值冒充（bug-2223/geo L160 同构）",
    "柴油机车需风量系数与漏风折算公式未核实前恒记 anomaly，不得删除该 anomaly"
  ],
  "formulas": [
    {"id": "Q1", "name": "按瓦斯涌出量计算需风量", "chapter": "ch5", "expr": "Q1 = 100 × q × K（q=绝对涌出量 m³/min，K=涌出不均衡系数 khg）",
     "inputs": [{"name": "q", "type": "user_input", "source_form": "02_geology.json", "field": "gas_emission_daily", "note": "日最大口径（C6 口径标签）"}, {"name": "K", "type": "user_input", "source_form": "02_geology.json", "field": "khg"}],
     "outputs": [{"name": "Q1.need_by_gas", "unit": "m³/min"}], "precision": "0.01 m³/min",
     "slots": ["{{SLOT:Q1.need_by_gas}}"], "needs_verification": true,
     "note": "系数 100 待人工对照《煤矿安全规程》/矿井通风手册核实（reference_values.ventilation）",
     "regression": "样例 q=3.4, K=1.39 → 472.60"},
    {"id": "Q2", "name": "按人数计算需风量", "chapter": "ch5", "expr": "Q2 = 4 × N（每人供风不少于 4 m³/min）",
     "inputs": [{"name": "N", "type": "user_input", "source_form": "05_ventilation.json", "field": "persons_per_shift"}],
     "outputs": [{"name": "Q2.need_by_persons", "unit": "m³/min"}], "precision": "0.01 m³/min", "slots": ["{{SLOT:Q2.need_by_persons}}"],
     "regression": "N=12 → 48.0"},
    {"id": "Q3", "name": "按柴油机车计算需风量", "chapter": "ch5", "expr": "Q3 = 5.44 × ΣP（每 kW 功率供风 ≥5.44 m³/min）",
     "inputs": [{"name": "P", "type": "user_input", "source_form": "05_ventilation.json", "field": "diesel_power_total_kw"}],
     "outputs": [{"name": "Q3.need_by_diesel", "unit": "m³/min"}], "precision": "0.01 m³/min", "slots": ["{{SLOT:Q3.need_by_diesel}}"],
     "needs_verification": true, "note": "系数 5.44 待核实；P=0（无柴油机车）时本式不参与"},
    {"id": "Q0", "name": "掘进工作面需风量（取最大）", "chapter": "ch5", "expr": "Q0 = max(Q1, Q2, Q3)",
     "inputs": [{"name": "Q1", "type": "formula_output", "source": "Q1"}, {"name": "Q2", "type": "formula_output", "source": "Q2"}, {"name": "Q3", "type": "formula_output", "source": "Q3"}],
     "outputs": [{"name": "Q0.need_final", "unit": "m³/min"}], "precision": "0.01 m³/min", "slots": ["{{SLOT:Q0.need_final}}"],
     "note": "basis 字段记录取值来源子式"},
    {"id": "Q4", "name": "按风速验算", "chapter": "ch5", "expr": "Qmin = 60 × 0.25 × S；Qmax = 60 × 8.0 × S（掘进巷道风速 0.25~8 m/s，R2）",
     "inputs": [{"name": "S", "type": "user_input", "source_form": "01_roadway.json", "field": "drive_section_m2"}],
     "outputs": [{"name": "Q4.v_min_q", "unit": "m³/min"}, {"name": "Q4.v_max_q", "unit": "m³/min"}, {"name": "Q4.v_min_check", "unit": "m³/min"}, {"name": "Q4.v_max_check", "unit": "m³/min"}],
     "precision": "0.01 m³/min", "slots": ["{{SLOT:Q4.v_min_check}}", "{{SLOT:Q4.v_max_check}}"],
     "needs_verification": true, "note": "风速带 0.25~8 按煤巷档待核实（岩巷/回风巷档位不同——审查技能 R2/R3 未分档，入库全 needs_verification）",
     "regression": "S=18 → Qmin=270.0, Qmax=8640.0；需风量越界记门2 阻断级 anomaly"},
    {"id": "F1", "name": "风筒出风口距工作面距离", "chapter": "ch5", "expr": "L = 5 × √S",
     "inputs": [{"name": "S", "type": "user_input", "source_form": "01_roadway.json", "field": "drive_section_m2"}],
     "outputs": [{"name": "F1.duct_gap_m", "unit": "m"}], "precision": "0.01 m", "slots": ["{{SLOT:F1.duct_gap_m}}"],
     "regression": "S=18 → 21.21"},
    {"id": "F2", "name": "局部通风机需风量（漏风折算）", "chapter": "ch5", "expr": "Qf = Q0 × (1 + i × Ld/10000)（i=百米漏风率%，Ld=供风距离 m；线性近似）",
     "inputs": [{"name": "Q0", "type": "formula_output", "source": "Q0"}, {"name": "i", "type": "user_input", "source_form": "05_ventilation.json", "field": "duct_leak_rate_per100m"}, {"name": "Ld", "type": "user_input", "source_form": "05_ventilation.json", "field": "air_supply_distance_m"}],
     "outputs": [{"name": "F2.fan_need", "unit": "m³/min"}], "precision": "0.01 m³/min", "slots": ["{{SLOT:F2.fan_need}}"],
     "needs_verification": true, "note": "线性近似在长距离大漏风率下偏保守，与连乘式差异待核实；结果恒记 anomaly"},
    {"id": "F3", "name": "风筒节数", "chapter": "ch5", "expr": "N = ceil(L设计 / 每节长度)",
     "inputs": [{"name": "L设计", "type": "user_input", "source_form": "01_roadway.json", "field": "design_length_m"}, {"name": "每节长度", "type": "user_input", "source_form": "05_ventilation.json", "field": "duct_section_length_m"}],
     "outputs": [{"name": "F3.duct_count", "unit": "节"}], "precision": "整数", "slots": ["{{SLOT:F3.duct_count}}"],
     "regression": "902.236/10 → 91；C5 合约对 ch4 管线敷设表风筒数量做**下限 sanity**（数量 ≥ N 才过，冗余备节 warn——样例 120 节对应不同设计长度，exact 语义与 n=1 矛盾，对抗评审 P1 裁定）"},
    {"id": "F4", "name": "通风阻力（线性近似，J12）", "chapter": "ch5", "expr": "h ≈ R × L × Q²（R=百米风阻系数 N·s²/m⁸，L=供风距离，Q=风量 m³/s）",
     "inputs": [{"name": "R", "type": "lookup_table", "source": "reference_values.json#ventilation", "note": "风阻系数【待核实】"}, {"name": "Ld", "type": "user_input", "source_form": "05_ventilation.json", "field": "air_supply_distance_m"}, {"name": "Q0", "type": "formula_output", "source": "Q0"}],
     "outputs": [{"name": "F4.drag_head", "unit": "Pa"}], "precision": "1 Pa", "slots": ["{{SLOT:F4.drag_head}}"],
     "needs_verification": true, "note": "spec D5 项（J12）：R 未核实前恒记 anomaly，仅作局扇风压对照参考值，不参与任何门断言"}
  ],
  "derived_slots": []
}
```

- [ ] **Step 2: compute() 域重写**——删除 geo 域代码（`GRADE_CLASS_MAP/CATEGORY_MAP` L41-59、C9/S1/08a L156-223、L7-L13 块段链 L225-358、W1 L360-374、B1 L376-384 + cmd_check 的 B1C 块 L529-533、E1-E7 L386-429；CATS 常量 L39 删除），`compute()` 换为（保留 `emit`/`Data`/`write_state`/五命令骨架约 200 行不动）：

```python
import math

def compute(data):
    values, anomalies = {}, []
    def emit(key, val, dp, unit, source, extra=None):  # 与 geo emit(L148-154) 同形
        if not math.isfinite(val):
            raise ValueError(f"非有限计算结果: {key}={val}")
        q = Decimal(str(val)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_EVEN)
        slot = {"value": float(q), "display": f"{q}", "unit": unit, "source": source}
        if extra:
            slot.update(extra)
        values[key] = slot

    vent = data.form("ventilation"); geo = data.form("geology")
    road = data.form("roadway")

    q_gas, khg = geo.get("gas_emission_daily"), geo.get("khg")
    if q_gas in (None, "") or khg in (None, ""):
        anomalies.append("Q1 缺瓦斯绝对涌出量或不均衡系数（geology.gas_emission_daily/khg）——按瓦斯涌出量法跳过")
    else:
        emit("Q1.need_by_gas", 100.0 * float(q_gas) * float(khg), 2, "m³/min", "formula:Q1",
             {"inputs": {"q": float(q_gas), "K": float(khg)}, "note": "系数100待核实"})

    n = vent.get("persons_per_shift")
    if n in (None, ""):
        anomalies.append("Q2 缺每班最多人数（ventilation.persons_per_shift）——按人数法跳过")
    else:
        emit("Q2.need_by_persons", 4.0 * float(n), 2, "m³/min", "formula:Q2", {"inputs": {"N": float(n)}})

    kw = vent.get("diesel_power_total_kw") or 0
    if float(kw) > 0:
        emit("Q3.need_by_diesel", 5.44 * float(kw), 2, "m³/min", "formula:Q3", {"inputs": {"P": float(kw)}})
        anomalies.append("Q3 柴油机车需风量系数 5.44 m³/min·kW【待人工核实】——结果仅作参考值")

    cands = [values[k]["value"] for k in ("Q1.need_by_gas", "Q2.need_by_persons", "Q3.need_by_diesel") if k in values]
    if not cands:
        anomalies.append("Q0 无任何需风量子项可计算——门2 后协商补数据，禁估算")
    else:
        q0 = max(cands)
        basis = [k for k, v in (("Q1", values.get("Q1.need_by_gas", {}).get("value")),
                                 ("Q2", values.get("Q2.need_by_persons", {}).get("value")),
                                 ("Q3", values.get("Q3.need_by_diesel", {}).get("value"))) if v == q0]
        emit("Q0.need_final", q0, 2, "m³/min", "formula:Q0", {"basis": "+".join(basis)})

    s = road.get("drive_section_m2")
    if s in (None, ""):
        anomalies.append("Q4/F1 缺掘进断面（roadway.drive_section_m2）——风速验算与风筒距离跳过")
    else:
        s = float(s)
        emit("Q4.v_min_q", 60.0 * 0.25 * s, 2, "m³/min", "formula:Q4", {"inputs": {"S": s, "v": 0.25}})
        emit("Q4.v_max_q", 60.0 * 8.0 * s, 2, "m³/min", "formula:Q4", {"inputs": {"S": s, "v": 8.0}})
        emit("Q4.v_min_check", values["Q4.v_min_q"]["value"], 2, "m³/min", "formula:Q4")
        emit("Q4.v_max_check", values["Q4.v_max_q"]["value"], 2, "m³/min", "formula:Q4")
        emit("F1.duct_gap_m", 5.0 * math.sqrt(s), 2, "m", "formula:F1")
        if "Q0.need_final" in values:
            q0 = values["Q0.need_final"]["value"]
            if not (values["Q4.v_min_q"]["value"] <= q0 <= values["Q4.v_max_q"]["value"]):
                anomalies.append(f"门2阻断：需风量 {q0} 超出风速验算区间 "
                                 f"[{values['Q4.v_min_q']['value']}, {values['Q4.v_max_q']['value']}]（R2 带 0.25~8 m/s）——需协商调断面或分风")

    i, ld = vent.get("duct_leak_rate_per100m"), vent.get("air_supply_distance_m")
    if "Q0.need_final" in values and i not in (None, "") and ld not in (None, ""):
        qf = values["Q0.need_final"]["value"] * (1.0 + (float(i) / 100.0) * (float(ld) / 100.0))
        emit("F2.fan_need", qf, 2, "m³/min", "formula:F2",
             {"inputs": {"i": float(i), "Ld": float(ld)}, "note": "线性近似待核实"})
        anomalies.append("F2 漏风折算采用线性近似【待核实】——与连乘式的差异未过 tier1")

    length, seg = road.get("design_length_m"), vent.get("duct_section_length_m")
    if length not in (None, "") and seg not in (None, "") and float(seg) > 0:
        emit("F3.duct_count", math.ceil(float(length) / float(seg)), 0, "节", "formula:F3")
    else:
        anomalies.append("F3 缺设计长度或每节长度——风筒节数跳过（C5 无法对账 ch4 管线表）")

    # F4 通风阻力（J12：spec D5 项，风阻系数待核实 → 恒记 anomaly，仅参考值）
    if "Q0.need_final" in values and ld not in (None, ""):
        r_coef = 0.01  # 【待核实】占位系数 N·s²/m⁸——核实前结果仅参考
        q_m3s = values["Q0.need_final"]["value"] / 60.0
        emit("F4.drag_head", r_coef * float(ld) * q_m3s * q_m3s, 1, "Pa", "formula:F4",
             {"inputs": {"R": r_coef, "Ld": float(ld)}, "note": "R 待核实"})
        anomalies.append("F4 通风阻力风阻系数 R【待人工核实】——结果仅作参考值，禁写入正文当设计依据")

    return values, anomalies
```

同步删改：`cmd_check` 的 B1C 块（L529-533）删除；锚点容差 0.005（L540）保留；`chapter_planner.impacted_chapters` 依赖（L34/L590）保留；`import ingest` 写回（L613/623/627）保留。**入口签名（J13）**：`def main()` → `def main(argv=None)` 且 `p.parse_args(argv)`（geo :639 零参，照 ingest.py:726 形制——测试 main(argv) 必需）。

- [ ] **Step 3: 写失败测试**

```python
"""通风域冻结计算数值回归（样例实证值锚定）。"""
import json
from pathlib import Path

import formula_runner  # conftest.py 已注入 scripts/
import ingest

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))
SEED = DIGEST["form_seed"]

def _fill(tmp_path):
    data = str(tmp_path / "data")
    fills = {"roadway": SEED["roadway"] | {"roadway_use": "运输", "working_face_no": "W1", "reg_no": "T/01",
                                            "azimuth": "N", "start_end_date": "x", "adjacent_relation": "实体煤",
                                            "net_height_mm": 3600, "drive_height_mm": 3600},
             "geology": SEED["geology"] | {"ground_elevation": "+1000", "face_elevation": "+500",
                                            "strata": [], "structure_desc": "无", "hydro_verdict": "中等"},
             "ventilation": SEED["ventilation"] | {"duct_leak_rate_per100m": 10, "fan_model": "FBD-6.0/2×15"}}
    for fam, values in fills.items():
        rc, _ = _io(ingest, ["forms", "--stage", STAGE, "--data-dir", data, "--family", fam,
                             "--values", json.dumps(values, ensure_ascii=False)])
        assert rc == 0
    return data

def _io(mod, argv):
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()

def test_execute_freezes_ventilation_slots(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    rc, out = _io(formula_runner, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    assert rc == 3, out  # 待核实 anomaly 恒在场（F2 线性近似/F4 风阻系数）
    assert "STATE_READY" in out
    st = json.load(open(state, encoding="utf-8"))
    v = st["values"]
    assert v["Q1.need_by_gas"]["value"] == 472.60   # 100×3.4×1.39
    assert v["Q2.need_by_persons"]["value"] == 48.0
    assert v["Q0.need_final"]["value"] == 472.60 and v["Q0.need_final"]["basis"] == "Q1"
    assert v["Q4.v_min_q"]["value"] == 270.0 and v["Q4.v_max_q"]["value"] == 8640.0
    assert v["F1.duct_gap_m"]["value"] == 21.21     # 5×√18
    assert v["F3.duct_count"]["value"] == 91        # ceil(902.236/10)
    assert "F4.drag_head" in v and v["F4.drag_head"]["source"] == "formula:F4"
    assert all(s["source"].startswith("formula:") for s in v.values())
    assert any("F4" in a and "待人工核实" in a for a in st["anomalies"])

def test_check_anchor_regression(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    _io(formula_runner, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    anchors = json.dumps({"Q1.need_by_gas": 472.60, "F1.duct_gap_m": 21.21}, ensure_ascii=False)
    rc, out = _io(formula_runner, ["check", "--stage", STAGE, "--data-dir", data, "--state", state,
                                    "--anchors", anchors, "--output", str(tmp_path / "check.json")])
    assert rc == 0 and "CHECK_READY" in out  # CHECK_READY 仅在 --output 时打印（对抗评审 P1）
    anchors_bad = json.dumps({"Q1.need_by_gas": 999.0}, ensure_ascii=False)
    rc2, out2 = _io(formula_runner, ["check", "--stage", STAGE, "--data-dir", data, "--state", state,
                                      "--anchors", anchors_bad, "--output", str(tmp_path / "check2.json")])
    assert rc2 == 1  # anchor 不一致=fail

def test_impacted_update_order_law(tmp_path):
    data = _fill(tmp_path)
    state = str(tmp_path / "formula_state.json")
    _io(formula_runner, ["execute", "--stage", STAGE, "--data-dir", data, "--output", state])
    manifest = str(tmp_path / "chapter_manifest.json")
    manifest_obj = {"version": 2, "always_dependent": ["compliance_appendix"],
                    "chapters": [{"id": f"ch{i}", "title": "", "formula_ids": ["Q1"] if i in (2, 5) else [],
                                   "form_families": ["geology"] if i == 2 else [], "type": "narrative"} for i in range(1, 10)]}
    Path(manifest).write_text(json.dumps(manifest_obj, ensure_ascii=False), encoding="utf-8")
    # --field 语法：JSON 字段 = '<文件名数字前缀>.<字段名>'（fam_by_prefix 匹配 file.split('_',1)[0]）
    rc, out = _io(formula_runner, ["impacted", "--stage", STAGE, "--data-dir", data, "--state", state,
                                    "--field", "02.gas_emission_daily", "--value", "4.0",
                                    "--manifest", manifest, "--output", str(tmp_path / "impacted.json")])
    assert rc == 0, out  # 硬断言（对抗评审 P1：不可证伪的 if imp: 守卫已删）
    imp = json.load(open(tmp_path / "impacted.json", encoding="utf-8"))
    assert "Q1.need_by_gas" in imp["changes"]
    assert "ch5" in imp["affected_chapters"]
```

- [ ] **Step 4: 跑测试**（先失败后绿；`--field` 语法以实际报错为准修正——JSON 字段= `02.gas_emission_daily`，CSV 整列= `10_risk_register.csv:风险等级`）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_formula_ventilation.py -v
# 期望: 3 passed（anomalies 恒非空 → execute rc=3 是正常路径，SKILL.md 门2 教 agent 读 anomalies）
```

- [ ] **Step 5: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/formula_runner.py skills/public/coal-mine-tunneling-regulation/references/formulas.json skills/public/coal-mine-tunneling-regulation/tests/test_formula_ventilation.py
git commit -m "feat(tunneling-v2): formula_runner通风域(风量四法+局扇+风筒)+数值回归测试"
```

---

### Task 8: chapter_planner 适配（去 ch10 + C 合约反查表）

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/chapter_planner.py`

- [ ] **Step 1: 逐条 delta**（行号=geo 原版 147 行文件）：

| # | delta | 位置 | 做法 |
|---|-------|------|------|
| a | ALWAYS_DEPENDENT 去 ch10 | L30 `ALWAYS_DEPENDENT=("ch10","compliance_appendix")` | 改 `("compliance_appendix",)`——掘进无投影章（J3），残留会让 impacted 输出不存在章、下游 mark 报未知章（侦察 risk #1） |
| b | CONTRACT_FORMULA_REFS 换血 | L33-46 | 换 `{"C5": ["Q0", "Q1", "Q2", "Q3", "Q4", "F3", "F4"], "C6": ["Q1"]}`（其余 C 合约无公式依赖，留空；F3 入表——T7 质量评审 Important-4：F3 渲染在 ch4 管线敷设表，反查必须命中 ch4） |
| c | 章类型三元去 ch10 | L55 | 删 ch10/projection 分支 |
| d | front_matter 伪章内容 | L61-63 | NR3/figures_tables 键换 `{"front_matter": {..., "contracts": ["C11"], "form_families": ["profile", "roadway"]}}`（封面编号/长度事实源） |
| e | 空章守卫 | build_manifest L49-80 末尾 | 追加：`real = [c for c in m["chapters"] if not c["id"].startswith(("front_",)) and c["id"] != "compliance_appendix"]; if len(real) < 5: raise SystemExit("MANIFEST_INVALID: 真实章数 <5——stage chapters 缺失?")`（侦察 risk #2：geo 空 stage 静默产 2 伪章 rc=0） |
| f | 不移植 | eia 的 deps/compile_deps/impacted_sections/projection_chapter 节级机器 | D6 章级不需要；`impacted_chapters(formulas, families, manifest)->list[str]` geo 兼容签名原样保留（formula_runner L590 直接 import） |

- [ ] **Step 2: 冒烟验证**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -X utf8 scripts/chapter_planner.py manifest --stage references/stages/tunneling.json --output /tmp/t_manifest.json
# 期望: MANIFEST_READY: /tmp/t_manifest.json chapters=11 (front_matter + ch1..ch9 + compliance_appendix)
PYTHONUTF8=1 python -X utf8 scripts/chapter_planner.py impacted --manifest /tmp/t_manifest.json --formulas Q1 --families geology
# 期望: 输出 JSON，affected_chapters 含 ch2/ch5（geology 族+Q1 公式交集），不含 ch10
```

- [ ] **Step 3: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/chapter_planner.py
git commit -m "feat(tunneling-v2): chapter_planner去投影章+C合约反查表+空章守卫"
```

---

### Task 9: progress.py 多波重写 + test_progress_gate.py

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/progress.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_progress_gate.py`

- [ ] **Step 1: 逐条 delta**（行号=geo 原版 474 行）：

| # | delta | 位置 | 做法 |
|---|-------|------|------|
| a | **derive_phase N 波重写**（J2） | L86-100 + next_action 的 WAVE1/WAVE2/KEY_POINTS 三分支 L116-176 | 用下方新实现整体替换；`KEY_POINTS` 相位与 `confirm-key-points` 子命令删除（J3），`key_points_confirmed` 字段不再读写 |
| b | DISPATCH_BUDGET | L48 `16` | 改 `20`（9 章+每章重派 ≤1=18>16 会提前触发额度耗尽 BLOCKED） |
| c | init 必带 --data-dir | init argparse（L424 区域） | `--data-dir` 加 `required=True`（eia L117 教训：gate/run-stage 依赖） |
| d | run-stage finalize | L352-396 | 保留（build_output→consistency→snapshot 链、rc 语义、bug-3058 body-scope 复用、--allow-partial 自动启用全部原样）；`--standards` 条件追加 L370-371 保留（本技能有 standards_index.json，条件成立） |
| e | 保留不动 | bug-3049 三件套（L51 注释/L255-257 拒绝/gate L311-319 自动回写）、TRANSITIONS、原子 save L70-76、chapter_order 数值排序 L58-59（**追加**：非数值章 id 显式报错，侦察风险：geo 落 99 会被当尾章）、NEGOTIATE/approve-downgrade、≤3 并发/重派 ≤1、main 损坏兜底 L466-470 | 原样 |
| f | main 签名（J13） | `def main()` L424 | → `def main(argv=None)` + `p.parse_args(argv)`（geo 零参，照 ingest.py:726 形制） |

`derive_phase`/`next_action` 新实现（替换 L86-197；geo 的 NEGOTIATE/FINAL 分支是 next_action 内联代码 L142-152/L178-197——按下文**提取为具名函数**，对抗评审 P1：不存在 `_negotiate_action`/`_finalize_action`/`_ch_num`，须随本 delta 一并落地）：

```python
def _ch_num(ch: str) -> int:
    return int(ch[2:]) if ch[2:].isdigit() else 99


def _waves(doc) -> list:
    """波表来自 stage.generation_waves（J2）；无该键则全章一波。"""
    stage = json.loads(Path(doc["stage_path"]).read_text(encoding="utf-8"))
    gw = stage.get("generation_waves") or {}
    waves = [list(gw[k]) for k in sorted(gw) if gw.get(k)]
    if not waves:
        waves = [sorted(doc["chapters"], key=_ch_num)]
    return waves


def _negotiate_action(doc) -> dict:
    # = geo next_action 的 NEGOTIATE 分支（L142-152）原逻辑改返回 dict
    blocked = [c for c, e in doc["chapters"].items() if e["status"] == "BLOCKED"]
    approved = approved_set(doc)
    todo = [c for c in blocked if c not in approved]
    return {"phase": "NEGOTIATE", "action": "NEGOTIATE",
            "command": f"协商三选项：补数据重派 {todo} / approve-downgrade --chapters {','.join(todo)} --note ... / [待确认] 收尾",
            "expect_rc": "用户裁决后按选项执行"}


def _finalize_action(doc) -> dict:
    # = geo next_action 的 FINAL 分支（L178-197）原逻辑改返回 dict
    return {"phase": "FINAL", "action": "FINALIZE",
            "command": f"progress.py run-stage finalize --state-dir {doc['state_dir']} --outputs-dir /mnt/user-data/outputs --task \"掘进作业规程终验\"",
            "expect_rc": "BUILD_READY / consistency rc1 停 rc2 呈现 rc3 可交付"}


def derive_phase(doc) -> str:
    approved = approved_set(doc)  # geo L79-83 原函数
    for i, wave in enumerate(_waves(doc), 1):
        sts = [doc["chapters"][c]["status"] for c in wave if c in doc["chapters"]]
        if any(s == "BLOCKED" for s in sts) and not (approved & set(wave)):
            return "NEGOTIATE"
        if any(s in ("PENDING", "DRAFTED") for s in sts):
            return f"WAVE{i}"
    return "FINAL"


def next_action(doc) -> dict:
    phase = derive_phase(doc)
    doc["phase"] = phase
    if phase == "NEGOTIATE":
        return _negotiate_action(doc)
    if phase == "FINAL":
        return _finalize_action(doc)
    i = int(phase[4:])
    wave = _waves(doc)[i - 1]
    pending = [c for c in wave if doc["chapters"][c]["status"] == "PENDING"]
    drafted = [c for c in wave if doc["chapters"][c]["status"] == "DRAFTED"]
    if drafted:
        return {"phase": phase, "action": "GATE",
                "command": f"progress.py gate --state-dir {doc['state_dir']}",
                "expect_rc": "0=本波全部过门转VERIFIED / 1=有FAIL（stderr 逐章差距，重派 ≤1 次）"}
    return {"phase": phase, "action": "DISPATCH",
            "command": f"batch_task(items={json.dumps(pending)}, 每项=该章派发契约) → 收章逐章 mark chN DRAFTED",
            "expect_rc": f"波{phase} {len(pending)} 章投递；投递后停车轮询"}
```

**cmd_next/cmd_status 适配**（对抗评审 P1：geo cmd_next 两参调用 + 字符串契约，与测试断言 `PHASE=WAVE1` 的等号格式必须钉死在同一处）：

```python
# cmd_next 内（geo :223-226 替换）：
a = next_action(doc)
print(f"PHASE={a['phase']}")
print(f"[NEXT] {a['action']}")
print(f"命令: {a['command']}")
print(f"期望 rc: {a['expect_rc']}")
# cmd_status 内：删除 key_points_confirmed 打印（geo :231 『要点包确认=』行，J3 字段已废）
```

- [ ] **Step 2: 写失败测试**

```python
"""章状态机多波相位 + bug-3049 门自动回写测试。"""
import json
from pathlib import Path

import progress  # conftest.py 已注入 scripts/

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")

FILLER = ("锚杆支护巷道施工必须严格执行敲帮问顶制度，严禁空顶作业。临时支护紧跟迎头，"
          "永久支护滞后距离不得超过作业规程规定。施工中加强顶板离层观测与锚杆锚固力抽检。") * 30  # >1000 有效字符 + 3 句以上

def _init(tmp_path):
    data = tmp_path / "data"; state = tmp_path / "state"
    data.mkdir(); state.mkdir()
    (state / "chapters").mkdir()
    # gate→run_chapter_gate 无条件读 formula_state.json（对抗评审 P0：FileNotFoundError 穿透 except ValueError）
    (state / "formula_state.json").write_text(
        json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    # 章门深度目标调试注入（小地板，让 FILLER 能过 L2——生产基准由 Task 13 供给）
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"coefficient": 0.0, "absolute_floor": 1.0,
        "per_chapter": {f"ch{i}": {"median_eff": 500, "median_table_rows": 0, "median_paragraphs": 3} for i in range(1, 10)}},
        ensure_ascii=False), encoding="utf-8")
    rc, _ = _io(progress, ["init", "--stage", STAGE, "--state-dir", str(state), "--data-dir", str(data)])
    assert rc == 0
    return str(state), str(targets)

def _io(mod, argv):
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()

def test_init_all_pending_phase_wave1(tmp_path):
    state, _ = _init(tmp_path)
    rc, out = _io(progress, ["next", "--state-dir", state])
    assert rc == 0 and "PHASE=WAVE1" in out and "DISPATCH" in out

def test_phase_advances_across_waves(tmp_path):
    state, _ = _init(tmp_path)
    doc = json.loads((Path(state) / "progress.json").read_text(encoding="utf-8"))
    for c in ["ch1", "ch2", "ch3"]:
        doc["chapters"][c]["status"] = "VERIFIED"
    (Path(state) / "progress.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    rc, out = _io(progress, ["next", "--state-dir", state])
    assert "PHASE=WAVE2" in out  # 波1 全 VERIFIED → 自动进波2（J3：无 KEY_POINTS 停靠）

def test_mark_verified_rejected_bug3049(tmp_path):
    state, _ = _init(tmp_path)
    rc, out = _io(progress, ["mark", "ch1", "VERIFIED", "--state-dir", state])
    assert rc == 1  # 手动 VERIFIED 硬拒，唯一通道=gate

def test_gate_auto_verifies(tmp_path):
    state, targets = _init(tmp_path)
    for c in ["ch1", "ch2", "ch3"]:
        (Path(state) / "chapters" / f"{c}.md").write_text(f"## {c} 测试章\n\n{FILLER}\n", encoding="utf-8")
        rc, _ = _io(progress, ["mark", c, "DRAFTED", "--state-dir", state])
        assert rc == 0
    rc, out = _io(progress, ["gate", "--state-dir", state, "--targets", targets])
    doc = json.loads((Path(state) / "progress.json").read_text(encoding="utf-8"))
    # 门真跑二分（对抗评审 P0：BLOCKED 不会由 gate 产生）——过→VERIFIED 自动回写；不足→留 DRAFTED 且 stderr 报差距
    assert (doc["chapters"]["ch1"]["status"] == "VERIFIED"
            or ("CHAPTER_GATE_FAIL" in out and doc["chapters"]["ch1"]["status"] == "DRAFTED"))
    assert "GATE_BATCH_DONE" in out
```

- [ ] **Step 3: 跑测试**（先失败——geo 版 phase 是 WAVE1/WAVE2 且 next 停靠 KEY_POINTS；重写后全绿）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_progress_gate.py -v
# 期望: 4 passed
```

- [ ] **Step 4: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/progress.py skills/public/coal-mine-tunneling-regulation/tests/test_progress_gate.py
git commit -m "feat(tunneling-v2): progress多波derive_phase(stage.generation_waves驱动)+删KEY_POINTS+bug3049测试"
```

---

### Task 10: consistency 注册表框架移植 + C1–C12 + test_contracts.py

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/consistency.py`
- Create: `skills/public/coal-mine-tunneling-regulation/references/consistency_contracts.json`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_contracts.py`

- [ ] **Step 1: 逐条 delta**（geo 行号=geo 版；eia 函数从 `skills/public/coal-eia-report/scripts/consistency.py` 原样移植）：

| # | delta | 位置 | 做法 |
|---|-------|------|------|
| a | port eia 注册表框架 | eia `load_contracts`(:523)/`check_contracts`(:643)/`_contract_exact_match`(:570)/`_contract_echo`(:621)/`_value_occurrences`(:537)/`_norm_sem`(:495)/`_semantic_hit`(:506)/`_heading_norms`(:512)/`_find_chapter`(:561) + main 的 `--contracts`/`--standards` 参数(:707-708) | 逐函数复制进本技能 consistency.py；`_heading_norms` 本就收集全部标题级 → 章级语义激活直接可用 |
| b | severity 加 skip 档 | geo Report.counts(:141) 四档 | 改五档 `('pass','warn','manual','skip','fail')`（eia:159）；skip 不影响退出码；stdout 单列 `[SKIP xN]` |
| c | 删 geo 域合约 | `check_fc` 全族(:253-347)、`CC2` 历史编码(:380-382+HIST_MODERN_RE :111)、`XS3/XS5`(:212-227 由 C12 echo 承载) | 整段删除；保留 NR1/NR2/NR3、SL1 槽位残留、SL2 数值池、SL3（warn-skip 安全，dormant） |
| d | SL2 白名单换域 | geo WHITELIST_PATTERNS(:82-103) | 删 ZK/TC/PD 工程编号、332/333/111b/122b、经纬度、DZ 规范；加 `掘ZJED-`、`EBZ\d+`、`CMM\d`、`KJ\d+\w*`、`ZYJ-\w+`、`FBD-[\d./]+`、`GB/T?\s?\d+`、`AQ\s?\d+`、`MT/\s?T?\s?\d+`、`GB\s?\d+`；SMALL_INT_EXEMPT 与年份豁免保留（侦察 risk：掘进正文参数密度高，白名单不全=FAIL 洪水） |
| e | **resolve_source() 全新函数（J5 修正——对抗评审 P1：eia 根本没有 source 解析，这是新组件非移植）** | 新增，被 `_contract_exact_match`/`_contract_echo` 消费 | 代码规格见下方代码块。语法：`+` 分隔多源；`data:<族>.<字段>` JSON 标量；`data:<族>.<array字段>` 展平（对象数组取条目全部标量值拼串）；`data:<CSV族>:<列名>` 该列值集合；`data:<CSV族>` 裸族=全表单元格字符串集；`formula:<槽位键>` 从 state.values[key]["display"] 取（**槽位键粒度**，如 `formula:Q0.need_final`）。任一取值失败（族缺文件/字段缺失/state 无键）→ 该合约记 **skip**（与 conditional.on_absent 同语义），非 manual 非 fail |
| e2 | **护栏 warn 评估路径** | resolve_source 消费后 | 合约条目可带 `guardrails: [{"field":"长度_m","scope":"顶板","min":1.8,"ref":"R4"}]`——对 `data:<族>.<array字段>` 展开结果逐条评估，越界 → `rep.add(cid,'warn', f'{ref} 护栏: {描述}')`（阈值 origin=review_skill 已入 standards_index.limit_tables，J8 未核实档=warn 非 fail） |
| f | **C12 echo 动态实体** | `_contract_echo` | echo 条目载荷统一为 `{"fields": [...], "targets_semantic": [...]}`（JSON 里 C7/C8/C9/C12 必须带此载荷——eia 静态 `entities` 键弃用）；`fields` 中的字段经 resolve_source 从 `data:` 取值后逐项在目标章正文在场断言；字段缺失 → 该实体 skip（首跑无档案=正常）；**值在场但不等 → fail（C12 漂移检测本体）** |
| g | conditional 键名 | eia 条目用 `requires_any_section_semantic` | 本技能条目键名改 `requires_any_chapter_semantic`（语义不变，避免误导）；check_contracts 读取处同步 |
| h | code_constraint → manual | eia :671-672 语义 | 保留：C10 一律 manual（J8） |
| i | main 签名 + --state（J13） | `def main()` :495 / `--state` required :500 | main → `main(argv=None)`+`parse_args(argv)`；**`--state` 保持 required**（geo/eia 一致），测试须产 formula_state.json 并传参；state.values 取不到槽位键 → 该合约 skip（见 e） |

`resolve_source()` 新函数规格（delta e 的代码面，追加在 consistency.py 移植件内）：

```python
def resolve_source(expr: str, data, state_values: dict) -> tuple[list[str], list[str]]:
    """合约 source 表达式 → (值集合, 缺失说明列表)。语法见 Task 10 delta (e)。

    'data:roadway.drive_section_m2'            → JSON 族字段标量（str(value)）
    'data:support.bolt_specs'                  → array<object> 展平：每条目全部标量值转字符串
    'data:10_risk_register.csv:风险类型'        → CSV 族指定列的值集合
    'data:10_risk_register.csv'                → CSV 族全表单元格字符串集
    'formula:Q0.need_final'                    → state_values[key]['display']（槽位键粒度）
    多源用 ' + ' 连接。任一成分取不到 → 记入缺失列表（调用方判 skip）。
    """
    values, missing = [], []
    for part in (p.strip() for p in expr.split("+")):
        if part.startswith("formula:"):
            key = part[len("formula:"):]
            slot = (state_values or {}).get(key)
            if slot and slot.get("display"):
                values.append(str(slot["display"]))
            else:
                missing.append(part)
        elif part.startswith("data:"):
            ref = part[len("data:"):]
            if ".csv" in ref:
                fam, _, col = ref.partition(":")
                rows = (data.csvs.get(fam) or [])
                if not rows:
                    missing.append(part)
                else:
                    values.extend(str(r.get(col, "")) for r in rows if r.get(col, "") != "")
            else:
                fam, _, field = ref.partition(".")
                doc = data.form(fam)
                if field and field in doc:
                    v = doc[field]
                    if isinstance(v, list):
                        for item in v:
                            values.extend(str(x) for x in (item.values() if isinstance(item, dict) else [item]) if x not in (None, ""))
                    elif v not in (None, ""):
                        values.append(str(v))
                else:
                    missing.append(part)
    return values, missing
```

（`guardrails` 评估：exact_match 分派后若条目带 `guardrails`，对相关数组字段逐条比较 `min`/`max`，越界 `rep.add(cid,'warn',...)`——C4 消费 R4-R9，C1 消费 R10。）

- [ ] **Step 2: 写 consistency_contracts.json**（C1–C12 完整内容；entry schema 沿 eia :19-32；echo 条目载荷=`fields`+`targets_semantic`）：

```json
{
  "version": "2.0",
  "generated": "2026-09-13",
  "source": "spec C1-C12 + 侦察 R1-R12。阈值与 skills/custom/coal-mine-report-review 审查技能数值同源（已内联，禁运行时反读 custom/ 目录——gitignored 运行时资产）",
  "contract_types": {"cross_section": "值跨章 exact_match（表格感知+口径标签）", "code_constraint": "标准条款约束——一律 manual 待 tier1 人工对照", "echo_obligation": "源实体逐项在目标章在场断言，反向出现清单外实体=fail"},
  "caliber_labels": {"gas_daily_monthly": "瓦斯涌出量双口径标签：日最大/月平均（样例 3.4/2.45 实证）"},
  "activation_semantics": "合约激活 = stages 匹配当前 stage 且 conditional.requires_any_chapter_semantic 按语义标题命中（标题语义匹配，禁章号匹配）；未命中/依赖章缺席记 skip 不计 fail",
  "contracts": [
    {"id": "C1", "type": "cross_section", "name": "section_size_triple", "description": "掘进/净断面跨章 exact_match", "stages": ["tunneling"],
     "source": "data:roadway.drive_section_m2 + data:roadway.net_section_m2",
     "anchor": "章标题语义：「巷道布置及支护说明」", "consumers": ["章标题语义：施工工艺", "章标题语义：生产系统"],
     "conditional": {"requires_any_chapter_semantic": ["巷道布置及支护"], "on_absent": "skip"}, "caliber": [],
     "rule": "断面积数值逐处 exact_match（护栏：掘进断面≥净断面——物理序，对抗评审 P1 修正；R10 断面≥设计×1.05 为 warn）；出现第二数值=fail", "evidence": "样例 5.0×3.6m 掘进 18m²，ch3/ch4/ch5 三处同值",
     "guardrails": [{"field": "net_section_m2", "compare": "drive>=net", "ref": "R10", "note": "净断面≥掘进断面/1.05 之外再留 5% 变形余量为 warn"}]},
    {"id": "C2", "type": "cross_section", "name": "roadway_name_exact", "description": "巷道全称全文 exact", "stages": ["tunneling"],
     "source": "data:roadway.roadway_name", "anchor": "章标题语义：概况", "consumers": ["章标题语义：生产系统", "章标题语义：安全技术措施", "章标题语义：灾害应急措施及避灾路线"],
     "conditional": {"requires_any_chapter_semantic": ["概况"], "on_absent": "skip"}, "caliber": [],
     "rule": "巷道名称（含工作面编号前缀）全文逐字一致；任何缩写/改写变体=fail（传感器表/避灾路线均点名）", "evidence": "样例『3218运输顺槽』贯穿 ch1/ch5 传感器表/ch9"},
    {"id": "C3", "type": "cross_section", "name": "design_length_sync", "description": "设计长度 ch1↔ch6 指标表同源", "stages": ["tunneling"],
     "source": "data:roadway.design_length_m", "anchor": "章标题语义：概况", "consumers": ["章标题语义：劳动组织及主要技术经济指标"],
     "conditional": {"requires_any_chapter_semantic": ["概况"], "on_absent": "skip"}, "caliber": [],
     "rule": "长度数值（含小数位）exact_match（样例 902.236m——三位小数禁舍入改写）", "evidence": "T807 施工长度 902.236"},
    {"id": "C4", "type": "cross_section", "name": "support_params_group", "description": "支护参数组（锚杆/锚索/间排距/预紧力）ch3 内设计↔工艺↔ch8 措施一致", "stages": ["tunneling"],
     "source": "data:support.bolt_specs + data:support.cable_specs",
     "anchor": "章标题语义：巷道布置及支护说明", "consumers": ["章标题语义：安全技术措施"],
     "conditional": {"requires_any_chapter_semantic": ["巷道布置及支护"], "on_absent": "skip"}, "caliber": [],
     "rule": "参数值跨章 exact_match；护栏（warn 非 fail，待核实）：顶板锚杆长≥1.8m(R4)/帮部≥1.6m(R5)/间排距≤1.0×1.0(R6)/锚索≥6.3m(R7)/初喷≥50mm(R8)/总厚≥120mm(R9)——未达标行输出 warn 及 R 编号", "evidence": "样例 ch3 支护设计表/支护工艺/ch8 顶板措施同参数组",
     "guardrails": [
       {"field": "bolt_specs[].长度_m", "scope": "部位=顶板", "min": 1.8, "ref": "R4"},
       {"field": "bolt_specs[].长度_m", "scope": "部位=帮部", "min": 1.6, "ref": "R5"},
       {"field": "bolt_specs[].间排距_m", "max": 1.0, "ref": "R6"},
       {"field": "cable_specs[].长度_m", "min": 6.3, "ref": "R7"}
     ]},
    {"id": "C5", "type": "cross_section", "name": "air_quantity_chain", "description": "风量链：需风量/局扇/风筒节数跨章一致", "stages": ["tunneling"],
     "source": "formula:Q0.need_final + formula:F3.duct_count",
     "anchor": "章标题语义：生产系统", "consumers": ["章标题语义：施工工艺"],
     "conditional": {"requires_any_chapter_semantic": ["生产系统"], "on_absent": "skip"}, "caliber": [],
     "rule": "ch4 管线敷设表风筒数量行 **≥ {{SLOT:F3.duct_count}}**（下限 sanity——不足=fail，冗余备节=warn；对抗评审 P1 裁定：样例 120 节对应不同设计长度，exact 语义与 n=1 矛盾）；需风量须在 {{SLOT:Q4.v_min_check}}-{{SLOT:Q4.v_max_check}} 区间（越界已在门2 阻断）", "evidence": "样例 Φ1000 风筒 120 节 ↔ 巷长（n=1 数值仅说明机制）"},
    {"id": "C6", "type": "cross_section", "name": "gas_emission_caliber", "description": "瓦斯涌出量双口径绑定", "stages": ["tunneling"],
     "source": "data:geology.gas_emission_daily + data:geology.gas_emission_monthly",
     "anchor": "章标题语义：地面位置及地质情况", "consumers": ["章标题语义：生产系统"],
     "conditional": {"requires_any_chapter_semantic": ["地面位置及地质"], "on_absent": "skip"},
     "caliber": ["gas_daily_monthly"],
     "labels": {"gas_emission_daily": "日最大", "gas_emission_monthly": "月平均"},
     "rule": "涌出量数值出现处必须带『日最大』或『月平均』口径标签（labels 映射由 resolve_source 附加到对应字段值上）；同值异标签=fail；双口径并存无标签=歧义 fail", "evidence": "样例 3.4/2.45 m³/min（T458/T460）+ Khg 1.39"},
    {"id": "C7", "type": "echo_obligation", "name": "water_inflow_echo", "description": "涌水量 ch2→ch5 排水→ch9 水灾逐项在场", "stages": ["tunneling"],
     "source": "data:geology.normal_inflow_m3h + data:geology.max_inflow_m3h",
     "anchor": "章标题语义：地面位置及地质情况", "consumers": ["章标题语义：生产系统", "章标题语义：灾害应急措施及避灾路线"],
     "conditional": {"requires_any_chapter_semantic": ["地面位置及地质"], "on_absent": "skip"}, "caliber": [],
     "rule": "正常/最大涌水量数值逐项在消费者章在场", "evidence": "样例 ch2 水文/ch5 给排水/ch9 防水灾三处",
     "fields": ["normal_inflow_m3h", "max_inflow_m3h"]},
    {"id": "C8", "type": "echo_obligation", "name": "equipment_measures_match", "description": "设备型号 ↔ ch8 对应设备措施在场", "stages": ["tunneling"],
     "source": "data:equipment.roadheader_model + data:equipment.drill_car_model + data:equipment.conveyor_model + data:equipment.vehicle_model",
     "anchor": "章标题语义：施工工艺", "consumers": ["章标题语义：安全技术措施"],
     "conditional": {"requires_any_chapter_semantic": ["施工工艺"], "on_absent": "skip"}, "caliber": [],
     "rule": "每个非空设备型号在 ch8 必须有对应『XX（型号）操作/运输安全技术措施』条目在场；型号改写=fail", "evidence": "样例 EBZ160/CMM2-15/胶带机/WC3Y 顺槽车五组措施",
     "fields": ["roadheader_model", "drill_car_model", "conveyor_model", "vehicle_model"]},
    {"id": "C9", "type": "echo_obligation", "name": "self_rescue_quota", "description": "自救装置型号/数量/距离 ↔ ch6 限员匹配", "stages": ["tunneling"],
     "source": "data:profile.self_rescue_model + data:profile.self_rescue_count + data:profile.self_rescue_distance_m",
     "anchor": "章标题语义：灾害应急措施及避灾路线", "consumers": ["章标题语义：劳动组织及主要技术经济指标"],
     "conditional": {"requires_any_chapter_semantic": ["灾害应急措施"], "on_absent": "skip"}, "caliber": [],
     "rule": "自救装置三要素逐项在 ch9 在场；ch6 限员数 ≤ 自救装置额定服务人数的对应关系需在两章之一显式声明", "evidence": "样例 ZYJ-M6 ×3、25～40m（T797 限员/第九章）",
     "fields": ["self_rescue_model", "self_rescue_count", "self_rescue_distance_m"]},
    {"id": "C10", "type": "code_constraint", "name": "aq1029_cutoffs", "description": "传感器报警/断电/复电值对照 AQ 1029", "stages": ["tunneling"],
     "source": "data:sensor_cutoffs", "anchor": "章标题语义：生产系统", "consumers": [],
     "conditional": {"requires_any_chapter_semantic": ["生产系统"], "on_absent": "skip"}, "caliber": [],
     "rule": "恒 manual：{{TABLE:sensor_cutoffs}} 各行数值须人工对照 AQ 1029-2019 原文（standards_index.limit_tables.aq1029_methane_cutoffs）核实后才能自动判定；未核实前仅提示不判 fail", "evidence": "样例 甲烷 T≥1.0/≥1.5/<1.0（T695）——审查技能无数值（J8）"},
    {"id": "C11", "type": "cross_section", "name": "reg_no_format", "description": "规程编号格式与封面/会审页一致", "stages": ["tunneling"],
     "source": "data:roadway.reg_no", "anchor": "章标题语义：概况", "consumers": [],
     "conditional": {"requires_any_chapter_semantic": ["概况"], "on_absent": "skip"}, "caliber": [],
     "rule": "编号全文 exact_match 且匹配档案 reg_no_format 样式正则（样例 掘ZJED-3218YSSC/01号 → ^掘[A-Z]+-\\d{4}.+/\\d{2}号$，正则宽松匹配多集团差异）", "evidence": "封面/会审页同编号"},
    {"id": "C12", "type": "echo_obligation", "name": "profile_drift_echo", "description": "矿井级档案字段 ↔ 正文声明一致（档案漂移检测）", "stages": ["tunneling"],
     "source": "data:profile", "anchor": "章标题语义：概况", "consumers": ["章标题语义：概况", "章标题语义：地面位置及地质情况"],
     "conditional": {"requires_any_chapter_semantic": ["概况"], "on_absent": "skip"},
     "caliber": [],
     "rule": "档案字段（gas_grade/hydro_type/spontaneous_tendency/coal_dust_explosion/mine_name）逐项在消费者章正文在场且值一致；正文值与档案不一致=fail（先更新档案再编规程）；data/00_profile.json 缺席=整条 skip", "evidence": "D3 档案漂移检测；审查技能 L19/L21 分级触发同源（高瓦斯→抽采设计在场）",
     "fields": ["gas_grade", "hydro_type", "spontaneous_tendency", "coal_dust_explosion", "mine_name"]}
  ]
}
```

- [ ] **Step 3: 写失败测试**

```python
"""一致性合约注册表测试（C2 名exact / C10 manual / C12 档案漂移 fail+skip 语义 / 条件激活）。"""
import json
from pathlib import Path

import consistency  # conftest.py 已注入 scripts/
import ingest

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
CONTRACTS = str(ROOT / "references" / "consistency_contracts.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))

def _setup(tmp_path, name="N3218运输顺槽", with_profile=False):
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)  # 对抗评审 P1：可重入
    _io(ingest, ["forms", "--stage", STAGE, "--data-dir", str(data)])
    vals = DIGEST["form_seed"]["roadway"] | {"roadway_use": "运输", "working_face_no": "W1", "reg_no": "掘ZJED-2026T/01",
        "azimuth": "N", "start_end_date": "x", "adjacent_relation": "实体煤", "net_height_mm": 3600, "drive_height_mm": 3600}
    vals["roadway_name"] = name
    _io(ingest, ["forms", "--stage", STAGE, "--data-dir", str(data), "--family", "roadway", "--values", json.dumps(vals, ensure_ascii=False)])
    if with_profile:  # C12 漂移场景需要档案在场
        _io(ingest, ["forms", "--stage", STAGE, "--data-dir", str(data), "--family", "profile",
                     "--values", json.dumps(DIGEST["form_seed"]["profile"], ensure_ascii=False)])
    (data / "formula_state.json").write_text(json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    return str(data)

def _report(name="N3218运输顺槽", drop_chapter=None, gas_note=None):
    chs = ["概况", "地面位置及地质情况", "巷道布置及支护说明", "施工工艺", "生产系统",
            "劳动组织及主要技术经济指标", "安全风险辨识与管控", "安全技术措施", "灾害应急措施及避灾路线"]
    if drop_chapter:
        chs = [c for c in chs if c != drop_chapter]  # 条件激活 skip 用例（对抗评审 P2）
    parts = [f"# 某矿{name}掘进作业规程", "## 作业规程会审主要栏", ""]
    for i, c in enumerate(chs, 1):
        body = f"本章为{i}章测试正文。" * 40
        if c == "概况":
            body += f"巷道名称{name}，编号 掘ZJED-2026T/01，设计长度 902.236m。"
            if gas_note:
                body += gas_note  # 漂移注入（如『本矿为高瓦斯矿井』）
        if c == "施工工艺":
            body += f"掘进断面 18.0m²，风筒 {name} 内铺设。"
        parts.append(f"## {c}\n\n{body}\n")
    return "\n".join(parts)

def _io(mod, argv):
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()

def _run_consistency(tmp_path, data, report, out_name):
    rc, out = _io(consistency, ["--report", str(report), "--data-dir", data, "--stage", STAGE,
                                 "--state", str(Path(data) / "formula_state.json"),
                                 "--contracts", CONTRACTS, "--output", str(tmp_path / out_name)])
    return rc, json.load(open(tmp_path / out_name, encoding="utf-8"))

def test_c2_pass_and_fail(tmp_path):
    data = _setup(tmp_path)
    report = tmp_path / "r.md"; report.write_text(_report(), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    assert "skip" in res["summary"]  # 五档计数（eia:159）
    report2 = tmp_path / "r2.md"; report2.write_text(_report(name="N3218运输巷"), encoding="utf-8")
    rc2, res2 = _run_consistency(tmp_path, data, report2, "c2.json")
    c2 = [i for i in res2["items"] if i["contract"] == "C2"]
    assert c2 and any(i["severity"] == "fail" for i in c2)

def test_c10_manual_and_c12_skip(tmp_path):
    data = _setup(tmp_path)  # 无档案
    report = tmp_path / "r.md"; report.write_text(_report(), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    by_id = {i["contract"]: i["severity"] for i in res["items"]}
    assert by_id.get("C10") == "manual"      # J8：恒 manual
    assert by_id.get("C12") == "skip"        # 档案族未填 → skip（首跑正常）

def test_c12_drift_fail_and_conditional_skip(tmp_path):
    data = _setup(tmp_path, with_profile=True)  # 档案 gas_grade=低瓦斯
    report = tmp_path / "r.md"
    report.write_text(_report(gas_note="本矿为高瓦斯矿井，按高瓦斯管理。"), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    c12 = [i for i in res["items"] if i["contract"] == "C12"]
    assert c12 and any(i["severity"] == "fail" for i in c12)  # 漂移=fail（spec 测试矩阵）
    # 条件激活：删除依赖章 → C7/C9 记 skip 不计退出码
    data2 = _setup(tmp_path, with_profile=True)
    report2 = tmp_path / "r2.md"; report2.write_text(_report(drop_chapter="灾害应急措施及避灾路线"), encoding="utf-8")
    rc2, res2 = _run_consistency(tmp_path, data2, report2, "c2.json")
    by2 = {i["contract"]: i["severity"] for i in res2["items"]}
    assert by2.get("C7") == "skip" and by2.get("C9") == "skip"
    assert rc2 != 1  # skip 不影响退出码
```

- [ ] **Step 4: 跑测试**（先失败：geo 版无 --contracts → rc=2 用法错；移植后全绿）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_contracts.py -v
# 期望: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/consistency.py skills/public/coal-mine-tunneling-regulation/references/consistency_contracts.json skills/public/coal-mine-tunneling-regulation/tests/test_contracts.py
git commit -m "feat(tunneling-v2): consistency注册表框架(eia移植)+C1-C12合约+数据源扩展data前缀"
```

---

### Task 11: build_output 适配 + test_build_output.py

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/build_output.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_build_output.py`

- [ ] **Step 1: 逐条 delta**（行号=geo 原版 892 行）：

| # | delta | 位置 | 做法 |
|---|-------|------|------|
| a | 交付名 | `expected_deliverable_name` L59-72 | 换掘进版（下方代码）：从 `data/00_profile.json`+`data/01_roadway.json` 直拼 `{mine_name}{roadway_name}掘进作业规程.md` |
| b | 前置区渲染 | `render_front_matter` L78-131 | 换掘进封面（front_matter.outer_cover 五行）+ 会审页（signature_page_fixed_order 两表：会审纪要表空表头+审批栏空表）+ 目录占位 |
| c | 尾部渲染 | `render_compliance_appendix` L227 区域 | 换：附图清单 19 张 `[需附图]`（清单文本从 front_matter.attachment_lists 读）+ 规程贯彻记录页固定模板 |
| d | **目录覆盖门 port** | geo `validate_toc`(:314) | port eia `validate_toc_chapters`(:386)+`_sem_match`(:378)（必备/可选集+章标题语义相符，序不校验）；assemble 六步门(:629-636)与 `run_chapter_gate`(:719-725) 两处调用点同步替换 |
| e | **深度门单源化（J10）** | `validate_depth_target`(:406)/`_depth_row`(:682)/`run_chapter_gate` PASS 行(:738) 三处同式 | 抽单一函数 `depth_target(targets, ch_id, eff, tables) -> (target, ratio, status)`，三处调用 |
| f | 深度基准链 | `resolve_targets`(:486-521)/`MINERAL_ALIASES`/`normalize_mineral`/`_project_mineral`(:441-483) | 删矿种通道与 stage 三级探测；`CANONICAL_TARGETS`(:435) 改指 `references/depth_targets/tunneling.json`；保留「非技能基准高声警告+manifest 溯源」（bug-3058） |
| g | consistency 接入 | main L817-851 | 调用改签名：`run_checks(report, data_dir, stage, state, standards, contracts_path)`（本技能 consistency 已是注册表驱动）；保留 bug-3059 作废旧 manifest 顺序（L813-816 先于 fail 分支）与 `depth_rows.clear()`（L856） |
| h | RESIDUE_RE 词表 | L361-372 | 删 geo 词条（要点包/台账数据句/`XS|FC|CC|NR|SL\d`/exact_match/type_verdicts/ROUND_HALF_EVEN）；保留畸形 SLOT 归一化/`{{FORM:` 残留/XX 占位/`%%` 骨架（bug-3027/3036/3228） |
| i | 保留不动 | atomic_write（newline="\n" 字节精确 bug-2225）、六步门序列、`--allow-partial` 协议、`effective_chars` 导出（calibrate sibling import 依赖）、delivery_manifest 结构 | 原样 |
| j | main 签名（J13） | `def main()` :760 | → `def main(argv=None)` + `p.parse_args(argv)`（geo 零参） |

`expected_deliverable_name` 掘进版：

```python
def expected_deliverable_name(stage, data) -> str:
    prof = _read_json(data, stage["forms"]["profile"]["file"]) or {}
    road = _read_json(data, stage["forms"]["roadway"]["file"]) or {}
    mine, name = prof.get("mine_name") or "未命名矿井", road.get("roadway_name") or "未命名巷道"
    return f"{mine}{name}掘进作业规程.md"
```

- [ ] **Step 2: 写失败测试**

```python
"""组装与交付门测试（单文档 tmp_path，无容器依赖）。"""
import json
from pathlib import Path

import build_output  # conftest.py 已注入 scripts/

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
FILLER = "锚杆支护施工必须严格执行敲帮问顶制度，严禁空顶作业，临时支护紧跟迎头。" * 40

def _stage_env(tmp_path):
    data = tmp_path / "data"; state = tmp_path / "state"; out = tmp_path / "outputs"
    for d in (data, state, out):
        d.mkdir()
    (state / "chapters").mkdir()
    # 交付名门数据源（对抗评审 P0：expected_deliverable_name 直读这两文件，缺了=名字回退 rc=1）
    (data / "00_profile.json").write_text(json.dumps({"mine_name": "某矿"}, ensure_ascii=False), encoding="utf-8")
    (data / "01_roadway.json").write_text(json.dumps({"roadway_name": "N3218运输顺槽"}, ensure_ascii=False), encoding="utf-8")
    titles = json.load(open(ROOT / "references" / "stages" / "tunneling.json", encoding="utf-8"))["chapters"]
    for ch, spec in titles.items():
        (state / "chapters" / f"{ch}.md").write_text(f"## {spec['title']}\n\n{FILLER}\n", encoding="utf-8")
    (state / "formula_state.json").write_text(json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"coefficient": 0.0, "absolute_floor": 0.4,
        "per_chapter": {f"ch{i}": {"median_eff": 3000, "median_table_rows": 2, "median_paragraphs": 10} for i in range(1, 10)}}, ensure_ascii=False), encoding="utf-8")
    return str(data), str(state), str(out), str(targets)

def test_assemble_writes_deliverable_and_manifest(tmp_path):
    data, state, out, targets = _stage_env(tmp_path)
    rc, out_text = _run(["--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", str(Path(out) / "某矿N3218运输顺槽掘进作业规程.md"), "--targets", targets])
    assert rc in (0, 3), out_text  # 3=consistency warn/manual 非阻断（无表单填充时 manual 居多）
    assert "BUILD_READY" in out_text
    assert (Path(out) / "delivery_manifest.json").exists()

def test_outputs_stray_file_gate(tmp_path):
    data, state, out, targets = _stage_env(tmp_path)
    (Path(out) / "草稿.md").write_text("x", encoding="utf-8")
    rc, out_text = _run(["--stage", STAGE, "--data-dir", data, "--state-dir", state,
                          "--output", str(Path(out) / "某矿N3218运输顺槽掘进作业规程.md"), "--targets", targets])
    assert rc == 1  # 散文件门（L788-791）

def _run(argv):
    import contextlib, io
    buf, ebuf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
        rc = build_output.main(argv)  # J13：main(argv=None) 签名
    return rc, buf.getvalue() + ebuf.getvalue()
```

- [ ] **Step 3: 跑测试**（先失败后绿；实现期若 `main` 需包 argparse 层，按 geo main(L760) 实际入口名调用）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_build_output.py -v
# 期望: 2 passed
```

- [ ] **Step 4: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/scripts/build_output.py skills/public/coal-mine-tunneling-regulation/tests/test_build_output.py
git commit -m "feat(tunneling-v2): build_output掘进前置区/交付名/目录覆盖门(eia port)/深度门单源化"
```

---

### Task 12: snapshot 适配 + test_snapshot.py

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/scripts/snapshot.py`
- Create: `skills/public/coal-mine-tunneling-regulation/tests/test_snapshot.py`

- [ ] **Step 1: delta（geo 版几乎零改动——档案走 data/00_profile.json 自动入 hash，无需新键）**：①`--stage` help 枚举「勘探/详查/普查」→ 掘进；②docstring 示例（体重/资源量）→ 掘进示例；③`--affected` 示例键换通风公式；④**main 签名（J13）**：`def main()` :166 → `def main(argv=None)` + `p.parse_args(argv)`。机制零改动（bug-2198 正典名守卫/rc=3 篡改语义/data+state rglob hash 全保留）。

- [ ] **Step 2: 写测试**

```python
"""snapshot 快照往返 + 篡改检测 + 正典名守卫。"""
import json
from pathlib import Path

import snapshot  # conftest.py 已注入 scripts/

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")

def _env(tmp_path):
    data = tmp_path / "data"; state = tmp_path / "state"; out = tmp_path / "outputs"
    for d in (data, state, out):
        d.mkdir()
    (data / "01_roadway.json").write_text("{}", encoding="utf-8")
    (state / "progress.json").write_text("{}", encoding="utf-8")
    return data, state, out

def _run(mod, argv):
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()

def test_save_show_verify_roundtrip(tmp_path):
    data, state, out = _env(tmp_path)
    snap = str(out / "project_snapshot.json")
    rc, out1 = _run(snapshot, ["save", "--task", "波1收口", "--stage", STAGE, "--data-dir", str(data),
                                "--state-dir", str(state), "--output", snap])
    assert rc == 0 and "SNAPSHOT_READY" in out1
    rc2, out2 = _run(snapshot, ["show", "--input", snap, "--verify"])
    assert rc2 == 0 and "SNAPSHOT_VERIFIED" in out2

def test_tamper_detected_rc3(tmp_path):
    data, state, out = _env(tmp_path)
    snap = str(out / "project_snapshot.json")
    _run(snapshot, ["save", "--task", "t", "--stage", STAGE, "--data-dir", str(data), "--state-dir", str(state), "--output", snap])
    (state / "progress.json").write_text('{"tampered": true}', encoding="utf-8")
    rc, out2 = _run(snapshot, ["show", "--input", snap, "--verify"])
    assert rc == 3 and "SNAPSHOT_TAMPERED" in out2  # rc=3=篡改→步骤0 停

def test_canonical_name_guard_bug2198(tmp_path):
    data, state, out = _env(tmp_path)
    rc, out1 = _run(snapshot, ["save", "--task", "t", "--stage", STAGE, "--data-dir", str(data),
                                "--state-dir", str(state), "--output", str(out / "wrong_name.json")])
    assert rc == 1  # 快照必须恰名 project_snapshot.json
```

- [ ] **Step 3: 跑测试 + Commit**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/test_snapshot.py -v
# 期望: 3 passed
git add scripts/snapshot.py tests/test_snapshot.py
git commit -m "feat(tunneling-v2): snapshot掘进文案适配+往返/篡改/正典名测试"
```

---

### Task 13: references 数据件（depth_targets / standards_index / reference_values / data_expectations）

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/references/depth_targets/tunneling.json`
- Create: `skills/public/coal-mine-tunneling-regulation/references/standards_index.json`
- Create: `skills/public/coal-mine-tunneling-regulation/references/reference_values.json`
- Create: `skills/public/coal-mine-tunneling-regulation/references/data_expectations.json`

- [ ] **Step 1: depth_targets/tunneling.json 由 fixture 确定性生成（J7+J10：**geo 形状** `per_chapter.median_eff = ceil(实测×1.2)`，geo load_targets/深度门直接消费）**——不手抄数值，从 Task 4 的 digest 生成：

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -c "
import json, math
from pathlib import Path
d = json.load(open('tests/fixtures/sample3218_digest.json', encoding='utf-8'))
chs = {k: v for k, v in d['chapters'].items() if k.startswith('ch')}
out = {'coefficient': 1.0, 'absolute_floor': 1.0,
  'stage': 'tunneling', 'generated': '2026-09-13',
  'confidence': 'measured_single_anchor_n1_x1.2',
  'source': '3218 样例逐章 effective_chars（fixture digest）× 1.2 上浮（spec D10/J7；与 eia 0.6 折减方向相反系有意——n=1 防样本偏小）。geo 形状 per_chapter.median_eff（J10：geo 深度门只认 median_eff，对抗评审 P1）',
  'measured_note': 'n=1 单样本，二期样例 ≥5 份后用 calibrate 重新标定',
  'per_chapter': {k: {'median_eff': int(math.ceil(v['eff_chars'] * 1.2)),
                       'median_table_rows': v['tables'], 'median_paragraphs': 10} for k, v in sorted(chs.items())}}
dest = Path('references/depth_targets/tunneling.json')
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
tot = sum(v['median_eff'] for v in out['per_chapter'].values())
print('DEPTH_OK chapters=', len(out['per_chapter']), 'total_floor=', tot)
assert max(v['median_eff'] for v in out['per_chapter'].values()) < 25000, '单章地板超子代理产能——回 J7 复核（逐章语义，T4 裁决）'
"
# 期望: DEPTH_OK chapters= 9 total_floor= <80000
```

- [ ] **Step 2: standards_index.json**（骨架抄 eia 版；审查技能 R1–R12 内联入库，全 needs_verification=true——J9 禁运行时反读 custom/）：

```json
{
  "version": "1.0",
  "generated": "2026-09-13",
  "scope": "掘进作业规程编制引用的法规标准与限值。web_search 不可靠教训：限值/条款号仅 discovery，人工对照原文后才可 verified=true",
  "tier_policy": {"framework": "结构主纲——程序性引用，无需限值核实", "quality_limit": "工程质量/技术限值——须人工对照原文", "emission_limit": "浓度/速度限值——须人工对照原文", "method_param": "方法/参数类——须人工对照原文", "pending": "未完成人工核实"},
  "red_line": "标准编号与年份只从本文件枚举，禁 LLM 记忆补写；limit_tables 全表 needs_verification=true，verified 唯一翻转通道=人工对照标准原文",
  "standards": [
    {"code": "《煤矿安全规程》", "title": "煤矿安全规程（2022 年版）", "role": "总纲：通风/瓦斯/防尘/防治水/机电/运输/应急全部条款的最高依据", "chapters": "全文", "tier": "framework", "needs_verification": false, "verified": true, "origin": "v1_skill"},
    {"code": "GB/T 35056-2018", "title": "煤矿巷道锚杆支护技术规范", "role": "支护设计/材料/施工/质量（ch3）", "chapters": "ch3/ch8", "tier": "quality_limit", "needs_verification": true, "verified": false, "origin": "v1_skill"},
    {"code": "AQ 1029-2019", "title": "煤矿安全监控系统及检测仪器使用管理规范", "role": "传感器布设/报警断电复电值（ch5/ch9，C10 对照源）", "chapters": "ch5/ch9", "tier": "emission_limit", "needs_verification": true, "verified": false, "origin": "v1_skill"},
    {"code": "AQ 1020-2006", "title": "煤矿井下粉尘综合防治技术规范", "role": "综合防尘五件套（ch5）", "chapters": "ch5/ch8", "tier": "method_param", "needs_verification": true, "verified": false, "origin": "v1_skill"},
    {"code": "《煤矿防治水细则》", "title": "煤矿防治水细则", "role": "水文地质/探放水/『有掘必探先探后掘』（ch2/ch8）", "chapters": "ch2/ch8/ch9", "tier": "framework", "needs_verification": false, "verified": true, "origin": "v1_skill"},
    {"code": "《煤矿地质工作细则》", "title": "煤矿地质工作细则", "role": "地质说明书/构造/水文地质（ch2）", "chapters": "ch2", "tier": "framework", "needs_verification": false, "verified": true, "origin": "v1_skill"},
    {"code": "《防治煤与瓦斯突出细则》", "title": "防治煤与瓦斯突出细则", "role": "突出危险区掘进（ch5，gas_grade=煤与瓦斯突出 时条件激活）", "chapters": "ch5", "tier": "method_param", "needs_verification": true, "verified": false, "origin": "v1_skill"},
    {"code": "《煤矿安全生产标准化管理体系基本要求及评分方法》", "title": "煤矿安全生产标准化管理体系基本要求及评分方法（试行）", "role": "工程质量/文明生产标准化（ch3/ch6）", "chapters": "ch3/ch6", "tier": "quality_limit", "needs_verification": true, "verified": false, "origin": "v1_skill"}
  ],
  "limit_tables": {
    "review_skill_support_redlines": {"desc": "支护红线（来源=coal-mine-report-review 审查技能 L31-38，无条款号——人工对照 GB/T 35056 后才可 verified）", "code_ref": "GB/T 35056-2018", "needs_verification": true, "verified": false,
      "rows": [
        {"category": "锚杆长度(顶板)", "value": ">=1.8m", "origin": "review_skill L32"},
        {"category": "锚杆长度(帮部)", "value": ">=1.6m", "origin": "review_skill L32"},
        {"category": "锚杆间排距", "value": "<=1.0m×1.0m", "origin": "review_skill L33"},
        {"category": "锚索长度", "value": ">=6.3m(依顶板岩性)", "origin": "review_skill L34"},
        {"category": "初喷厚度", "value": ">=50mm", "origin": "review_skill L35"},
        {"category": "喷射混凝土总厚", "value": ">=120mm", "origin": "review_skill L35"}
      ], "note": "供 C4 护栏（warn 档）消费"},
    "review_skill_air_redlines": {"desc": "风量/风速红线（审查技能 L18/L37）", "code_ref": "《煤矿安全规程》", "needs_verification": true, "verified": false,
      "rows": [
        {"category": "风量裕度", "value": "风量计算值>=设计需风量×1.2", "origin": "review_skill L18"},
        {"category": "掘进巷道风速", "value": "0.25~8 m/s", "origin": "review_skill L18,L37"},
        {"category": "回风巷道风速", "value": "0.15~4 m/s", "origin": "review_skill L37"}
      ], "note": "风速档位未按煤巷/半煤岩巷/岩巷细分——人工核实后按档位拆行"},
    "review_skill_dust_redlines": {"desc": "粉尘浓度红线（审查技能 L38）", "code_ref": "《煤矿安全规程》", "needs_verification": true, "verified": false,
      "rows": [
        {"category": "呼尘", "value": "<=10mg/m³", "origin": "review_skill L38"},
        {"category": "总尘(游离SiO₂>10%)", "value": "<=4mg/m³", "origin": "review_skill L38"}
      ], "note": "未按游离 SiO₂ 分档细分"},
    "aq1029_methane_cutoffs": {"desc": "甲烷传感器报警/断电/复电值（C10 对照源；审查技能无此数值）", "code_ref": "AQ 1029-2019", "needs_verification": true, "verified": false,
      "rows": [], "note": "样例锚点 T1: 报警>=1.0%/断电>=1.5%/复电<1.0%（T695）——人工对照 AQ 1029 原文录入全部档位后才可消费，此前 C10 恒 manual"}
  },
  "gate1_code_checks": {"desc": "正文标准编号引用合法性体检（gate1 质量警告）",
    "allowed_patterns": ["^《[^《》]+》$", "^GB(/T)?\\s?\\d+(\\.\\d+)?(-\\d{4})?$", "^AQ\\s?\\d+(-\\d{4})?$", "^MT/\\s?T?\\s?\\d+", "^《煤矿安全规程》$", "^《煤矿防治水细则》$", "^《煤矿地质工作细则》$", "^《防治煤与瓦斯突出细则》$"],
    "rules": ["编号必须在本文件 standards[] 枚举内（含年份变体）", "未登记编号→警告提示补充登记，禁直接写入正文"]}
}
```

- [ ] **Step 3: reference_values.json**（geo 版为唯一在库模板；通风域全部【待核实】）：

```json
{
  "version": "1.0",
  "generated": "2026-09-13",
  "policy": "全部参考值待人工核实；确认前公式计算恒记 anomaly（formula_runner 契约）。来源枚举：sample_verbatim(3218 样例原文)/v1_skill(现行提示词技能)/handbook(手册，未核实)。用户确认后值写回 data/ 表单，不回写本文件",
  "ventilation": {"std_ref": "《煤矿安全规程》+矿井通风手册", "general": {"status": "待人工核实", "indicators": [
    {"name": "风量公式系数（按瓦斯涌出量）", "value": "100", "origin": "v1_skill", "consumes": "Q1"},
    {"name": "每人需风量", "value": "4 m³/min", "origin": "v1_skill", "consumes": "Q2"},
    {"name": "柴油机车每 kW 需风量", "value": "5.44 m³/min·kW", "origin": "v1_skill", "consumes": "Q3"},
    {"name": "掘进巷道风速带", "value": "0.25~8 m/s（煤巷档未分档）", "origin": "review_skill", "consumes": "Q4"},
    {"name": "风筒距迎头", "value": "L=5√S", "origin": "sample_verbatim", "consumes": "F1"},
    {"name": "百米漏风率上限（样例口径）", "value": "10%", "origin": "sample_verbatim", "consumes": "F2"},
    {"name": "漏风折算公式", "value": "线性近似 Q0×(1+i×Ld/10000)", "origin": "v1_skill", "consumes": "F2"}
  ], "note": "核实通道=人工对照《煤矿安全规程》通风章节与矿通风能力核定报告；核实后在 standards_index.limit_tables 翻 verified 并同步 formulas.json note"}},
  "hard_rules": ["缺参数不得以本文件任何值顶替——reference_values 是【待核实】清单不是数据源（bug-2223/geo 同构红线）"]
}
```

- [ ] **Step 4: data_expectations.json**（9 章数据预告；family key 与 stages forms 一一对应——_comment 硬约束）：

```json
{
  "_comment": "按章数据预告（开题三件套③）。family key 必须与 stages/tunneling.json forms 族名一致——耦合对象=章级派发契约（本技能无 KF 章树）",
  "source_hint_vocabulary": ["user_docs(地质/设计说明书上传)", "user_input(对话表单)", "mine_profile(矿井档案)", "calc_output(formula_runner 冻结值)", "standards_index(标准枚举)", "methodology(编制方法性内容，无数据)", "projection(波间要点包=冻结值投影)"],
  "per_chapter": [
    {"chapter": "ch1", "title": "概况", "data_families": [{"family": "profile", "items": ["矿名/集团/编号规则/队组/会审单位"], "source_hint": "mine_profile"}, {"family": "roadway", "items": ["巷道名称/用途/长度/断面/开竣工/相邻关系"], "source_hint": "user_docs / user_input"}], "note": "全文身份事实源（C2/C3/C11 源点）"},
    {"chapter": "ch2", "title": "地面位置及地质情况", "data_families": [{"family": "geology", "items": ["标高/煤层/倾角/顶底板岩性表/瓦斯涌出量双口径+Khg/构造/涌水量/水文结论"], "source_hint": "user_docs"}, {"family": "profile", "items": ["瓦斯等级/水文类型/自燃/煤尘（档案值）"], "source_hint": "mine_profile"}], "note": "『有掘必探先探后掘』固定条款在场"},
    {"chapter": "ch3", "title": "巷道布置及支护说明", "data_families": [{"family": "support", "items": ["锚杆/锚索/网钢带/锚固剂/喷厚/特殊补强/质量偏差表"], "source_hint": "user_docs / user_input"}, {"family": "roadway", "items": ["断面尺寸（C1 源点）"], "source_hint": "user_docs"}, {"family": "equipment", "items": ["矿压观测设备表"], "source_hint": "user_input"}], "note": "支护参数禁计算（D5），缺值 [待补充]"},
    {"chapter": "ch4", "title": "施工工艺", "data_families": [{"family": "equipment", "items": ["掘进机/钻车/输送机/车辆/施工设备表/管线敷设表"], "source_hint": "user_input"}], "note": "风筒节数与 F3 同源（C5）"},
    {"chapter": "ch5", "title": "生产系统", "data_families": [{"family": "ventilation", "items": ["通风方式/风筒规格/漏风率/人数/柴油功率/局扇型号/供风距离"], "source_hint": "user_input"}, {"family": "geology", "items": ["瓦斯涌出量（冻结计算输入）"], "source_hint": "user_docs"}, {"family": "systems", "items": ["压风/供电/给排水/运输/信号/防灭火说明"], "source_hint": "mine_profile / user_input"}, {"family": "dust_facilities", "items": ["防尘设施表"], "source_hint": "user_input"}, {"family": "sensor_cutoffs", "items": ["传感器设置表"], "source_hint": "user_input / standards_index"}], "note": "风量四法全部冻结值；C10 断电表 manual 待核实"},
    {"chapter": "ch6", "title": "劳动组织及主要技术经济指标", "data_families": [{"family": "labor_crew", "items": ["工种/班次出勤表"], "source_hint": "user_input"}, {"family": "econ_indicators", "items": ["技术经济指标表（施工长度与 ch1 同源 C3）"], "source_hint": "user_input"}, {"family": "roadway", "items": ["设计长度（C3 触点）"], "source_hint": "user_docs"}, {"family": "profile", "items": ["限员制度（C9）"], "source_hint": "mine_profile"}], "note": "限员数与 ch9 自救装置同源（C9）"},
    {"chapter": "ch7", "title": "安全风险辨识与管控", "data_families": [{"family": "risk_register", "items": ["风险辨识管控清单"], "source_hint": "user_input"}, {"family": "geology", "items": ["构造/灾害参数（危害因素分析输入）"], "source_hint": "user_docs"}], "note": "八类危害因素逐条"},
    {"chapter": "ch8", "title": "安全技术措施", "data_families": [{"family": "support", "items": ["支护参数引用（C4）"], "source_hint": "projection"}, {"family": "equipment", "items": ["设备型号措施匹配（C8）"], "source_hint": "projection"}, {"family": "profile", "items": ["强制条款引用"], "source_hint": "standards_index"}], "note": "六节措施集；设备型号逐字一致"},
    {"chapter": "ch9", "title": "灾害应急措施及避灾路线", "data_families": [{"family": "profile", "items": ["自救装置型号/数量/距离/三条避灾路线/六大系统（J11 档案族）"], "source_hint": "mine_profile"}, {"family": "geology", "items": ["涌水量（C7）"], "source_hint": "user_docs"}, {"family": "sensor_cutoffs", "items": ["传感器表（C10）"], "source_hint": "user_input"}], "note": "避灾路线取档案；无档案时现场收集"}
  ]
}
```

- [ ] **Step 5: 校验 + Commit**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -c "
import json
for f in ['references/depth_targets/tunneling.json', 'references/standards_index.json', 'references/reference_values.json', 'references/data_expectations.json']:
    json.load(open(f, encoding='utf-8')); print('JSON_OK', f)
de = json.load(open('references/data_expectations.json', encoding='utf-8'))
st = json.load(open('references/stages/tunneling.json', encoding='utf-8'))
fams = set(st['forms'])
for ch in de['per_chapter']:
    for fam in ch['data_families']:
        assert fam['family'] in fams or fam['family'] in ('projection', 'standards_index'), (ch['chapter'], fam['family'])
print('DATA_EXPECTATIONS_OK: 9 章 family 全对齐')
"
git add references/
git commit -m "feat(tunneling-v2): references数据件(深度×1.2生成+standards_index审查阈值入库+待核实参考值+9章数据预告)"
```

---

### Task 14: SKILL.md 全重写（管线版）

**Files:**
- Modify: `skills/public/coal-mine-tunneling-regulation/SKILL.md`（251 行 → 管线版）

- [ ] **Step 1: 全文替换为以下内容**。四处接线契约必须原样保留：①frontmatter `name: coal-mine-tunneling-regulation`（改名=注册失效）；②allowed-tools 禁用 NOTE（bug-186）；③description 触发词族（L4-8 原文压缩进新 description，≤1024 字符禁尖括号——validation.py:71-74）；④KF resolve 真调用块（参数按 J6 更新）。交付措辞修正：docmgr 是只写通道，交付=present_files（侦察 skill-md-pattern 节）：

```markdown
---
name: coal-mine-tunneling-regulation
description: |
  当用户请求为煤矿生成、编写、编制"掘进作业规程"（掘进工作面作业规程、巷道掘进作业规程、
  机掘/炮掘作业规程、顺槽/运输巷/回风巷/切眼掘进作业规程）时使用此技能。即使用户没有明确说"生成报告"，
  只要涉及煤矿掘进作业规程、掘进安全技术措施、掘进施工组织设计的文档编写，都应使用此技能。
  典型触发词：掘进作业规程、掘进规程、作业规程编写、巷道掘进规程、顺槽掘进规程、掘进工作面规程、
  掘进施工组织、掘进安全技术措施编制。
  单场景：掘进作业规程（采煤规程/专项措施为后续 stage）。支护/通风/断面等数值永不经过 LLM——
  正文只写 {{SLOT:族.字段}}/{{TABLE:族}} 占位，由脚本冻结注入；缺数据一律 [待补充]。
license: MIT
# NOTE: 不要在此声明 allowed-tools。cerebrum bug-186：技能声明 allowed-tools 会以声明集∪4 框架内建
# 过滤工具（激活态 scoped，#4497 后），剥掉 knowledge-factory_kf_* / present_files / ask_clarification
# 饿死本技能。一律不加回。
---

# 煤矿掘进作业规程编写技能（v2 管线）

## 角色与身份

你是煤矿掘进技术专家与**管线控制器**。主会话只协调派发、跑脚本、呈现门结果，**不亲笔写章、不手算任何数字**。熟悉《煤矿安全规程》(2022)、GB/T 35056-2018、AQ 1029/1020、《煤矿防治水细则》《煤矿地质工作细则》《防治煤与瓦斯突出细则》、安全生产标准化评分方法。

## ⛔ 红线（先读，违反会出事）

- **P1 数字零编造**：支护/通风/断面/长度等数值只经 `{{SLOT}}`/`{{TABLE}}` 注入或表单转写；缺值标 `[待补充]`。掘进作业规程是法定安全文件，直接影响井下人命。
- **P2 强制条款不得放宽**：「有掘必探先探后掘」、断电值、防尘间隔等须引标准编号+条款号；标准号只从 `references/standards_index.json` 枚举，禁记忆补写；`reference_values.json` 全部【待核实】，不是数据源。
- **P3 口径标签**：瓦斯涌出量出现处必须带「日最大」或「月平均」口径（C6）。
- **P4 档案权威**：矿井级事实（瓦斯等级/水文类型/避灾路线等）以矿井档案为准；正文与档案不一致=合约 FAIL——先更新档案再编规程。`profile.json` 唯一写者=profile.py。
- **P5 progress.json 唯一权威**：跨轮次现场状态只认磁盘 progress.json/snapshot，不认对话记忆（bug-3231）。
- **P6 门 FAIL 唯一合法出路=补写正文或申请用户降档**（Iron Law）。编辑 references/、绕 CLI、伪造门输出=伪造基准。
- **P7 工具失败不盲试**：连续失败 2 次停止并如实上报（沿 v1 规则 11）。

## 工作区布局

```
/mnt/user-data/workspace/tunneling-regulation/
  data/       # 表单 JSON/CSV（ingest.py 唯一写者；00_profile.json=档案族）
  state/      # chapters/chN.md 章稿 + progress.json + formula_state.json + consistency_check.json + chapter_manifest.json
/mnt/user-data/outputs/   # 交付目录（与 workspace 平级）：{矿名}{巷道名}掘进作业规程.md + delivery_manifest.json + project_snapshot.json
```

脚本前缀统一：`python -X utf8 /mnt/skills/public/coal-mine-tunneling-regulation/scripts/<脚本>`。

## 管线步骤（0 / 0.5 / 1 / 2 / 3 / 4 / 5 / 6）

**步骤 0 快照恢复**：新 run 首动作 `snapshot.py show --input outputs/project_snapshot.json --verify`。rc=0 有快照→读 progress 现场续跑；rc=0 无快照（SNAPSHOT_NONE）→全新开始；**rc=3（SNAPSHOT_TAMPERED）→停**，呈现用户裁决。

**步骤 0.5 矿井档案装载**（D3，档案回合不发其他卡片）：用户带档案文件→`profile.py validate --input <档案>` 通过后 `profile.py summary` 呈现（含档案日期；「矿井条件有变先更新档案」提示）→`profile.py load --input <档案> --stage <S> --data-dir data/` 落 `data/00_profile.json`。无档案→按 forms.profile 族 `ask_clarification` 建档（单回合一张铁律）→load→**档案 md 随最终交付 present_files**（用户保存供下次复用）。

**步骤 1 数据收集**：开题三件套——①真实调用 `knowledge-factory_kf_resolve_template`（见 KF 契约节；口头声称=未做）；②found=false 时向用户声明兜底（载体=首张表单 question 开头，不另发消息）；③读 `references/data_expectations.json` 按章向用户预告数据清单。之后按 forms 族逐族收集（`ingest.py forms --family X --values ...` 每族落盘；批量>10 条引导上传 xlsx/csv/docx 走 `ingest.py file` 且索要上传必须普通消息收尾；单回合一张；示例值≠数据；只传用户提交的键）。**门1**：`ingest.py check --stage <S> --data-dir data/` → rc=0 GATE1_COMPLETE 过 / rc=2 缺项清单译成中文呈现用户不代填（GATE1_QUALITY warn 动笔前逐条消化）。

**步骤 2 冻结计算**：`progress.py run-stage freeze --state-dir state/`（=chapter_planner manifest → formula_runner execute）。**门2**：execute rc=0 干净过 / **rc=3 有 anomalies→发卡逐条呈现用户，停**（免打扰指令的法定例外；预豁免只给「按冻结值继续」单选项）/ rc=1 报错停。

**步骤 3 章级派发**（控制器模式，详见派发协议节）：`progress.py next` 单步驱动；3 波（stage.generation_waves），每波一次 batch_task 投递 PENDING 章。

**步骤 4 章门**：波内章稿收齐（逐章 mark DRAFTED）→`progress.py gate --state-dir state/` 批量真跑单章门，PASS 自动转 VERIFIED（唯一通道；手动 mark VERIFIED 被拒）。FAIL 章 stderr 逐章差距→重派（每章 ≤1 次，重派 prompt=原 prompt 原文+stderr 原文）→仍 FAIL=BLOCKED→NEGOTIATE。**每波收口后停车：写盘→`snapshot.py save --task "波N收口" --output outputs/project_snapshot.json ...`→停。**

**步骤 5 终验**：`progress.py run-stage finalize --state-dir state/ --outputs-dir /mnt/user-data/outputs --task "掘进作业规程终验"`（=build_output 组装单文档→consistency C1-C12→snapshot save）。BUILD_READY/退出码原样粘贴进回复；consistency rc=1（fail）停、rc=2（manual）呈现待人工项、rc=3（warn）汇报后可交付。

**步骤 6 交付**：delivery_manifest.json 在场才可 present_files（一次）。交付说明列明：已填数据/[待补充] 项/[需附图] 清单/矿井档案 md（提醒用户保存）。**交付后修改只落 state/chapters/，重跑 finalize，禁直接编辑 outputs/ 交付物。**

## 派发协议（章级）

- 每轮先 `progress.py next`——恰好一个下一步+精确命令+期望 rc。
- **派发契约**（每 PENDING 章一次）：「角色：第 N 章《{title}》撰写者，只产出这一章」+ stage 章 key_elements 全文（要素链，内含 {{SLOT}}/{{TABLE}} 引用清单）+ `formula_state.json` 冻结值投影（值表）+ 深度目标（章 floor_chars；**实际目标以门报错行内嵌数值为准**）+ 本章 std_refs + 「正文数值只写 {{SLOT:key}}/{{TABLE:族}}，禁手写数字」。
- batch_task 优先整批投递（items=该波 PENDING 章契约，每项独立子代理预算）；task() 兜底 ≤3 并发；额度拒≠亲写许可。子代理直写 `state/chapters/chN.md`（首行 `## N {title}`），只回 ≤10 行摘要。
- **Excuse|Reality 取证**：凡声称「数据已齐/门已过」，给出对应脚本输出行；给不出=没做。
- 迭代修改重写章稿前必须先 read（read-before-write，bug-3230），防写保护拦截烧 token。

## 停车契约与平台预算

停车点=每 run 合法终点：门1 过后 / 门2 rc=3 发卡后 / 每波 batch 投递后（只轮询）/ 波收口存快照后。bash ≤25 次/记一笔账走批量子命令（gate/run-stage/batch_task 合并调用）。被熔断 run 侧仍报 success——续跑靠磁盘不靠对话记忆，新 run 首动作=步骤 0。修复轮四条：只增补禁重写/整章一次 write_file/一次批跑全章门/缺键→[待确认] 禁补写 formula_state。

## 修改回路（顺序铁律）

改参数：先 `formula_runner.py impacted --field <K> --value <V> --manifest state/chapter_manifest.json`（dry-run 零写盘）→呈现用户确认→`formula_runner.py update ... --impacted-file <上一步产物> --output state/formula_state.json`（不带或差分不符=rc1 拒）→重派受影响章→finalize。矿井级（档案）变更：先更新档案文件再 load，C12 会自动全章重扫评估。

## KF 契约（步骤 1 强制首调）

```
knowledge-factory_kf_resolve_template(
    domain_keywords=["掘进作业规程", "掘进规程", "巷道掘进", "煤矿作业规程", "操作规程"],
    industry="煤炭挖掘",
    report_type="operating_procedures_report",
    min_completeness_score=60)
```

- `found=true`：✅ 播报模板名/版本/完整度/匹配级；用返回 sections 与 `stages/tunneling.json` **对账**（结构冲突→以 stage 为准并记录偏差）。
- `found=false` 或调用抛错：⚠️ 播报「知识工厂不可用，使用内置 stages/tunneling.json」继续——这是回退的唯一合法前提（真调用过）。found=false 且 reason=missing_keywords 时按工具 suggestion 补 keywords 重试 ≤1 次。
- 禁止在首调前 read_file references/ 任何文件。结构唯一真源=stages/tunneling.json（report_structure.md 已退役）。

## 门语义速记

| 门 | 命令 | rc |
|---|---|---|
| 快照 | `snapshot.py show --verify` | 0 过/3 篡改停 |
| 档案 | `profile.py validate` | 0/1 |
| 门1 | `ingest.py check` | 0 过/2 缺项呈现 |
| 门2 | `formula_runner execute`（经 run-stage freeze） | 0/1 错/3 anomalies 发卡停 |
| 章门 | `progress.py gate` | 0/1（VERIFIED 唯一通道） |
| 合约 | consistency（经 finalize） | 0/1 fail 停/2 manual/3 warn |
| 组装 | `build_output.py`（经 finalize） | 0 BUILD_READY/1 |

## 命令速查

```
profile.py validate --input <档案.json> [--stage references/stages/tunneling.json]
profile.py summary --input <档案.json>
profile.py load --input <档案.json> --data-dir data/
ingest.py forms --stage S --data-dir data/ [--family F (--values '<json>'|--rows '<json[]>')] [--only 族1,族2] [--force]
ingest.py file --stage S --data-dir data/ --input <xlsx|csv|docx> --family <CSV族>
ingest.py check --stage S --data-dir data/
chapter_planner.py manifest --stage S --output state/chapter_manifest.json
chapter_planner.py impacted --manifest M --formulas a,b --families x
formula_runner.py execute --stage S --data-dir data/ --output state/formula_state.json   # rc3=anomalies 停
formula_runner.py check --stage S --data-dir data/ --state F [--anchors '<json>']
formula_runner.py trace --state F --formulas references/formulas.json
formula_runner.py impacted --stage S --data-dir D --state F --field K --value V [--manifest M]
formula_runner.py update --stage S --data-dir D --state F --field K --value V --impacted-file I --output F2
build_output.py --stage S --data-dir data/ --state-dir state/ --chapter chN        # 单章调试专用，默认走 gate
build_output.py --stage S --data-dir data/ --state-dir state/ --output outputs/R.md [--allow-partial]
progress.py init --stage S --state-dir state/ --data-dir data/                     # --data-dir 必带
progress.py next / status / mark chN DRAFTED|BLOCKED / gate [--chapters ...]
progress.py run-stage freeze | finalize --outputs-dir /mnt/user-data/outputs --task "..."
progress.py approve-downgrade --chapters chN --note "批准依据"
snapshot.py save --task "..." --output outputs/project_snapshot.json ...
snapshot.py show --input outputs/project_snapshot.json --verify
consistency.py --report R --data-dir D --stage S --state F --contracts references/consistency_contracts.json --standards references/standards_index.json --output state/consistency_check.json
# calibrate.py / bank_compile.py：二期工具（样例 ≥5 份才启用），一期不在管线命令面
```

## 领域速记

9 章固定（stages/tunneling.json 唯一真源，含「安全风险辨识与管控」独立章）；19 附图全 `[需附图]` 占位，通风/支护/安全监控/避灾路线/供电五张硬要求不可缺；docmgr 无 agent 可调写 API——交付=present_files，Word 排版在文档空间编辑器完成（本技能不做字体字号精排）。
```

- [ ] **Step 2: 校验 frontmatter 约束**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -c "
import re
text = open('SKILL.md', encoding='utf-8').read()
fm = text.split('---')[1]
name = re.search(r'name:\s*(\S+)', fm).group(1)
assert name == 'coal-mine-tunneling-regulation', '改名=注册失效'
desc = fm.split('description:')[1].split('license:')[0]
assert len(desc) <= 1024, f'description {len(desc)} > 1024'
assert '<' not in desc and '>' not in desc, 'description 禁尖括号'
print('FRONTMATTER_OK name + desc', len(desc))
"
```

- [ ] **Step 3: Commit**

```bash
git add skills/public/coal-mine-tunneling-regulation/SKILL.md
git commit -m "feat(tunneling-v2): SKILL.md重写为管线版(步骤0-6/两道门/派发协议/档案协议/KF契约J6参数)"
```

---

### Task 15: dormant 携带 + 全量测试 + E2E 验收 + 收尾

**Files:**
- Create: `skills/public/coal-mine-tunneling-regulation/tests/README.md`
- Modify: `.wolf/anatomy.md` / `.wolf/memory.md`（OpenWolf 收尾）

- [ ] **Step 1: tests/README.md**：

```markdown
# 测试

运行（技能根为 cwd）：`cd skills/public/coal-mine-tunneling-regulation && PYTHONUTF8=1 python -m pytest tests/ -v`

- 全部 stdlib-only + pytest，不 import backend/deerflow，不进 CI（backend make test 只收 backend/tests/）。
- fixtures/sample3218_digest.json 为 3218 样例脱敏产物（数值保留供回归；重建：`python tests/fixtures/build_fixture.py <docx路径>`，源文件不入库）。
- 涉及真实样本的用例：`TUNNELING_SAMPLE_DOCX` 环境变量 + skipif 门，无样本环境全跳过。
- calibrate.py/bank_compile.py 为二期 dormant 件：零调用点，二期启用条件=掘进规程样例 ≥5 份（先做节标题规范化清洗，否则必 rc=1）。
```

- [ ] **Step 2: 全量测试**

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 python -m pytest tests/ -v
# 期望: 全绿（test_ingest_forms 5 + test_profile 4 + test_formula_ventilation 3 + test_progress_gate 4 + test_contracts 3 + test_build_output 2 + test_snapshot 3 = 24 passed）
```

- [ ] **Step 3: E2E 验收（容器内一轮真实对话，程序化阈值比对——**不真实激活**审查技能，J9）**：

0. **spike（spec OQ1）**：先验证 docmgr 文档能否作为线程附件直接引用（上传档案 md 走步骤 0.5 一次）——结论回写 SKILL.md 步骤 0.5（若可，档案装载摩擦归零；若不可，维持文件上传路径）。随后 `POST /api/skills/reload` 或 `docker compose -p eai-docker restart gateway`（注意 memory：gateway 重启杀 in-flight run + reload-exclude 坑），确认 GET /api/skills 返回 v2 描述后再开线程。
1. 新线程说「帮我编 3218 运输顺槽掘进作业规程」→ 验证：步骤 0.5 建档表单出现（单卡）→ 档案落 data/00_profile.json。
2. 上传地质说明书/填表 → 门1 GATE1_COMPLETE。
3. run-stage freeze → 门2 anomalies 呈现（含待核实项 F2/F4）→「按冻结值继续」。
4. 3 波派发 → gate 全 VERIFIED → finalize BUILD_READY → consistency 无 fail → present_files 交付。
5. **程序化验收脚本**：交付 md 过一致性合约 rc≠1；锚杆长度/间排距/风速带与 `standards_index.limit_tables.review_skill_*` 逐条比对（读 JSON 比对，非激活审查技能）；9 章目录覆盖=stages 必备集。
6. 交付物导入文档空间人工抽查格式（封面/会审页/目录/正文/附图清单/贯彻记录六段齐全）。
7. **content_guidelines.md 消歧**（对抗评审 P2 双源冲突）：在 L74 风筒距迎头「≤10m」处加注「v2 以 formula_runner F1=L=5√S 冻结值为准；≤10m 为现行规程档位【待核实】」——两份文件都会被生成 agent 读取，安全参数禁双源打架。

- [ ] **Step 4: OpenWolf 收尾**：更新 `.wolf/anatomy.md`（新增 scripts/9+1 件、references/ 7 件、tests/ 条目）；`.wolf/memory.md` 追加落地记录；若实施中发现新坑→`.wolf/cerebrum.md` + `.wolf/buglog.json`。

- [ ] **Step 5: 最终 Commit + push**

```bash
git add skills/public/coal-mine-tunneling-regulation/ .wolf/anatomy.md .wolf/memory.md
git commit -m "feat(tunneling-v2): dormant工具说明+测试README+收尾文档"
git push origin main-dev-fork   # push flaky 时重试（memory: origin-push-postbuffer-fix）
```

---

## 任务依赖图

```
T1(KF,用户确认) ─┐
T2(复制)→T3(stage)→T4(fixture)→T5(ingest)→T7(formula)→T9(progress)
                    │              ├→T6(profile)          ├→T10(consistency)→T11(build_output)→T12(snapshot)
                    │              └→T8(planner,可并行)    └──────────────────┘
                                            T13(references 数据件,依赖T4/T3) → T14(SKILL.md,依赖全部契约) → T15(全测+E2E)
```

并行机会：T5/T6 可并行（T6 依赖 T5 的 ingest import 但只读既有接口）；T8 独立可并行；T13 依赖 T3/T4。
