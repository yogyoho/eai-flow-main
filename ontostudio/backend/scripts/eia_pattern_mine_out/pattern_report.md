# EIA B 库领域规律挖掘报告（子项目 5 交付 1）

- 挖掘时间：2026-09-30T14:20:22.454268+00:00
- 数据：真实图断言层（dg_* 全量 → 内存 kernel，生产同路径 load）；只挖 scope=sample 实体
- support 定义：去重报告数（mention 溯源 ∪ attrs.source_report）；入图门槛 ≥3

| 类型 | 配对数 | 入图候选（support≥3） |
|---|---|---|
| 治理规律 | 325 | 318 |
| 标准规律 | 7 | 2 |
| 处置规律 | 280 | 202 |

## 治理规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| ss（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 22 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 22 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| ss（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| bod（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| cod（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| ss（pollutant）→ 矿井水处理（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| ss（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 20 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| bod（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| cod（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 氨氮（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 悬浮物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 悬浮物、cod、石油类、氟化物、溶解性总固体（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 硫化物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| codcr（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 19 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| ss（pollutant）→ 水处理站（treatment_measure） | emitted_as+treated_by | 19 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| bod（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 19 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| bod（pollutant）→ 伊敏河镇污水处理厂（treatment_measure） | emitted_as+treated_by | 19 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |

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
| 危险废物（waste_stream）→ 有资质的危废处置公司（org） | disposed_by | 16 | 2 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质危废处置单位（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质的专业公司安全处置（treatment_measure） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质单位（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有危废资质的处置单位（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质的专业公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质的单位进行安全处置（treatment_measure） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有相关资质的单位（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质的公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 有资质的单位（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 内蒙古志飞环保科技有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 内蒙古东联循环技术有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 当地环卫部门（org） | disposed_by | 16 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 矸石（waste_stream）→ 回填井下（treatment_measure） | disposed_by | 16 | 1 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 露天矿排土场（engineering_site） | disposed_by | 16 | 1 | balasu、gaotaoyao、guojiatai、hegang、hengcheng… |
| 矸石（waste_stream）→ 排矸场（engineering_site） | disposed_by | 16 | 1 | balasu、guojiatai、hegang、hengcheng、huating… |
| 矸石（waste_stream）→ 矸石充填站（treatment_measure） | disposed_by | 15 | 2 | balasu、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 合理处置（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |