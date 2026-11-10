# 批十五:抽取契约扩面(bid-review P1 β15)计划

日期:2026-11-11 · 分支:main-dev-fork · 前置:批十四(1b5997566/3e711bfca,已推)
用户裁决:「① W-real-4 抽取契约扩面批」(2026-11-11)

## 背景

真实件复采(917827881)判读 W-real-4=抽取覆盖缺口:7 键 UNKNOWN + 业绩表漏抽
(similar_performances=None→m4 链饿死)+ deposit_required 抽成布尔 + 执照名抽成证书名
(L1-016 假 FAIL×4)。批十四 T2 补查再证:执照/资质字段抽取质量面同根因。

## 根因(2026-11-11 调查,extract.py/rulepack/realcase md 对读)

机制:prompt 逐路径渲染,`FIELD_TYPE_CONTRACTS` 命中才附类型契约,未命中=裸路径一行
——目标 12 键**全部零契约**(grep 实证),模型对路径名自由发挥:deposit_required→True、
license_name→「高新技术企业证书」、qual_levels→证书名集、业绩表在文本内
(/tmp/realcase-bid.md 实证「业绩表**」+合同总价/签订时间列)却 similar_performances=None。
批六 T1 先例:契约入 prompt 即提升抽取质量,零引擎改动。

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| 11 契约入 FIELD_TYPE_CONTRACTS | **做** | 缺值 5(bid_deadline/bid_scope/bid_letter_signatory/entity 四件,alternative_price_offers 已有 LIST 契约其 UNKNOWN=内容缺席诚实 null)+质量 6(deposit_required 金额非布尔/license_name 主体名禁证书名/name_in_bid_letter/business_scope/license_valid_until/similar_performances 业绩表定向/qual_levels+required_qual_level 资质类禁荣誉证书) |
| bid.deposit_receipt_present 契约 | **不做** | 服务端派生(SERVER_DERIVED_PATHS,attachment_index 名称匹配),模型不产该键;其 UNKNOWN=附件索引空=OCR 边界挂账非契约缺口 |
| L1-002 covers(null) 语义 | **挂账** | required_qual_level=null 时 covers "None" in str() → False → FAIL 错位(抽取批不碰引擎判定面;真实件三试后再裁) |
| 业绩表独立抽取通道(m4 前置) | **不做** | 首段 similar_performances 契约定向即可喂 m4;YAGNI |
| 引擎/锁面 | **零改动** | 契约=纯 prompt 面;universe 126/首段 114·det 51·pack 60·golden 83·EXPECTED_COVERAGE 60 冻结 |

## 任务

- [ ] T1 契约面(extract.py FIELD_TYPE_CONTRACTS + 11 条 + 测试钉):钉:11 键全注册且
  ∈collect_field_paths()(prompt 可达);build_extract_prompt 渲染含关键短语(deposit「金额…非布尔」/
  license_name「营业执照…禁止…证书」/similar_performances「业绩表」);门禁 family `-k bid_review`
  只增(基线 764p/6s/0f),lint 双清。零引擎零锁面。
- [ ] T2 真实件复采:gateway restart + realcase 探针(wait_confirm 全链路),判读:L1-016 假 FAIL
  消失面/license_valid_until+bid_deadline 抽出率/similar_performances 非空+m4 entries 复活/
  deposit_required 数值化;余 FAIL 只升不降记档(新增=合理捕获)。模型方差族律:单样本不做硬锚,
  判读以规则 id 级翻转为单位。
- [ ] T3 收口:plan 勾兑 + spec 批十五段 + wolf 三件 + session memory + closure。

## 挂账

- OCR 管道边界(eai-flow-ocr :8010 锚;开工提醒 paddleocr-vl)——deposit_receipt_present
  类派生布尔与 L2 链饿死都在此域。
- covers(null) 判定语义、_BIN 全局硬化、ADJ-1 方式集字段批(可并)、万/亿乘数。
