# R2+ 规则族补齐(M1-M5 悬空字段接入规则消费)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 4 条 deterministic 规则(L2-022/L2-023/L3-019/L3-020),消费 M1-M5 落地后零规则消费的七个字段路径中的五个(tender.required_fields+bid.boq_rows / bid.attachments / bid.performance_groups / bid.section_tree),零引擎/求值器/golden/universe 改动。

**Architecture:** 纯 yaml 追加(1.0.0.yaml 就地,L2 家族先例)+ 新测试文件。DSL 既有算子已够(`!=`/`or`/null 字面量/`op:all` 逐行 issue),零 expr.py/rule_runner.py 改动。零翻红论证(取证定案):golden 55 个案 fields 无第二段键 → 新规则 inputs 缺失 → `_need_human`(verdict=need_human≠violation)→ strict 案不炸(strict 只数期望外 violation);smoke stub 无第二段键同;universe 77 不变(inputs ⊆ 既有宇宙)。

**Tech Stack:** Python 3.12, pytest, ruff;改动面=1 个 yaml + 1 个新测试文件 + 1 处既有计数断言。

**Spec:** docs/superpowers/specs/2026-11-04-bid-review-extract-engine-b-design.md §7 挂账「L1/L3 规则包扩族(设计稿尾②)——独立队列」;消费缺口取证:registry.consumed_by 实测 bid.attachments/bid.section_tree/bid.boq_rows/bid.table_cells/bid.performance_entries/bid.performance_groups/tender.required_fields 七路径 rules 全空(2026-11-05)。

---

## 七裁决(2026-11-05,取证后定案)

1. **纯 det 追加,零引擎改动**(裁决基座):DSL 白名单已含 `!=`/`or`/`null` 字面量/`op:all`(target/var/cond 逐行 issue,行 dict 入 env,message 可渲染 var 属性——L3-006 先例);dedup_key=`{rule_id}|-|{msg[:40]}` 消息含行号/组号/标题→逐行天然不撞(L3-006 同款)。expr.py/rule_runner.py/eval_core.py/golden/tuning.yaml/fingerprints 全不动。
2. **四规则定案**(null 安全统一用「!= True」形态:operator.ne 下仅值恰为 True 时判 False,False 与 None 双双通过):
   - **L2-022 必填清单行未报价**(消费 tender.required_fields+bid.boq_rows):`cond: "r.required != True or r.price != null"`,severity **fatal**(未对必填项报价=废标级,与 L2-020 fatal 同向;**qty 不判**——费率/总价行无数量合法,单价缺失才是无歧义违例);消息含行号+名称。
   - **L2-023 附件实体内容空白**(消费 bid.attachments):`cond: "a.is_empty_text != True"`,severity **major**(文本量启发是近似,图表型章节/扫描件可能误标,人工裁决兜底)。
   - **L3-019 业绩条目聚类存疑**(消费 bid.performance_groups):`cond: "g.ok != False"`,severity **major**——M4「ok=false→UNKNOWN 人工,禁强行 PARTIAL」的规则面:UNKNOWN 必须在 issue 流可见,不得被误读为通过(对齐审计病灶精神)。
   - **L3-020 章节正文空缺**(消费 bid.section_tree):`cond: "s.is_empty != True"`,severity **major**(同②近似性理由)。
3. **ID 编号**:L2-022/023 用 EAI 家族空闲号(L2 编号本就 EAI-native,P1/P2 切片自建);L3-019/020 **越过素材④未转录空洞**(015/017),取连续高位防未来上游转录碰撞;四条全部 `EAI-CUSTOM` 注释(eai-custom 铁律)。
4. **缺行不判**:必填行完全缺席(tender required code 无对应 bid 行)= L1-011 set_eq(boq_items)领域,L2-022 不重复报告——boq_rows 只含在场行,负空间不可见;单关注点纪律。
5. **零翻红铁律**(取证定案,2026-11-05):golden runner strict 只数「期望外 **violation**」,expect_absent 只查 violation;新规则在旧基线(无第二段字段)全落 need_human → golden 55 零翻红;universe 仍 77(test_anchored_77 锁不动);materials_hash/M0 26/26 零触碰。新增保险测试:evaluate_fields 在首段-only 字段上断言新四规则零 violation 全 need_human。
6. **计数锁显式更新**(bug-4018 教训先 grep):test_full_pack_loads det 29→33(L1 det 14 + L3 det 15 + L2 det 4),hyb 5/sem 1 不变;全测试面 grep 确认无其他 det/hyb 计数锁;rules_total 39 生产面无测试锁数值(summary 断言全为 None 或子集)。
7. **消费缺口收口口径**:七悬空路径中五个本轮接入;**bid.table_cells 保持临时契约挂账**(单元格=原始数据,无自然 det 语义,消费待 hyb 场景定契约);**bid.performance_entries 经 groups.members 间接消费**(直接消费规则如金额比对挂账 R2+);M5 页偏移进 verify gate 仍挂账(动既有语义翻 golden,非本切片)。

---

### Task 1: 计划预提交

- [ ] **Step 1:** `git add -f docs/superpowers/plans/2026-11-05-bid-review-r2-rule-families-plan.md && git commit -m "docs(bid-review): R2+规则族补齐计划——四条det规则消费M1-M5悬空字段七裁决"`

### Task 2: 失败测试(新文件 tests/test_bid_review_rule_families.py)

**Files:** tests/test_bid_review_rule_families.py(新建;先红——pack 无 L2-022 等规则,`pack_rules[...]` KeyError)

- [ ] **Step 1: 写失败测试**

```python
"""R2+ 规则族补齐测试(2026-11-05):四条 det 规则消费 M1-M5 悬空字段。

零翻红取证(plan 裁决⑤):golden 55 个案无第二段字段→新规则 need_human→
strict 只数 violation→零翻红;本文件 test_new_rules_need_human_on_legacy_baseline
是该论证的常驻回归锁。
"""

import SimpleNamespace  # noqa: F401  (实际从 types 导入)
from pathlib import Path

from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.registry import consumed_by, lint_rules, universe
from app.extensions.bid_review.engine.rule_runner import load_rulepack

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")

NEW_IDS = {"L2-022", "L2-023", "L3-019", "L3-020"}


def _rules():
    return {r.id: r for r in load_rulepack(PACK).rules}


class TestL2022RequiredRowPrice:
    def test_required_row_missing_price_violation(self):
        rule = _rules()["L2-022"]
        fields = {
            "tender.required_fields": ["BOQ-1", "BOQ-2"],
            "bid.boq_rows": [
                {"id": "BOQ-1", "name": "设备采购", "unit": "套", "qty": 2, "price": None, "required": True},
                {"id": "BOQ-2", "name": "安装费", "unit": "项", "qty": 1, "price": 5000, "required": True},
                {"id": "X-9", "name": "自附行", "unit": "批", "qty": 1, "price": None, "required": False},
            ],
        }
        issues = run_det_rule_imported(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "fatal"
        assert "BOQ-1" in issues[0]["message"] and "设备采购" in issues[0]["message"]

    def test_pass_and_missing_inputs(self):
        rule = _rules()["L2-022"]
        ok = {"tender.required_fields": ["B1"], "bid.boq_rows": [{"id": "B1", "name": "x", "unit": "", "qty": 1, "price": 9.9, "required": True}]}
        assert run_det_rule_imported(rule, ok) == []
        assert run_det_rule_imported(rule, {"tender.required_fields": ["B1"]})[0]["verdict"] == "need_human"


class TestL2023BlankAttachment:
    def test_blank_and_pass(self):
        rule = _rules()["L2-023"]
        fields = {"bid.attachments": [
            {"no": "A", "name": "营业执照", "norm_name": "营业执照", "pages": [1, 2], "type_fingerprint": "license", "fingerprint_conf": 0.9, "is_empty_text": True, "anchor": {}},
            {"no": "B", "name": "业绩合同", "norm_name": "业绩合同", "pages": [3, 9], "type_fingerprint": "contract", "fingerprint_conf": 0.8, "is_empty_text": False, "anchor": {}},
        ]}
        issues = run_det_rule_imported(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "营业执照" in issues[0]["message"]
        assert run_det_rule_imported(rule, {"bid.attachments": [dict(fields["bid.attachments"][0], is_empty_text=None)]}) == []

    def test_missing_input_need_human(self):
        assert run_det_rule_imported(_rules()["L2-023"], {})[0]["verdict"] == "need_human"


class TestL3019ClusterUnsure:
    def test_ok_false_group_violation(self):
        rule = _rules()["L3-019"]
        fields = {"bid.performance_groups": [
            {"group_id": "G1", "ok": False, "members": [{"name": "一期", "client": "甲"}]},
            {"group_id": "G2", "ok": True, "members": [{"name": "二期", "client": "乙"}]},
        ]}
        issues = run_det_rule_imported(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "G1" in issues[0]["message"]

    def test_all_ok_or_missing(self):
        rule = _rules()["L3-019"]
        assert run_det_rule_imported(rule, {"bid.performance_groups": [{"group_id": "G1", "ok": True, "members": []}]}) == []
        assert run_det_rule_imported(rule, {})[0]["verdict"] == "need_human"


class TestL3020EmptySection:
    def test_empty_section_violation(self):
        rule = _rules()["L3-020"]
        fields = {"bid.section_tree": [
            {"code": "3", "title": "施工组织设计", "toc_page": 3, "body_page": 20, "is_empty": True, "offset": 17, "offset_flag": True},
            {"code": "4", "title": "质量管理", "toc_page": 30, "body_page": 40, "is_empty": False, "offset": 10, "offset_flag": True},
            {"code": "5", "title": "安全文明", "toc_page": 50, "body_page": None, "is_empty": None, "offset": None, "offset_flag": None},
        ]}
        issues = run_det_rule_imported(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "施工组织设计" in issues[0]["message"]
        assert run_det_rule_imported(rule, {}) [0]["verdict"] == "need_human"


class TestGoldenFaceInsurance:
    """裁决⑤常驻锁:首段-only 基线上新四规则零 violation 全 need_human(golden 55 零翻红的机理)。"""

    async def test_new_rules_need_human_on_legacy_baseline(self):
        from types import SimpleNamespace

        pack = load_rulepack(PACK)
        quiet = json.dumps({"verdicts": [{"clause_id": "quiet", "verdict": "full", "confidence": 1.0, "reason": "安静", "evidence": []}]}, ensure_ascii=False)
        model_fn = wrap_model_fn(lambda messages: SimpleNamespace(content=quiet))
        fields = {"bid.total_price": 100.0, "tender.max_price": 200.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
        issues = await evaluate_fields(pack, fields, model_fn=model_fn)
        new = [i for i in issues if i["rule_id"] in NEW_IDS]
        assert len(new) == 4 and all(i["verdict"] == "need_human" for i in new), f"新规则旧基线必须 need_human: {new}"


class TestFamilyWiring:
    def test_universe_unchanged_and_consumption_wired(self):
        assert len(universe()) == 77  # inputs ⊆ 既有宇宙,零宇宙churn(test_anchored_77 同锁)
        for path in ("tender.required_fields", "bid.boq_rows", "bid.attachments", "bid.performance_groups", "bid.section_tree"):
            assert consumed_by(path)["rules"], f"{path} 仍零规则消费"
        assert not consumed_by("bid.table_cells")["rules"]  # 临时契约挂账不动(裁决⑦)

    def test_real_pack_lint_clean(self):
        pack = load_rulepack(PACK)
        assert lint_rules(pack.rules) == []
```

