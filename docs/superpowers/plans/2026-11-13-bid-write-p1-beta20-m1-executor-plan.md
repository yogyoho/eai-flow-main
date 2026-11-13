# 批二十 M1:断言执行器骨架(Assertion Executor)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline,batch execution with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 断言执行器 v0.1 落地 `app/extensions/bid_write/executor/`——加载 43 条注册表、逐条 Python 校验函数(无 DSL)、D0 短路执行语义、导出门禁+待补清单、确定性 20 次字节级一致(spec §8 裁决兑现)。

**Architecture:** 纯函数执行核(runner: ctx → RunReport,零 IO 零时钟)+ 落库面(BidWriteSkillRun 表,共享 Base)+ 待补清单并经既有 `gaps` 端点数据面产出。校验器按 assertion_id 注册 `dict[str, callable]`,上下文缺失=ERROR E-CTX-MISSING 不得静默。

**Tech Stack:** Python 3.12 / SQLAlchemy(共享 Base,bug-4303 律)/ PyYAML / pytest。无新依赖。

**真相源:** spec `docs/superpowers/specs/2026-11-13-bid-write-p0-skills-spec.md` §8(执行语义裁决)+ §6(rule_ref 映射);注册表 `backend/app/extensions/bid_write/assertions/p0.yaml`(43 条/31 D0/CMN×5 共享层);词汇 `contracts.py`(FORBIDDEN_WORDS/DEGRADE_LEVELS/SCHEMA_VERSION)。

---

## 文件结构

```
backend/app/extensions/bid_write/executor/
  __init__.py        # 公共 API re-export(run_assertions/RunReport/load_registry)
  loader.py          # p0.yaml → list[AssertionDef];加载期静态校验
  models.py          # AssertionDef/AssertionResult/Outcome dataclasses + SkillRun ORM 表
  runner.py          # 纯函数执行核:排序/短路/委托/CtxMissing→ERROR
  gate.py            # 导出门禁 + 水印位(M1 恒 False,L4 面 M2)
  report.py          # 确定性序列化 + 待补清单 + SKIPPED 可解释性注记
  amount_cn.py       # 金额大小写双向转换(角分全支撑;review 端 _number_to_words 角分 v2 未做且私有,不跨端复用)
  wordscan.py        # FORBIDDEN_WORDS 分类扫描(占位符/绝对化/模糊调价/空应答/红线;大小写不敏感面)
  cli.py             # 金标准 oracle 适配面:ctx JSON→报告 JSON,退出码 0/1/2
  validators/
    __init__.py      # REGISTRY: dict[str, Callable] + register 装饰器
    cmn.py bl.py ps.py rt.py ai.py   # 每条断言一个函数,expr 注=验收基准
backend/tests/
  test_bid_write_executor_loader.py
  test_bid_write_executor_runner.py
  test_bid_write_executor_validators.py   # 43 条逐条正/负例
  test_bid_write_executor_gate_report.py
  test_bid_write_executor_negatives.py    # golden 注入负例夹具驱动
  test_bid_write_executor_determinism.py  # 20× 字节级
  bid_write_exec_fixtures.py              # ctx 夹具构造器(全绿基线 + 每技能变体)
app/extensions/bid_write/golden/cases-write/exec-negatives.yaml  # 每技能 8–12 条注入负例
```

**既有文件改动(全部一行级):**
- `bid_write/models.py`:不动(SkillRun 落 executor/models.py,经 routers import 注册 metadata)。
- `bid_write/routers.py`:`from .executor.models import SkillRun as _SkillRun  # noqa 注册 Base.metadata`(一行)+ `get_gaps` 增断言维度段(读最新 SkillRun)。
- `bid_write/crud.py`:`record_skill_run`(+8 行)。

---

## 执行语义契约(spec §8 逐条兑现)

| 语义 | 落地 |
|---|---|
| 排序 | 执行序=(level_rank, assertion_id) 字典序,level_rank D0=0<D1=1<D2=2<D3=3;**委托条(AI-009)不进执行序**,全量跑完后派生;报告序同键排序 |
| 短路 | D0 FAIL → 同技能未执行断言 SKIPPED(`skipped_reason="short_circuit"`,注明因谁);其他技能继续;CMN 层恒执行(export 级全扫描,不受 skills 参数裁剪) |
| 上下文缺失 | 校验器 raise `CtxMissing(key)` → runner 转 `status=ERROR`,`message="E-CTX-MISSING: <key>"`,计失败面,绝不静默 |
| 运行时升级 | 词级断言(BL-006/CMN-002/PS-009)命中词取 `FORBIDDEN_WORDS[word][0]`,final_level=max(static, word_level);blocks_export 由 levels 表 `blk` 列按 final_level 分派(yaml `blocks_export` 列仅加载期一致性校验) |
| 特免降级 | 仅 yaml expr 明文者:PS-006 限价未抽到→SKIPPED(no_signal,「限价未确认」);PS-010 历史价缺失→SKIPPED(no_signal, D3 静默)。其余缺操作数一律 ERROR |
| 委托 | AI-009 result ← CMN-005 result(status/level 镜像,自持 assertion_id/错误码登记;CMN-005 短路 SKIPPED 则同样镜像) |
| 门禁 | blocked = ∃ result(final_level=D0 ∧ status∈{FAIL,ERROR});L1 fatal 面=M2(ctx `pre_review` 键预留);watermark M1 恒 False(`l4_counts_toward_gate: false` 注释) |
| 待补清单 | pending = FAIL/ERROR ∧ levels 表 todo∈{required,optional};含 assertion_id/level/message/human_action |
| 确定性 | 报告无时钟无集合序;`json.dumps(sort_keys=True, ensure_ascii=False)` 20 次逐字节相等 |

## 校验器契约表(ctx 键 → 判定 → 特免)

ctx 形状:`{"tender": {...抽学子集}, "products": {"bid_letter": {...}, "price_sheet": {...}, "response_table": {...}, "attachment_index": {...}}, "material": {...}|缺省, "pre": {...注入面}}`。夹具基线构造器 `bid_write_exec_fixtures.green_ctx(skills)` 产全绿上下文,负例从基线变异。

| 断言 | ctx 读取 | 判定 |
|---|---|---|
| CMN-001 | products 全文切片 | 占位符词(待补充/待定/TBD/XX 大小写不敏感)+未闭合 `{{calc(`/`{{ref(` 0 命中 |
| CMN-002 | 全文 | 绝对化/红线类扫描;final=max(static D1, 词级) |
| CMN-003 | products[*].entity_refs + material.entities | ref 全可解析且值一致;material 缺位→D0 缺件 FAIL(诚实) |
| CMN-004 | pre.kernel_replay_equal | True 才过;price_sheet 空则 PASS(note) |
| CMN-005 | products[*].pending_items[].negative_evidence | status=待补 项全带负证据 |
| BL-001 | bid_letter.slots | REQUIRED_LETTER_SLOTS=yaml expr 点名 11 项全非空;「12 个」第 12 槽位无 repo 真源(L1-007 实为签章完整,input 无槽位清单)→挂账 spec,F4 模板落地时锁定 |
| BL-002 | slots.total_amount_cn/num + price_sheet.total_amount | amount_cn 双向相等 ∧ ==报价表总额 |
| BL-003 | slots.valid_days + tender.required_validity_days | ≥;操作数缺→ERROR |
| BL-004 | slots.bidder_name + material.bidder_profile.name | 完全一致;material 缺→D0 缺件 |
| BL-005 | slots.sign_date + tender.bid_deadline | ≤;缺→ERROR |
| BL-006 | bid_letter.text | 五类词扫描,final=max(D1, 词级) |
| BL-007 | pre.bl_fixed_similarity | ≥0.98;deterministic=False |
| BL-008 | bid_letter.signature | 盖章位+签字位锚点在 |
| BL-009 | bid_letter.entity_refs + material | 同 CMN-003 技能级 |
| BL-010 | bid_letter.extra_commitments[] | 每条含 clause_id 或「通用承诺」 |
| PS-001/002 | price_sheet.rows + tender.boq_items | 行覆盖(键=name norm)∧ qty/unit 逐行相等 |
| PS-003 | price_sheet 四额 | 明细=汇总=开标一览=投标函 |
| PS-004 | note + total_amount | 大小写互转相等 |
| PS-005 | price_mode + tax_rate | mode 唯一;税率一致或分行标注 |
| PS-006 | total + tender.max_price | ≤;max_price 缺→SKIPPED「限价未确认」(特免) |
| PS-007 | rows[].unit_price | 全 >0(缺失=FAIL 不补) |
| PS-008 | pre.ps_replay_equal | True;deterministic=False 注入面 |
| PS-009 | price_sheet.note + price_adjust_mechanism | 调价类词;无机制→命中升 D0 |
| PS-010 | total + material.price_history | 低于均值阈值→FAIL(D2 提示);历史价缺→SKIPPED(D3,特免) |
| RT-001 | response_table.matrix_star_clause_ids + rows[].clause_id | ★全覆盖 |
| RT-002 | rows(star,conclusion) | 无 star∧负偏离 |
| RT-003 | rows[].response_text | 空应答类词 0 命中 |
| RT-004 | pre.rt_excerpt_overlaps{clause_id: float} | ≥0.80;deterministic=False |
| RT-005 | rows(负偏离) | 原因+替代方案齐 |
| RT-006 | pre.rt_cross_field{field: {rt, other}} | 全相等 |
| RT-007 | rows[].evidence_refs + material | refs 非空∧实体存在;M0 无实体库→全 D0 待补 |
| RT-008 | rows(完全响应) | 正文无偏离表述(DEVIATION_MARKERS) |
| RT-009 | response_table 全文 | 占位符 0 命中(技能级 CMN-001 镜像) |
| AI-001 | attachment_index.items[].no | norm 去重数相等 |
| AI-002 | items + tender.attachment_requirements | 要求逐项有索引项或标待补 |
| AI-003 | body_text + items[].no | 「见附件X」全可解析 |
| AI-004 | items[].page + total_pages + pre.toc_page_estimates | page≤总页;有目录估值时偏差≤1(>5 标「页码待核对」) |
| AI-005 | items[].copies + tender.volume_specs | 份数达标 |
| AI-006 | items[].type_fingerprint | ≠unknown_type |
| AI-007 | items[].source | 内容锚点非空 |
| AI-008 | toc_titles + body_headings | 目录/正文标题逐条匹配 |
| AI-009 | (委托) | ← CMN-005 镜像 |

