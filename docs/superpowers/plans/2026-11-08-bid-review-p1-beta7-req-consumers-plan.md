# P1-β批七(§6.1 ❌4 消费规则)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 §6.1 差表最后 4 个 ❌ 字段(pm_req/subcontract_limit/required_signatures/format_requirements)及其规格消费规则(L1-004/L1-020/L1-022/L1-026 + L1-007 inputs 扩),❌4→0 收口 tender 33 字段差表。

**Architecture:** 沿批六形态——模型抽取契约入 FIELD_TYPE_CONTRACTS(T1)→ 规则卡入 rulepack(T2)→ L1-007 富化扩(T3)→ 宇宙五锁 bump(T4)→ golden 面(T5)→ spec 收口(T6)。sem 规则走 L1-013 先例(steps:[] 形态门放行),hyb 走 L1-007 双键模式(det_expr+op),det 日期比较复制 L3-014 先例。

**Tech Stack:** Python 3.12 + pytest;rulepack yaml;无前端面。

---

## 裁决表(controller-locked;实现者按裁决精神处理,偏离须显式声明)

| # | 裁决 |
|---|---|
| A-β7-① | 字段+消费规则同批(批六红线沿用)。四字段各配规格消费规则;format_requirements 双消费(L1-022+L1-026)同批落 |
| A-β7-② | 数字锁:宇宙 105→**113** / det 49→**50** / 包 55→**59** / golden 题 78→**82** / EXPECTED_COVERAGE 55→**59** / 首段请求面 93→**101**(=113−6−6) |
| A-β7-③ | L1-007 扩走批六 T4 富化模式:inputs += tender.required_signatures,det_expr/op/message_tpl/fix_tpl 逐字冻结,hyb prompt 自动富化。**L2-030 不扩**(翻案:tender.required_signatures 是 list[str],L2-030 cond 消费 t.no 结构化 slots——shape 不匹配,强落即 bug;挂账待规格侧明确两字段关系) |
| A-β7-④ | L1-004 v1 窄化:inputs=[bid.pm, tender.pm_req]。bid.business_items 不落(M4 聚类后仓库无此路径,零消费不落;「无在建」维度由 bid.pm.on_other_project 承担,business_items 跨引维度挂账) |
| A-β7-⑤ | L1-026 v1 只落时间维(check 复制 L3-014 日期比较先例 `bid.submit_time <= tender.bid_deadline`);「递交方式在允许集合」维挂账(规格未定义允许集合字段源);**bid.submit_method 不落**(无消费不落红线)。bid.fields.* 规格命名空间按仓库平路径惯例拍平为 bid.submit_time(C-09 式别名注记挂账) |
| A-β7-⑥ | L1-022 severity v1=major 固定。规格「招标明示否决时升 fatal」需 severity_override 机制(规格 L1 严重度说明允许,仓库未实现)——机制挂账,本批不发明 |
| A-β7-⑦ | **中期红清单(批六教训,逐任务显式)**:T1 后 registry `TestCrossSourceSubset::test_contracts_subset_universe` 红(契约未入宇宙)→T4 复绿;T2 后 golden `test_coverage_complete_marker` 红(题库缺 4 新规则期望)→T5 复绿;各 pin 归属:T2 动 pack 面 pin(det 数/包数/EXPECTED_V1_IDS),T4 动宇宙面 pin(EXPECTED_UNIVERSE/首段算式/anchored/families len),T5 动 golden 面 pin(EXPECTED_COVERAGE) |
| A-β7-⑧ | 引擎小折(同批,T3):dict-step 缺 `expr` 键 → 载入期拒载(现静默不收集,实评 KeyError→need_human 太晚);L1-006 forms step 补「免缴 N/A 语义」yaml 注。keywords 纯 ASCII 精化**不落**(零夹具压力,保持挂账——无失败案例不改匹配语义) |
| A-β7-⑨ | 新锚点注册:A-PM-CERT/A-PM-SOCIAL/A-TENDER-FORMAT 入 ANCHOR_REGISTRY(anchors.py:17;未注册锚 bug-3985 拒载/静默丢证据)。golden 面与台账 controller 直办(A-β6-⑨⑩ 沿用) |

## 实态勘误(recon 已验证,实现者免重查)

