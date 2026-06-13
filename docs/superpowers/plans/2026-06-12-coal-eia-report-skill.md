# 煤炭环评报告编写技能 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `coal-eia-report` 技能，支持在项目工作流中按章节逐步生成煤炭矿区总体规划环评报告。

**Architecture:** 单一 SKILL.md 技能文件驱动，复用现有 `knowledge-factory` MCP（模板解析）、`project` MCP（章节读写）和知识库 REST API（RAG 检索）。内置 Python 计算脚本支持专业计算。四重仿写防护确保不照抄样例。

**Tech Stack:** Markdown (SKILL.md + references)、Python 3.12+ (计算脚本)、现有 MCP 工具链

**设计文档:** `docs/superpowers/specs/2026-06-12-coal-eia-report-skill-design.md`

**样例报告源:** `D:\aiproj\Pisuan-Know\docs\横城矿区总体规划环评报告书.md`

---

## 文件结构总览

### 新建文件

| 文件 | 职责 |
|------|------|
| `skills/custom/coal-eia-report/SKILL.md` | 主技能文件：工作流 + 关键规则 + 章节生成指引 |
| `skills/custom/coal-eia-report/README.md` | 技能说明文档 |
| `skills/custom/coal-eia-report/references/report_structure.md` | 13章完整结构（模板不可用时的回退方案） |
| `skills/custom/coal-eia-report/references/terminology.md` | 环评专业术语词典 |
| `skills/custom/coal-eia-report/references/content_guidelines.md` | 各章节编写规范 |
| `skills/custom/coal-eia-report/references/compliance_checklist.md` | 合规检查条目 |
| `skills/custom/coal-eia-report/references/sample_entities.md` | 样例报告实体黑名单 |
| `skills/custom/coal-eia-report/references/calc_params_guide.md` | 计算参数说明 |
| `skills/custom/coal-eia-report/references/chapter_examples/sample_subsidence.md` | 沉陷预测章节样例 |
| `skills/custom/coal-eia-report/references/chapter_examples/sample_air_quality.md` | 大气影响预测章节样例 |
| `skills/custom/coal-eia-report/references/chapter_examples/sample_water_quality.md` | 水环境影响章节样例 |
| `skills/custom/coal-eia-report/references/chapter_examples/sample_ecology.md` | 生态环境影响章节样例 |
| `skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py` | 概率积分法沉陷预测 |
| `skills/custom/coal-eia-report/scripts/calc/calc_noise.py` | 噪声衰减计算 |
| `skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py` | 矿区水量平衡 |
| `skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py` | AERSCREEN 简化大气估算 |
| `skills/custom/coal-eia-report/scripts/calc/calc_capacity.py` | 大气/水环境容量估算 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `extensions_config.json` | 在 `skills` 中添加 `"coal-eia-report": { "enabled": true }` |

---

## Task 1: 创建目录结构

**Files:**
- Create: `skills/custom/coal-eia-report/`（目录）
- Create: `skills/custom/coal-eia-report/references/`（目录）
- Create: `skills/custom/coal-eia-report/references/chapter_examples/`（目录）
- Create: `skills/custom/coal-eia-report/scripts/calc/`（目录）

- [ ] **Step 1: 创建所有目录**

```bash
mkdir -p skills/custom/coal-eia-report/references/chapter_examples
mkdir -p skills/custom/coal-eia-report/scripts/calc
```

- [ ] **Step 2: 验证目录结构**

```bash
find skills/custom/coal-eia-report -type d
```

Expected:
```
skills/custom/coal-eia-report
skills/custom/coal-eia-report/references
skills/custom/coal-eia-report/references/chapter_examples
skills/custom/coal-eia-report/scripts
skills/custom/coal-eia-report/scripts/calc
```

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report
git commit -m "chore(skills): create coal-eia-report directory structure"
```

---

## Task 2: 样例实体黑名单

仿写防护的核心文件。列出横城样例报告中所有关键实体，用于生成后泄露检测。

**Files:**
- Create: `skills/custom/coal-eia-report/references/sample_entities.md`

- [ ] **Step 1: 创建实体黑名单文件**

从横城样例报告中提取所有实体。参考源文件 `D:\aiproj\Pisuan-Know\docs\横城矿区总体规划环评报告书.md` 的前150行，提取项目名称、矿井、地理、敏感目标、企业、产能数值。

写入 `skills/custom/coal-eia-report/references/sample_entities.md`，内容格式：

```markdown
# 样例报告实体黑名单

> 本文件列出了样例报告（横城矿区总体规划环评报告书）中的所有关键实体。
> 生成章节后必须扫描这些实体，确保不会泄露到新报告中。

## 项目名称
- 横城矿区
- 横城矿区总体规划
- 宁夏回族自治区横城矿区总体规划（修编）

## 矿井名称
- 马莲台煤矿（马莲台矿井）
- 任家庄煤矿（任家庄矿井）
- 红石湾煤矿（红石湾矿井）
- 丁家梁煤矿（丁家梁矿井）
- 甜水河勘查区

## 企业名称
- 宁夏宝丰能源集团
- 宝丰能源
- 神华宁夏煤业集团
- 神华宁煤
- 宁夏煤业
- 中煤科工集团北京华宇工程有限公司

## 地理位置
- 灵武市
- 灵武
- 宁东
- 宁东基地
- 宁东能源化工基地
- 甜水河
- 鸭子荡水库
- 银川市

## 敏感目标
- 白芨滩国家级自然保护区
- 白芨滩
- 明长城
- 鸭子荡水库饮用水水源地

## 行政区划
- 宁夏回族自治区
- 宁夏

## 产能数值（需替换为实际项目数据）
- 8.3Mt/a
- 6.0Mt/a
- 2.4Mt/a
- 3.6Mt/a
- 1.1Mt/a
- 0.6Mt/a
- 9.20Mt/a
- 58km²
- 86km²

## 其他专有名词
- 发改能源〔2004〕2166号
- 环审〔2006〕180号
- 环审〔2006〕179号
- 宁环审发〔2012〕30号
```

- [ ] **Step 2: 验证文件存在**

```bash
wc -l skills/custom/coal-eia-report/references/sample_entities.md
```

Expected: 60+ 行

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/sample_entities.md
git commit -m "feat(skills/coal-eia): add sample entity blacklist for anti-copy protection"
```

---

## Task 3: 环评专业术语词典

**Files:**
- Create: `skills/custom/coal-eia-report/references/terminology.md`

- [ ] **Step 1: 创建术语词典**

从横城样例报告和环评导则中提取核心术语。写入 `skills/custom/coal-eia-report/references/terminology.md`。

内容应包含以下分类（每个术语一行，中文定义）：

1. **环评基础术语**：环境影响评价、规划环评、建设项目环评、环境影响识别、环境影响预测、环境承载力、环境容量、环境功能区划、评价等级、评价范围、评价时段、环境保护目标、环境敏感目标
2. **大气环境术语**：环境空气质量标准（GB3095）、TSP、PM10、PM2.5、SO2、NOx、大气扩散模型、AERMOD、CALPUFF、最大落地浓度、卫生防护距离、大气环境容量
3. **水环境术语**：地表水环境质量标准（GB3838）、地下水质量标准（GB/T14848）、COD、BOD、氨氮、SS、水文地质、含水层、地下水补给、径流、水环境容量、水源地保护区
4. **生态术语**：生态系统、生物多样性、植被覆盖度、NPP（净第一性生产力）、土地利用/覆盖变化（LUCC）、生态弹性度、生态承载力、水土流失、荒漠化、采煤沉陷、沉陷区
5. **噪声术语**：声环境质量标准（GB3096）、等效连续A声级（Leq）、昼间/夜间噪声限值、声环境功能区、噪声衰减
6. **固废术语**：煤矸石、矿井水、危险废物、一般工业固废、综合利用、处置率
7. **地质/沉陷术语**：概率积分法、下沉系数、水平移动系数、主要影响角正切、充分采动、非充分采动、地表移动变形、倾斜、曲率、水平变形、保护煤柱
8. **法规标准术语**：HJ（环境保护行业标准）、GB（国家标准）、环评导则、三同时、排污许可证、总量控制、清洁生产

- [ ] **Step 2: 验证文件**

```bash
wc -l skills/custom/coal-eia-report/references/terminology.md
```

Expected: 80+ 行

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/terminology.md
git commit -m "feat(skills/coal-eia): add EIA terminology dictionary"
```

---

## Task 4: 13章报告结构（模板回退方案）

**Files:**
- Create: `skills/custom/coal-eia-report/references/report_structure.md`

- [ ] **Step 1: 创建13章结构文档**

从横城样例报告的完整标题层级提取。参考源文件 `D:\aiproj\Pisuan-Know\docs\横城矿区总体规划环评报告书.md` 的全部 `#`/`##`/`###` 标题。

写入 `skills/custom/coal-eia-report/references/report_structure.md`，每章包含：
- 章节标题和编号
- 二级/三级子节标题
- 每节的主要内容要点（1-3行）
- 该章节适用的 HJ 导则和 GB 标准

格式参考现有的 `skills/custom/fire-protection-report-v2/references/report_structure.md`。

13章结构概要（从样例报告提取的完整标题）：

```
第1章 总则（10个二级节）
  1.1 规划背景与任务由来
  1.2 编制依据（法律/法规/规章/技术规范/相关规划/技术资料）
  1.3 评价目的与原则
  1.4 评价范围
  1.5 评价时段
  1.6 评价分区
  1.7 环境功能区划及评价标准
  1.8 环境保护目标
  1.9 评价工作重点
  1.10 评价方法 / 评价工作程序

第2章 规划方案概况及分析（4个二级节）
  2.1 矿区交通与地理位置
  2.2 原矿区总体规划实施情况及规划本次修编主要变化
  2.3 本次规划方案概况（11个三级节）
  2.4 规划方案协调性分析

第3章 区域自然和社会经济概况（4个二级节）
  3.1 自然环境概况（6个三级节：地形/气候/水文/土壤/植被/地震）
  3.2 社会经济概况
  3.3 矿区环境质量现状调查与评价（4个三级节：大气/水/声/土壤）
  3.4 矿区生态环境现状调查与评价（7个三级节）

第4章 矿区开发环境影响回顾性评价（8个二级节）

第5章 环境影响识别与评价指标体系（2个二级节）

第6章 规划实施环境影响预测与评价（10个二级节）
  6.1 沉陷预测 / 6.2 生态 / 6.3 地表水 / 6.4 地下水
  6.5 大气 / 6.6 声 / 6.7 固废 / 6.8 社会经济
  6.9 敏感目标影响 / 6.10 风险

第7章 资源环境承载力分析（4个二级节）

第8章 规划方案综合论证及优化调整建议（9个二级节）

第9章 环境影响减缓措施（5个二级节）

第10章 环境管理、监测计划与跟踪评价（4个二级节）

第11章 清洁生产与循环经济分析（2个二级节）

第12章 公众参与（3个二级节）

第13章 结论与建议（10个二级节）
```

- [ ] **Step 2: 验证文件**

```bash
grep -c "^#" skills/custom/coal-eia-report/references/report_structure.md
```

Expected: 80+ 个标题行

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/report_structure.md
git commit -m "feat(skills/coal-eia): add 13-chapter report structure as template fallback"
```

---

## Task 5: 各章节编写规范

**Files:**
- Create: `skills/custom/coal-eia-report/references/content_guidelines.md`

- [ ] **Step 1: 创建编写规范文档**

为每个核心章节编写生成指南。文件 `skills/custom/coal-eia-report/references/content_guidelines.md`。

内容包含以下各节的编写规范（每节约10-20行描述）：

1. **通用规范**：Markdown 格式要求、表格格式、占位符规范、引用格式
2. **第1章 总则**：法律/法规/规章的分级列举方式、技术规范的引用格式
3. **第3章 环境现状**：监测数据表格的列要求（测点/日期/浓度/标准/达标情况）、各要素的评价方法
4. **第6章 影响预测**：计算章节的方法论描述规范（模型→参数→结果→结论）、预测结果表格格式、浓度等值线/沉陷等值线描述方式
5. **第9章 减缓措施**：措施的分级分类方式（源头控制→过程减排→末端治理）、与标准条文的对应关系
6. **第7章 承载力**：容量计算结果呈现方式、承载力判定标准
7. **第8章 综合论证**：论证逻辑结构、优化建议的格式

- [ ] **Step 2: 验证文件**

```bash
wc -l skills/custom/coal-eia-report/references/content_guidelines.md
```

Expected: 120+ 行

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/content_guidelines.md
git commit -m "feat(skills/coal-eia): add content writing guidelines for each chapter"
```

---

## Task 6: 合规检查条目

**Files:**
- Create: `skills/custom/coal-eia-report/references/compliance_checklist.md`

- [ ] **Step 1: 创建合规检查条目**

列出环评报告必须遵守的核心标准条款。文件 `skills/custom/coal-eia-report/references/compliance_checklist.md`。

内容包含：

```markdown
# 环评报告合规检查条目

## 法律法规层
- [ ] 报告引用的法律是否为最新版本
- [ ] 是否包含《中华人民共和国环境保护法》
- [ ] 是否包含《中华人民共和国环境影响评价法》
- [ ] 是否包含规划环评相关法规（国务院令第559号）
- [ ] 是否包含行业专项法规（煤炭法、矿产资源法等）

## 技术导则层
- [ ] 是否遵循 HJ130-2019《规划环境影响评价技术导则 总纲》
- [ ] 是否遵循 HJ463-2009《规划环评导则 煤炭工业矿区总体规划》
- [ ] 大气评价是否遵循 HJ2.2-2018
- [ ] 地表水评价是否遵循 HJ2.3-2018
- [ ] 地下水评价是否遵循 HJ610-2016
- [ ] 声环境评价是否遵循 HJ2.4-2009
- [ ] 生态评价是否遵循 HJ19-2011
- [ ] 土壤评价是否遵循 HJ964-2018
- [ ] 煤炭采选是否遵循 HJ619-2011

## 标准规范层
- [ ] 环境空气质量标准引用 GB3095 是否为最新版
- [ ] 地表水质量标准引用 GB3838 是否正确
- [ ] 地下水质量标准引用 GB/T14848 是否正确
- [ ] 声环境质量标准引用 GB3096 是否正确
- [ ] 土壤环境质量引用 GB15618/GB36600 是否正确
- [ ] 工业企业厂界噪声标准 GB12348 引用是否正确
- [ ] 大气污染物排放标准 GB16297 引用是否正确
- [ ] 煤炭工业污染物排放标准 GB20426 引用是否正确

## 评价方法层
- [ ] 沉陷预测是否使用概率积分法
- [ ] 大气预测是否说明选用的模型及理由
- [ ] 地表水预测是否说明选用的模型及理由
- [ ] 地下水预测是否说明选用的模型及理由
- [ ] 噪声预测是否说明计算方法
- [ ] 生态评价是否包含生物多样性调查
- [ ] 是否包含清洁生产分析
- [ ] 是否包含循环经济分析
- [ ] 是否包含公众参与
- [ ] 是否包含环境监测计划
- [ ] 是否包含跟踪评价方案

## 数据完整性层
- [ ] 是否提供了评价范围图
- [ ] 是否提供了环境敏感目标分布图
- [ ] 监测数据是否注明监测时间和监测单位
- [ ] 计算结果是否列明输入参数
- [ ] 减缓措施是否可对应到具体影响结论
```

- [ ] **Step 2: 验证文件**

```bash
grep -c "\- \[ \]" skills/custom/coal-eia-report/references/compliance_checklist.md
```

