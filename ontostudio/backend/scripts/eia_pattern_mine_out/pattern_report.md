# EIA B 库领域规律挖掘报告（子项目 5 交付 1 · 归并深化版）

- 挖掘时间：2026-09-30T15:12:52.805413+00:00
- 数据：真实图断言层（dg_* 全量 → 内存 kernel，生产同路径 load）；只挖 scope=sample 实体
- support 定义：去重报告数（mention 溯源 ∪ attrs.source_report）；入图门槛 ≥2
- 归并：受控词表归一（D:\eai\eai-flow-main\ontostudio\backend\scripts\eia_schema_mining\controlled_vocab.yaml），名称归一命中 256 次、复合名全分解 13 次

| 类型 | 配对数 | 入图候选（support≥2） |
|---|---|---|
| 治理规律 | 298 | 298 |
| 标准规律 | 7 | 2 |
| 处置规律 | 228 | 179 |

## 治理规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 悬浮物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 22 | 6 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 22 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 22 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 6 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 矿井水处理（treatment_measure） | emitted_as+treated_by | 21 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| bod（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 20 | 6 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| bod（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 氨氮（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 氨氮（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氟化物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 石油类（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 矿化度（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 硫化物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 悬浮物（pollutant）→ 水处理站（treatment_measure） | emitted_as+treated_by | 19 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 矿井水处理及回用措施（treatment_measure） | emitted_as+treated_by | 19 | 4 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |

## 标准规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 矸石充填系统（treatment_measure）→ 《煤炭工业污染物排放标准》(gb20426-2006)（emission_standard） | governed_by | 4 | 1 | baiyinhua2、baiyinhua3、guojiatai、jiulongchuan |
| 除尘设备（treatment_measure）→ 《煤炭工业污染物排放标准》(gb20426-2006)（emission_standard） | governed_by | 3 | 1 | baiyinhua2、baiyinhua3、guojiatai |
| 危废暂存库（treatment_measure）→ 《危险废物贮存污染控制标准》(gb18597-2023)（emission_standard） | governed_by | 1 | 1 | guojiatai |
| 反渗透深度处理（treatment_measure）→ 《地表水环境质量标准》(gb3838-2002)iii类标准（emission_standard） | governed_by | 1 | 1 | lingtai |
| 水浴脱硫除尘器（treatment_measure）→ 排放标准（emission_standard） | governed_by | 1 | 1 | wujianfang |
| 生活用水净化设施（treatment_measure）→ 《生活饮用水卫生标准》(gb 5749-2022)（emission_standard） | governed_by | 1 | 1 | yimin |
| 矿坑水处理设施（treatment_measure）→ 矿坑水处理要求（emission_standard） | governed_by | 1 | 1 | baiyinhua3 |

## 处置规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 矸石（waste_stream）→ 综合利用（treatment_measure） | utilized_by | 17 | 1 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 综合利用（treatment_measure） | disposed_by | 17 | 1 | balasu、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质单位（org） | disposed_by | 16 | 11 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 井下充填（treatment_measure） | disposed_by | 16 | 5 | balasu、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 环卫部门（org） | disposed_by | 16 | 4 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 危险废物（waste_stream）→ 内蒙古志飞环保科技有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 内蒙古东联循环技术有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 露天矿排土场（engineering_site） | disposed_by | 16 | 1 | balasu、gaotaoyao、guojiatai、hegang、hengcheng… |
| 矸石（waste_stream）→ 排矸场（engineering_site） | disposed_by | 16 | 1 | balasu、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 市政垃圾处理厂（place） | disposed_by | 15 | 9 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 矸石（waste_stream）→ 井下充填（measure_process_concept） | utilized_by | 15 | 7 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 沉陷区充填（treatment_measure） | utilized_by | 15 | 5 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 沉陷区充填（place） | disposed_by | 15 | 2 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 场地平整（measure_process_concept） | utilized_by | 15 | 2 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 采坑回填（treatment_measure） | disposed_by | 15 | 2 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 矸石充填站（treatment_measure） | disposed_by | 15 | 2 | balasu、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 合理处置（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 环卫部门统一处理（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 白银三峰环保发电有限公司（org） | utilized_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 无害化处置率100%（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |