# bid-review P1-β批一:行乘算引擎面 + L3-019 + C-11 src 严重度覆盖 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引擎补二元乘法与容差比较,boq_rows 契约扩合价键,落地 L3-019(单价×数量=合价)与 C-11(附件行 src 覆盖严重度),账本同步。

**Architecture:** 全部改动收敛在 bid_review 扩展层:expr.py 加 `*` 算子(term 级优先层)与 `close(a,b,tol)` 内建;extract.py/registry.py 双源契约串扩 `amount`/`src` 键;rule_runner.py att_* 分支挂 src→severity 覆盖 helper;规则包 yaml 追加 L3-019。零 DB 面改动。

**Tech Stack:** Python 3.12 / pytest / PyYAML。离线可验:全部测试与 golden 均无模型调用。

**裁决记录(实现者不得擅改,有异议即 BLOCKED 上报):**

| # | 裁决 | 内容 |
|---|---|---|
| A-β1-① | 三值 UNKNOWN 传播 = need_human 通路等价 | 规格 §4.8.2 各算子「null → UNKNOWN」与仓库「缺字段/KeyError → need_human → UNKNOWN 不判通过」机制分歧、结果同构。新算子空值一律 raise KeyError 走既有 need_human 通路,**不引入三值哨兵**。回写台账 W10。 |
| A-β1-② | Decimal 两位精度缓议 | 单行乘算 float64 相对误差 ~1e-16,金额 ≤1e10 时绝对误差 ~1e-6,远小于规格 L3-019 容差 0.01;`close(a,b,0.01)` 足够。Decimal(加总链累计误差场景)挂 β批二。 |
| A-β1-③ | C-11 rg 二义取保守侧 | 规格 C-11:「rg→fatal 或 major(按法规强制程度)」。抽取层不可靠判定法规强制程度,**regulation→fatal**(L1 宁可多报取向;fatal UNKNOWN 报告降 major 展示不影响用户)。合并 issue 的 severity 取成员行映射的**最严档**。规则级 severity_override 配置后台 = P2 不做。 |
| A-β1-④ | regex/subset_of/level_ge 移 β批二 | 批一无消费规则(YAGNI);随 β批二 L2 扩展作 Task 0 引擎前奏落地。W9/L2-021 抑制联动同样移 β批二(需先建 `bid.attachment_refs` 抽取契约,appendix_references 现无编号键)。 |

**关键既有事实(实现者免重新考证):**

- expr.py 白名单:`_BIN`=lte/gte/eq/ne/lt/gt/in;`_FUNCS` 11 个;`_TOK` 已含 `*` token(:24)但仅用于 `[*]` 通配;解析链 `expr→_and→_cmp→_atom`,需在 _cmp 与 _atom 间插 `_term` 层。
- `run_det_rule` 缺字段/KeyError → need_human(:217-221/:339-340);`eval_core` 为 worker 与 golden 共用分派核。
- golden runner `_rule_pool` 只按 expect 点名 rule_id 取池(runner.py:37-40)——新规则对存量 59 题**零影响**(老夹具 boq_rows 无 amount 键 → L3-019 need_human → 不入任何池、expect_absent 只查 violation)。
- `bid.boq_rows` 已在 SECOND_STAGE_FIELDS(registry.py:67)→ 加 amount 键宇宙数不变(test_anchored_78 断言 78 不动);契约串双源 = extract.py:431 + registry.py:67。
- pack 条数硬面仅两处:yaml 包头注释(:1「39 条」)+ test_bid_review_golden.py:295 注释;`EXPECTED_COVERAGE == pack_ids == covered` 三方精确相等(:363-365)。
- CALIBRATION.md det 引擎对表有 L3-012 行先例(:82),新行同格式。
- L3 severity 白名单 {major, minor}(registry.py:31-35),L3-019 major 合法;A-BOQ 锚已注册(L3-006 evidence 先例 yaml:456)。
- L1-010 = 纵向加总链(detail→subtotal→total→大写),与 L3-019 行内乘算实体不同、不重叠(spec 主责矩阵 :956 算术归 L1 指 sum 链;L3-019 联动注记非抑制)。

---

### Task 1: expr.py — `*` 乘法算子 + `close` 容差内建

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/expr.py`
- Test: `backend/tests/test_bid_review_expr_mul_close.py`(新建)

- [ ] **Step 1: 写失败测试**

```python
"""`*` 乘法算子 + close 容差内建(P1-β批一 Task 1;裁决 A-β1-①②:空值 KeyError→need_human 通路,无三值哨兵)。"""
import pytest

from app.extensions.bid_review.engine.expr import eval_expr, validate_expr


def test_mul_basic_and_precedence():
    assert eval_expr("2 * 3 == 6") is True
    assert eval_expr("2 * 3 == 7") is False
    # * 优先级高于比较:a * b == c 解析为 (a*b)==c,不是 a==(b*c)
    assert eval_expr("close(100 * 3, 300, 0.01)") is True


def test_mul_left_assoc_chain():
    assert eval_expr("2 * 3 * 4 == 24") is True


def test_mul_close_tolerance_band():
    assert eval_expr("close(0.1 * 3, 0.3, 0.01)") is True  # float 误差 ~5.5e-17 << 0.01
    assert eval_expr("close(100.0, 100.5, 0.01)") is False


def test_wildcard_path_unaffected():
    # [*] 通配走 _atom 内部括号消费,不受 _term 层影响(回归面)
    fields = {"bid.rows": [{"amount": 1}, {"amount": 2}]}
    assert eval_expr("count(bid.rows[*].amount)", fields) == 2


def test_mul_none_coercion_keyerror():
    # A-β1-①:None/非数值 → KeyError(上层 run_det_rule 转 need_human),禁 TypeError 逃逸
    with pytest.raises(KeyError):
        eval_expr("null * 2")
    with pytest.raises(KeyError):
        eval_expr("'abc' * 2")


def test_close_bad_input_keyerror():
    with pytest.raises(KeyError):
        eval_expr("close('abc', 1, 0.01)")
    with pytest.raises(KeyError):
        eval_expr("close(1, null, 0.01)")


def test_load_time_validation_accepts_new_syntax():
    validate_expr("close(r.price * r.qty, r.amount, 0.01)")  # 不抛即过
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest tests/test_bid_review_expr_mul_close.py -q`
Expected: FAIL(parse 层 `*` 无 _term 处理/未知函数 close)

- [ ] **Step 3: expr.py 三处最小改动**

(1) `_P` 类内,`_cmp` 改为调 `_term`,新增 `_term` 方法(_cmp 与 _atom 之间):

```python
    def _cmp(self):
        n = self._term()
        while self.peek() in _BIN:
            n = (self.eat(), n, self._term())
        return n

    def _term(self):
        # 乘法项层(P1-β批一):* 结合级高于比较、低于括号;左结合链
        n = self._atom()
        while self.peek() == "*":
            self.eat()
            n = ("mul", n, self._atom())
        return n
```

(2) `_eval` 加 mul 分支(置于 `if k == "and"` 之前任意位置):

```python
    if k == "mul":
        return _mul(_eval(n[1], fields, env), _eval(n[2], fields, env))
```

(3) 模块级 helper + 内建注册(`_close` 定义放 `_BUILTIN` 之前):

```python
def _mul(a, b):
    # A-β1-①:非数值/None → KeyError(need_human 通路),禁 TypeError 逃逸(run_det_rule 只捕 KeyError)
    try:
        return float(a) * float(b)
    except (TypeError, ValueError) as exc:
        raise KeyError(f"乘法无法数值化 {a!r}*{b!r}") from exc


def _close(a, b, tol):
    # 容差比较(A-β1-②:float 误差 ~1e-6 << 0.01,Decimal 挂 β批二)
    try:
        return abs(float(a) - float(b)) <= float(tol)
    except (TypeError, ValueError) as exc:
        raise KeyError(f"close 无法数值化 {a!r}/{b!r}/{tol!r}") from exc
```

`_BUILTIN` dict 追加一项:`"close": _close,`

- [ ] **Step 4: 跑测试确认通过 + 家族回归**

Run: `uv run pytest tests/test_bid_review_expr_mul_close.py tests/test_bid_review_expr.py -q`(若既有 expr 测试文件名不同,`ls tests/ | grep expr` 定位,把既有 expr 测试一并跑)
Expected: 全 PASS(既有表达式语义零回归)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/expr.py backend/tests/test_bid_review_expr_mul_close.py
git commit -m "feat(bid-review): expr引擎乘法算子*+close容差内建——_term优先级层/空值KeyError走need_human通路(A-β1-①②);无三值哨兵"
```

注:技能内 `rules-det-subset.yaml` 为 M1 七条副本(包头注释 :1),无 `*`/close 消费者,本任务**不同步副本**(既有副本治理挂账,勿扩散范围)。

---

### Task 2: boq_rows 契约扩 `amount` 合价键

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py:431-432`(FIELD_TYPE_CONTRACTS)
- Modify: `backend/app/extensions/bid_review/engine/registry.py:67-68`(SECOND_STAGE_FIELDS)
- Modify: `backend/app/extensions/bid_review/engine/extract.py:510` 附近(normalize_boq_rows)
- Test: `backend/tests/test_bid_review_extract.py`(追加)

- [ ] **Step 1: 写失败测试**(追加到既有 boq normalize 测试所在文件;先 `grep -n "normalize_boq_rows" tests/test_bid_review_extract.py` 定位既有用例组,紧随其后追加)

```python
def test_normalize_boq_rows_amount_field():
    rows = _norm_boq([{"id": "B1", "name": "x", "unit": "m3", "qty": 3, "price": 100, "amount": "300.50"}])
    assert rows[0]["amount"] == 300.5  # 字符串数值化
    rows2 = _norm_boq([{"id": "B2", "name": "y", "unit": "项", "qty": None, "price": None, "amount": None}, {"id": "B3", "name": "z"}])
    assert rows2[0]["amount"] is None and rows2[1]["amount"] is None  # null 保 null;缺键保 None
    assert all(isinstance(r["amount"], (int, float)) or r["amount"] is None for r in rows + rows2)


def test_boq_rows_contract_has_amount():
    from app.extensions.bid_review.engine.extract import FIELD_TYPE_CONTRACTS
    from app.extensions.bid_review.engine.registry import SECOND_STAGE_FIELDS
    assert "amount" in FIELD_TYPE_CONTRACTS["bid.boq_rows"]
    assert "amount" in SECOND_STAGE_FIELDS["bid.boq_rows"]
```

(导入别名 `_norm_boq` 按该文件既有导入习惯改;若 normalize 测试在不同文件,测试放同文件。)

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_bid_review_extract.py -k amount -q`
Expected: FAIL(KeyError 'amount' / 断言 in 失败)

- [ ] **Step 3: 双源契约串 + normalize 改动**

extract.py FIELD_TYPE_CONTRACTS(整串替换,保持句式):

```python
FIELD_TYPE_CONTRACTS["bid.boq_rows"] = (
    '[{"id":"清单项编号","name":"项目名称","unit":"单位","qty":数量或null,"price":单价或null,"amount":合价金额或null}] 对象列表;'
    "逐行一项,从投标报价清单逐行提取;清单没有的行不编造;数量单价合价只引用原文数字;required 由服务端按招标 BOQ codes 回填,模型禁报"
)
```

registry.py SECOND_STAGE_FIELDS 同步(:67-68 整串替换,保留 required 注记句):

```python
    "bid.boq_rows": '清单行级(M3,spec §5):[{id:"清单项编号",name:"项目名称",unit:"单位",qty:数量或null,price:单价或null,amount:合价金额或null}] 对象列表;'
    "逐行一项,从投标报价清单逐行提取;清单没有的行不编造;数量单价合价只引用原文数字;required 由服务端按招标 BOQ codes 回填,模型禁报",
```

normalize_boq_rows(:510 附近,qty/price 行旁追加一行,复用 `_num`):

```python
                "amount": _num(row.get("amount")),
```

- [ ] **Step 4: 跑测试确认通过 + prompt 契约传播验证**

Run: `uv run pytest tests/test_bid_review_extract.py tests/test_bid_review_worker_prod_model.py tests/test_bid_review_registry.py -q`
Expected: 全 PASS(prompt 从 FIELD_TYPE_CONTRACTS 渲染自动携带 amount;宇宙 78 不变;SECOND_STAGE_FIELDS 集合断言不变)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/app/extensions/bid_review/engine/registry.py backend/tests/test_bid_review_extract.py
git commit -m "feat(bid-review): boq_rows契约扩amount合价键——extract/registry双源同步+normalize数值化;宇宙78不变,旧线程存量字段缺amount走need_human诚实降级"
```

---

### Task 3: L3-019 单价×数量=合价 规则 + golden + CALIBRATION

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(L3 段尾追加规则 + 包头注释 :1)
- Create: `backend/app/extensions/bid_review/golden/cases/L3-019-price-qty-amount.yaml`
- Modify: `backend/tests/test_bid_review_golden.py:295-297`(注释 + EXPECTED_COVERAGE)
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`(det 引擎对表追加行)

- [ ] **Step 1: golden case 先行(失败态)**

创建 `golden/cases/L3-019-price-qty-amount.yaml`:

```yaml
case: L3-019-price-qty-amount
desc: 行 BOQ-02 单价×数量(100×3=300)与合价 250 不一致 → violation;BOQ-01 乘算相符与 BOQ-03 缺分量行均跳过
fields:
  bid.boq_rows:
    - {id: BOQ-01, name: 土方开挖, unit: m3, qty: 10, price: 50, amount: 500}
    - {id: BOQ-02, name: 混凝土浇筑, unit: m3, qty: 3, price: 100, amount: 250}
    - {id: BOQ-03, name: 费率项, unit: 项, qty: null, price: null, amount: null}
expect_issues:
  - rule_id: L3-019
    severity: major
    contains: ["BOQ-02", "单价×数量与合价不一致"]
expect_absent: []
strict: false
```

- [ ] **Step 2: yaml 规则(L3 段尾,L3-026 之后追加;包头注释 :1 `39 条`→`40 条`)**

```yaml
  - id: L3-019
    name: 清单行单价×数量=合价
    layer: L3
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.boq_rows]
    # P1-β批一(spec L3-019 :891,容差≤0.01):行内乘算;任一分量 null 跳过(费率行/未填
    # 合价合法,不误报);全分量齐且乘算超差才 violation;与 L1-010 不重叠(纵向加总链 vs
    # 行内乘算,实体不同);存量线程字段缺 amount 键 → KeyError → need_human 诚实降级
    check:
      op: all
      target: bid.boq_rows
      var: r
      cond: "r.price == null or r.qty == null or r.amount == null or close(r.price * r.qty, r.amount, 0.01)"
    severity: major
    evidence: [A-BOQ]
    message_tpl: "清单项 {r.id} 单价×数量与合价不一致:{r.price:money}×{r.qty} ≠ {r.amount:money}"
    fix_tpl: "逐行复核报价清单单价、数量与合价的乘算关系,修正算术错误"
    confidence_gate: 1.0
    enabled: true
```

- [ ] **Step 3: 覆盖率三方精确相等更新(test_bid_review_golden.py)**

:295 注释改为:`# 批C 起覆盖率翻全集(L1 17 + L2 6 + L3 17 = pack 40 条精确相等;P1-β批一 +L3-019 行乘算 2026-11-06)`;
EXPECTED_COVERAGE 集合内按序插入 `"L3-019",`。

- [ ] **Step 4: CALIBRATION.md det 引擎对表追加一行(仿 :82 L3-012 行格式)**

```markdown
| L3-019-price-qty-amount | 引擎对 | 行乘算 close 容差 0.01;任一分量 null 行跳过;与 L1-010 纵向加总链不重叠 |
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_registry.py tests/test_bid_review_rule_runner.py -q`
Expected: 全 PASS(golden 60 题 60/60;`EXPECTED_COVERAGE == pack_ids == covered`;lint severity L3 major 合法;A-BOQ 锚已注册)

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/golden/cases/L3-019-price-qty-amount.yaml backend/tests/test_bid_review_golden.py backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L3-019单价×数量=合价落地——det行内乘算close容差0.01/缺分量行跳过;golden 60题+EXPECTED_COVERAGE三方精确相等+CALIBRATION记档;包40条"
```

---

### Task 4: C-11 附件行 src 覆盖严重度

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py:51-56`(attachment_requirements 契约)
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(att_* 分支)
- Test: `backend/tests/test_bid_review_c11_severity.py`(新建)

- [ ] **Step 1: 写失败测试**

```python
"""C-11 src→severity 覆盖(P1-β批一 Task 4;裁决 A-β1-③:rg→fatal 保守侧,合并 issue 取成员行最严档,未知/空 src 不覆盖)。"""
from app.extensions.bid_review.engine.rule_runner import Rule, load_rulepack, run_det_rule

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml"


def _att_rule():
    pack = load_rulepack(PACK)
    return next(r for r in pack.rules if r.check.get("op") == "att_check")


def _fields(reqs):
    return {"tender.attachment_requirements": reqs, "bid.attachments": [], "bid.attachment_index": []}


def test_src_tender_mandatory_overrides_to_fatal():
    reqs = [{"no": "A1", "name": "营业执照", "src": "tender_mandatory"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "violation"]
    assert miss and miss[0]["severity"] == "fatal"


def test_empty_src_keeps_rule_default():
    reqs = [{"no": "A2", "name": "业绩合同", "src": ""}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "violation"]
    assert miss and miss[0]["severity"] == _att_rule().severity  # 缺省不覆盖,golden 存量零回归


def test_unknown_src_keeps_rule_default():
    reqs = [{"no": "A3", "name": "x", "src": "whatever"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "violation"]
    assert miss and miss[0]["severity"] == _att_rule().severity


def test_mixed_rows_take_strictest():
    reqs = [{"no": "A4", "name": "a", "src": "internal_template"}, {"no": "A5", "name": "b", "src": "tender_mandatory"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "violation"]
    assert miss and miss[0]["severity"] == "fatal"  # 合并 issue 取 max


def test_regulation_maps_fatal_conservative():
    reqs = [{"no": "A6", "name": "x", "src": "regulation"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "violation"]
    assert miss and miss[0]["severity"] == "fatal"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_bid_review_c11_severity.py -q`
Expected: FAIL(severity 恒为规则默认)

- [ ] **Step 3: extract.py 契约扩 src 键(:51-56 整串替换)**

```python
FIELD_TYPE_CONTRACTS["tender.attachment_requirements"] = (
    '[{no:"附件编号或空串", name:"附件名称", clause:"要求出处条款号", '
    'mandatory:"★|必需|建议", min_count:最少份数数字或null, year_span:年份数字或null, '
    'src:"要求来源或空串:★/必需条款=tender_mandatory;招标一般要求=tender_required;'
    '法规强制材料(如资格审查法定件)=regulation;企业模板惯例件=internal_template;逻辑必要件=logical_necessary"}]。'
    "只从招标文件的投标文件组成/格式条款及资格审查条款逐条抄录附件要求,禁止编造;无编号填空串;无法判定来源时 src 填空串。"
)
```

- [ ] **Step 4: rule_runner.py 覆盖 helper + 三分支接线**

模块级(`_entity_key` 之前)新增:

```python
# C-11 附件要求行 src→severity 覆盖(spec :862-867,EAI-CUSTOM P1-β批一;裁决 A-β1-③:
# regulation 二义按保守侧 fatal;多行合并 issue 取映射最严档;未知/空 src 行不参与覆盖
# ——缺省=规则默认,golden 存量夹具(无 src)零回归)。
_SRC_SEVERITY = {"tender_mandatory": "fatal", "tender_required": "major", "regulation": "fatal", "internal_template": "minor", "logical_necessary": "major"}
_SEVERITY_ORDER = ["info", "minor", "major", "fatal"]


def _src_severity(rows, default: str) -> str:
    mapped = [_SRC_SEVERITY[str(r.get("src") or "").strip()] for r in rows or [] if str(r.get("src") or "").strip() in _SRC_SEVERITY]
    return max(mapped, key=_SEVERITY_ORDER.index) if mapped else default
```

att_check MISSING 分支(:257-260)在 `iss["entity_keys"] = ...` 后追加一行:

```python
                        iss["severity"] = _src_severity([r["req"] for r in miss], rule.severity)
```

att_count PARTIAL 分支(:326-332)同位置追加:

```python
                        iss["severity"] = _src_severity([r["req"] for r in partial], rule.severity)
```

att_missing_rows 候选分支(:314-322)循环内 `iss["entity_keys"] = ...` 后追加(逐行候选,单行覆盖):

```python
                        iss["severity"] = _src_severity([r["req"]], rule.severity)
```

注:`_need_human` 产物**不覆盖**(成员严重度未知,保守留规则默认)。

- [ ] **Step 5: 跑测试确认通过 + 附件系回归**

Run: `uv run pytest tests/test_bid_review_c11_severity.py tests/test_bid_review_attachments.py tests/test_bid_review_rule_runner.py tests/test_bid_review_worker.py -q`(若附件测试文件名不同,`ls tests/ | grep att` 定位一并跑)
Expected: 全 PASS(存量夹具无 src → 零回归)

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_c11_severity.py
git commit -m "feat(bid-review): C-11附件行src覆盖严重度——五枚举映射/合并issue取最严档/rg保守侧fatal(A-β1-③);空src零回归;att三分支接线"
```

---

### Task 5: 账本同步 + 全量验收

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`
- Modify: `.wolf/buglog.json`(如有修复)/ `.wolf/memory.md`(会话记档,controller 负责)

- [ ] **Step 1: 台账五处刷新**

1. §2 矩阵 §4 行:覆盖数 `39/90` → `40/90`(L3 17/25);§5 行:算子注记「24 算子(实装 3)」→「实装 5(lte/gte/eq + mul/close,批一)」。
2. §3.2 表追加 W10 行:`| W10 | 规格 §4.8.2 算子空值行为「null→UNKNOWN」三值传播 | 仓库 KeyError→need_human→UNKNOWN 不判通过,机制分歧结果同构 | 维持仓库机制(无哨兵);规格侧回写候选 |`。
3. §3.3 C-11 行 → `已兑付(2026-11-06 P1-β批一:src 五枚举覆盖+合并最严档+rg 保守 fatal;规则级 severity_override 配置后台=P2)`。
4. §4 表:L3 行实有 `16/25` → `17/25`,待建清单移除 `-019 单价×数量(需乘法算子)`;表达式引擎配套缺口段改写:`~~乘法~~/~~容差比较~~ 已兑付(close 代 Decimal,裁决 A-β1-②);regex/subset_of/level_ge/or(check-op 层)/三值传播(W10 等价裁决)/Decimal(加总链) → β批二`。
5. §6 P1 行追加:「批一(2026-11-06)兑付:乘算引擎+L3-019+C-11 src 覆盖;批二=L2 要件/文件级包+L4+regex/subset_of/level_ge+L2-021/W9 抑制联动;批三=verdict 值域五值迁」。

- [ ] **Step 2: 全量验证**

Run: `uv run pytest tests/ -k bid_review -q`
Expected: 全绿(预期 600+ passed,新增 ~15 测试),0 fail

Run: `uv run pytest tests/test_bid_review_golden.py -q`
Expected: 60/60

- [ ] **Step 3: Commit**

```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): β批一账本同步——覆盖40/90+W10三值等价裁决+C-11兑付标注+表达式缺口改写+批次划分注记"
```

---

## 验收门(全任务完成判据)

1. `uv run pytest tests/ -k bid_review -q` 全绿,零 fail 零新 skip;
2. golden 60 题 60/60;`EXPECTED_COVERAGE == pack_ids == covered` 三方相等;
3. 宇宙断言 78 不动(test_anchored_78);SECOND_STAGE_FIELDS 集合不变;
4. 五 commit 链,每任务独立可回退;docs/superpowers 记得 `-f`;
5. 四条裁决 A-β1-①~④ 未被实现者擅改(有异议 BLOCKED 上报,不得自行变更语义)。

## 范围红线(本批不做)

- verdict 值域五值迁(PASS/FAIL/UNKNOWN/ERROR/SKIP)→ β批三(59 题冻结面迁移,独立批);
- L2 要件/文件级规则包、L4 十条、L2-021+W9 抑制联动、regex/subset_of/level_ge → β批二;
- 规则级 severity_override 配置后台 → P2;
- eval_det.py 技能副本同步(无消费者,既有挂账)。