Expected: 35+ 个检查条目

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/compliance_checklist.md
git commit -m "feat(skills/coal-eia): add compliance checklist for EIA report validation"
```

---

## Task 7: 计算参数指南

**Files:**
- Create: `skills/custom/coal-eia-report/references/calc_params_guide.md`

- [ ] **Step 1: 创建计算参数指南**

描述各计算脚本所需的输入参数、取值范围和典型值。文件 `skills/custom/coal-eia-report/references/calc_params_guide.md`。

内容包含5个计算模块的参数说明：

1. **沉陷预测（概率积分法）**：下沉系数 q (0.5-1.0)、水平移动系数 b (0.2-0.4)、主要影响角正切 tanβ (1.5-3.0)、拐点偏移距 s、开采厚度 m、采深 H、煤层倾角 α
2. **噪声衰减**：声源类型（点/线）、源强 dB(A)、距离 m、大气吸收系数、地面衰减、屏障衰减
3. **水量平衡**：矿井涌水量、选煤用水量、生活用水量、绿化用水量、蒸发损耗、回用水量
4. **大气估算（AERSCREEN）**：排放速率 g/s、烟囱高度 m、烟囱出口内径 m、烟气温度 K、排气量 m³/s、环境温度、风速
5. **环境容量**：环境质量目标值、现状浓度、排放量、背景浓度

- [ ] **Step 2: 验证文件**

```bash
wc -l skills/custom/coal-eia-report/references/calc_params_guide.md
```

Expected: 60+ 行

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/references/calc_params_guide.md
git commit -m "feat(skills/coal-eia): add calculation parameter guide"
```

---

## Task 8: 章节样例（4个）

从横城样例报告中提取4个核心章节的方法论部分（去除实体数据），作为生成参考。

**Files:**
- Create: `skills/custom/coal-eia-report/references/chapter_examples/sample_subsidence.md`
- Create: `skills/custom/coal-eia-report/references/chapter_examples/sample_air_quality.md`
- Create: `skills/custom/coal-eia-report/references/chapter_examples/sample_water_quality.md`
- Create: `skills/custom/coal-eia-report/references/chapter_examples/sample_ecology.md`

- [ ] **Step 1: 提取沉陷预测章节样例**

从 `D:\aiproj\Pisuan-Know\docs\横城矿区总体规划环评报告书.md` 中找到第6.1章的内容。提取沉陷预测的方法论部分，将实体数据替换为 `[样例数据已移除]`。

写入 `skills/custom/coal-eia-report/references/chapter_examples/sample_subsidence.md`。

保留内容：概率积分法的公式、参数选取方法、预测结果表格格式、结论表述范式。
移除内容：横城矿区具体参数值、矿井名称、具体下沉量数值。

- [ ] **Step 2: 提取大气影响预测章节样例**

从样例报告第6.4章提取大气环境影响预测部分。同样去除实体数据。

写入 `skills/custom/coal-eia-report/references/chapter_examples/sample_air_quality.md`。

保留内容：预测模型选取逻辑、计算参数说明方式、浓度预测结果表格格式、达标分析表述。
移除内容：具体排放源数据、具体浓度值。

- [ ] **Step 3: 提取水环境影响章节样例**

从样例报告第6.3章提取。写入 `skills/custom/coal-eia-report/references/chapter_examples/sample_water_quality.md`。

- [ ] **Step 4: 提取生态环境影响章节样例**

从样例报告第6.2章提取。写入 `skills/custom/coal-eia-report/references/chapter_examples/sample_ecology.md`。

- [ ] **Step 5: 验证所有样例文件存在且不为空**

```bash
for f in sample_subsidence sample_air_quality sample_water_quality sample_ecology; do
  echo "$f: $(wc -l < skills/custom/coal-eia-report/references/chapter_examples/${f}.md) lines"
done
```

Expected: 每个文件 30+ 行

- [ ] **Step 6: 提交**

```bash
git add skills/custom/coal-eia-report/references/chapter_examples/
git commit -m "feat(skills/coal-eia): add chapter examples for 4 core sections"
```

---

## Task 9: 沉陷预测计算脚本（TDD）

概率积分法沉陷预测，最核心的计算工具。

**Files:**
- Create: `skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py`

- [ ] **Step 1: 编写沉陷预测脚本**

创建 `skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py`，实现概率积分法的核心计算：

```python
#!/usr/bin/env python3
"""概率积分法沉陷预测计算脚本。

输入参数（JSON）:
  - q: 下沉系数 (0.5-1.0)
  - b: 水平移动系数 (0.2-0.4)
  - tan_beta: 主要影响角正切 (1.5-3.0)
  - m: 开采厚度 (m)
  - H: 平均采深 (m)
  - alpha: 煤层倾角 (度)
  - s_offset: 拐点偏移距 (m)，可选，默认 0
  - points: 计算点列表 [{x, y}]，可选，默认计算主断面

输出（JSON）:
  - max_subsidence: 最大下沉值 (mm)
  - max_horizontal_move: 最大水平移动值 (mm)
  - max_inclination: 最大倾斜 (mm/m)
  - max_curvature: 最大曲率 (10^-3/m)
  - max_horizontal_deform: 最大水平变形 (mm/m)
  - influence_radius: 主要影响半径 (m)
  - profile: 主断面曲线数据点 [{x, subsidence, ...}]
"""
import argparse
import json
import math
import sys


def calc_subsidence(q, b, tan_beta, m, H, alpha_deg, s_offset=0):
    """概率积分法核心计算。

    公式：
      W_max = q * m * cos(alpha)         最大下沉值
      r = H / tan_beta                   主要影响半径
      U_max = b * W_max                   最大水平移动
      i_max = W_max / r                   最大倾斜
      K_max = 1.52 * W_max / r^2          最大曲率
      eps_max = 1.52 * b * W_max / r      最大水平变形
    """
    alpha_rad = math.radians(alpha_deg)
    W_max = q * m * math.cos(alpha_rad) * 1000  # 转换为 mm
    r = H / tan_beta
    U_max = b * W_max
    i_max = W_max / r
    K_max = 1.52 * W_max / (r * r)
    eps_max = 1.52 * b * W_max / r

    return {
        "max_subsidence_mm": round(W_max, 2),
        "max_horizontal_move_mm": round(U_max, 2),
        "max_inclination_mm_per_m": round(i_max, 4),
        "max_curvature_per_km": round(K_max * 1e-3, 6),
        "max_horizontal_deform_mm_per_m": round(eps_max, 4),
        "influence_radius_m": round(r, 2),
    }


def calc_profile(q, b, tan_beta, m, H, alpha_deg, num_points=50):
    """计算主断面下沉曲线。"""
    r = H / tan_beta
    alpha_rad = math.radians(alpha_deg)
    W_max = q * m * math.cos(alpha_rad) * 1000

    points = []
    for i in range(num_points + 1):
        x = -2 * r + (4 * r * i / num_points)
        # 概率积分法的下沉分布函数 W(x) = W_max/2 * [1 + erf(x*sqrt(pi)/(r*2))]
        erf_arg = x * math.sqrt(math.pi) / (2 * r)
        W_x = (W_max / 2) * (1 + math.erf(-erf_arg))
        U_x = b * W_max * math.exp(-(x * math.sqrt(math.pi) / (2 * r)) ** 2) * (
            -math.sqrt(math.pi) / (2 * r)
        )
        # 避免除零
        if abs(x) < 0.01:
            i_x = 0
        else:
            i_x = (W_max / r) * math.exp(-(x * math.sqrt(math.pi) / (2 * r)) ** 2)

        points.append({
            "x_m": round(x, 2),
            "subsidence_mm": round(max(0, W_x), 2),
            "horizontal_move_mm": round(U_x, 2),
            "inclination_mm_per_m": round(abs(i_x), 4),
        })

    return points


def main():
    parser = argparse.ArgumentParser(description="概率积分法沉陷预测")
    parser.add_argument("--params", required=True, help="JSON格式输入参数")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    params = json.loads(args.params)
    result = calc_subsidence(
        q=params["q"],
        b=params["b"],
        tan_beta=params["tan_beta"],
        m=params["m"],
        H=params["H"],
        alpha_deg=params["alpha"],
        s_offset=params.get("s_offset", 0),
    )

    if params.get("include_profile", False):
        result["profile"] = calc_profile(
            params["q"], params["b"], params["tan_beta"],
            params["m"], params["H"], params["alpha"],
        )

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"最大下沉值: {result['max_subsidence_mm']} mm")
        print(f"最大水平移动: {result['max_horizontal_move_mm']} mm")
        print(f"最大倾斜: {result['max_inclination_mm_per_m']} mm/m")
        print(f"最大曲率: {result['max_curvature_per_km']} ×10⁻³/m")
        print(f"最大水平变形: {result['max_horizontal_deform_mm_per_m']} mm/m")
        print(f"主要影响半径: {result['influence_radius_m']} m")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 测试脚本基本计算**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py \
  --params '{"q": 0.78, "b": 0.3, "tan_beta": 2.2, "m": 3.5, "H": 350, "alpha": 8}' \
  --output text
```

Expected: 输出最大下沉值约 2725 mm、主要影响半径约 159 m 等合理数值。

- [ ] **Step 3: 测试 JSON 输出**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py \
  --params '{"q": 0.78, "b": 0.3, "tan_beta": 2.2, "m": 3.5, "H": 350, "alpha": 8, "include_profile": true}' \
  --output json | python -m json.tool > /dev/null
```

Expected: 无错误退出（exit code 0）

- [ ] **Step 4: 提交**

```bash
git add skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py
git commit -m "feat(skills/coal-eia): add subsidence prediction calc script (probability integral method)"
```

---

## Task 10: 噪声衰减计算脚本

**Files:**
- Create: `skills/custom/coal-eia-report/scripts/calc/calc_noise.py`

- [ ] **Step 1: 编写噪声衰减计算脚本**

创建 `skills/custom/coal-eia-report/scripts/calc/calc_noise.py`，实现：

```python
#!/usr/bin/env python3
"""噪声衰减计算脚本。

支持点声源和线声源衰减计算。
输入参数（JSON）:
  - source_type: "point" 或 "line"
  - source_level_dbA: 声源级 dB(A)
  - distances_m: 计算距离列表 [50, 100, 200, ...]
  - atmospheric_absorption: 大气吸收衰减 dB/km，默认 5
  - ground_factor: 地面衰减因子 (0-1)，默认 0

输出（JSON）:
  - results: 各距离点的噪声级 [{distance_m, noise_level_dBA}]
  -达标判断（依据 GB3096 或 GB12348 标准限值）
"""
import argparse
import json
import math
import sys


POINT_SOURCE_REF_DIST = 1.0  # 点声源参考距离 1m
LINE_SOURCE_REF_DIST = 7.5   # 线声源参考距离 7.5m


def calc_point_attenuation(source_db, distance, atm_absorption=5, ground_factor=0):
    """点声源衰减。Lp = Lw - 20*log10(r) - 11 - ΔLatm - ΔLground"""
    if distance <= 0:
        return source_db
    geometric_spread = 20 * math.log10(distance / POINT_SOURCE_REF_DIST)
    atm_loss = atm_absorption * distance / 1000
    ground_loss = ground_factor * 4.8 * math.log10(max(distance, 1) / 7.5)
    return source_db - geometric_spread - atm_loss - max(0, ground_loss)


def calc_line_attenuation(source_db, distance, atm_absorption=5, ground_factor=0):
    """线声源衰减。Lp = Lw - 10*log10(r/7.5) - ΔLatm - ΔLground"""
    if distance <= 0:
        return source_db
    geometric_spread = 10 * math.log10(max(distance, 0.1) / LINE_SOURCE_REF_DIST)
    atm_loss = atm_absorption * distance / 1000
    ground_loss = ground_factor * 4.8 * math.log10(max(distance, 1) / 7.5)
    return source_db - geometric_spread - atm_loss - max(0, ground_loss)


def check_compliance(noise_level, standard_limit_day=60, standard_limit_night=50):
    """检查是否达标（GB12348 2类标准默认值）。"""
    return {
        "day_compliant": noise_level <= standard_limit_day,
        "night_compliant": noise_level <= standard_limit_night,
    }


def main():
    parser = argparse.ArgumentParser(description="噪声衰减计算")
    parser.add_argument("--params", required=True, help="JSON格式输入参数")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    params = json.loads(args.params)
    source_type = params.get("source_type", "point")
    source_db = params["source_level_dBA"]
    distances = params.get("distances_m", [50, 100, 200, 400, 800])
    atm = params.get("atmospheric_absorption", 5)
    ground = params.get("ground_factor", 0)
    day_limit = params.get("day_limit_dBA", 60)
    night_limit = params.get("night_limit_dBA", 50)

    calc_fn = calc_point_attenuation if source_type == "point" else calc_line_attenuation
    results = []
    for d in distances:
        level = calc_fn(source_db, d, atm, ground)
        compliance = check_compliance(level, day_limit, night_limit)
        results.append({
            "distance_m": d,
            "noise_level_dBA": round(level, 1),
            "day_compliant": compliance["day_compliant"],
            "night_compliant": compliance["night_compliant"],
        })

    output = {"source_type": source_type, "results": results}
    if args.output == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"声源类型: {source_type}, 源强: {source_db} dB(A)")
        for r in results:
            status = "✅" if r["day_compliant"] else "❌"
            print(f"  {r['distance_m']}m: {r['noise_level_dBA']} dB(A) {status}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 测试点声源计算**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_noise.py \
  --params '{"source_type": "point", "source_level_dBA": 95, "distances_m": [50, 100, 200, 400]}' \
  --output text
```

Expected: 50m 处约 60 dB(A) 附近，距离翻倍衰减约 6 dB。

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/scripts/calc/calc_noise.py
git commit -m "feat(skills/coal-eia): add noise attenuation calc script"
```

---

## Task 11: 水量平衡计算脚本

**Files:**
- Create: `skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py`

- [ ] **Step 1: 编写水量平衡脚本**

创建 `skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py`：

```python
#!/usr/bin/env python3
"""矿区水量平衡计算脚本。

输入参数（JSON）:
  - supply: 供水量各项 [{name, volume_m3d}]
  - demand: 用水量各项 [{name, volume_m3d, category}]
  - reuse: 回用水量各项 [{name, volume_m3d, from_process}]
  - discharge: 外排水量各项 [{name, volume_m3d}]

输出（JSON）:
  - total_supply: 总供水量
  - total_demand: 总用水量
  - total_reuse: 总回用水量
  - total_discharge: 总外排水量
  - balance: 盈余/亏缺
  - reuse_rate: 水资源复用率
  - balance_table: 供需平衡表
"""
import argparse
import json
import sys


def calc_water_balance(supply, demand, reuse, discharge):
    """计算水量平衡。"""
    total_supply = sum(s["volume_m3d"] for s in supply)
    total_demand = sum(d["volume_m3d"] for d in demand)
    total_reuse = sum(r["volume_m3d"] for r in reuse)
    total_discharge = sum(d["volume_m3d"] for d in discharge)
    balance = total_supply - total_demand

    # 水资源复用率 = 回用水量 / (总用水量 + 回用水量)
    reuse_rate = total_reuse / (total_demand + total_reuse) if (total_demand + total_reuse) > 0 else 0

    # 外排水率
    discharge_rate = total_discharge / total_supply if total_supply > 0 else 0

    # 损耗量 = 供水量 - 外排水量 - 回用水量
    loss = total_supply - total_discharge - total_reuse

    return {
        "total_supply_m3d": round(total_supply, 2),
        "total_demand_m3d": round(total_demand, 2),
        "total_reuse_m3d": round(total_reuse, 2),
        "total_discharge_m3d": round(total_discharge, 2),
        "balance_m3d": round(balance, 2),
        "loss_m3d": round(loss, 2),
        "reuse_rate_pct": round(reuse_rate * 100, 1),
        "discharge_rate_pct": round(discharge_rate * 100, 1),
        "supply_items": supply,
        "demand_items": demand,
        "reuse_items": reuse,
        "discharge_items": discharge,
    }


def main():
    parser = argparse.ArgumentParser(description="矿区水量平衡计算")
    parser.add_argument("--params", required=True, help="JSON格式输入参数")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    params = json.loads(args.params)
    result = calc_water_balance(
        supply=params.get("supply", []),
        demand=params.get("demand", []),
        reuse=params.get("reuse", []),
        discharge=params.get("discharge", []),
    )

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"总供水量: {result['total_supply_m3d']} m³/d")
        print(f"总用水量: {result['total_demand_m3d']} m³/d")
        print(f"总回用水量: {result['total_reuse_m3d']} m³/d")
        print(f"总外排水量: {result['total_discharge_m3d']} m³/d")
        print(f"平衡: {result['balance_m3d']} m³/d ({'盈余' if result['balance_m3d'] >= 0 else '亏缺'})")
        print(f"复用率: {result['reuse_rate_pct']}%")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 测试水量平衡**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py \
  --params '{"supply":[{"name":"矿井涌水","volume_m3d":5000},{"name":"市政供水","volume_m3d":2000}],"demand":[{"name":"选煤用水","volume_m3d":3000},{"name":"井下洒水","volume_m3d":1500},{"name":"生活用水","volume_m3d":800}],"reuse":[{"name":"矿井水处理后回用","volume_m3d":2000}],"discharge":[{"name":"处理后外排","volume_m3d":2700}]}' \
  --output text
```

Expected: 总供水量 7000, 总用水量 5300, 复用率约 27.4%

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py
git commit -m "feat(skills/coal-eia): add water balance calc script"
```

---

## Task 12: 大气估算和环境容量脚本

**Files:**
- Create: `skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py`
- Create: `skills/custom/coal-eia-report/scripts/calc/calc_capacity.py`

- [ ] **Step 1: 编写 AERSCREEN 简化大气估算脚本**

创建 `skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py`：

```python
#!/usr/bin/env python3
"""AERSCREEN 简化大气估算脚本。

基于高斯烟羽模式的简化版本，估算最大落地浓度。
输入参数（JSON）:
  - emission_rate_gs: 排放速率 (g/s)
  - stack_height_m: 烟囱高度 (m)
  - stack_diameter_m: 烟囱出口内径 (m)
  - exit_velocity_ms: 烟气出口速度 (m/s)
  - exit_temp_K: 烟气温度 (K)
  - ambient_temp_K: 环境温度 (K)，默认 293
  - wind_speed_ms: 风速 (m/s)，默认 3.0
  - stability_class: 大气稳定度 (A-F)，默认 "D"

输出（JSON）:
  - max_ground_concentration_ugm3: 最大地面浓度
  - max_distance_m: 最大落地浓度距离
  - effective_height_m: 有效烟囱高度
"""
import argparse
import json
import math
import sys


def calc_effective_height(stack_height, exit_velocity, stack_diameter, wind_speed, exit_temp, ambient_temp):
    """计算有效烟囱高度 H_eff = H + ΔH（Holland 公式）。"""
    delta_T = exit_temp - ambient_temp
    if wind_speed <= 0:
        wind_speed = 0.5
    # Holland 抬升公式
    delta_H = (exit_velocity * stack_diameter / wind_speed) * (
        1.5 + 2.68e-3 * delta_T * stack_diameter / wind_speed
    )
    return stack_height + max(0, delta_H)


def calc_gaussian_concentration(Q, H_eff, u, stability="D"):
    """简化高斯烟羽模式，估算最大地面浓度。"""
    # Briggs 扩散参数（城市条件）
    sigma_y_coeff = {"A": 0.32, "B": 0.32, "C": 0.22, "D": 0.16, "E": 0.11, "F": 0.11}
    sigma_z_coeff = {"A": 0.24, "B": 0.24, "C": 0.20, "D": 0.14, "E": 0.08, "F": 0.06}
    sigma_y_power = {"A": 0.78, "B": 0.78, "C": 0.89, "D": 0.89, "E": 0.89, "F": 0.89}
    sigma_z_power = {"A": 0.50, "B": 0.50, "C": 0.50, "D": 0.50, "E": 0.50, "F": 0.50}

    ay = sigma_y_coeff.get(stability, 0.16)
    py = sigma_y_power.get(stability, 0.89)
    az = sigma_z_coeff.get(stability, 0.14)
    pz = sigma_z_power.get(stability, 0.50)

    # 求最大浓度距离（数值搜索）
    max_conc = 0
    max_dist = 0
    for x in range(100, 20000, 50):
        sigma_y = ay * x ** py
        sigma_z = az * x ** pz
        if sigma_z <= 0 or sigma_y <= 0:
            continue
        # 地面中心线浓度 C = Q/(π*u*σy*σz) * exp(-H²/(2σz²))
        exp_term = math.exp(-(H_eff ** 2) / (2 * sigma_z ** 2))
        C = (Q / (math.pi * u * sigma_y * sigma_z)) * exp_term
        if C > max_conc:
            max_conc = C
            max_dist = x

    # Q in g/s → μg/m³ 转换：C * 1e6
    return max_conc * 1e6, max_dist


def main():
    parser = argparse.ArgumentParser(description="AERSCREEN 简化大气估算")
    parser.add_argument("--params", required=True, help="JSON格式输入参数")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    params = json.loads(args.params)
    H_eff = calc_effective_height(
        params["stack_height_m"],
        params["exit_velocity_ms"],
        params["stack_diameter_m"],
        params.get("wind_speed_ms", 3.0),
        params["exit_temp_K"],
        params.get("ambient_temp_K", 293),
    )
    max_conc, max_dist = calc_gaussian_concentration(
        params["emission_rate_gs"],
        H_eff,
        params.get("wind_speed_ms", 3.0),
        params.get("stability_class", "D"),
    )

    result = {
        "max_ground_concentration_ugm3": round(max_conc, 4),
        "max_distance_m": max_dist,
        "effective_height_m": round(H_eff, 2),
    }

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"最大地面浓度: {result['max_ground_concentration_ugm3']} μg/m³")
        print(f"最大浓度距离: {result['max_distance_m']} m")
        print(f"有效烟囱高度: {result['effective_height_m']} m")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 测试大气估算**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py \
  --params '{"emission_rate_gs": 10, "stack_height_m": 60, "stack_diameter_m": 2.5, "exit_velocity_ms": 15, "exit_temp_K": 373}' \
  --output text
```

Expected: 输出最大地面浓度和距离

- [ ] **Step 3: 编写环境容量估算脚本**

创建 `skills/custom/coal-eia-report/scripts/calc/calc_capacity.py`：

```python
#!/usr/bin/env python3
"""大气/水环境容量估算脚本。

基于 A-P 值法估算大气环境容量。
基于一维水质模型估算水环境容量。
"""
import argparse
import json
import math
import sys


def calc_air_capacity(area_km2, target_conc, background_conc, a_value, p_value=None):
    """A值法大气环境容量估算。

    Qa = A * (Cs - Cb) * S / sqrt(S)
    A: 地理区域总量控制系数
    Cs: 环境质量目标浓度
    Cb: 背景浓度
    S: 区域面积 km²
    """
    if p_value is not None:
        # 考虑本底排放的修正
        Qa = a_value * (target_conc - background_conc) * math.sqrt(area_km2) * p_value
    else:
        Qa = a_value * (target_conc - background_conc) * math.sqrt(area_km2)

    remaining = max(0, target_conc - background_conc)
    return {
        "method": "A值法",
        "total_capacity_ta": round(Qa, 2),
        "background_conc_ugm3": background_conc,
        "target_conc_ugm3": target_conc,
        "remaining_capacity_ugm3": round(remaining, 2),
        "area_km2": area_km2,
    }


