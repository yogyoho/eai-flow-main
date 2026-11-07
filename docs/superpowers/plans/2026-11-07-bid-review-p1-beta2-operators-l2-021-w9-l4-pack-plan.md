# bid-review P1-β批二 实施计划——引擎四算子 + W11 迁移 + Decimal 加总链 + L2-021/W9 抑制联动 + L4 独立包

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** β批二落地:表达式引擎补 `or`(check-op 层)/`regex`/`subset_of`/`level_ge`/`col` 五件套、Decimal 加总链、L2-021 附件编号引用规则 + W9 抑制联动 + 去重键、L1-021→L2-031 迁移改名(W11)、L4 竞争力包结构落地(离线态);规则覆盖 40/90 → 41/90,宇宙 78 不变。

**Architecture:** 引擎先行的同一打法:算子面与迁移不动抽取面;L2-021 复用 bid.appendix_references 路径扩 `no` 键(宇宙不变);抑制联动落 eval_core 聚合后单插入位;L4 走独立包目录(registry 只 glob bid-review-core,零 live 扰动),activation 全挂批二续。

**Tech Stack:** Python 3.12 / pytest / uv / 既有 rulepack YAML schema。

**工作目录:** 全部命令在 `D:\eai\eai-flow-main\backend` 下执行;pytest 必须带 `tests/` 路径(`uv run pytest tests/ ...`)。基线:全家 `uv run pytest tests/ -k bid_review -q` = **628 passed, 6 skipped**(T2 时点实测=已提交树 627 + 并发会话未提交测试 1;前值 618/624/596 均为各时点陈旧口径,详见 T2 评审分解);golden CLI 60 题;宇宙 78;包 40 条(det 34 + hyb 5 + sem 1)。

---

## 裁决(锁死;实现者不得擅改语义,异议 BLOCKED 上报)

- **A-β2-①(W10 等价延伸)**:新算子 null/未知值一律 KeyError→need_human 通路,无三值哨兵(W10 裁决同构:机制分歧结果同构)。
- **A-β2-②(level 阶梯)**:`_LEVEL_LADDER` 为 expr 模块常量,保守集合(常见资质等级);外置挂账——出现第二消费者或真实资质数据时迁 tuning 式外置。
- **A-β2-③(L4 severity 映射)**:critical→major、high→major、medium→minor、info→info;lint 拒 L4 fatal(C.1.4);`gate_effect` 字段不建——L4 不入门禁以「worker 不接线本包」兑付,激活任务再落显式过滤(记档)。
- **A-β2-④(L4 输入路径命名)**:已有 repo 路径用 repo 名(bid.warranty_period/bid.duration_main_text/tender.substantive_clauses/tender.scoring_items/bid.table_cells/bid.total_price/bid.device_models/bid.personnel_technical/bid.personnel_commercial);无 repo 路径的用规格名(bid.service_commitments/bid.full_text/bid.response_sections/bid.figures/bid.staff/bid.equipment/bid.schedule_milestones/bid.section_for_score/tender.clauses)——批二续契约以同名落地,卡注释记 spec 等价 alias。
- **A-β2-⑤(L4 激活面)**:worker 多包接线/advisory 独立分节/gate 排除/L4 不计正式问题数 = 批二续任务;本批 worker.py/routers.py 零改动。
- **A-β2-⑥(L2-031 兑付=W11 迁移)**:L1-021→L2-031 纯改名(W1-W5 先例:改名不改 check);现 check 仅声明函存在性=规格 L2-031 语义的声明函半边;签署维度(L1-021 真语义)与承诺函清单挂账签署态/承诺函清单抽取面。旧 L1-021 DB override 键=孤儿 no-op(check 未变无语义翻转),键清理挂账。
- **A-β2-⑦(抑制形态)**:L3-012 折叠=从 issues 移除并打 `suppressed_by: "L2-021"` 内标(审计可查);dedup_key=repo 形态 `{layer}|{rule_id}|{entity}`(spec 4.7.4 category 映射挂账 C.1.5 lint 未建)。
- **A-β2-⑧(golden 冻结面)**:L4 golden 题入独立目录 `golden/cases-l4/`,主 CLI 60 题冻结面不动。

**范围红线(本批不做→批二续)**:文件级 L2-001~004/050/051(需 tender.file_composition/bid.file_index 等 9 条新路径)、要件级 L2-030/032/033(需 signature_slots/三件套/deposit_receipt 路径)、L4 激活面(A-β2-⑤)、L2 章节级/字段级/复合(-010~014/-040/-042/-043/-025)、or 之外的其他 check-op(neq/gt/lt/in 结构级——表达式级已覆盖,YAGNI)、spec 4.7.5 全量去重引擎。

---

### Task 1: expr/check-op 五件套——`or`(check-op 层)+ `regex` + `subset_of` + `level_ge` + `col`

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/expr.py`(_FUNCS/_BUILTIN + 新函数 + `_LEVEL_LADDER`)
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(_KNOWN_OPS + or 分支 + 校验键)
- Test: `backend/tests/test_bid_review_expr_operators2.py`(新建)

- [ ] **Step 1: 写失败测试** `backend/tests/test_bid_review_expr_operators2.py`

```python
"""P1-β批二 T1:or(check-op 层)/regex/subset_of/level_ge/col(A-β2-①:null/未知一律 KeyError→need_human,无哨兵;A-β2-②:阶梯常量保守集)。"""
import pytest

from app.extensions.bid_review.engine.expr import eval_expr
from app.extensions.bid_review.engine.rule_runner import Rule, load_rulepack

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml"


def test_or_check_op_branch():
    from app.extensions.bid_review.engine.rule_runner import Rule, run_det_rule

    rule = Rule(id="T-OR", name="t", layer="L3", type="deterministic", applies_to=["*"], inputs=["bid.warranty_period"],
                check={"op": "or", "any": ["bid.warranty_period == null", "bid.warranty_period >= 12"]},
                severity="minor", evidence=[], message_tpl="or 未满足", enabled=True)
    assert run_det_rule(rule, {"bid.warranty_period": 24}) == []         # 任一支成立(>=12)=过
    issues = run_det_rule(rule, {"bid.warranty_period": 6})
    assert len(issues) == 1 and issues[0]["verdict"] == "violation"      # 全支不成立=violation
    assert run_det_rule(rule, {}) [0]["verdict"] == "need_human"         # 字段缺失=need_human


def test_regex_operator():
    assert eval_expr('regex(bid.full_text, "草稿|内部版")', {"bid.full_text": "内部版请勿外传"}) is True
    assert eval_expr('regex(bid.full_text, "草稿|内部版")', {"bid.full_text": "正式版"}) is False
    with pytest.raises(KeyError):
        eval_expr('regex(bid.full_text, "x")', {"bid.full_text": None})   # A-β2-①


def test_subset_of_operator():
    assert eval_expr('subset_of(bid.a, bid.b)', {"bid.a": [" 营业执照 ", "授权书"], "bid.b": ["营业执照", "授权书", "业绩"]}) is True
    assert eval_expr('subset_of(bid.a, bid.b)', {"bid.a": ["营业执照"], "bid.b": ["授权书"]}) is False
    assert eval_expr('subset_of(bid.a, bid.b)', {"bid.a": [], "bid.b": ["x"]}) is True   # 空集是子集(all 空表 PASS 同款显式语义)
    with pytest.raises(KeyError):
        eval_expr("subset_of(bid.a, bid.b)", {"bid.a": None, "bid.b": ["x"]})


def test_level_ge_operator():
    assert eval_expr('level_ge(bid.lv, tender.lv)', {"bid.lv": "一级", "tender.lv": "二级"}) is True
    assert eval_expr('level_ge(bid.lv, tender.lv)', {"bid.lv": "三级", "tender.lv": "二级"}) is False
    assert eval_expr('level_ge(bid.lv, tender.lv)', {"bid.lv": "甲级", "tender.lv": "乙级"}) is True
    with pytest.raises(KeyError):
        eval_expr("level_ge(bid.lv, tender.lv)", {"bid.lv": "不限资质", "tender.lv": "二级"})  # 未知等级→need_human 通路


def test_col_operator():
    assert eval_expr('col(bid.rows, "no")', {"bid.rows": [{"no": "A1"}, {"no": "A2"}, "junk"]}) == ["A1", "A2"]


def test_pack_loads_cleanly_after_new_functions():
    pack = load_rulepack(PACK)  # 既有包继续干净加载:新 _FUNCS/_KNOWN_OPS 不破坏 lint(计数锁定在 test_golden,此处不重复)
    assert len(pack.rules) >= 40