---

### Task 1: loader + models(数据面)

- [x] `executor/models.py`:AssertionDef(id/skill/name/level/blocks_export/rule_ref/expr/human_action/delegates_to)+ Outcome/AssertionResult/CtxMissing;SkillRun ORM 表 `bid_write_skill_runs`(id/task_id FK/owner_id/skills/verdict JSON/blocked/schema_version/created_at;**共享 Base**)
- [x] `executor/loader.py`:load_registry()→defs;静态校验=ID 唯一/level∈DEGRADE_LEVELS/D0⇔blocks_export/meta.schema_version==contracts.SCHEMA_VERSION/delegates 目标存在/CMN 范围钉;module 级 lru_cache。rule_ref 悬空面=既有 pin test(CI 时点),运行时不重扫审查注册表(零增益);plan 级注记
- [x] 测试 loader:43 条全载/版本不符拒载/D0⇔blk 违例拒载/delegates 悬空拒载/ID 重复拒载
- [x] routers.py 一行 import;测试:Base.metadata 含 bid_write_skill_runs
- [x] `make lint` 双清;commit「批二十 M1-a1」

### Task 2: runner 核 + AI/CMN-005 校验器(跑通 1 技能)

- [x] `validators/__init__.py` REGISTRY+register;`validators/ai.py`(AI-001..008+AI-009 委托登记)+`validators/cmn.py`(CMN-005 单实现)
- [x] `runner.py`:run_assertions(ctx, skills=None)→RunReport;排序/短路/委托派生/CtxMissing→ERROR/CMN 恒执行
- [x] 测试 runner:AI 全绿/SK-AI-001 D0 fail→AI-002..008 SKIPPED 注明因谁+AI-009 镜像/缺 ctx 键→E-CTX-MISSING/delegates 不重复执行(CMN-005 只跑一次)/skills=["BL"] 时 CMN 仍执行
- [x] commit「批二十 M1-a2 跑通 AI 技能」

### Task 3: 全量 43 条校验器

- [x] `amount_cn.py`(num→CN 含零/整/角分;CN→num;单测 20 组边界值内嵌)
- [x] `wordscan.py`(分类扫描+词级 max;大小写不敏感面)
- [x] `cmn.py` 补 001-004;`bl.py` 10 条;`ps.py` 10 条;`rt.py` 9 条(逐条按契约表)
- [x] 测试 validators:43×(正例/负例/特免 PS-006 PS-010/词级升级 BL-006 PS-009)/fixtures 构造器落 `bid_write_exec_fixtures.py`
- [x] commit「批二十 M1-b 全量 43 条」

### Task 4: report + gate + 待补清单 + gaps 接线 + 注入负例全红

- [x] `report.py` to_dict(确定性序)+ pending 提取 + SKIPPED 注记「因 SK-XX 失败跳过 N 条」;`gate.py` blocked/水印位
- [x] crud.record_skill_run + get_gaps 增 `assertions` 段(最新 SkillRun;无 run→M0 形状不变,向后兼容)
- [x] `golden/cases-write/exec-negatives.yaml`(每技能 8–12 条变异负例)+ 夹具驱动测试:**负例全红**(注入缺陷 100% 检出,零漏报)
- [x] 测试 gate_report:gate 阻断/水印恒 False/pending 含 human_action/序列化键序稳定
- [x] commit「批二十 M1-c 清单+门禁+负例」

### Task 5: 确定性 20× + CLI oracle + 收口

- [x] `cli.py`(ctx JSON 路径→报告 stdout,exit 0 全过/1 有 FAIL/2 有 ERROR)+ 单测
- [x] determinism 测试:green_ctx 20 次 run → dumps 字节级相等
- [x] plan 勾兑 + spec §7 挂账更新(执行器落地态)+ wolf 三件套(memory/anatomy/cerebrum)
- [x] `cd backend && make lint && PYTHONPATH=. uv run pytest tests/ -k bid_write -q` 全绿;commit「批二十 M1-d 收口」

## Self-Review

- spec §8 采纳面全覆盖:排序✓ 短路✓ SKIPPED 可解释✓ E-CTX-MISSING✓ 门禁+水印✓ 职责分界(断言/规则不重复计,报告分开展示=M2 预审查面注记)✓ 20× 确定性✓
- 适配面:executor 目录✓ 无 DSL✓ skill_run 落库✓ SCHEMA_VERSION 比对✓ CLI oracle✓ gaps 面✓
- 零上游/审查端文件改动;新表共享 Base;commit 显式文件清单;不入库不 push(用户令)
