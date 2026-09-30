# EIA 实体质量抽检清单（子项目 3.5 §4）

- 生成: 2026-09-30T12:49:11.728511+00:00　seed=42　目标 n=100　实际抽样 **102** 条
- 语料: 2521 实体 / 35 etype / 无 mention 行 0（source_report=unknown）
- 判定由主会话 LLM 逐条填写 `verdict` 后回填（本清单不含判定结果）；判定结果决定噪声清除范围——本轮一律保留不清除。

## 三档判定标准

- **correct_entity**: 正确实体——真实存在于源文档、指代边界清晰、etype 挂挂正确的抽取结果
- **wrong_extraction**: 错误抽取——指向错误对象/边界错切/etype 错挂/张冠李戴（判定结果决定后续噪声清除范围，本轮仍保留不清除）
- **meaningless_fragment**: 无意义碎片——非实体的碎片字符串（截断残句/表头残留/编号碎屑）；v1 一律保留不清除，仅标记

## 分层统计（population / sampled）

| etype | 语料 | 抽样 |
|---|---|---|
| aquifer | 1 | 1 |
| carrying_capacity | 3 | 3 |
| chapter | 41 | 3 |
| coal_seam | 16 | 3 |
| emission_point | 7 | 3 |
| emission_standard | 11 | 3 |
| engineering_site | 102 | 3 |
| evidence_requirement | 3 | 3 |
| impact_result | 94 | 3 |
| measure_process_concept | 53 | 3 |
| measure_spec | 40 | 3 |
| mine | 129 | 3 |
| mine_field | 58 | 3 |
| mining_district | 12 | 3 |
| mining_method | 51 | 3 |
| monitoring | 49 | 3 |
| org | 47 | 3 |
| place | 434 | 3 |
| planning_change | 4 | 3 |
| planning_scheme | 14 | 3 |
| pollutant | 43 | 3 |
| pollution_process_concept | 4 | 3 |
| pollution_source | 224 | 3 |
| project | 3 | 3 |
| receiving_medium | 13 | 3 |
| regulation_clause | 63 | 3 |
| report | 23 | 3 |
| retrospective_problem | 2 | 2 |
| section | 44 | 3 |
| sensitive_point | 307 | 3 |
| standard_threshold | 19 | 3 |
| stratigraphic_unit | 16 | 3 |
| treatment_measure | 461 | 3 |
| waste_stream | 114 | 3 |
| working_face | 16 | 3 |

## 统计骨架（判定回填）

```json
{
  "per_verdict": {
    "correct_entity": null,
    "wrong_extraction": null,
    "meaningless_fragment": null
  },
  "per_etype": {}
}
```

## 待判定条目