```

- [ ] **Step 2: 跑红** `uv run pytest tests/test_bid_review_expr_operators2.py -q` —— 预期:or/regex/subset_of/level_ge/col 相关断言 FAIL(`RulePackError: 未知函数` 或 KeyError 缺失);末尾 clean-load 回归测绿。

- [ ] **Step 3: expr.py 实现** —— 以实际文件为准定位(行号为 β批一后约数):

`_FUNCS`(expr.py:20)追加四名:`"regex", "subset_of", "level_ge", "col"`。

模块级(与其他 _ 前缀函数同区)新增:

```python
# 资质等级阶梯(A-β2-②:保守集合,外置挂账至第二消费者/真实数据出现;未知等级 KeyError→need_human,
# W10 机制等价——不判通过)。数值只用于互比,非对外语义。
_LEVEL_LADDER = {"特级": 6, "一级": 5, "甲级": 5, "二级": 4, "乙级": 4, "三级": 3, "丙级": 3, "四级": 2, "丁级": 2, "暂定": 1, "暂定级": 1}


def _regex(text, pattern):
    if not isinstance(text, str) or not isinstance(pattern, str):
        raise KeyError(f"regex 需字符串两侧,得 {type(text).__name__}/{type(pattern).__name__}")
    return re.search(pattern, text) is not None


def _subset_of(a, b):
    if a is None or b is None:
        raise KeyError("subset_of 任一侧 null(A-β2-① need_human 通路)")
    norm = lambda xs: {str(x).strip() for x in xs if str(x).strip()}
    return norm(a) <= norm(b)


def _level_ge(a, b):
    ka, kb = _LEVEL_LADDER.get(str(a or "").strip()), _LEVEL_LADDER.get(str(b or "").strip())
    if ka is None or kb is None:
        raise KeyError(f"资质等级未知:{a!r}/{b!r}(need_human)")
    return ka >= kb


def _col(rows, key):
    return [r.get(key) for r in (rows or []) if isinstance(r, dict)]
```

`_BUILTIN`(expr.py:266 区)追加:

```python
    "regex": _regex,
    "subset_of": _subset_of,
    "level_ge": _level_ge,
    "col": _col,
```

注意:文件头缺 `import re` 则补;`_subset_of`/`_level_ge`/`_col` 若放 lambda 形态与其他成员风格不一致,可定义在模块级后入表(如 `_close` 先例)。

- [ ] **Step 4: rule_runner.py `or` check-op** —— `elif chk["op"] == "and":` 分支(rule_runner.py:242-244)之后镜像新增:

```python
        elif chk["op"] == "or":  # check-op 层析取(P1-β批二):任一支成立即过;全支不成立=violation
            if not any(eval_expr(str(e), fields) for e in chk["any"]):
                issues.append(_issue(rule, fields, {}))