- `eval_core:136` 剥 None(bug-4227):**本批所有 golden 夹具新键必须给非 None 真实值**
- L3-014 check 逐字:`steps: ["bid.bid_letter_date <= tender.bid_deadline"]`——字符串 step 单消息形态
- L1-013(sem 先例,rulepack :404+):`type: semantic` + `check: {steps: [], verdict_set: [...]}`——load 形态门靠 steps 键放行,执行走 run_sem_rule
- L1-007(hyb 双键先例,rulepack :384+):det_expr 与 op 并存;prefilter 门=`det_expr or op`(llm_runner:189)
- `_KNOWN_OPS` 含 or(check-op 层,批二);**表达式级 or 未验证**——L1-022 用 op:or any 形态(仅用已证明形态),禁 det_expr 内写裸 or(除非实现者先证 parser 支持,见 T2 勘误步骤)
- `codes()`/`col()` 只收 dict 行;字符串列表禁入
- L1-007 现有 golden 夹具 3 件(L1-007-signature-missing/L2-030-l1007-folded/L2-030-signature-slot-missing)T3 后需补 `tender.required_signatures` 真实值键
- ANCHOR_REGISTRY 在 anchors.py:17;A-COMMIT/A-TENDER-CLAUSE/A-TOC/A-BID-LETTER/A-TENDER-NOTICE 已注册,A-PM-CERT/A-PM-SOCIAL/A-TENDER-FORMAT 未注册
- lint_rules 正确形态:`lint_rules(load_rulepack(PACK).rules)`(非 _pack_rules())
- 家族门:`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(并发 merge 期加 `--continue-on-collection-errors`)

---

### Task 1: 8 条模型抽取契约(extract.py + 契约测试)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(FIELD_TYPE_CONTRACTS 区尾,批六 12 条之后)
- Test: `backend/tests/test_bid_review_extract.py`(新 class TestBeta7FieldContracts)

- [ ] **Step 1: 写失败测试**(仿 TestBeta6FieldContracts 形态,BETA7_PATHS 8 条逐行)

```python
BETA7_PATHS = [
    "tender.pm_req",
    "tender.subcontract_limit",
    "tender.required_signatures",
    "tender.format_requirements",
    "bid.pm",
    "bid.service_commitments",
    "bid.format",
    "bid.submit_time",
]


class TestBeta7FieldContracts:
    """批七:§6.1 ❌4 消费面 8 条抽取契约(规格 §6.2 形状逐字)。"""

    def test_contracts_registered(self):
        for path in BETA7_PATHS:
            assert path in FIELD_TYPE_CONTRACTS, path

    def test_contract_shapes_hint_model(self):
        # 形状提示关键字在场:模型侧照形状诚实产出
        assert "certs" in FIELD_TYPE_CONTRACTS["tender.pm_req"]
        assert "allowed" in FIELD_TYPE_CONTRACTS["tender.subcontract_limit"]
        assert "签字盖章" in FIELD_TYPE_CONTRACTS["tender.required_signatures"]
        assert "copies" in FIELD_TYPE_CONTRACTS["tender.format_requirements"]
        assert "on_other_project" in FIELD_TYPE_CONTRACTS["bid.pm"]
        assert "value" in FIELD_TYPE_CONTRACTS["bid.service_commitments"]
        assert "sealing_label" in FIELD_TYPE_CONTRACTS["bid.format"]
        assert "递交" in FIELD_TYPE_CONTRACTS["bid.submit_time"]