### 1. [aquifer] 白垩系含水层
- id: `98379206-2c73-4d27-b3bd-fee7d4472971`　status: pending_review　confidence: 0.6　source_report: baiyinhua2
- attrs: {}
- 邻接(1): 入边 located_in → 疏干观测孔(monitoring)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 2. [carrying_capacity] 水资源承载力
- id: `0c8ea0d9-d7c5-49eb-973b-ca80da93a4a5`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 入边 constrained_by → 矿区开发(project)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 3. [carrying_capacity] 区域水资源承载能力
- id: `8920be41-8f53-4b9f-8313-88e63a6ded10`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- attrs: {}
- 邻接(1): 入边 constrained_by → 矿区规划项目(project)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 4. [carrying_capacity] 大气环境容量
- id: `d5c052bc-b98f-4073-97a6-e18c1de7802a`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 入边 constrained_by → 矿区(project)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 5. [chapter] 矿区开发环境影响回顾评价
- id: `1cb4f654-0cd5-4a6e-88f0-5c2b03847803`　status: pending_review　confidence: 0.6　source_report: wujianfang
- 多源: wujianfang, yakeshi2026
- attrs: {}
- 邻接(3): 入边 has_chapter → 内蒙古自治区锡林郭勒盟五间房矿区总体规划环境影响报告书(report); 入边 has_chapter → 牙克石-五九煤田矿区总体规划环境影响报告书(report); 出边 has_subsection → 矿区存在的环保问题及整改建议(section)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 6. [chapter] 野生动物现状调查与评价
- id: `39f9ccdf-ecae-4250-b661-d64d8b0823e5`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 入边 has_chapter → 评价区(report)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 7. [chapter] 12 公众参与
- id: `5d503992-3ed6-4e8f-9ad5-827a095e3be3`　status: pending_review　confidence: 0.6　source_report: weizhou
- attrs: {}
- 邻接(1): 入边 has_chapter → 宁夏回族自治区韦州矿区总体规划（修编）环境影响报告书(report)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 8. [coal_seam] 16下煤层
- id: `1dd02ff5-13cb-4a65-90d2-7bc458f51477`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 入边 mines → 伊敏露天矿(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 9. [coal_seam] 3-3煤
- id: `6a9608e8-77de-48d6-8ee4-f428e89e4145`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 入边 mines → 西一矿井(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 10. [coal_seam] 7层煤层
- id: `837f7848-f8c3-49df-b2ae-4d936c36c4e4`　status: pending_review　confidence: 0.6　source_report: yueerwan
- attrs: {}
- 邻接(1): 入边 mines → 月儿湾矿井(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 11. [emission_point] 总排水口
- id: `31a29724-a6d9-45ee-ad58-ec9ab59bea5b`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 入边 emitted_via → 疏干水(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 12. [emission_point] 高60m烟囱
- id: `b0702a5d-0757-4f87-b78f-08cb0602b6d0`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 入边 emitted_via → 锅炉房(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 13. [emission_point] 50m烟囱
- id: `b7dff803-b95c-4c66-96a1-089793ebc517`　status: pending_review　confidence: 0.6　source_report: baiyinhua3
- attrs: {}
- 邻接(1): 入边 emitted_via → 锅炉烟气(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 14. [emission_standard] 《地表水环境质量标准》（GB3838-2002）Ⅲ类标准
- id: `30870935-68ef-406f-a6b3-e249de5944a0`　status: active　confidence: 0.7　source_report: lingtai
- attrs: {}
- 邻接(1): 入边 governed_by → 反渗透深度处理(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 15. [emission_standard] 《煤炭工业污染物排放标准》（GB20426-2006）
- id: `b8262b0c-363d-41ef-8951-7a2611e3c031`　status: pending_review　confidence: 0.6　source_report: baiyinhua2
- 多源: baiyinhua2, baiyinhua3, guojiatai
- attrs: {}
- 邻接(3): 入边 complies_with → 矿坑水(pollution_source); 入边 governed_by → 矸石充填系统(treatment_measure); 入边 governed_by → 除尘设备(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 16. [emission_standard] 达标排放要求
- id: `cf718f87-ecca-4e4e-a23a-719d1f27d459`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 入边 complies_with → 煤矿集中供热燃煤锅炉(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 17. [engineering_site] 矿区道路
- id: `0a29293e-a9f9-433f-829a-d6eeff833fa5`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(1): 出边 treated_by → 每天洒水抑尘作业3-4次(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 18. [engineering_site] 矸石周转场
- id: `b01fa1fe-3600-4c49-9d5d-58dc0f2017b6`　status: pending_review　confidence: 0.6　source_report: balasu
- 多源: balasu, guojiatai, lingtai, sijitun, yueerwan
- attrs: {}
- 邻接(8): 入边 disposed_by → 弃方(waste_stream); 入边 disposed_by → 矸石(waste_stream); 入边 disposed_by → 矸石(waste_stream); 入边 disposed_by → 矸石(waste_stream); 出边 located_in → 工业场地东侧的地势低洼处(place); 出边 located_in → 矿区内(place); 出边 located_in → 选煤厂工业场地东北侧(place); 出边 treated_by → 硬化防渗处理(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 19. [engineering_site] 运输道路
- id: `c33778e3-ec8d-4661-b7ce-4519e8ce2124`　status: pending_review　confidence: 0.6　source_report: yitai
- attrs: {}
- 邻接(1): 出边 treated_by → 洒水降尘措施(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 20. [evidence_requirement] 20-30年恢复期
- id: `325ffb59-7866-4106-a615-e1d3539f499d`　status: pending_review　confidence: 0.6　source_report: yimin
- attrs: {}
- 邻接(1): 入边 requires_evidence → 植被恢复(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 21. [evidence_requirement] 全年降水量
- id: `75a66ec2-866a-4d5b-a823-fa6a232c5716`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(1): 入边 requires_evidence → 矸石堆存(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 22. [evidence_requirement] 充填料配比实验
- id: `7e80d4aa-f05b-4519-ae12-3ecf77a8d6c1`　status: pending_review　confidence: 0.6　source_report: yakeshi2026
- attrs: {}
- 邻接(1): 入边 requires_evidence → 充填开采(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 23. [impact_result] 地表下沉
- id: `628de4e4-bc08-4208-927f-fdecc84c93dd`　status: pending_review　confidence: 0.6　source_report: yakeshi2026
- attrs: {}
- 邻接(1): 出边 causes → 积水(impact_result)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 24. [impact_result] 汇水通道截断
- id: `8d4d9f8b-b819-4550-9202-243e6e75e256`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(2): 入边 causes → 条湖五号井田(working_face); 入边 causes → 汉水泉五号井(working_face)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 25. [impact_result] 井田积水
- id: `d32025d2-4d88-4134-8931-070b951b5165`　status: pending_review　confidence: 0.6　source_report: gaotaoyao
- attrs: {}
- 邻接(1): 入边 causes → 泊江海子煤矿(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 26. [measure_process_concept] 混凝沉淀
- id: `05aaa9dc-b520-471b-9bab-91c63820b9fd`　status: pending_review　confidence: 0.6　source_report: hengcheng
- attrs: {}
- 邻接(2): 入边 treated_by → 任家庄矿井水(pollution_source); 入边 treated_by → 红石湾矿井水(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 27. [measure_process_concept] 预处理、脱盐、二次浓缩及蒸发结晶
- id: `ee1d2891-92db-4ea5-bbd9-e4ba5176a6e9`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 入边 treated_by → 矿井水(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 28. [measure_process_concept] 掺入末煤销售
- id: `fc7b58c4-2f96-4d8a-9a6a-4105b9f8a714`　status: pending_review　confidence: 0.6　source_report: nalinxili
- attrs: {}
- 邻接(2): 入边 utilized_by → 煤泥(waste_stream); 入边 utilized_by → 矿井水处理站污泥(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 29. [measure_spec] 除尘总效率不低于99.9%
- id: `32acef91-6142-41ad-a4cb-d152cc7a38e1`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 入边 specified_by → 电袋复合除尘技术(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 30. [measure_spec] FBC-30
- id: `84199a8b-ada1-4d20-9644-2bf7690fc934`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 入边 specified_by → 振打布袋除尘器(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 31. [measure_spec] PM10控制效率59%
- id: `9ebf8dc1-3c3b-4735-885d-dcb736707852`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 入边 specified_by → 洒水降尘(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 32. [mine] 伊敏三井
- id: `5535d5f5-5bbe-4338-9356-0cb02076af78`　status: pending_review　confidence: 0.6　source_report: yimin
- attrs: {}
- 邻接(3): 出边 located_in → 锡尼河东苏木(place); 出边 method_of → 多水平立井开拓(mining_method); 出边 treated_by → 留设煤柱保护(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 33. [mine] 胜利煤矿
- id: `684767ff-201d-48d6-9af8-8324cc61c804`　status: pending_review　confidence: 0.6　source_report: yakeshi2026
- attrs: {}
- 邻接(2): 出边 located_in → 东区(place); 出边 located_in → 低山丘陵区(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 34. [mine] 新疆伊宁矿区北区
- id: `8d1cbdca-e0ae-443d-904e-d72652db95ab`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(4): 出边 located_in → 伊宁县(place); 出边 located_in → 伊宁市(place); 出边 located_in → 新疆伊犁哈萨克自治州伊犁盆地北部低山丘陵区(place); 出边 located_in → 霍城县(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 35. [mine_field] 井田6采区
- id: `1a181bd8-b391-4244-8f0c-f57e92a7584d`　status: pending_review　confidence: 0.6　source_report: yueerwan
- attrs: {}
- 邻接(3): 入边 located_in → 110kV罗强甲乙线(sensitive_point); 入边 located_in → 800kV灵绍线(sensitive_point); 入边 located_in → 灵州-绍兴±800kV直流输电线路(sensitive_point)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 36. [mine_field] 四号井田
- id: `57bd98c5-0f99-48ee-9b3f-f242e8898ad4`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 入边 located_in → 英也尔火龙洞(sensitive_point)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 37. [mine_field] 淖毛湖矿区
- id: `d05d1bc0-d6cc-4eeb-8d7c-c72e64eb23ea`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- attrs: {}
- 邻接(2): 入边 located_in → 公益林(sensitive_point); 出边 part_of → 吐哈煤田(mining_district)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 38. [mining_district] 赤城片区
- id: `2dd292c9-0969-4522-8027-48cfa5602c16`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(2): 入边 located_in → 五举煤矿(mine); 入边 part_of → 百贯沟煤矿(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 39. [mining_district] 呼吉尔特矿区
- id: `760fa11b-f5c4-4f3f-a949-76e84abf5465`　status: pending_review　confidence: 0.6　source_report: nalinxili
- attrs: {}
- 邻接(2): 入边 part_of → 梅林庙井田(mine_field); 入边 part_of → 门克庆井田(mine_field)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 40. [mining_district] 吐哈煤田
- id: `eeff7fd7-e0b5-4a5f-885e-e8da3bee8843`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- 多源: naomaohu2025, santanghu
- attrs: {}
- 邻接(2): 入边 part_of → 三塘湖矿区(mine); 入边 part_of → 淖毛湖矿区(mine_field)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 41. [mining_method] 立井单水平开拓
- id: `52fe0d1d-36d3-4a7d-9a82-a4cb3eb584e3`　status: pending_review　confidence: 0.6　source_report: yimin
- attrs: {}
- 邻接(1): 入边 method_of → 伊敏四井(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 42. [mining_method] 单斗—自移式破碎机+带式输送机半连续工艺
- id: `7602ea90-c871-4f93-bbba-ef816fd13855`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 入边 method_of → 伊敏露天矿(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 43. [mining_method] 单斗—自移式破碎机—带式输送机半连续开采工艺
- id: `c65b31fe-ed33-4c65-8772-bc89de47a6ce`　status: pending_review　confidence: 0.6　source_report: yimin
- attrs: {}
- 邻接(2): 入边 method_of → 五号露天矿(mine); 入边 method_of → 四号露天矿(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 44. [monitoring] 土壤侵蚀
- id: `030c202d-eb73-4c84-ada7-fe4c56c24c47`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 入边 monitored_by → 各排矸场(engineering_site)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 45. [monitoring] 矿区生活污水综合利用率监测
- id: `bd906d46-7c47-40af-b982-c8655bda2479`　status: pending_review　confidence: 0.6　source_report: weizhou
- attrs: {}
- 邻接(1): 入边 monitored_by → 韦州矿区(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 46. [monitoring] 生态系统整体性和生态功能变化趋势监测
- id: `f6a757c4-32f5-4a54-a718-dce129903896`　status: pending_review　confidence: 0.6　source_report: weizhou
- attrs: {}
- 邻接(1): 入边 monitored_by → 韦州矿区(mine)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 47. [org] 矿方
- id: `3e6c255f-cb0b-4860-9448-b0d2f990dfd9`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 出边 regulated_by → 申请污染物排污许可和更新入河排污口设置(regulation_clause)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 48. [org] 西乌珠沁旗鑫玉空心砖厂
- id: `76fd7115-cae6-4416-afa3-4a4dbe7482f2`　status: pending_review　confidence: 0.6　source_report: baiyinhua2
- attrs: {}
- 邻接(1): 入边 utilized_by → 锅炉除尘灰与脱硫灰渣(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 49. [org] 宁夏聚鑫融工贸有限公司
- id: `b398b382-fe3a-4bad-b49f-9070bfcbb1fb`　status: pending_review　confidence: 0.6　source_report: hengcheng
- attrs: {}
- 邻接(1): 入边 disposed_by → 任家庄煤矿矸石(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 50. [place] 内流区
- id: `17bf210e-6518-4e73-9d7d-e14a7680759c`　status: pending_review　confidence: 0.6　source_report: nalinxili
- attrs: {}
- 邻接(1): 入边 located_in → 矿区(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 51. [place] 振兴井田南部及西北部
- id: `5cf5e2b5-2970-4bed-992f-8cf8b290086e`　status: pending_review　confidence: 0.6　source_report: hegang
- attrs: {}
- 邻接(1): 入边 located_in → 石头河(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 52. [place] 采掘场的东南侧
- id: `ae53558a-0043-4959-80bf-1ba7b069f522`　status: pending_review　confidence: 0.6　source_report: baiyinhua3
- attrs: {}
- 邻接(1): 入边 located_in → 工业场地(engineering_site)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 53. [planning_change] 韦州矿区总体规划（修编）
- id: `3daecccf-f869-4f49-abac-49d871acdb08`　status: pending_review　confidence: 0.6　source_report: weizhou
- attrs: {}
- 邻接(1): 出边 changes → 原规划范围(planning_scheme)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 54. [planning_change] 白音华煤炭矿区总体规划（修编）
- id: `6a842057-b8ed-416a-8141-b8571f077d9d`　status: pending_review　confidence: 0.6　source_report: baiyinhua2
- attrs: {}
- 邻接(1): 出边 changes → 《内蒙古白音华矿区总体规划》(planning_scheme)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 55. [planning_change] 规划方案
- id: `8dc884d1-7071-4b55-b3dd-207644b4978c`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 出边 changes → 新增周寨南矿井(planning_scheme)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 56. [planning_scheme] 横城矿区总体规划（修编）
- id: `0454ed0a-3bbb-45ab-8ad4-195a56007ef8`　status: pending_review　confidence: 0.6　source_report: hengcheng
- attrs: {}
- 邻接(1): 出边 specifies_threshold → 马莲台3.6Mt/a、任家庄3.6Mt/a、红石湾1.1Mt/a、丁家梁0.9Mt/a(standard_threshold)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 57. [planning_scheme] 积家井矿区总体规划
- id: `14fa79d2-a75f-4f0d-98f6-6be62cb2c4ef`　status: pending_review　confidence: 0.6　source_report: yueerwan
- attrs: {}
- 邻接(1): 入边 changes → 《宁夏回族自治区宁东煤田积家井矿区总体规划（修编）》(planning_change)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 58. [planning_scheme] 灵台矿区规划
- id: `ca8ab619-fa0c-435a-b711-affc9753d4d7`　status: pending_review　confidence: 0.6　source_report: lingtai
- attrs: {}
- 邻接(2): 出边 specifies_threshold → 30万吨/年(standard_threshold); 出边 specifies_threshold → 矸石处置率100%(standard_threshold)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 59. [pollutant] 氰
- id: `546b7888-5e76-414f-a134-309ae01a47c9`　status: pending_review　confidence: 0.6　source_report: hengcheng
- attrs: {}
- 邻接(1): 入边 emitted_as → 辅助企业废水(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 60. [pollutant] BOD
- id: `5e228e69-af7d-43d9-99f5-5f0c341ef6c7`　status: pending_review　confidence: 0.6　source_report: huating
- 多源: huating, naomaohu2025, santanghu
- attrs: {}
- 邻接(3): 入边 emitted_as → 施工期生活污水(pollution_source); 入边 emitted_as → 生活污水(pollution_source); 入边 emitted_as → 生活污水(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 61. [pollutant] 粉尘
- id: `f03c53ec-bd67-4d10-9c02-4560ee56a4b3`　status: pending_review　confidence: 0.6　source_report: hengcheng
- 多源: hengcheng, yitai
- attrs: {}
- 邻接(5): 入边 emitted_as → 煤矿大气污染物(pollution_source); 入边 emitted_as → 爆破作业(pollution_source); 入边 emitted_as → 破碎站(pollution_source); 入边 emitted_as → 穿孔作业(pollution_source); 入边 emitted_as → 钻机穿孔(pollution_source)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 62. [pollution_process_concept] 冻土冻融
- id: `29b3f72c-9bab-4dde-9846-9147414e14bc`　status: pending_review　confidence: 0.6　source_report: sijitun
- attrs: {}
- 邻接(1): 出边 causes → 冻胀、冻裂及融陷(impact_result)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 63. [pollution_process_concept] 矸石（剥离物）淋溶水入渗
- id: `60e436f3-730f-4449-91b7-917f746075d6`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- attrs: {}
- 邻接(1): 出边 causes → 第四系、新近系地下水受影响(impact_result)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 64. [pollution_process_concept] 露天矿长期疏干地下水
- id: `f2d8a893-0e1f-49c7-9f60-b235416a90a7`　status: active　confidence: 0.7　source_report: baiyinhua2
- attrs: {}
- 邻接(1): 出边 causes → 地下水降落漏斗(impact_result)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 65. [pollution_source] 机修车间高噪声设备
- id: `4cc23ac1-a825-40ea-9b90-0d2f3f972a2c`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 出边 treated_by → 隔声门窗(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 66. [pollution_source] 规划矿区内煤矿煤泥水
- id: `718069f6-8c65-485b-b976-b67d166086c3`　status: pending_review　confidence: 0.6　source_report: hegang
- attrs: {}
- 邻接(1): 出边 treated_by → 一级闭路循环(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 67. [pollution_source] 锅炉灰渣堆存
- id: `803d0ba9-337b-40ed-9033-fe46a3709019`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 出边 treated_by → 防尘、防渗措施(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 68. [project] 矿区
- id: `07972749-be7f-45b0-8640-9e543be94c5e`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 出边 constrained_by → 大气环境容量(carrying_capacity)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 69. [project] 矿区开发
- id: `26aacb32-5948-4d59-8de9-db75ffd5a86a`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 出边 constrained_by → 水资源承载力(carrying_capacity)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 70. [project] 矿区规划项目
- id: `41b44aed-55f9-4a65-9a77-4ddf11d6b8f3`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- attrs: {}
- 邻接(1): 出边 constrained_by → 区域水资源承载能力(carrying_capacity)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 71. [receiving_medium] 冲沟
- id: `36d3e073-4080-4683-bd2e-943b524e1eeb`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 出边 drains_to → 景泰县南沙河(receiving_medium)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 72. [receiving_medium] 无定河
- id: `506a7292-093f-4c8b-90e9-632972dd3621`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 入边 drains_to → 白城河(receiving_medium)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 73. [receiving_medium] 景泰县南沙河
- id: `ecbb8ee5-27f1-48ae-a0d2-aa2b59779ec5`　status: pending_review　confidence: 0.6　source_report: guojiatai
- attrs: {}
- 邻接(1): 入边 drains_to → 冲沟(receiving_medium)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 74. [regulation_clause] 《建设项目环境风险评价技术导则》（HJ169-2018）
- id: `4787a0cc-e4e9-4a01-9885-2ce57ff84b69`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(2): 入边 regulated_by → 卡保间(org); 入边 regulated_by → 油库区(org)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 75. [regulation_clause] 《关于发布〈矿山生态环境保护与污染防治技术政策〉的通知》
- id: `b1f4aab5-6a04-48ee-97e1-8261fec695ac`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 入边 cites_clause → 新疆伊宁矿区北区总体规划（修编）环境影响报告书(report)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 76. [regulation_clause] 《中华人民共和国煤炭法》
- id: `b445e615-67ba-4fbd-bb65-c8b08667a149`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 入边 cites_clause → 新疆伊宁矿区北区总体规划（修编）环境影响报告书(report)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 77. [report] 环评报告
- id: `24d734da-585b-4bc7-baf4-e0f582a620ea`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(1): 出边 has_chapter → 环境管理、监测计划与跟踪评价(chapter)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 78. [report] 本次环评
- id: `e5327034-c960-43f8-888f-61e4b851ae97`　status: pending_review　confidence: 0.6　source_report: hengcheng
- 多源: hengcheng, yining
- attrs: {}
- 邻接(2): 出边 cites_clause → 《环境影响评价公众参与办法》(regulation_clause); 出边 cites_clause → 规划环境影响评价技术导则（试行）(regulation_clause)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 79. [report] 本报告
- id: `e5902350-6a5f-4c99-8c5b-34268e1a27a7`　status: pending_review　confidence: 0.6　source_report: hengcheng
- 多源: hengcheng, sijitun
- attrs: {}
- 邻接(2): 出边 cites_clause → 《土地复垦质量控制标准》(regulation_clause); 出边 cites_clause → 《宁夏回族自治区水资源配置保障规划(2016—2020年)》(regulation_clause)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 80. [retrospective_problem] 采煤沉陷
- id: `43539f65-d7c7-447f-8abc-ed53ad90a5c6`　status: pending_review　confidence: 0.6　source_report: hengcheng
- attrs: {}
- 邻接: 无
- verdict(正确实体/错误抽取/无意义碎片): ______

### 81. [retrospective_problem] 二号矿田1号外排土场生态恢复效果欠佳
- id: `58556d63-1a0d-4e44-b96f-76e43a724aab`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 出边 problem_of → 二号矿田(mine_field)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 82. [section] 4.4.4 土壤侵蚀影响回顾性评价
- id: `4b3c468f-3d10-4f66-bcf1-f57f6f05774d`　status: pending_review　confidence: 0.6　source_report: naomaohu2025
- attrs: {}
- 邻接(1): 入边 has_subsection → 4.4 生态环境影响回顾性评价(chapter)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 83. [section] 矿山简介
- id: `7d91d3c2-95f2-486a-8316-e801fa79552d`　status: pending_review　confidence: 0.6　source_report: sijitun
- attrs: {}
- 邻接(1): 入边 has_subsection → 矿山基本情况(chapter)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 84. [section] 矿山地质环境监测
- id: `ac0c5292-ed0b-43c4-bb25-0a231b418530`　status: pending_review　confidence: 0.6　source_report: sijitun
- attrs: {}
- 邻接(1): 入边 has_subsection → 矿山地质环境治理与土地复垦工程(chapter)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 85. [sensitive_point] bl076
- id: `5affbc9d-baf7-4812-a6bc-bb6f59c86643`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 出边 located_in → 巴拉素镇武松界四队(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 86. [sensitive_point] 十二亩险墓群
- id: `729bcd94-5863-4538-871b-f8a344743a38`　status: pending_review　confidence: 0.6　source_report: lingtai
- attrs: {}
- 邻接(1): 出边 located_in → 蒲窝镇五星村小湾社(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 87. [sensitive_point] 中湖村烽燧
- id: `ea0d8a30-e79c-4fb6-a8f9-58c32ef1ce6c`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(2): 出边 located_in → 三塘湖乡中湖村(place); 出边 located_in → 条湖四号矿井田边界附近(place)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 88. [standard_threshold] 含盐量不得超过1000毫克/升
- id: `103deec1-5ef8-4b65-8a49-6b0c58647d1f`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 入边 specifies_threshold → 地表水III类水质标准(emission_standard)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 89. [standard_threshold] 煤矸石综合利用率80%
- id: `5c9bc9bf-3798-4bae-a60b-57ec8b4657bc`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 入边 specifies_threshold → 矿区总体规划(planning_scheme)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 90. [standard_threshold] SO2≤100mg/m3
- id: `74d424fd-a567-4368-a423-9eb4779d4d30`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 入边 specifies_threshold → 《锅炉大气污染排放标准》（DB61/1226-2018）(emission_standard)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 91. [stratigraphic_unit] 西山窑组
- id: `27c53b27-dc8f-4fbc-adf6-22c119d7944f`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(1): 出边 part_of → 侏罗系(stratigraphic_unit)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 92. [stratigraphic_unit] 白垩系下统
- id: `4a4fcee5-975f-422d-98d6-78c0af57ef7c`　status: pending_review　confidence: 0.6　source_report: baiyinhua2
- attrs: {}
- 邻接(1): 入边 part_of → 大磨拐河组第三段(stratigraphic_unit)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 93. [stratigraphic_unit] 兴安地层区
- id: `8dc59974-26df-4044-83f0-d45ba080036a`　status: pending_review　confidence: 0.6　source_report: yimin3500
- attrs: {}
- 邻接(1): 入边 part_of → 北疆-兴安地层大区(stratigraphic_unit)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 94. [treatment_measure] 综合利用途径
- id: `1359547a-a7f7-4a3a-ad54-397474313198`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 入边 utilized_by → 矸石、粉煤灰、脱硫石膏(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 95. [treatment_measure] 无害化处置率100%
- id: `5401cd19-3eb7-4cd6-9108-f8ce4504e798`　status: pending_review　confidence: 0.6　source_report: yining
- attrs: {}
- 邻接(1): 入边 disposed_by → 生活垃圾(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 96. [treatment_measure] 回填矿区洼地、填作路基、平整工业场地
- id: `7851f619-4a79-4f6b-b343-f6ae5775e3b2`　status: pending_review　confidence: 0.6　source_report: yakeshi2026
- attrs: {}
- 邻接(1): 入边 utilized_by → 矸石(waste_stream)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 97. [waste_stream] 疏干水
- id: `42b6e4ac-307e-43a6-9e7a-828827168c5d`　status: pending_review　confidence: 0.6　source_report: gaotaoyao
- attrs: {}
- 邻接(2): 出边 treated_by → 沉淀处理(treatment_measure); 出边 treated_by → 除氟系统(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 98. [waste_stream] 矸石、粉煤灰、脱硫石膏
- id: `9cc8355b-4c5a-4c12-a19e-40c461a8cd04`　status: pending_review　confidence: 0.6　source_report: wujianfang
- attrs: {}
- 邻接(1): 出边 utilized_by → 综合利用途径(treatment_measure)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 99. [waste_stream] 水处理站有机污泥
- id: `fe6201ee-a56b-4be7-93d8-bf6b31559046`　status: pending_review　confidence: 0.6　source_report: santanghu
- attrs: {}
- 邻接(1): 出边 disposed_by → 巴里坤县环卫部门或矿区生活垃圾填埋场统一处置(org)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 100. [working_face] 2101工作面
- id: `0f04143f-3563-4d0f-80b5-1f22e9c4a79e`　status: pending_review　confidence: 0.6　source_report: balasu
- attrs: {}
- 邻接(1): 出边 method_of → 长壁综合机械化采煤工艺(mining_method)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 101. [working_face] 胜利煤矿工作面
- id: `8bd079ab-45a3-49ca-89d9-3b98b9fafaae`　status: pending_review　confidence: 0.6　source_report: yakeshi2026
- attrs: {}
- 邻接(1): 出边 method_of → 后退式回采(mining_method)
- verdict(正确实体/错误抽取/无意义碎片): ______

### 102. [working_face] 新窑煤矿4506工作面
- id: `db05154b-eefa-42e0-b85a-fadcfacb56e5`　status: pending_review　confidence: 0.6　source_report: huating
- attrs: {}
- 邻接(1): 出边 method_of → 缓倾斜特厚煤层走向长壁综合机械化低位放顶煤采煤法(mining_method)
- verdict(正确实体/错误抽取/无意义碎片): ______