```

`_KNOWN_OPS`(rule_runner.py:20)追加 `"or"`;check 校验键循环(`for key in ("steps", "all", "values")`,rule_runner.py:51)追加 `"any"`(校验语义与 "all" 一致:字符串列表)。**先读该循环实码确认校验形态再改**。

- [ ] **Step 5: 跑绿 + 回归**

```
uv run pytest tests/test_bid_review_expr_operators2.py -q
uv run pytest tests/test_bid_review_expr_mul_close.py tests/test_bid_review_rule_runner.py tests/test_bid_review_golden.py -q
uv run pytest tests/ -k bid_review -q   # 618 基线不翻(T1 实测 618+6 新增=624)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/expr.py backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_expr_operators2.py
git commit -m "feat(bid-review): β批二引擎五件套——or(check-op层)/regex/subset_of/level_ge/col;阶梯常量保守集(A-β2-②);null一律KeyError→need_human(A-β2-①/W10等价)"
```

---

### Task 2: W11 迁移——L1-021 → L2-031(纯改名,声明函存在性)

**依据:** 仓库 L1-021 现语义=`all d in required_declarations: d in declaration_letter_codes`(纯存在性)= 规格 L2-031「各类声明函逐份存在;内容合规归 L1-021」的声明函半边;规格 L1-021 真语义(存在**且已签署**)repo 未覆盖——同号不同义,W1-W5 先例适用,改名迁位(A-β2-⑥)。签署维度+承诺函清单挂账抽取面。

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(:314 规则 id/name/注释)
- Rename+Modify: `backend/app/extensions/bid_review/golden/cases/L1-021-declaration-missing.yaml` → `L2-031-declaration-missing.yaml`(expect rule_id 同步)
- Modify: `backend/tests/test_bid_review_golden.py`(EXPECTED_COVERAGE :315 位移至 L2 段)
- Modify: `backend/tests/test_bid_review_rule_runner.py`(:86 id 清单)
- Modify: `backend/app/extensions/bid_review/engine/crosscheck.py`(docstring L1-021→L2-031,两处)

- [ ] **Step 1: yaml 迁移** —— id `L1-021`→`L2-031`;name→`必备声明函齐备(签署判定挂账签署态抽取面,承诺函清单挂账)`;规则注释块记 W11 迁移依据(现 check=存在性=规格 L2-031 声明函半边;severity fatal 不变,L2 白名单含 fatal);**check/inputs/message_tpl 逐字节不动**。包头注释条数不变(40 条)。

- [ ] **Step 2: golden case 迁移** —— 文件改名(`git mv`);内部 expect `rule_id: L1-021`→`L2-031`;case id/desc 同步;断言语义零变。

- [ ] **Step 3: 测试与 docstring 同步** —— EXPECTED_COVERAGE 的 `"L1-021"`(:315)移入 L2 字典段(真实字典位,L3-019 先例:不复现计划假想位);test_rule_runner :86 id 清单同步;crosscheck.py docstring 两处 L1-021→L2-031(语义描述「`all` 而非 `set_eq`」不动)。

- [ ] **Step 4: 跑绿 + 回归**

```
uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_registry.py tests/test_bid_review_rule_runner.py -q
uv run pytest tests/ -k bid_review -q   # 624 不翻;golden 计数不变(60 题)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/golden/cases/ backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_rule_runner.py backend/app/extensions/bid_review/engine/crosscheck.py
git commit -m "refactor(bid-review): W11迁移 L1-021→L2-031——现check=声明函存在性恰为规格L2-031语义;签署维度+承诺函清单挂账抽取面;改名不改check(W1-W5先例);旧override键孤儿no-op记档(A-β2-⑥)"
```

---

### Task 3: Decimal 加总链(expr sum)

**依据:** expr.py:273 `"sum": lambda vals: float(sum(...))` 浮点累加;金额加总链(L1-010 steps 消费)在多行累加下浮点误差可累积。迁 Decimal 累加、float 出口(契约不变);A-β1-② 边界注记同步(容差比较仍 close/float 域)。

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/expr.py`(:273 sum)
- Test: `backend/tests/test_bid_review_expr_operators2.py`(追加测)

- [ ] **Step 1: 写失败测试**(追加到 T1 测试文件)

```python
def test_sum_decimal_accumulation():
    # 浮点:0.1+0.2=0.30000000000000004;Decimal 累加=0.3 精确(金额加总链无漂移)
    assert eval_expr("sum(bid.vals) == 0.3", {"bid.vals": [0.1, 0.2]}) is True
    assert eval_expr("sum(bid.vals) == bid.total", {"bid.vals": [0.1] * 10, "bid.total": 1.0}) is True
```

跑红(`0.30000000000000004 != 0.3`)。

- [ ] **Step 2: 实现** —— expr.py:273 改:

```python
    "sum": lambda vals: float(sum(Decimal(str(v)) for v in (vals or []) if isinstance(v, (int, float)) and math.isfinite(v))),
```

模块头补 `from decimal import Decimal`;`math` 缺导入则补。bool 是 int 子类——`isinstance(v, bool)` 显式排除(True 会被当 1 计入);与 `_num` 的 bool→None 门对齐:

```python
    "sum": lambda vals: float(sum(Decimal(str(v)) for v in (vals or []) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))),
```

- [ ] **Step 3: 跑绿 + 全 golden 零翻转证明**

