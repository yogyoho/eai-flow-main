# EIA B 库领域规律挖掘报告（子项目 5 交付 1 · 归并深化版）

- 挖掘时间：2026-10-01T03:44:49.568559+00:00
- 数据：真实图断言层（dg_* 全量 → 内存 kernel，生产同路径 load）；只挖 scope=sample 实体
- support 定义：去重报告数（mention 溯源 ∪ attrs.source_report）；入图门槛 ≥3
- 归并：受控词表归一（D:\eai\eai-flow-main\ontostudio\backend\scripts\eia_schema_mining\controlled_vocab.yaml），名称归一命中 270 次、复合名全分解 47 次

| 类型 | 配对数 | 入图候选（support≥3） |
|---|---|---|
| 治理规律 | 249 | 245 |
| 标准规律 | 7 | 2 |
| 处置规律 | 190 | 114 |
| 敏感点防护规律 | 25 | 10 |
| 监测覆盖规律 | 49 | 1 |

## 治理规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 化学需氧量（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 22 | 7 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 22 | 6 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 22 | 4 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 7 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 矿井水处理（treatment_measure） | emitted_as+treated_by | 21 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生化需氧量（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 21 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 21 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 悬浮物（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 20 | 7 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生化需氧量（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 5 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氨氮（pollutant）→ 移动式生活污水处理装置（treatment_measure） | emitted_as+treated_by | 20 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 石油类（pollutant）→ 生活污水处理站（treatment_measure） | emitted_as+treated_by | 20 | 3 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 化学需氧量（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 氨氮（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 石油类（pollutant）→ 处理后回用（treatment_measure） | emitted_as+treated_by | 20 | 2 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 氟化物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 石油类（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 矿化度（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |
| 硫化物（pollutant）→ 矿井水处理站（treatment_measure） | emitted_as+treated_by | 20 | 1 | baiyinhua2、balasu、gaotaoyao、guojiatai、hegang… |

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
| 危险废物（waste_stream）→ 有资质单位（org） | disposed_by | 16 | 11 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 环卫部门（org） | disposed_by | 16 | 4 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 危险废物（waste_stream）→ 内蒙古志飞环保科技有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 危险废物（waste_stream）→ 内蒙古东联循环技术有限公司（org） | disposed_by | 16 | 1 | baiyinhua2、guojiatai、hegang、hengcheng、huating… |
| 生活垃圾（waste_stream）→ 市政垃圾处理厂（place） | disposed_by | 15 | 9 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 合理处置（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 环卫部门统一处理（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 白银三峰环保发电有限公司（org） | utilized_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 无害化处置率100%（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 巴里坤县环卫部门统一处置（org） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 鄂尔多斯市环卫部门统一处置（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 压缩式垃圾中转站（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 当地环卫部门处理（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 白银三峰环保发电有限公司（org） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 鄂尔多斯市蓝盈环保科技有限公司（org） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 榆林绿能新能源有限公司集中焚烧处置（treatment_measure） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 生活垃圾（waste_stream）→ 榆阳市芹河乡环境卫生管理站（org） | disposed_by | 15 | 1 | baiyinhua2、baiyinhua3、balasu、gaotaoyao、guojiatai… |
| 煤矸石（waste_stream）→ 井下充填（measure_process_concept） | utilized_by | 14 | 3 | gaotaoyao、guojiatai、hegang、huating、jiulongchuan… |
| 煤矸石（waste_stream）→ 井下充填（treatment_measure） | disposed_by | 14 | 1 | gaotaoyao、guojiatai、hegang、huating、jiulongchuan… |
| 洗选矸石（waste_stream）→ 井下充填（treatment_measure） | disposed_by | 12 | 4 | balasu、gaotaoyao、guojiatai、hegang、hengcheng… |

## 敏感点防护规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 公益林（sensitive_point）→ 禁止开采措施（treatment_measure） | protected_by | 9 | 1 | hegang、hengcheng、lingtai、naomaohu2025、santanghu… |
| 公益林（sensitive_point）→ 经济补偿、边开采边恢复（treatment_measure） | protected_by | 9 | 1 | hegang、hengcheng、lingtai、naomaohu2025、santanghu… |
| 水体（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 3 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 保护区（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 2 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 线路（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 2 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 城镇边界（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 1 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 村庄居民点（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 1 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 遗址文物（sensitive_point）→ 保护煤柱（treatment_measure） | protected_by | 7 | 1 | gaotaoyao、guojiatai、hengcheng、jiulongchuan、lingtai… |
| 基本农田（sensitive_point）→ 充填整治恢复耕种功能（treatment_measure） | protected_by | 5 | 1 | guojiatai、hegang、lingtai、weizhou、yueerwan |
| 草地（sensitive_point）→ 生态治理（treatment_measure） | protected_by | 3 | 1 | baiyinhua3、wujianfang、yakeshi2026 |
| 村庄居民点（sensitive_point）→ 留设保护煤柱或搬迁（treatment_measure） | protected_by | 2 | 1 | huating、lingtai |
| 水体（sensitive_point）→ 污染防治措施（treatment_measure） | protected_by | 2 | 1 | jiulongchuan、yakeshi2026 |
| 水体（sensitive_point）→ 留设煤柱的避让措施（treatment_measure） | protected_by | 2 | 1 | jiulongchuan、yakeshi2026 |
| 保护区（sensitive_point）→ 禁采及530-600m宽保护煤柱（treatment_measure） | protected_by | 1 | 1 | lingtai |
| 保护区（sensitive_point）→ 禁采并留设保护煤柱（treatment_measure） | protected_by | 1 | 1 | lingtai |
| 保护生物（sensitive_point）→ 围栏（treatment_measure） | protected_by | 1 | 1 | jiulongchuan |
| 保护生物（sensitive_point）→ 拯救措施（treatment_measure） | protected_by | 1 | 1 | yakeshi2026 |
| 保护生物（sensitive_point）→ 标志牌（treatment_measure） | protected_by | 1 | 1 | jiulongchuan |
| 城镇边界（sensitive_point）→ 禁采及保护煤柱（treatment_measure） | protected_by | 1 | 1 | lingtai |
| 水体（sensitive_point）→ 禁采及570-610m宽保护煤柱（treatment_measure） | protected_by | 1 | 1 | lingtai |

## 监测覆盖规律（按 support 降序，Top 20）

| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |
|---|---|---|---|---|
| 工业场地（engineering_site）→ 地表岩移观测（monitoring） | monitored_by | 7 | 1 | baiyinhua2、baiyinhua3、balasu、guojiatai、jiulongchuan… |
| 矿区整体（mine）→ 地表岩移观测（monitoring） | monitored_by | 2 | 1 | guojiatai、weizhou |
| 工业场地（engineering_site）→ 13个监测点（monitoring） | monitored_by | 1 | 1 | jiulongchuan |
| 工业场地（engineering_site）→ 地下水水质补充监测（monitoring） | monitored_by | 1 | 1 | balasu |
| 工业场地（engineering_site）→ 厂界噪声监测（monitoring） | monitored_by | 1 | 1 | baiyinhua3 |
| 矸石堆场（mine）→ 放射性监测（monitoring） | monitored_by | 1 | 1 | yueerwan |
| 矸石堆场（engineering_site）→ 土壤侵蚀（monitoring） | monitored_by | 1 | 1 | wujianfang |
| 矸石堆场（engineering_site）→ 地下水水质跟踪监测点（monitoring） | monitored_by | 1 | 1 | lingtai |
| 矸石堆场（engineering_site）→ 植被跟踪监测（monitoring） | monitored_by | 1 | 1 | gaotaoyao |
| 矿区整体（mine）→ 工业场地绿化率达到20%监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 区域土地资源承载力监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 生态系统整体性和生态功能变化趋势监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 污染物排放总量符合率监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 煤矸石煤泥处置率监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 单位入选原煤取水量监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 矿区资源回采率监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 塌陷稳定后土地复垦率监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 扰动区林草植被恢复率监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 水土流失总治理度监测（monitoring） | monitored_by | 1 | 1 | weizhou |
| 矿区整体（mine）→ 农用地土壤污染风险管制值达标率监测（monitoring） | monitored_by | 1 | 1 | weizhou |