def calc_water_capacity(target_mgl, background_mgl, flow_m3s, decay_rate=0.1):
    """一维水质模型水环境容量估算。

    W = 86.4 * Q * (Cs - Cb) + k * Cs * V
    简化: W ≈ Q * (Cs - Cb) + k * Cs * Q * L / u
    """
    capacity_conc = max(0, target_mgl - background_mgl)
    # 简化计算 W = 86.4 * Q * ΔC (吨/天)
    W_daily = flow_m3s * 86400 * capacity_conc / 1000  # 吨/天
    W_yearly = W_daily * 365 / 1000  # 吨/年

    return {
        "method": "一维水质模型",
        "capacity_conc_mgl": round(capacity_conc, 3),
        "capacity_daily_t": round(W_daily, 2),
        "capacity_yearly_t": round(W_yearly, 2),
        "target_mgl": target_mgl,
        "background_mgl": background_mgl,
        "flow_m3s": flow_m3s,
    }


def main():
    parser = argparse.ArgumentParser(description="环境容量估算")
    parser.add_argument("--params", required=True, help="JSON格式输入参数")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    params = json.loads(args.params)
    env_type = params.get("type", "air")

    if env_type == "air":
        result = calc_air_capacity(
            area_km2=params["area_km2"],
            target_conc=params["target_conc_ugm3"],
            background_conc=params["background_conc_ugm3"],
            a_value=params.get("a_value", 4.2),
        )
    elif env_type == "water":
        result = calc_water_capacity(
            target_mgl=params["target_mgl"],
            background_mgl=params["background_mgl"],
            flow_m3s=params["flow_m3s"],
        )
    else:
        print(json.dumps({"error": f"Unknown type: {env_type}"}))
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 测试环境容量**

```bash
python skills/custom/coal-eia-report/scripts/calc/calc_capacity.py \
  --params '{"type": "air", "area_km2": 86, "target_conc_ugm3": 70, "background_conc_ugm3": 35}' \
  --output text
```

Expected: 输出大气环境容量（吨/年）

- [ ] **Step 5: 提交两个脚本**

```bash
git add skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py \
        skills/custom/coal-eia-report/scripts/calc/calc_capacity.py
git commit -m "feat(skills/coal-eia): add air dispersion and environmental capacity calc scripts"
```

---

## Task 13: SKILL.md 主技能文件

这是最核心的文件，定义整个技能的工作流和规则。

**Files:**
- Create: `skills/custom/coal-eia-report/SKILL.md`

- [ ] **Step 1: 创建 SKILL.md**

写入 `skills/custom/coal-eia-report/SKILL.md`，完整内容如下（参考 `skills/custom/fire-protection-report-v2/SKILL.md` 的格式模式）：

```markdown
---
name: coal-eia-report
description: |
  当用户请求为煤炭矿区项目生成、创建或编写环境影响评价报告书（环评报告）时使用此技能。

  此技能优先从知识工厂（Knowledge Factory）获取报告模板元数据——通过 MCP 工具 kf_resolve_template
  智能匹配已抽取和编辑优化的模板，使用模板中的 generation_hint、compliance_rules、content_contract
  等元数据驱动高质量报告生成。模板不可用时自动回退到内置参考文档。

  触发场景：用户提及"环评报告""环境影响评价报告书""煤炭环评""矿区总体规划环评""环境影响报告书"
  "环评报告书生成""环评编写""环评报告编制"等关键词；
  或需要在煤炭/矿业项目中编写环境影响评价相关文档时。
  即使用户没有明确说"生成报告"，只要涉及煤炭项目环境影响评价文档编写，都应使用此技能。
---

# 煤炭矿区总体规划环评报告编写技能

## ⛔ 关键规则

### 关于输出方式

1. 本技能在项目工作流中按章节生成**结构化 Markdown 文本**，通过 `project` MCP 的 `write_chapter` 写入。
2. 生成后用户在项目工作流中审阅、编辑、提交审批。
3. 不直接生成 .docx 文件——用户会在项目工作流中自行编辑排版后导出。
4. 不使用 `word-document-server` MCP 工具、`markdown-to-docx` skill 或自写 Python 脚本来生成 Word。

### 关于模板获取

5. 优先调用 `kf_resolve_template` 获取知识工厂模板元数据。
6. 仅当 MCP 工具返回 `found=false` 或调用失败时，才回退到读取 `references/` 下的参考文档。

### 关于仿写约束（极其重要）

7. 样例报告是**方法论和结构参考**，不是内容来源。
8. **禁止原样复制**样例报告中的任何段落、表格数据或数值。
9. 从样例报告中只学习：
   - 各章节的论证逻辑和分析思路
   - 专业术语和表述方式
   - 表格和图表的结构范式
   - 评价方法的选用和描述
10. **必须替换**样例中的所有实体数据：
   - 项目/矿区/矿井名称 → 使用项目实体卡片中的名称
   - 地理位置描述 → 使用当前项目的地理位置
   - 产能/规模数值 → 使用当前项目的数据
   - 环境监测数据 → 使用当前项目的数据或标注[待补充]
   - 敏感目标名称 → 使用当前项目的敏感目标
11. 缺少数据时用 `[待补充: 需提供XX数据]` 占位，**绝不**用样例数据填充。
12. 生成后自动进行实体泄露检测（检查 `references/sample_entities.md` 黑名单）。

### 关于执行顺序

13. 每次对话轮次生成**一个章节**（或一个二级子章节）。
14. 通过 `list_chapters` 查找下一个 `status=pending` 的章节继续。
15. 章节生成顺序遵循批次依赖关系（批次1→2→3→4→5）。

## 概述

此技能为煤炭矿区总体规划项目生成专业的环境影响评价报告书。优先从知识工厂获取报告模板元数据，利用模板中从样本报告抽取的结构化知识驱动报告生成。当知识工厂模板不可用时，自动回退到内置参考文档。

生成的内容为结构化 Markdown，逐章节通过 `project` MCP 写入项目工作流，供用户后续编辑、审批和 Word 导出。

## 报告结构（13章）

标准煤炭矿区总体规划环评报告遵循以下结构（来源：模板 `root_sections` 或 `references/report_structure.md`）：

| 章 | 标题 | 内容类型 |
|----|------|----------|
| 1 | 总则 | 法律法规、技术规范、评价范围和标准 |
| 2 | 规划方案概况及分析 | 项目参数表格、规划方案、协调性分析 |
| 3 | 区域自然和社会经济概况 | 地形气候、环境现状监测数据 |
| 4 | 矿区开发环境影响回顾性评价 | 历史 data 分析、回顾评价 |
| 5 | 环境影响识别与评价指标体系 | 影响识别矩阵、指标体系 |
| 6 | 规划实施环境影响预测与评价 | **核心**：沉陷/生态/水/大气/声/固废预测 |
| 7 | 矿区资源、环境承载力分析 | 水资源/生态/大气/水环境容量 |
| 8 | 规划方案综合论证及优化调整 | 合理性分析、优化建议 |
| 9 | 规划实施环境影响减缓措施 | 各要素减缓措施 |
| 10 | 环境管理、监测计划与跟踪评价 | 管理计划、监测方案 |
| 11 | 矿区清洁生产与循环经济分析 | 清洁生产指标、循环经济 |
| 12 | 公众参与 | 公众调查结果 |
| 13 | 结论与建议 | 综合结论 |

## 引用的核心标准

- HJ130-2019 规划环境影响评价技术导则 总纲
- HJ463-2009 规划环评导则 煤炭工业矿区总体规划
- HJ2.1-2016 环评导则 总纲
- HJ2.2-2018 环评导则 大气环境
- HJ2.3-2018 环评导则 地表水环境
- HJ610-2016 环评导则 地下水环境
- HJ2.4-2009 环评导则 声环境
- HJ19-2011 环评导则 生态影响
- HJ964-2018 环评导则 土壤环境
- HJ619-2011 环评导则 煤炭采选工程
- GB3095 环境空气质量标准
- GB3838 地表水环境质量标准
- GB/T14848 地下水质量标准
- GB3096 声环境质量标准

---

## 工作流

### 步骤1：了解需求 + 建立项目实体卡片

当用户请求环评报告时，确定以下信息。用户可能不会一次提供全部信息，对于缺失的关键信息应主动追问，对于可从上下文推断的信息直接使用：

**必须确认**（缺少则追问）：
- 项目名称和矿区名称
- 报告类型：总体规划环评 / 建设项目环评 / 规划环评跟踪
- 评价范围（km²）

**尽量收集**（缺少时可标注待补充）：
- 矿区现有矿井名称和产能
- 地理位置（省/市/县）
- 用户选择的计算模式：内置脚本 / 占位符 / 外部API
- 是否有已批复的环评或验收文件
- 设计/评价单位名称

**建立项目实体卡片**：将收集的信息组织为结构化的实体卡片，通过项目元数据存储。实体卡片模板见 `references/content_guidelines.md` 中的"项目实体卡片"章节。

**信息不足时的策略**：
- 如果用户只给了项目名，先基于常见煤炭矿区模板生成草稿，在需要具体数据的表格中标注 `[待补充]`
- 绝不编造具体数值（如污染物浓度、产能数据），用占位符 `[XX]` 并提示用户补充
- 绝不从样例报告中取用实体数据

### 步骤2：解析报告模板

**首先尝试从知识工厂获取模板元数据。** 调用 MCP 工具：

```
kf_resolve_template(
    domain_keywords=["煤炭环评报告", "矿区总体规划环评", "环境影响评价报告书"],
    industry="煤炭",
    report_type="环境影响评价",
    min_completeness_score=60
)
```

**成功时**（`found=true`）：
- 使用返回的 `sections` 作为报告结构
- 每个章节独立拥有 `generation_hint`、`compliance_rules`、`content_contract`、`example_snippet`
- 输出提示：`✅ 已从知识工厂获取模板：{template_name} v{version}（完整度: {completeness_score}/100, 匹配级别: {match_level}）`
- **跳过**读取 `references/report_structure.md` 的子步骤

**失败时**（`found=false` 或 MCP 调用超时/报错/不可用）：
- 输出提示：`⚠️ 知识工厂模板不可用（{reason}），使用内置参考文档继续生成`
- 读取 `references/report_structure.md` 获取13章结构
- 后续步骤使用全局标准列表替代逐章 compliance_rules

### 步骤3：加载补充知识（始终执行）

无论模板是否获取成功，始终读取以下文件：
- `references/terminology.md` — 环评专业术语
- `references/content_guidelines.md` — 各章节编写规范
- `references/sample_entities.md` — 样例实体黑名单

这些是领域背景知识，模板的 `generation_hint` 不包含完整的术语定义和编写规范。

### 步骤4：按章节生成（循环执行）

**每次对话轮次生成一个章节**，执行以下微流程：

1. 调用 `project` MCP → `list_chapters(project_id)` 找到第一个 `status=pending` 的章节
2. 调用 `get_chapter_spec(chapter_id)` 获取写作规范
3. 加载项目实体卡片，确保实体数据从卡片取值
4. 根据章节类型选择知识库执行 RAG 检索（方法论查询优先）
5. 如涉及计算，按用户选择的模式处理
6. 按 `generation_hint` + `content_contract` 约束生成内容（约2000-8000字）
7. 执行实体泄露检测（扫描 `sample_entities.md` 黑名单）
8. 调用 `write_chapter(chapter_id, content, status="draft")` 写入
9. 输出摘要给用户：章节标题 + 字数 + 关键结论 + 泄露检查结果 + 下一步建议

**章节类型与知识库映射**：

| 章节类型 | 检索知识库 |
|----------|------------|
| 环境现状（第3章） | 样例报告库 + 地理环境库 |
| 影响预测（第6章） | 样例报告库 + 技术导则库 |
| 减缓措施（第9章） | 样例报告库 + 法规标准库 |
| 回顾评价（第4章） | 样例报告库 |
| 承载力（第7章） | 样例报告库 + 技术导则库 |
| 综合论证（第8章） | 样例报告库 + 法规标准库 |
| 法律法规（第1章） | 法规标准库 |
| 监测管理（第10章） | 样例报告库 + 法规标准库 |

**使用模板时**，每章按以下元数据约束生成：

| 元数据字段 | 作用 |
|-----------|------|
| `generation_hint` | 该章的 LLM 生成提示词——描述内容要点、引用标准条款、建议结构 |
| `content_contract.key_elements` | 必须覆盖的要素清单，逐项检查 |
| `content_contract.min_word_count` | 字数下限约束，防止内容过于简略 |
| `content_contract.forbidden_phrases` | 禁止出现的用语（如"大约""可能""暂定"） |
| `content_contract.structure_type` | 输出格式：`narrative_text` / `table` / `mixed` |
| `compliance_rules` | 该章必须遵循的具体标准条款 |
| `example_snippet` | 样例内容片段，供参考风格和详略 |

### 步骤5：三重检查（全部章节完成后）

**5a. 实体泄露检测**：扫描全篇所有章节，确认无 `references/sample_entities.md` 黑名单中的样例实体残留。

**5b. 模板合规规则校验**：
- 有模板时：汇总所有章节的 `compliance_rules` 进行逐项检查
- 无模板时：使用 `references/compliance_checklist.md` 中的全局检查条目
- 输出：`✅ 通过` / `⚠️ 需复核` + 具体条款说明

**5c. 法规知识库 RAG 对照**：
- 针对报告内容，从法规标准库检索相关 GB/HJ 标准条款
- 比对报告结论与标准要求的一致性
- 输出：合规检查摘要表

### 步骤6：质量报告

- 各章节字数统计 vs `word_count_target`
- `content_contract.key_elements` 覆盖率
- 合规检查通过率
- 计算结果占位符清单（如有）
- 建议人工复核的重点章节

---

## 模板元数据驱动 vs Markdown 回退对比

| 约束维度 | 知识工厂模板 | Markdown 回退 |
|----------|-------------|---------------|
| generation_hint | 每章精准提示（从样本报告抽取） | 通用段落描述 |
| compliance_rules | 每章独立标准条款 | 全局标准列表 |
| content_contract.key_elements | 必须覆盖的要素清单 | 无强制要求 |
| content_contract.min_word_count | 字数下限约束 | 不限制 |
| content_contract.forbidden_phrases | 禁止用语排除 | 不禁止 |
| content_contract.structure_type | 输出格式约束 | 自由选择 |
| example_snippet | 样例片段参考 | 无参考 |
| 模板演进 | 知识工厂编辑模板 → 下次生成即时生效 | 手动编辑 markdown |

---

## MCP 工具依赖

此技能依赖以下 MCP 服务：

1. **knowledge-factory**（优先使用）：
   - `kf_resolve_template` — 智能模板匹配（核心工具）
   - `kf_list_domains` — 列出可用领域（辅助发现）

2. **project**（章节读写）：
   - `list_chapters` — 查看项目章节进度
   - `get_chapter_spec` — 获取章节写作规范
   - `write_chapter` — 写入章节内容
   - `get_project` — 获取项目元数据

3. **知识库 REST API**（RAG 检索）：
   - `/{kb_id}/chat` — 单库检索
   - `/search` — 跨库联邦检索

## 计算工具

涉及专业计算时，使用 `scripts/calc/` 下的 Python 脚本：

| 脚本 | 用途 | 调用方式 |
|------|------|----------|
| `calc_subsidence.py` | 概率积分法沉陷预测 | `python scripts/calc/calc_subsidence.py --params '...'` |
| `calc_noise.py` | 噪声衰减计算 | `python scripts/calc/calc_noise.py --params '...'` |
| `calc_water_balance.py` | 水量平衡计算 | `python scripts/calc/calc_water_balance.py --params '...'` |
| `calc_air_screen.py` | AERSCREEN 大气估算 | `python scripts/calc/calc_air_screen.py --params '...'` |
| `calc_capacity.py` | 环境容量估算 | `python scripts/calc/calc_capacity.py --params '...'` |

用户选择的计算模式决定如何处理计算需求：
- **内置脚本**：直接调用上述脚本
- **占位符**：生成 `[待补充: 需使用XX模型，输入参数为...]`
- **外部API**：调用预配置的计算服务（需在 extensions_config.json 中配置）

## 参考文件

- `references/report_structure.md` — 13章结构详细说明（模板不可用时 fallback）
- `references/terminology.md` — 环评术语词典（补充知识，始终加载）
- `references/content_guidelines.md` — 各章节内容编写指南（补充知识，始终加载）
- `references/compliance_checklist.md` — 合规检查条目（合规校验时使用）
- `references/sample_entities.md` — 样例实体黑名单（实体泄露检测时使用）
- `references/calc_params_guide.md` — 计算参数说明（计算时参考）
- `references/chapter_examples/` — 4个核心章节样例（生成时参考风格）

## 注意事项

- 优先级：知识工厂模板 > markdown 参考文件
- 补充知识始终加载（术语 + 编写规范 + 实体黑名单独立于数据源）
- 整体判断不混用：模板整体不可用 → 全部回退 markdown
- 模板版本自动感知：`kf_resolve_template` 按 published + completeness_score DESC 自动获取最新版本
- 始终使用最新版本的标准和法规
- 验证所有数值满足规范要求
- 不编造具体数值，用 `[XX]` 或 `[待补充]` 标注不确定数据
- 输出为结构化 Markdown，逐章通过 project MCP 写入
- 每次只生成一个章节，用户确认后继续下一章
```

- [ ] **Step 2: 验证 SKILL.md 格式**

```bash
head -5 skills/custom/coal-eia-report/SKILL.md
echo "---"
grep -c "^##\|^###" skills/custom/coal-eia-report/SKILL.md
```

Expected: 文件以 `---` 开头的 YAML frontmatter 开始，包含 20+ 个标题

- [ ] **Step 3: 提交**

```bash
git add skills/custom/coal-eia-report/SKILL.md
git commit -m "feat(skills/coal-eia): add main SKILL.md with complete workflow and rules"
```

---

## Task 14: README.md

**Files:**
- Create: `skills/custom/coal-eia-report/README.md`

- [ ] **Step 1: 创建 README.md**

写入 `skills/custom/coal-eia-report/README.md`：

```markdown
# 煤炭矿区总体规划环评报告编写技能

## 概述

为煤炭矿区总体规划项目生成专业的环境影响评价报告书。采用项目工作流模式，按章节逐步生成，支持知识工厂模板驱动和多知识库 RAG 检索。

## 功能特性

- **模板驱动**：优先从知识工厂获取报告模板，利用 generation_hint / compliance_rules / content_contract 等元数据驱动生成
- **仿写而非照抄**：四重防护机制确保不复制样例报告的实体数据
- **多知识库支持**：样例报告库、法规标准库、技术导则库、地理环境库
- **三种计算模式**：内置 Python 脚本 / 占位符 / 外部 API
- **双重合规检查**：模板规则 + 法规知识库 RAG 对照
- **章节级生成**：每次生成一个章节，支持跨会话恢复

## 报告结构

标准13章结构：总则 → 规划概况 → 环境现状 → 回顾评价 → 影响识别 → 影响预测 → 承载力 → 综合论证 → 减缓措施 → 监测管理 → 清洁生产 → 公众参与 → 结论建议

## MCP 工具依赖

- `knowledge-factory`：kf_resolve_template, kf_list_domains
- `project`：list_chapters, get_chapter_spec, write_chapter, get_project
- 知识库 REST API：/{kb_id}/chat, /search

## 计算脚本

| 脚本 | 功能 |
|------|------|
| `scripts/calc/calc_subsidence.py` | 概率积分法沉陷预测 |
| `scripts/calc/calc_noise.py` | 噪声衰减计算 |
| `scripts/calc/calc_water_balance.py` | 水量平衡计算 |
| `scripts/calc/calc_air_screen.py` | AERSCREEN 简化大气估算 |
| `scripts/calc/calc_capacity.py` | 环境容量估算 |

## 参考文档

- `references/report_structure.md` — 13章完整结构
- `references/terminology.md` — 环评专业术语
- `references/content_guidelines.md` — 编写规范
- `references/compliance_checklist.md` — 合规检查条目
- `references/sample_entities.md` — 样例实体黑名单
- `references/calc_params_guide.md` — 计算参数说明
- `references/chapter_examples/` — 4个核心章节样例

## 设计文档

详见 `docs/superpowers/specs/2026-06-12-coal-eia-report-skill-design.md`
```

- [ ] **Step 2: 提交**

```bash
git add skills/custom/coal-eia-report/README.md
git commit -m "docs(skills/coal-eia): add README"
```

---

## Task 15: 注册技能到 extensions_config.json

**Files:**
- Modify: `extensions_config.json`

- [ ] **Step 1: 在 extensions_config.json 中添加技能条目**

在 `skills` 对象中添加 `"coal-eia-report"` 条目：

```json
"coal-eia-report": {
  "enabled": true
}
```

读取当前 `extensions_config.json`，找到 `"skills"` 部分，在 `"fire-protection-report-v2"` 条目后添加新条目。

- [ ] **Step 2: 验证 JSON 格式**

```bash
python -c "import json; json.load(open('extensions_config.json')); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3: 提交**

```bash
git add extensions_config.json
git commit -m "feat(config): register coal-eia-report skill in extensions_config"
```

---

## Task 16: 端到端验证

- [ ] **Step 1: 验证完整文件结构**

```bash
find skills/custom/coal-eia-report -type f | sort
```

Expected 文件列表：
```
skills/custom/coal-eia-report/README.md
skills/custom/coal-eia-report/SKILL.md
skills/custom/coal-eia-report/references/calc_params_guide.md
skills/custom/coal-eia-report/references/chapter_examples/sample_air_quality.md
skills/custom/coal-eia-report/references/chapter_examples/sample_ecology.md
skills/custom/coal-eia-report/references/chapter_examples/sample_subsidence.md
skills/custom/coal-eia-report/references/chapter_examples/sample_water_quality.md
skills/custom/coal-eia-report/references/compliance_checklist.md
skills/custom/coal-eia-report/references/content_guidelines.md
skills/custom/coal-eia-report/references/report_structure.md
skills/custom/coal-eia-report/references/sample_entities.md
skills/custom/coal-eia-report/references/terminology.md
skills/custom/coal-eia-report/scripts/calc/calc_air_screen.py
skills/custom/coal-eia-report/scripts/calc/calc_capacity.py
skills/custom/coal-eia-report/scripts/calc/calc_noise.py
skills/custom/coal-eia-report/scripts/calc/calc_subsidence.py
skills/custom/coal-eia-report/scripts/calc/calc_water_balance.py
```

- [ ] **Step 2: 验证所有计算脚本可运行**

```bash
for script in calc_subsidence calc_noise calc_water_balance calc_air_screen calc_capacity; do
  echo "Testing $script..."
  python skills/custom/coal-eia-report/scripts/calc/${script}.py --help > /dev/null 2>&1 && echo "  ✅ OK" || echo "  ❌ FAIL"
done
```

Expected: 全部 ✅ OK

- [ ] **Step 3: 验证 SKILL.md frontmatter 可解析**

```bash
python -c "
import yaml
with open('skills/custom/coal-eia-report/SKILL.md') as f:
    content = f.read()
    parts = content.split('---')
    if len(parts) >= 3:
        meta = yaml.safe_load(parts[1])
        print(f'Name: {meta[\"name\"]}')
        print(f'Description length: {len(meta[\"description\"])} chars')
    else:
        print('ERROR: no frontmatter found')
"
```

Expected: 输出 `Name: coal-eia-report` 和描述长度

- [ ] **Step 4: 重启 gateway 容器使技能生效**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 5: 验证技能已被加载**

```bash
curl -s http://localhost:2026/api/skills/ | python -m json.tool | grep -A2 coal-eia
```

Expected: 看到 `coal-eia-report` 技能条目

- [ ] **Step 6: 最终提交**

如果有任何未提交的改动：

```bash
git status
git add -A skills/custom/coal-eia-report/
git commit -m "feat(skills/coal-eia): complete coal-eia-report skill — phase 1"
```