```
uv run pytest tests/test_bid_review_expr_operators2.py tests/test_bid_review_golden.py -q
uv run python -m app.extensions.bid_review.golden   # 60/60(L1-010 steps 消费 sum,零翻转实证)
uv run pytest tests/ -k bid_review -q
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/bid_review/engine/expr.py backend/tests/test_bid_review_expr_operators2.py
git commit -m "feat(bid-review): Decimal加总链——expr sum累加迁Decimal/float出口契约不变;bool排除与_num门对齐;0.1+0.2==0.3精确钉;A-β1-②挂账兑付"
```

---

### Task 4: L2-021 附件编号引用 + W9 抑制联动 + 去重键

**依据:** 规格 :848(L2-021 附件编号与正文引用对应,det major,抑制 L3-012)/:884(L3-012 被抑制)/主责矩阵 :958(存在性归 L2-021)/去重键模板 :986-991;W9 台账承诺「建 L2-021 时同步落抑制联动+去重键模板」。

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(appendix_references 契约扩 `no` 键 :111)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(L3-012 注释补抑制说明;新增 L2-021;包头 40→41 条)
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(_issue 工厂挂 dedup_key + _dedup_key helper)
- Modify: `backend/app/extensions/bid_review/engine/eval_core.py`(聚合后抑制单插入位 + helper)
- Test: `backend/tests/test_bid_review_golden.py`(EXPECTED_COVERAGE +L2-021 = 41;:295 注释 L1 16+L2 8+L3 17)
- Test: `backend/app/extensions/bid_review/golden/cases/L2-021-ref-no-missing.yaml`(新)
- Test: `backend/app/extensions/bid_review/golden/cases/W9-l3-012-suppressed.yaml`(新,strict:true 负证据)
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`(批P1-β2 裁决表新小节,仿批P1-β1 先例)
- Modify: `backend/tests/test_bid_review_rule_runner.py`(det 计数 34→35 带算式)

- [ ] **Step 1: 契约扩键** —— extract.py:111 改(既有短语零丢失,src 教训):

```python
FIELD_TYPE_CONTRACTS["bid.appendix_references"] = '[{name:"附件名", no:"正文引用处标注的附件编号,无编号填空串"}] 对象列表;只报正文引用到的附件名,present 由服务端按附件清单归一比对回填(禁模型换算,不产该键);no 由服务端仅透传不校验;禁止纯值列表/标量。'
```

normalize 透传核验:appendix_references 行为 dict 原样透传则零改动;若有逐键重建处须保 `no` 键(实现者核 `_normalize_list_shape`/normalize 函数实码)。

- [ ] **Step 2: L2-021 规则落包** —— L3 段尾或 L2 段(以包内分层排序惯例为准,层=L2)新增:

```yaml
  - id: L2-021
    name: 附件编号与正文引用对应
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.appendix_references, bid.attachment_index]
    check:
      op: all
      target: bid.appendix_references
      var: r
      cond: "r.no == null or r.no == '' or r.no in col(bid.attachment_index, 'no')"
    severity: major
    evidence: [A-BOQ]
    message_tpl: "正文引用附件编号 {r.no}({r.name})在投标文件附件清单中不存在"
    fix_tpl: "补齐引用编号对应的附件,或修正正文引用编号与附件清单一致"
    confidence_gate: 1.0
    enabled: true
```

(`evidence` 锚以 registry 注册表实际合法值为准——实现者 grep anchors.py 选附件族已注册锚,不得造新锚。)包头注释 40→41 条。L3-012 规则注释补一行:「W9:P1-β批二起被 L2-021 同实体引用抑制(eval_core 折叠),存在性归 L2-021 主责(spec :958)」——**L3-012 check 本体零改动**。

- [ ] **Step 3: dedup_key 挂 _issue 工厂** —— rule_runner.py `_issue` 内(A-β2-⑦ repo 形态):

```python
def _dedup_key(rule, entity: dict | None) -> str:
    ent = "|".join(f"{k}={v}" for k, v in sorted((entity or {}).items())) or "-"
    return f"{rule.layer}|{rule.id}|{ent}"
```

`_issue` 产物 dict 增 `"dedup_key": _dedup_key(rule, env)`(env 为行 var 环境或 None;所有 det issue 统一带键,零行为面变化——消费方本批仅抑制 helper 与测试)。_need_human 是否带键:不带(非正式违规,spec 模板只覆盖 issue 级正式违规)。

- [ ] **Step 4: W9 抑制** —— eval_core.py 聚合循环后、`return out` 前单插入:

```python
    out = _suppress_l3012_by_l2021(out)
```

模块级 helper(eval_core.py):

```python
def _suppress_l3012_by_l2021(issues: list[dict]) -> list[dict]:
    """W9 抑制联动(spec :848/:884,主责矩阵 :958;P1-β批二 A-β2-⑦):L2-021 已报的引用缺失,
    同实体的 L3-012 violation 折叠(suppressed_by 内标后移除,存在性归 L2 主责;L2-021 未覆盖的
    行照常出 L3-012)。匹配键=实体名归一(两侧 issue 的 entity/message 共有成分)。"""
    l2021 = [i for i in issues if i.get("rule_id") == "L2-021" and i.get("verdict") == "violation"]
    if not l2021:
        return issues

    def _names(i: dict) -> set[str]:
        # \u53ea\u53d6\u7ed3\u6784\u5316 entity_keys:message \u5168\u6587\u7981\u5165\u5339\u914d\u9762(\u6837\u677f\u8bcd\u81ea\u7531\u91cd\u53e0\u4f1a\u628a\u5168\u90e8 L3-012 \u8bef\u6298\u53e0)
        toks = set()
        for k in i.get("entity_keys") or []:
            for part in str(k).replace(":", "|").split("|"):
                p = part.strip().lower()
                if len(p) >= 2:
                    toks.add(p)
        return toks

    keys = set().union(*(_names(i) for i in l2021))
    out, suppressed = [], 0
    for i in issues:
        if i.get("rule_id") == "L3-012" and i.get("verdict") == "violation" and _names(i) & keys:
            i = {**i, "suppressed_by": "L2-021"}
            suppressed += 1
            continue
        out.append(i)
    if suppressed:
        logger.info("W9 抑制:L2-021 主责下折叠 L3-012 violation %d 条", suppressed)
    return out
```

(实现者先跑一个真实 L3-012 issue 看 entity_keys 键形;若键形不含行名致 W9 golden 不折叠,改以行 name/no 为锚取材,但**禁止 message 全文重叠匹配**;核心不变式:**只折叠 violation,need_human 不动;L2-021 无 violation 时零折叠**。logger 缺则补模块级 `logging.getLogger(__name__)`。)

- [ ] **Step 5: golden 两题 + 记账** —— EXPECTED_COVERAGE +`"L2-021"`(41 个,L2 段字典位);:295 注释改「L1 16 + L2 8 + L3 17 = pack 41 条」+批二注记;test_rule_runner :133 det 计数 34→35(L1 det 14 + L3 det 15 + L2 det 6)带算式;CALIBRATION 新立 `## 批P1-β2(P1-β批二)裁决表`(批P1-β1 小节后,三列同格式)两行:L2-021 引擎对行 + W9 抑制行。

`L2-021-ref-no-missing.yaml`:bid.appendix_references 三行(行1 no="附件一" 在 index/行2 no="附件九" 不在 index→violation/行3 no 空串跳过);bid.attachment_index 含 no 附件一/附件二;expect L2-021 major contains ["附件九","不存在"];strict true。

`W9-l3-012-suppressed.yaml`:构造 L2-021 与 L3-012 同实体命中(appendix_references 行 name="业绩合同" 且 no 缺失→L3-012 走 present=False violation,L2-021 因 no 空串跳过不抑制——**反向钉**:no 缺失时 L2-021 不报,L3-012 照常);另一行 name="审计报告" no="附件三" 不在 index 且 name 不在清单→L2-021 报、L3-012 折叠;expect L2-021 命中 + expect_absent ["L3-012"];strict true(证明折叠生效零残留)。

- [ ] **Step 6: 跑绿 + 全家**

```
uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_rule_runner.py tests/test_bid_review_eval_core.py -q   # eval_core 测试文件名以 ls tests/ | grep eval 为准
uv run python -m app.extensions.bid_review.golden   # 62 题(60+2)全 PASS
uv run pytest tests/ -k bid_review -q   # 基线+新增 不翻
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/engine/rule_runner.py backend/app/extensions/bid_review/engine/eval_core.py backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_rule_runner.py backend/app/extensions/bid_review/golden/cases/ backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-021附件编号引用+W9抑制联动——appendix_references扩no键/col取列;L3-012同实体折叠suppressed_by;dedup_key三层键(A-β2-⑦);包40→41;golden62题"
```