```

- [ ] **Step 2: 跑测试确认失败**:`PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py::TestBeta7FieldContracts -q` → FAIL(KeyError/missing)
- [ ] **Step 3: 实现**(extract.py FIELD_TYPE_CONTRACTS 区尾追加,批七注释块;逐字):

```python
# ── 批七(A-β7-①,2026-11-08):§6.1 ❌4 消费面 8 条抽取契约(规格 §6.2 形状逐字)──
FIELD_TYPE_CONTRACTS["tender.pm_req"] = '{certs:["证书名称"],social_months:12,exclusive:true} 对象;项目负责人资格要求(证书类别/社保连续月数/是否须专职无在建);无明示给 null。'
FIELD_TYPE_CONTRACTS["tender.subcontract_limit"] = '{allowed:true,scope:"允许分包的范围"} 对象;分包限制;无明示给 null。'
FIELD_TYPE_CONTRACTS["tender.required_signatures"] = '["签字盖章处名称"] 字符串列表;招标要求签章的位置清单;无明示给空数组。'
FIELD_TYPE_CONTRACTS["tender.format_requirements"] = '{toc:true,page_numbering:true,font:"字体字号要求",copies:4,sealing:"密封标识要求"} 对象;格式份数密封要求;无明示给 null。'
FIELD_TYPE_CONTRACTS["bid.pm"] = '{name:"拟任项目经理姓名",certs:["证书名称"],social_months:24,on_other_project:false} 对象;拟任项目负责人实体;无明示给 null。'
FIELD_TYPE_CONTRACTS["bid.service_commitments"] = '[{item:"承诺事项",value:"承诺内容",section:"所在章节"}] 对象列表;分包/转包相关服务承诺;无明示给空数组。'
FIELD_TYPE_CONTRACTS["bid.format"] = '{toc:true,page_numbering:true,font:"实际字体字号",copies:4,sealing_label:"密封标识实际描述"} 对象;投标文件格式实体;无明示给 null。'
FIELD_TYPE_CONTRACTS["bid.submit_time"] = '"2026-11-08 09:00:00" 时间字符串;投标文件递交时间;无明示给 null。'
```

- [ ] **Step 4: 跑测试确认通过** + `TestCrossSourceSubset::test_contracts_subset_universe` **预期红**(中期红清单 A-β7-⑦,T4 复绿——此红**不是**回归,勿修)
- [ ] **Step 5: lint + commit**(`git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_extract.py`;commit msg `feat(bid-review): 批七T1——§6.1 ❌4 消费面 8 条抽取契约入 FIELD_TYPE_CONTRACTS(规格 §6.2 形状逐字,无明示给 null/空数组,A-β7-①);registry subset 中期红声明(A-β7-⑦)`)

### Task 2: 4 条新规则 + 锚点注册(rulepack + anchors + pack pins + 规则单测)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(尾追加 4 规则)
- Modify: `backend/app/extensions/bid_review/engine/anchors.py`(ANCHOR_REGISTRY +3)
- Test: `backend/tests/test_bid_review_rule_runner.py`(新 class TestBeta7Rules + pins)

- [ ] **Step 1: 写失败测试**(run_det_rule 直跑可测 L1-026;hyb/sem 用 run_sem_rule+scripted model_fn 测管线走通;另更新 pins:test_full_pack_loads det 49→50/包 55→59、EXPECTED_V1_IDS += [L1-004, L1-020, L1-022, L1-026])

L1-026 直跑测试(构造 fields 喂 run_det_rule):
```python
class TestBeta7Rules:
    """批七:4 条新消费规则(L1-004 hyb/L1-020 sem/L1-022 hyb/L1-026 det)。"""

    def _rule(self, rid):
        pack = load_rulepack(PACK)
        return next(r for r in pack.rules if r.id == rid)

    def test_l1_026_late_submission_fails(self):
        rule = self._rule("L1-026")
        fields = {"bid.submit_time": "2026-11-09 09:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1
        assert issues[0]["verdict"] == "FAIL"
        assert "递交" in issues[0]["message"]

    def test_l1_026_in_time_passes(self):
        rule = self._rule("L1-026")
        fields = {"bid.submit_time": "2026-11-08 09:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
        assert run_det_rule(rule, fields) == []

    def test_l1_026_missing_fields_need_human(self):
        rule = self._rule("L1-026")
        issues = run_det_rule(rule, {"bid.submit_time": "2026-11-08 09:00:00"})
        assert issues[0]["verdict"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_l1_020_sem_pipeline_runs(self):
        rule = self._rule("L1-020")
        script = '{"verdicts": [{"clause_id": "SC-1", "verdict": "none", "confidence": 0.9, "reason": "承诺含转包表述", "evidence": []}]}'

        class R:
            content = script

        issues = await run_sem_rule(rule, {"tender.subcontract_limit": {"allowed": False, "scope": "不允许分包"}, "bid.service_commitments": [{"item": "分包", "value": "允许转包", "section": "承诺函"}]}, "", wrap_model_fn(lambda m: R()), "")
        assert any(i["rule_id"] == "L1-020" and i["verdict"] == "FAIL" for i in issues)

    def test_pack_pins(self):
        pack = load_rulepack(PACK)
        dets = [r for r in pack.rules if r.type == "deterministic"]
        assert len(pack.rules) == 59
        assert len(dets) == 50
```

(注:run_sem_rule/wrap_model_fn 的既有 import 形态从该测试文件现头照抄;L1-004/L1-022 hyb 管线测试仿 L1-020 形态各一条——L1-004 用 det 粗筛候选+scripted partial 断 FAIL,L1-022 用 op:or 候选+scripted partial 断 FAIL。)

- [ ] **Step 2: 跑测试确认失败**(L1-004/020/022/026 KeyError + pins 红)
- [ ] **Step 3: rulepack 尾追加 4 规则**(批七注释块;逐字;**先跑勘误验证**):

实态勘误步骤(先于 yaml 落笔跑一遍):
```bash
PYTHONPATH=. uv run python -c "
from app.extensions.bid_review.engine.rule_runner import load_rulepack
p = load_rulepack('app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml')
r7 = next(r for r in p.rules if r.id == 'L1-007')
print(r7.type, list(r7.check.keys()))  # 确认 hyb 双键形态
"
```

```yaml
  # ── 批七(A-β7-①..⑥,2026-11-08):§6.1 ❌4 消费规则四条 ──
  # L1-004(hyb,fatal):项目负责人资格/社保/无在建——det 粗筛=证书清单非空出候选,模型确认
  # 类别匹配/社保达标/无在建/主体核验;A-β7-④ 窄化:business_items 跨引维度挂账
  - id: L1-004
    name: 项目负责人资格、社保与无在建
    layer: L1
    type: hybrid
    applies_to: ["*"]
    inputs: [bid.pm, tender.pm_req]
    check:
      det_expr: "count(bid.pm.certs) >= 1"
      op: eq
      left: "count(bid.pm.certs)"
      right: 0
      verdict_set: [full, partial, none, unclear]
    severity: fatal
    evidence: [A-PM-CERT, A-PM-SOCIAL, A-TENDER-CLAUSE]
    message_tpl: "项目负责人资格要件不满足:{bid.pm.name} 证书类别/社保月数/在建情况与招标要求不符"
    fix_tpl: "补齐或更正项目负责人证书与社保证明,确认无其他在建项目后重新上传"
    confidence_gate: 0.75
    enabled: true
  # L1-020(sem,fatal):分包转包承诺合规——纯语义规则,L1-013 steps:[] 形态门先例
  - id: L1-020
    name: 分包转包承诺合规
    layer: L1
    type: semantic
    applies_to: ["*"]
    inputs: [tender.subcontract_limit, bid.service_commitments]
    check:
      steps: []
      verdict_set: [full, partial, none, unclear]
    severity: fatal
    evidence: [A-COMMIT, A-TENDER-CLAUSE]
    message_tpl: "分包/转包承诺与招标分包限制冲突或含转包表述"
    fix_tpl: "修改服务承诺与招标分包限制一致,删除任何转包表述"
    confidence_gate: 0.75
    enabled: true
  # L1-022(hyb,major):格式份数密封——stage1 det 可判定维(份数/目录/页码)op:or 出候选,
  # stage2 模型确认字体/装订/密封;A-β7-⑥ severity v1=major 固定(severity_override 机制挂账)
  - id: L1-022
    name: 格式、份数与密封标识
    layer: L1
    type: hybrid
    applies_to: ["*"]
    inputs: [tender.format_requirements, bid.format]
    check:
      op: or
      any:
        - "tender.format_requirements.copies != bid.format.copies"
        - "bid.format.toc == False"
        - "bid.format.page_numbering == False"
      verdict_set: [full, partial, none, unclear]
    severity: major
    evidence: [A-TOC, A-TENDER-FORMAT]
    message_tpl: "格式要件不符:份数/目录/页码与招标要求不一致(要求 {tender.format_requirements.copies} 份)"
    fix_tpl: "按招标格式要求调整份数、目录与页码编制,补齐密封标识"
    confidence_gate: 0.75
    enabled: true
  # L1-026(det,fatal):递交时间符合——A-β7-⑤ v1 只落时间维(L3-014 字符串日期比较先例逐字同构);
  # 「递交方式在允许集合」挂账(规格无允许集合字段源,bid.submit_method 无消费不落)
  - id: L1-026
    name: 递交时间符合
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.submit_time, tender.bid_deadline]
    check:
      steps:
        - "bid.submit_time <= tender.bid_deadline"
    severity: fatal
    evidence: [A-BID-LETTER, A-TENDER-NOTICE]
    message_tpl: "递交时间晚于投标截止:递交 {bid.submit_time} / 截止 {tender.bid_deadline}"
    fix_tpl: "核查递交回执时间;逾期递交按废标处理流程上报"
    confidence_gate: 1.0
    enabled: true
```

- [ ] **Step 4: 锚点注册**(anchors.py ANCHOR_REGISTRY +3,仿既有条目形态;A-PM-CERT/A-PM-SOCIAL/A-TENDER-FORMAT,用途注记批七)
- [ ] **Step 5: 跑测试确认通过 + lint_rules 零违例**:`PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -q` + `PYTHONPATH=. uv run python -c "from app.extensions.bid_review.engine.rule_runner import load_rulepack, PACK; from app.extensions.bid_review.engine.lint import lint_rules; ..."`(lint 调用形态按该文件现有用法);**golden test_coverage_complete_marker 预期红**(中期红清单,T5 复绿)
- [ ] **Step 6: lint + commit**(`git add` rulepack/anchors/规则测试三件;msg `feat(bid-review): 批七T2——4 条新消费规则:L1-004 项目负责人(hyb 双键,A-β7-④ 窄化)+L1-020 分包承诺(sem,L1-013 形态先例)+L1-022 格式密封(hyb op:or,severity major 固定 A-β7-⑥)+L1-026 递交时间(det,L3-014 先例 A-β7-⑤);锚点注册+3;pack pins 50/59;golden 面中期红声明`)

### Task 3: L1-007 inputs 扩 + 3 夹具补键 + 引擎 dict-step 载入拒载

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(L1-007 inputs 行)
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(load_rulepack dict-step expr 校验,一行)
- Modify: 3 golden 夹具(补 tender.required_signatures 真实值)
- Modify: rulepack L1-006 forms step 补免缴 N-A yaml 注(A-β7-⑧)
- Test: `backend/tests/test_bid_review_rule_runner.py`(2 小测)

- [ ] **Step 1: 写失败测试**:

```python
class TestBeta7L1007Extension:
    """批七 L1-007 inputs 扩(A-β7-③ 富化模式)+ dict-step 载入拒载(A-β7-⑧)。"""

    def test_l1_007_inputs_enriched(self):
        pack = load_rulepack(PACK)
        rule = next(r for r in pack.rules if r.id == "L1-007")
        assert "tender.required_signatures" in rule.inputs
        # 冻结面:det_expr/op 逐字不动
        assert rule.check["det_expr"] == "count(bid.missing_signature_pages) == 0"

    def test_l1_007_required_signatures_enriches_prompt(self):
        rule = next(r for r in load_rulepack(PACK).rules if r.id == "L1-007")
        card = build_rule_card(rule, {"bid.missing_signature_pages": [], "tender.required_signatures": ["法定代表人签字", "公章"]}, "")
        assert "法定代表人签字" in card

    def test_dict_step_missing_expr_rejected_at_load(self):
        # 载入期拒载:dict step 缺 expr 键(现静默不收集,实评才炸——左移)
        import copy
        pack = load_rulepack(PACK)
        rule = next(r for r in pack.rules if r.id == "L1-006")
        bad = copy.deepcopy(dataclasses.asdict(rule))
        for st in bad["check"]["steps"]:
            if isinstance(st, dict):
                st.pop("expr")
                break
        # 拒载路径:load_rulepack 对缺 expr 的 dict step raise RulePackError
        # (实现形态:load_rulepack 循环内对 chk["steps"] dict 项校验 "expr" in st)
```

(第三测实现形态:抽取一个纯 yaml dict(直接构造 raw dict 喂 load 路径的校验函数,或把校验提成模块级 `_validate_dict_steps(chk, rid)` 供 load 调用+测试直调——实现者按现有 load_rulepack 结构选最小侵入形态,不得为测试重构加载器。)

- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现**:rulepack L1-007 `inputs: [bid.missing_signature_pages]` → `inputs: [bid.missing_signature_pages, tender.required_signatures]`(行尾批七注释:富化模式 A-β7-③,det/op 逐字冻结);rule_runner load 校验一行;L1-006 forms step 注释追加「免缴场景:tender.deposit_forms 与 bid.deposit_forms 均声明时才判(set_eq step),免缴(N/A)不产此步 issue——语义注记,行为零变」;3 夹具各补 `tender.required_signatures` 真实值键(与各案例场景一致,如 `["法定代表人签字", "公章"]`;**禁 null**——bug-4227)
- [ ] **Step 4: 跑测试确认通过 + L1-007/L2-030 既有测试零回归**
- [ ] **Step 5: lint + commit**(msg `feat(bid-review): 批七T3——L1-007 inputs 富化 tender.required_signatures(A-β7-③ det/op 冻结;L2-030 shape 不匹配不扩挂账)+引擎 dict-step 缺 expr 载入拒载(A-β7-⑧ 左移)+3 golden 夹具补真实值键(bug-4227 禁 null)+免缴 N-A yaml 注`)

### Task 4: 宇宙五锁 bump(101/113/50/59)

**Files:**
- Modify: `backend/tests/test_bid_review_registry.py`(EXPECTED_UNIVERSE +8、首段算式 93→101、anchored_105→anchored_113)
- Modify: `backend/tests/test_bid_review_rule_families.py`(:134 `len(universe()) == 105` → 113)
- Modify: `backend/tests/test_bid_review_extract.py`(T1 skip 解除)

- [ ] **Step 1: skip 解除**:删 T1 首段请求面测试的 skip 标记,跑之——8 新路径入请求面
- [ ] **Step 2: 宇宙 pin 更新**(逐字核对 8 新路径行注释;EXPECTED_UNIVERSE 105→113;首段 81→...→101 算式注释随迁;anchored 测试名与体随迁;families len 113)
- [ ] **Step 3: 跑 registry+families+extract 三件全绿**(T1 中期红在此复绿——A-β7-⑦)
- [ ] **Step 4: lint + commit**(msg `test(bid-review): 批七T4——宇宙五锁 bump:105→113(❌4 面八新路径,首段 93→101,det 50/包 59);T1 skip 解除;registry subset 中期红复绿(A-β7-⑦)`)

### Task 5: golden 面(controller 直办)

**Files:**
- Create: 4 golden 案例(`L1-004-pm-qual-short.yaml`/`L1-020-subcontract-conflict.yaml`/`L1-022-format-mismatch.yaml`/`L1-026-late-submission.yaml`)
- Modify: `backend/tests/test_bid_review_golden.py`(EXPECTED_COVERAGE +4)

- [ ] **Step 1: EXPECTED_COVERAGE += 4 id**(批七注释链追加;55→59)
- [ ] **Step 2: 4 新案例**(正期望模板仿 L2-015;hyb/sem 带 model_script 仿 L1-003-performance-short;fields 手构含各规则 inputs **非 None 真实值**——bug-4227;L1-026 det 无 script)
- [ ] **Step 3: 跑 golden 全量逐条审真阳性**;CLI rc=0;题 78→82
- [ ] **Step 4: 全量门**:`pytest tests/ -k bid_review -q --continue-on-collection-errors`(并发 merge 期形态)预期 ~740p/0f
- [ ] **Step 5: commit**(msg `test(bid-review): 批七T5——golden 面兑付(A-β7-⑨ controller 直办):题 78→82 四新规则专用案例+EXPECTED_COVERAGE 55→59;家族门全绿`)
- [ ] **Step 6: 备份分支重钉** `git branch -f bid-review-batch7 <T5-commit>`

### Task 6: spec §6.1 收口 + 台账(controller 直办)

- [ ] **Step 1: spec §6.1**:❌4→**0**(批七兑付清单:pm_req→L1-004、subcontract_limit→L1-020、required_signatures→L1-007 富化、format_requirements→L1-022+L1-026;批七批注:33 字段差表全清);§4 覆盖 55/90→59/90(L1 21/29);§5 注记;P1 段批七兑付段(commit hash/裁决兑付/挂账:severity_override 机制、L1-026 方式集维、L1-004 business_items 跨引、L2-030 required_signatures 关系、bid.fields 命名空间别名、bid.submit_method、years()、keywords 精化、dict-branch 收窄)
- [ ] **Step 2: plan 勾选 + .wolf 三件 + buglog(如有)+ 最终报告**

## 中期红清单(A-β7-⑦,批六教训)

| 窗口 | 预期红 | 复绿 |
|---|---|---|
| T1 后 | registry `test_contracts_subset_universe`(8 契约未入宇宙) | T4 |
| T2 后 | golden `test_coverage_complete_marker`(pack 59 vs 题库 55) | T5 |
| T3 后 | 无(L1-007 夹具同任务补键) | — |
| T4 后 | 无(宇宙面全绿) | — |