(实现时:`run_det_rule_imported` 即 `from app.extensions.bid_review.engine.rule_runner import run_det_rule` 的直名;`json`/`run_det_rule` 正常 import;`SimpleNamespace` 顶部一行误写实现时收进测试函数内——以实际 ruff 通过为准。)

- [ ] **Step 2: 跑红** `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_families.py -q`(KeyError 红)

### Task 3: yaml 追加四规则(1.0.0.yaml 就地)

**Files:** app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml

- [ ] **Step 1: 追加**(文件尾,四条全带 EAI-CUSTOM 注释)

```yaml
  # ── R2+ 规则族补齐(EAI-CUSTOM 2026-11-05,plan 2026-11-05-bid-review-r2-rule-families):
  # 四条 det 消费 M1-M5 悬空字段(取证:registry.consumed_by 七路径 rules 全空)。
  # null 安全统一「!= True」形态:仅值恰为 True 时判 False,False/None 双双通过。
  # ID: L2 家族 EAI-native 空闲号;L3-019/020 越过素材④未转录空洞(015/017)防碰撞。
  - id: L2-022
    name: 必填清单行未报价
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.required_fields, bid.boq_rows]
    # required 服务端按 tender.required_fields 回填(M3 铁律:必填口径唯一来自招标侧);
    # 只判单价缺失(费率行无数量合法,qty 不判);必填行完全缺席=L1-011 set_eq 领域不重复报告。
    check:
      op: all
      target: bid.boq_rows
      var: r
      cond: "r.required != True or r.price != null"
    severity: fatal
    evidence: [A-TENDER-BOQ, A-BOQ]
    message_tpl: "必填清单行 {r.id}({r.name})未报单价,需按招标清单补报"
    fix_tpl: "按招标清单逐项核对必填行报价,缺价行补齐单价与合价"
    confidence_gate: 1.0
    enabled: true
  - id: L2-023
    name: 附件实体内容空白
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.attachments]
    # is_empty_text=M1 文本量启发近似(图表型可能误标)→ major 人工裁决兜底,不判 fatal。
    check:
      op: all
      target: bid.attachments
      var: a
      cond: "a.is_empty_text != True"
    severity: major
    evidence: [A-BID-DOC]
    message_tpl: "附件「{a.name}」内容为空(疑似空白/无效扫描件),需补有效文件"
    fix_tpl: "核对该附件扫描件,空白或无效的重新扫描上传有效版本"
    confidence_gate: 1.0
    enabled: true
  - id: L3-019
    name: 业绩条目聚类存疑
    layer: L3
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.performance_groups]
    # M4 UNKNOWN 语义的规则面:ok=false(疑似同项待人工,禁强行 PARTIAL)必须在 issue 流可见,
    # 不得被误读为通过;组员明细在 payload.bid.performance_groups 可查,消息只点名组号。
    check:
      op: all
      target: bid.performance_groups
      var: g
      cond: "g.ok != False"
    severity: major
    evidence: [A-PERF-DOCS]
    message_tpl: "类似业绩条目组 {g.group_id} 疑似同项重复,需人工确认是否重复凑数"
    fix_tpl: "人工核对该组业绩条目,重复的删除或更正为不同项目业绩"
    confidence_gate: 1.0
    enabled: true
  - id: L3-020
    name: 章节正文空缺
    layer: L3
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.section_tree]
    # is_empty=M2 文本量启发近似(图表型章节可能误标)→ major 人工裁决兜底。
    check:
      op: all
      target: bid.section_tree
      var: s
      cond: "s.is_empty != True"
    severity: major
    evidence: [A-TOC, A-MAIN-TEXT]
    message_tpl: "章节「{s.title}」正文内容为空或过简,需补全章节内容"
    fix_tpl: "补齐该章节实质性内容,空章节在评标中可能被认定未实质响应"
    confidence_gate: 1.0
    enabled: true
```