---

### Task 5: L4 竞争力独立包(10 卡,离线态,A-β2-③④⑤)

**Files:**
- Create: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml`
- Modify: `backend/app/extensions/bid_review/engine/registry.py`(SEVERITY_BY_LAYER + "L4": {"major","minor","info"};lint_rules 加 L4 fatal 拒载)
- Test: `backend/tests/test_bid_review_l4_pack.py`(新建)
- Create: `backend/app/extensions/bid_review/golden/cases-l4/L4-001-warranty-overcommit.yaml`、`cases-l4/L4-008-hedge-words.yaml`

- [ ] **Step 1: 包文件** —— 10 条卡,sem 卡镜像 L1-013 卡形(check: {per_clause: true, steps: [], verdict_set: [full, partial, none, unclear]}),hyb 卡(L4-006/008)镜像 L2-023 卡形(实现者先读 L2-023 yaml 实块);severity 按 A-β2-③ 映射;`enabled: true`(离线 golden 可跑;live-off 由「worker 单包不接线本目录」构造性保证,A-β2-⑤)。卡内 spec 名路径按 A-β2-④;每卡注释记 spec C.2 出处+映射理由;evidence 锚同 T4 警示:只用 anchors.py 已注册锚,不得造新锚。10 卡:001 质保超额(sem major,warranty_period×min_warranty_period×service_commitments)/002 工期超额(sem major,duration_main_text×max_duration×schedule_milestones)/003 服务承诺超额(sem major,service_commitments×substantive_clauses)/004 无边界承诺(sem major,service_commitments×full_text)/005 合同冲突承诺(sem major,service_commitments×clauses)/006 评分覆盖不足(hyb major,scoring_items×section_for_score)/007 承诺资源不匹配(sem major,service_commitments×total_price×personnel_technical×personnel_commercial×equipment)/008 模糊限定(hyb minor,full_text×response_sections)/009 论证不足(sem minor,response_sections×figures×table_cells)/010 红队风险点(sem info,full_text×scoring_items×response_sections)。包头 meta 注释:`counts_toward_bid_gate: false / max_issues_per_report: 10 / gate_effect: info(激活任务兑付显式过滤)`。

- [ ] **Step 2: registry** —— SEVERITY_BY_LAYER 加 `"L4": {"major", "minor", "info"}`;lint_rules 内加:layer=="L4" 且 severity=="fatal" → problem「L4 fatal 直接拒载(C.1.4)」。

- [ ] **Step 3: 测试** `backend/tests/test_bid_review_l4_pack.py`

```python
"""L4 独立包离线态(A-β2-③④⑤):加载/lint/映射/golden-scripted 两题;live-off=worker 单包不接线(构造性)。"""
from app.extensions.bid_review.engine import registry
from app.extensions.bid_review.engine.rule_runner import Rule, load_rulepack

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml"


def test_l4_pack_loads_and_lints():
    pack = load_rulepack(PACK)
    assert len(pack.rules) == 10
    assert registry.lint_rules(pack.rules) == []


def _l4_rule(**over):
    base = dict(id="L4-T", name="t", layer="L4", type="semantic", applies_to=["*"], inputs=["bid.full_text"],
                check={"per_clause": True, "steps": [], "verdict_set": ["full", "partial", "none", "unclear"]},
                severity="info", evidence=[], message_tpl="m", enabled=True)
    base.update(over)
    return Rule(**base)


def test_l4_fatal_rejected():
    assert any("fatal" in p for p in registry.lint_rules([_l4_rule(severity="fatal")]))


def test_l4_severity_mapping_recorded():
    pack = load_rulepack(PACK)
    sev = {r.id: r.severity for r in pack.rules}
    assert sev["L4-001"] == "major" and sev["L4-008"] == "minor" and sev["L4-010"] == "info"


def test_l4_inputs_named_per_adjudication():
    pack = load_rulepack(PACK)
    all_in = {p for r in pack.rules for p in r.inputs}
    assert "bid.warranty_period" in all_in and "bid.warranty_months" not in all_in   # repo 名优先
    assert "bid.service_commitments" in all_in and "tender.clauses" in all_in        # 新路径规格名
