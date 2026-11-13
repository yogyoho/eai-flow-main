# 批二十 M1 收尾:F3 章节装配 + F4 四技能生成器(骨架)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**日期:** 2026-11-13 · 分支: main-dev-fork · 前置: 批二十 M1-a..d 五 commit(e0ea87ef6..e8065bc21)执行器已收官

**Goal:** F4 四技能生成器骨架 + F3 章节装配——纯函数确定性装配(零 LLM),输入=抽取 fields+matrix 行+素材+人工单价,输出=executor ctx 契约形(products 四切片);金标闭环=生成产物直接喂 run_assertions 全 43 PASS。

**Architecture:** `app/extensions/bid_write/generate/` 新子包(独立模块律),五生成器各一文件+`__init__.build_ctx` 总装。确定性=Decimal 算术+模板渲染+difflib 相似度;待补不静默(CMN-005 负证据随行);降级走断言面(生成物缺件→D0 FAIL 诚实暴露,不造假绿)。

**Tech Stack:** Python 3.12 stdlib(decimal/difflib)+ 既有 executor.amount_cn/wordscan + bid_write.contracts

**真相源:** spec §2 骨架(四技能模板/降级/验收)+ §7(M1 面=F3+F4)+ executor ctx 契约(=tests/bid_write_exec_fixtures.green_ctx 形,校验器即验收)

---

## 机制(2026-11-13 调查)

- worker 管线现状:created→parsing→extracting→matrix_ready(F1 矩阵);生成器接线进 worker=M2(批廿一,与 F6 预审查/导出前置同批),本批只落纯函数层。
- tender 输入两面:商务子集(`COMMERCIAL_TENDER_SUBSET` 22 路径)不含 boq_items/max_price——这两路走审查端全量抽取;build_ctx 输入=fields dict(dotted 键)取用即取。
- ctx 契约真源=green_ctx():tender 面=扁平点分键;products 四切片形见夹具(material.entities/bidder_profile/price_history + pre.* 注入面)。
- 禁用词约束=生成文本面(bid_letter.text/price_sheet.note/rt.response_text/ai.body_text)必须零命中 6 桶;空应答词桶(empty_answer)钉死「满足招标文件要求」类——RT 参数化应答模板必须绕开。
- CMN-005 律:凡 status=待补 行必带 negative_evidence(dict 至少一键非空)——AI 待补占位行随行产负证据(检索范围/匹配键/最近候选)。
- PS-003 四表加总含 bid_letter 信面:BL slots.total_amount_num 必须引用 PS detail_total(§2.1 金额必须引用报价表)。

## 文件结构

```
backend/app/extensions/bid_write/generate/
  __init__.py            # build_ctx 总装(tender_fields, matrix_rows, material, knobs)→ctx
  price_sheet.py         # SK-PS 计算内核(明细唯一事实源;Decimal;缺价留空)
  bid_letter.py          # SK-BL 模板渲染(金额引用 PS;主体信息 entity/素材源)
  response_table.py      # SK-RT 矩阵→响应表(参数化应答;★透传)
  sections.py            # F3 章节装配(required_sections→sec:N 树)
  attachment_index.py    # SK-AI 需求×素材→索引行(待补负证据随行)+目录
backend/tests/
  bid_write_generate_fixtures.py   # 输入面夹具(tender fields+matrix 行+素材+单价)
  test_bid_write_generate_price_sheet.py
  test_bid_write_generate_bid_letter.py
  test_bid_write_generate_response_table.py
  test_bid_write_generate_sections_index.py
  test_bid_write_generate_ctx.py    # 金标闭环:build_ctx→run_assertions 43 PASS+降级负例
```

## 契约表(生成器输出=green_ctx 形,逐键)

| 生成器 | 输入 | 关键输出契约 |
|---|---|---|
| price_sheet | tender.boq_items+unit_prices{id:价}+knobs(mode/tax_rate/note/mech) | rows[{id,name,qty,unit,unit_price,amount}](缺价→None 留空)/detail_total=Σ(amount 非 None)/summary_total/open_letter_total/amount_cn=num_to_cn(detail)/price_mode/tax_rate/note/price_adjust_mechanism/pending_items |
| bid_letter | tender fields+ps+material.bidder_profile+knobs(sign_date/承诺) | slots 11(total_cn/num 引 ps;bidder/legal_rep 缺素材→"")/text=模板渲染(致→报价→有效期→承诺→落款;零禁用词)/fixed_text 固定段/signature 双锚 True/extra_commitments←decl 行+通用/entity_refs/pending_items |
| response_table | matrix 行(kind∈attachment,clause)+row.requirement | matrix_star_clause_ids/rows[{clause_id,star,conclusion:完全响应,response_text=参数化(绕空应答桶),requirement_excerpt,evidence_refs 透传,deviation_reason:None,replacement_plan:None}]/pending_items |
| sections(F3) | tender.required_sections | [{code:sec:N,title,level}](编号前缀定级;稳定序) |
| attachment_index | attachment_requirements×material.entities(名归一匹配)+volume_specs+sections | items(ready=命中实体+指纹;待补=占位行+negative_evidence 随行)/total_pages/toc_titles=sections+items 名/body_text 参数化零禁用词/pending_items(待补同步) |

- 相似度注入(pre 面,build_ctx 内 difflib SequenceMatcher):bl_fixed_similarity(fixed_text vs text 内固定段)/rt_excerpt_overlaps{clause_id:ratio}(excerpt vs requirement)/ps_replay_equal/kernel_replay_equal=重算比对(纯代码零漂移应恒 True)/rt_cross_field{total_amount:{rt,other}}/toc_page_estimates。
- Decimal 律(§2.2 硬约束):中间 4 位→落表 2 位 ROUND_HALF_UP;零浮点累加(qty/unit_price 入口 Decimal(str(v)));amount_cn 复用 executor.amount_cn.num_to_cn。

## 任务(本批=批二十 M1-e..i,TDD 序)

### Task 1 (M1-e): price_sheet 计算内核

- [x] `generate/price_sheet.py`:calc_price_sheet(boq_items, unit_prices, *, price_mode, tax_rate, note, price_adjust_mechanism)→price_sheet dict;缺价行 amount=None;detail_total 只加非 None;行序=boq 序
- [x] 测试:两行全价=green 形逐键相等/缺单价→None+总额只计有价行/Decimal 2dp HALF_UP 边界(xxx.005)/行序稳定/amount_cn canonical/qty 改动不发生(输入原样透传)
- [x] commit「批二十 M1-e PS 计算内核」

### Task 2 (M1-f): bid_letter 模板渲染

- [x] `generate/bid_letter.py`:render_bid_letter(tender_fields, ps, material, knobs)→bid_letter dict;金额三源引用 ps;主体信息仅素材源(缺→"" 诚实缺件);text 固定模板(段落骨架 §2.1);wordscan 自检(零命中断言)
- [x] 测试:全输入=green slots 逐键/素材缺位→bidder_name=""(下游 BL-004 FAIL 面)/extra_commitments 来自 decl 行带 clause_id+通用 tag/text 无禁用词/金额与 ps 三面一致
- [x] commit「批二十 M1-f BL 渲染」

### Task 3 (M1-g): response_table 装配

- [x] `generate/response_table.py`:build_response_table(matrix_rows)→rt dict;只取 kind∈(attachment,clause);response_text=f"我方已按招标要求完成准备:{excerpt[:40]}。"(绕空应答/模糊桶,测试钉 zero-hit);excerpt=requirement 截 120;★透传
- [x] 测试:green matrix 两行→green 形逐键/非附件条款行不收/★集=star 行集/response_text 六桶零命中/excerpt cap120
- [x] commit「批二十 M1-g RT 装配」

### Task 4 (M1-h): sections(F3)+ attachment_index

- [x] `generate/sections.py`:assemble_sections(required_sections)→[{code,title,level}];编号前缀("1."→1,"1.1"→2,无编号→1)稳定序
- [x] `generate/attachment_index.py`:build_attachment_index(attachment_requirements, volume_specs, material, sections, knobs)→ai dict;名归一匹配实体→ready(指纹=实体 type);未命中→status=待补+copies=min_count+**negative_evidence{retrieved,match_key,nearest}** 随行进 items 行+pending_items;volumes→V1.. 行;total_pages=estimates 和;body_text 参数化零禁用词
- [x] 测试:命中→ready 逐键/未命中→待补行+负证据键非空(钉 CMN-005 面)/volumes V1V2/toc=章节+件名/编号唯一/待补名称列无「待补」词(AI 铁律:待补只在 status 列)
- [x] commit「批二十 M1-h F3 章节树+AI 索引」

### Task 5 (M1-i): build_ctx 总装+金标闭环+收口

- [x] `generate/__init__.py`:build_ctx(tender_fields, matrix_rows, material, knobs)→ctx(tender 面=fields 直通;products=四生成器;pre=注入面重算);tender.boq_items/max_price 不在 fields 时如实缺(tender.get)
- [x] 测试(test_bid_write_generate_ctx.py):金标闭环=夹具输入→build_ctx→run_assertions 全 43 PASS;降级负例:①缺一张单价→PS-007 FAIL(留空暴露非造假)②素材缺→BL-004/RT-007 FAIL ③decl 行承诺→BL-010 PASS(clause_id 溯源)④二跑字节级相等(确定性);CLI 面冒烟(可选)
- [x] plan 勾兑+spec §7 更新(F3/F4 落地态)+wolf 三件套
- [x] `cd backend && make lint && PYTHONPATH=. uv run pytest tests -k bid_write -q` 全绿;commit「批二十 M1-i 收口 F3+F4」

## Self-Review

- spec §2 逐技能骨架对照:BL 金额引用 PS✓ 主体素材源✓ 固定段✓;PS 明细唯一事实源✓ 缺价留空✓ 禁止自动补行✓(boq 外行不造);RT ★透传✓ 参数化应答绕空应答桶✓;AI 待补不静默✓ 负证据随行✓ 编号唯一✓
- 降级=断言面暴露(生成物缺件→D0 FAIL),生成器自身不吞错不造假绿✓
- 零上游/审查端文件改动;新子包独立模块律;commit 显式文件清单;不入库不 push(用户令)
- worker 接线/F6 预审查/导出前置=M2(批廿一),本批不碰 worker.py