- [ ] **Step 2: 跑绿** Task 2 测试全绿

### Task 4: 计数锁显式更新(test_full_pack_loads)

**Files:** tests/test_bid_review_rule_runner.py

- [ ] **Step 0(先 grep,bug-4018 教训):** `grep -rn "deterministic\|hybrid" tests/test_bid_review*.py | grep -i "len\|== 29\|== 5\|== 1"` 确认仅此一处计数锁
- [ ] **Step 1:** det 断言 29→33,注释更新为「L1 det 14 + L3 det 13+2(L3-019/020 R2+ 规则族)+ L2 det 2+2(L2-020/024+L2-022/023 R2+ 规则族)= 33」;hyb 5/sem 1 断言与注释不动
- [ ] **Step 2:** 该文件测试全绿

### Task 5: 全量验证

- [ ] **Step 1:** `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(后台;期望 538+~9 新增全绿;golden 55 零翻红+M0 26/26 含在全家)
- [ ] **Step 2:** ruff check --fix + format 改动文件→重跑受影响测试

### Task 6: 收官

- [ ] **Step 1:** push 重试至 `0\t0`
- [ ] **Step 2:** wolf(memory/buglog 若 bug)+ anatomy(yaml/新测试文件条目注记)+ plan 勾选 docs commit(`git add -f`)
- [ ] **Step 3:** auto-memory `bid-review-r2-rule-families-landed.md` + MEMORY.md 索引;终报+队列下一项+「继续」

### 挂账(显式)

- bid.table_cells 临时契约:等首个 hyb 消费场景定契约(裁决⑦)
- bid.performance_entries 直接消费规则(如业绩金额 vs 总价一致性)挂账
- M5 页偏移注记进 verify gate(动既有语义翻 golden,独立切片)
- golden 增题覆盖新四规则(不破 55 锁的前提下扩 59+,可选)
- 素材④全量规则包可达后对账(015/017 空洞语义)