```

- [ ] **Step 4: golden 两题(cases-l4/ 独立目录,A-β2-⑧)** —— `L4-001-warranty-overcommit.yaml`:fields 带 warranty_period=60/min_warranty_period=12/service_commitments=[...],model_script {"L4-001": partial verdict 应答} → expect L4-001 verdict violation severity major contains ["质保"];`L4-008-hedge-words.yaml`:full_text/response_sections 不给(null)→ hyb prefilter fail-open need_human → expect L4-008 verdict need_human(钉 fail-open 路径)。专用测试文件 `tests/test_bid_review_l4_golden.py`(或并入 l4_pack 测试)用 `run_case(case, pack=l4pack)` 跑 cases-l4 两题,主 golden 套件/CLI 零触碰(60 题冻结)。

- [ ] **Step 5: 跑绿 + 全家 + 主 golden 冻结证明**

```
uv run pytest tests/test_bid_review_l4_pack.py -q
uv run python -m app.extensions.bid_review.golden   # 仍 62 题(60+2,T4 的),L4 不入主面
uv run pytest tests/ -k bid_review -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-l4/ backend/app/extensions/bid_review/engine/registry.py backend/tests/test_bid_review_l4_pack.py backend/app/extensions/bid_review/golden/cases-l4/
git commit -m "feat(bid-review): L4竞争力独立包结构落地——10卡(C.2映射A-β2-③④)/lint拒L4fatal/live-off=worker单包不接线(A-β2-⑤);scripted golden两题(cases-l4冻结面隔离A-β2-⑧);激活面挂批二续"
```

---

### Task 6: 台账同步 + CALIBRATION + 全量验收

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`
- Modify: `.wolf/buglog.json` / `.wolf/memory.md`(controller 负责,实现者不碰)

- [ ] **Step 1: 台账刷新**(行号漂移以 grep 定位):

1. §0 速览:覆盖 `40/90` → `41/90`(L1 16/29,L2 8/26,L3 17/25;L2-021 兑付+L2-031 迁移注记;L4 0/10 结构落地注记);实装算子注记 `实装 5` → `实装 9(check-op 层 or 增至 6)`。
2. §2 矩阵 §4 行同步 41/90;§11 行算子注记同步。
3. §3.2 W9 行更新:「L2-021+抑制联动+去重键已兑付(P1-β批二 2026-11-07);L3-012 一致性职责独存(存在性归 L2-021)」。
4. §3.1 迁移表追加 W11 行(L1-021→L2-031,依据与挂账)。
5. §4 表:L1 行 17/29→16/29(L1-021 迁出注记,-021 从待建清单移除);L2 行 6/26→8/26(-021/-031 兑付注记;待建清单移除编号引用 -021 与要件级 -031,余文件级/章节级/字段级/复合/-030/-032/-033);L4 行注记「结构落地(10 卡离线态),激活挂批二续」;缺口段:regex/subset_of/level_ge/or 划线兑付,Decimal(加总链)划线兑付,余三值传播(W10 已裁等价,无码)——本段改写为「表达式引擎缺口已清(A-β1-②/A-β2 批);余 check-op 结构级 neq/gt/lt/in=表达式级覆盖,YAGNI 不建」。
6. §6 批次注记改写:「批二(2026-11-07)兑付:引擎五件套+Decimal 加总链+L2-021/W9 抑制联动+L2-031 迁移+L4 包结构;批二续=文件级/要件级剩余抽取面(9+3 新路径)+L4 激活(advisory 分节/gate 排除/worker 多包);批三=verdict 值域五值迁」。

- [ ] **Step 2: 全量验收**

```
uv run pytest tests/ -k bid_review -q        # 全绿零翻转零新 skip
uv run python -m app.extensions.bid_review.golden   # 62/62
python -c "from app.extensions.bid_review.engine import registry; print(len(registry.universe()))"   # 78 不变
```

验收门:① 全家绿零翻转零新 skip;② golden CLI 62/62 + EXPECTED_COVERAGE==pack_ids==covered 三方相等(41);③ 宇宙 78 不变;④ commit 链每任务独立;⑤ 八裁决未擅改;⑥ worker.py/routers.py 零 diff(A-β2-⑤)。

- [ ] **Step 3: Commit**

```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): β批二账本同步——41/90+W9兑付+W11迁移行+算子缺口清零+批次划分改写(批二续=L4激活与抽取面)"
```
