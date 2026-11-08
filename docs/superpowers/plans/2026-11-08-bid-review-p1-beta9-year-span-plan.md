# P1-β批九:L2-052 附件年份连续性(plan)

日期:2026-11-08 · 分支:main-dev-fork · 前置:批八收官(929a666c0,门 740p/6s/0f) · 挂账来源:A-β6-③(L2-024 年份连续性,「无法解析→UNKNOWN」v2 语义待裁)+years() 原语已备(批八)

## 裁决

| # | 裁决 |
|---|---|
| A-β9-① | **范围锁**:批九 = 单规则 L2-052 附件年份连续性达标(新算子 `att_year_span` 镜像 att_* 家族 + 规则卡)。招标侧契约**已带 `year_span` 字段**(extract.py :55 实证),bid 侧匹配行名即年份载体——双向 inputs(tender.attachment_requirements/bid.attachment_index)均已在宇宙,**宇宙 126/首段 114/anchored 不动**;锁面动四处:包 59→60、det 50→51、golden 82→83、EXPECTED_COVERAGE 59→60。 |
| A-β9-② | **v2 语义(controller 拍板,规格侧落此为准)**:对 year_span 为正整数且状态∈{MATCHED,PARTIAL} 的要求行,Y = 命中(matched)提供行 name 的 4 位年份 token 集 `(?<!\d)(\d{4})(?!\d)`;①`|Y| < year_span` → violation「年份不足」;②`max(Y)-min(Y)+1 != \|Y\|` → violation「年份断档」(连续性=无断档;**不锚定截止日日历年**——财年书写惯例异构,锚定=FP 源);③命中行年份零可解析 → need_human「无法解析年份」(A-β6-③ v2 的 无法解析→UNKNOWN);④MISSING/UNKNOWN 行零参与(L2-020/023 属地,零双报);⑤severity 行源覆盖 `_src_severity` 同 att 家族;entity_keys/dedup_key 按要求行实体键同构。 |
| A-β9-③ | **每 commit 全绿切分**:T1 实现者只落算子分支(dispatch 第四模式)+matched 暴露核对+算子单测(rulepack 不动→钉不红);T2 controller 直办规则卡 L2-052+四锁 bump+golden 一案例+EXPECTED_COVERAGE(controller 直办 golden face/五锁,批六 T6/批七 T5 先例)。 |
| A-β9-④ | **验证协议**:家族门全绿(基线 740p/6s/0f→T2 后实际数只增不减);lint 门仅本批文件(check+生产 format --check);spec P1 段批九兑付段 controller 落账。 |

## 任务分解

- [ ] **T1(实现者)**:`att_year_span` 算子分支(rule_runner.py dispatch)——per_req 遍历,matched 行名年份集(A-β9-② ①②③④⑤ 逐条),violations 走 `_issue`+entity_keys+dedup_key+`_src_severity`,零解析走 `_need_human`。attachments.py 若 matched 暴露面不足才动(实测 :254 已出 dict 行,预期零改)。tests/test_bid_review_rule_runner.py 新 TestBeta9 算子单测(合规/不足/断档/零解析 need_human/year_span null 跳过/MISSING 跳过 六钉)。禁触:rulepack、golden、五锁数字面、.wolf/、docs/。
- [ ] **T2(controller 直办)**:pack 卡 L2-052(det,severity major,evidence A-TENDER-NOTICE+A-BOQ,tpl {span_fail})+rule_runner 测试钉 det 51/包 60+golden 案例 L2-052-year-span-short.yaml(strict:false,bug-4227 律双 inputs 全值)+EXPECTED_COVERAGE 59→60+家族门+spec 批九段+wolf 记账。

## 挂账延续(批九后)

keywords ASCII 精化、severity_override 机制、L1-026 方式集维、L1-004 business_items 跨引、L2-030↔required_signatures 关系、bid.fields 别名、bid.submit_method、生产侧 21 叶键真值 live 验证(live 批);L2-024 年份连续性**销账**(本批兑付)。
