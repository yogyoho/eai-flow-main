# P1-β批六(tender 字段实补)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tender 33 字段差表(spec §6.1)的 det 层实补——5 条新 det 规则(L1-017/L2-012/L2-013/L2-014/L2-040)连同 13 条新抽取路径落地,⚠️2 窄化字段(performance_req/deposit)以 L1-003/L1-006 inputs 扩展补全;字段与消费规则同批(消费驱动正门)。

**Architecture:** 字段入宇宙唯一正门 = 规则 pack_inputs(registry.universe = pack_inputs ∪ anchor_paths ∪ PROJECTION ∪ SECOND_STAGE),故每条新路径必绑在包内规则的 inputs 上;bid.tables 走服务端派生(SERVER_DERIVED_PATHS,规格 :2165 表格骨架识别 det);golden 面全部 controller 直办(三方精确相等锁)。

**Tech Stack:** Python 3.12 / pytest / rulepack yaml(1.0.0.yaml 追加)/ expr 求值器既有 _FUNCS。

---

## 裁决表(controller-locked,实现者不得改动;偏差按裁决精神处理并声明)

| # | 裁决 |
|---|---|
| A-β6-① | **字段+消费规则同批**。字段无包内消费者 = silo,不落地(3 层模型红线)。sample_required 规格亦无规则卡(仅字段+extractor 行)→ 纯挂账注记,本批不落地。 |
| A-β6-② | **范围锁**:批六 = det 五卡(L1-017/L2-012/L2-013/L2-014/L2-040)+ ⚠️2 扩(L1-003 inputs +L1-006 forms step)。挂批七:pm_req(L1-004)、subcontract_limit(L1-020)、format_requirements(L1-022/026)、required_signatures(L1-007 扩)、sample_required、deposit_deadline(+bid.deposit_paid_at)、L2-024 年份连续性。 |
| A-β6-③ | **L2-024 已存在**(包内「附件份数达标」att_count,inputs=tender.attachment_requirements/bid.attachment_index)——份数主责已承担,attachment_count_reqs 路径**不落地**,年份连续性挂账(引擎无 years 提取 func,规格「无法解析→UNKNOWN」语义 v2 再做)。 |
| A-β6-④ | **数字锁(目标值)**:宇宙 92→**105**(13 新路径: tender 8+bid 4+derived 1)、det 44→**49**、包 50→**55**、golden 题 73 不变(题库行 +5,EXPECTED_COVERAGE 50→55);family 计数实现跑出后 controller 复核落档。 |
| A-β6-⑤ | **bid.tables = 服务端派生**(SERVER_DERIVED_PATHS + extract.py 派生函数,规格 :2165「表格骨架识别 det」,name 经 norm 对齐 required_tables);不做模型抽取。bid.figures = 模型抽取(契约入首段)。 |
| A-β6-⑥ | **L1-017 v1 det 形态**:precondition `bid.is_consortium == True`(非联合体自然 SKIP=规格「非联合体时跳过」);三查 = 招标允许 + 协议实体存在 + (lead 字段在实体形状中,「牵头人明确」并入协议实体判定消息措辞);「各方资质达标」联动挂账;**不造新锚**,evidence 用既有 A-TENDER-NOTICE + A-QUAL-CERT(批二续先例)。 |
| A-β6-⑦ | **章节/表格名称匹配惯用式**:`contains_any(col(bid.X, "name"), keywords(t))` ——contains_any 内建 `str(hay or "")` 对 list 求值即整体 repr 串搜子串,keywords(t) 抽中文连串为 needles;确定性、零引擎新 func。近义词/改述标题漏判容忍(v1),refinement 挂账。 |
| A-β6-⑧ | **L1-003/L1-006 扩形态**:L1-003 仅加 inputs(min_performance_amount/performance_window_months,hyb prompt 自动富化),det_expr/message_tpl/fix_tpl **逐字冻结**(golden contains 面);L1-006 加 forms set_eq step(前置门 count≥1 双侧,夹具无新字段时行为不变),金额判定与既有消息逐字不动;steps 分支消息机制实现者先读 run_det_rule 再落(per-step message 键若有则用)。 |
| A-β6-⑨ | **golden 面全 controller**:EXPECTED_COVERAGE、题库 5 行、73 夹具期望重推导(逐条真阳性审,禁止无脑快照)。实现者禁区照旧:`.wolf/`、`docs/superpowers/`、`golden/CALIBRATION.md`、golden 夹具目录、五锁文件结构(本批五锁 bump 由 T5 显式执行,锁结构不重构)。 |
| A-β6-⑩ | 台账(spec/plan 勾选/.wolf 三件/buglog)controller 包办。 |

## 实态勘误(实现者先验证再动手;与 plan 冲突时以实态为准并声明)

- rulepack 单文件:`backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(规则以 `- id:` 列表追加,L2-024 att_count 模板在 :609-625,set_eq left/right 渲染契约陷阱见 :59-64 注释)。
- expr funcs 全集(expr.py:22):`normalize_unit/number_to_words/months_ago/codes/covers/keywords/sum/count/contains_any/imply/all_equal/close/regex/subset_of/level_ge/col`;`contains_any(hay, needles)`= `any(str(n) in str(hay or ""))`(list hay 走 str() repr,这是 A-β6-⑦ 惯用式的根基);`keywords(name)`=`re.findall(r"[一-龥]{2,}", name)`。
- `op: and` 包内可能无用例(批二只落了 or 析取)——L1-017 check 先 grep `op: or` 先例(:380 附近 run_det_rule 分支)镜像形态;若 and 分支语义不明,改用单 cond 表达:`{"op":"eq","left":"bid.is_consortium != True or (tender.consortium_allowed == True and count(bid.consortium) >= 1)","right":"True"}` 等价形态(实现者按求值器实测定,测试先行)。
- det 规则 steps 形态:rule_runner.py:23「steps 形态无 op 键,单独判」——check 可为 dict 或 list;L1-006 扩前先读 run_det_rule steps 分支的消息机制。
- SERVER_DERIVED 生产者模式:extract.py:236 `out["bid.deposit_receipt_present"] = _any_name((r"保证金", ...))`;先查既有 SERVER_DERIVED 路径是否有 FIELD_TYPE_CONTRACTS 条目并镜像(bid.tables 大概率**无**契约,派生字段模型自产被 :218 闸门丢弃)。
- universe 钉子位置:`tests/test_bid_review_rule_families.py:134`(`assert len(universe()) == 92`)+ `tests/test_bid_review_registry.py`(实现者先 `grep -rn "92" tests/test_bid_review_registry.py` 找全部钉点);det 计数/EXPECTED_V1_IDS 钉在 rule_families/registry 测试,先 grep 再改。
- golden 三方精确相等:tests/test_bid_review_golden.py:376-379(EXPECTED_COVERAGE == pack_ids == 题库实 coverage)——新规则不建题库行必三向红。
- 首段请求面:`collect_field_paths()`(extract.py:291)= universe − SECOND_STAGE − SERVER_DERIVED,新路径入宇宙即自动进首段 prompt;`normalize_candidates` 只收已知路径 + JSON-safe 门。
- 测试布局:`backend/tests/` 平铺;family gate = `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(695p/6s/0f 基线)。
- 附件份数对照:L2-023/024 吃 `tender.attachment_requirements`+`bid.attachment_index`(已 ✅ 差表),与批六新路径无关。

## 新路径清单(13,数字锁 A-β6-④)

| 路径 | 类型 | 消费者 | 备注 |
|---|---|---|---|
| tender.consortium_allowed | bool | L1-017(T3) | conf 0.90 |
| tender.tech_sections_required | list[str] | L2-012(T3) | conf 0.80 |
| tender.commitment_sections | list[str] | L2-013(T3) | conf 0.85 |
| tender.required_figures | list[{id,name}] | L2-014(T3) | conf 0.80 |
| tender.required_tables | list[str] | L2-040(T3) | conf 0.85 |
| tender.min_performance_amount | money/null | L1-003 inputs 扩(T4) | 单项业绩最低金额(万元) |
| tender.performance_window_months | int/null | L1-003 inputs 扩(T4) | 业绩年限(近 N 月) |
| tender.deposit_forms | list[str] | L1-006 forms step(T4) | 缴纳形式 |
| bid.is_consortium | bool | L1-017 precondition(T3) | conf 0.90 |
| bid.consortium | list[{lead,members}] | L1-017(T3) | 协议实体 |
| bid.figures | list[{id,name}] | L2-014(T3) | conf 0.80 |
| bid.deposit_forms | list[str] | L1-006 forms step(T4) | 实际缴纳形式 |
| bid.tables | (服务端派生) | L2-040(T3)+T2 派生 | SERVER_DERIVED_PATHS |

---

### Task 1: 12 条模型抽取契约(extract.py + 契约测试)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(FIELD_TYPE_CONTRACTS 追加 12 条,按域分组插入)
- Test: `backend/tests/test_bid_review_extract.py`(新增 test class)

- [ ] **Step 1: 写失败测试**

`test_bid_review_extract.py` 文件尾部新增(沿用该文件现行 unittest 风格):

```python
class TestBeta6FieldContracts(unittest.TestCase):
    """批六 tender 字段实补(A-β6-①②):12 条新契约入 FIELD_TYPE_CONTRACTS 且入首段请求面。"""

    BETA6_PATHS = [
        "tender.consortium_allowed", "tender.tech_sections_required",
        "tender.commitment_sections", "tender.required_figures",
        "tender.required_tables", "tender.min_performance_amount",
        "tender.performance_window_months", "tender.deposit_forms",
        "bid.is_consortium", "bid.consortium", "bid.figures", "bid.deposit_forms",
    ]

    def test_contracts_present_with_shape_hints(self):
        from app.extensions.bid_review.engine.extract import FIELD_TYPE_CONTRACTS
        for p in self.BETA6_PATHS:
            assert p in FIELD_TYPE_CONTRACTS, p
        # 形状关键词抽查(A-β6-⑥⑦ 契约可诚实产出:无明示给 null/空数组)
        assert "null" in FIELD_TYPE_CONTRACTS["tender.min_performance_amount"]
        assert "空数组" in FIELD_TYPE_CONTRACTS["tender.tech_sections_required"]
        assert "联合体" in FIELD_TYPE_CONTRACTS["bid.is_consortium"]

    def test_new_paths_enter_first_stage_request(self):
        from app.extensions.bid_review.engine.extract import collect_field_paths
        paths = set(collect_field_paths())
        for p in self.BETA6_PATHS:
            assert p in paths, p  # T3/T4 规则未注册前靠 T5 前 universe 暂不含;本测试在 T5 后复跑
```

注意:`test_new_paths_enter_first_stage_request` 在 T1 阶段**预期失败**(契约在但宇宙未含——宇宙正门是规则 inputs),T5 完成后复跑转绿。T1 提交时该测试打 `@unittest.skip("T5 宇宙注册后启用")`,T5 实现者移除 skip 并确认转绿。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py::TestBeta6FieldContracts -v
```
预期:FAIL(12 键缺)。

- [ ] **Step 3: 实现(FIELD_TYPE_CONTRACTS 追加)**

在 `FIELD_TYPE_CONTRACTS` dict 内按既有域分组插入(tender.* 挨 tender 组,bid.* 挨 bid 组;先 grep 相邻键定位):

```python
    # ── P1-β批六 tender 字段实补(spec §6.1 差表,A-β6-①②;消费驱动正门:全部绑包内规则 inputs)──
    "tender.consortium_allowed": "bool;招标文件是否允许联合体投标;只依据材料原文,无明示给 null。",
    "tender.tech_sections_required": '["技术方案必备章节名"] 字符串数组;招标要求投标技术方案应包含的章节(总体/实施/进度/质量/安全/应急/售后/培训类);无要求给空数组。',
    "tender.commitment_sections": '["承诺类章节名"] 字符串数组;工期/质量/质保/服务响应/廉洁/保密等承诺章节要求;无要求给空数组。',
    "tender.required_figures": '[{id:"要求编号或空串",name:"图表名称"}] 对象列表;招标要求的附图/图表;id/name 非空才收;无给空数组。',
    "tender.required_tables": '["必备表格名"] 字符串数组;报价汇总/分项报价/清单响应/参数偏离/人员表/设备表类;无要求给空数组。',
    "tender.min_performance_amount": "数字或 null;单项类似业绩最低金额要求(万元);无明示给 null。",
    "tender.performance_window_months": "数字或 null;类似业绩时间跨度要求(近 N 个月);无明示给 null。",
    "tender.deposit_forms": '["缴纳形式"] 字符串数组(现金/银行保函/保证保险等);招标要求的保证金缴纳形式;无明示给空数组。',
    "bid.is_consortium": "bool;投标文件是否以联合体形式投标;无依据给 null。",
    "bid.consortium": '[{lead:"牵头人名称",members:["成员名称"]}] 对象列表;联合体协议书实体;非联合体给空数组。',
    "bid.figures": '[{id:"图号或空串",name:"图表名称"}] 对象列表;投标文件中的图纸/图表清单;id/name 非空;无给空数组。',
    "bid.deposit_forms": '["实际缴纳形式"] 字符串数组;投标文件载明的保证金缴纳形式;无给空数组。',
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py -v
```
预期:全 PASS(新 class 除 skip 项外全绿;既有契约测试不破)。

- [ ] **Step 5: lint + commit**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/extract.py tests/test_bid_review_extract.py
cd D:/eai/eai-flow-main
git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_extract.py
git commit -m "feat(bid-review): 批六T1——12 条模型抽取契约入 FIELD_TYPE_CONTRACTS(tender 8+bid 4,差表 ❌/⚠️2 路径,无明示给 null/空数组可诚实产出,A-β6-①②);首段请求面测试 skip 待 T5 宇宙注册(A-β6-④数字锁分步兑付)"
```

**Review 分工:** engine 契约 diff 小而机械 → controller inline review。

### Task 2: bid.tables 服务端派生(extract.py + 测试)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(SERVER_DERIVED_PATHS :146 + 派生函数 + build_baseline :854 接线)
- Test: `backend/tests/test_bid_review_extract.py`

实态已证:parse 表格块 = `{kind:"table", text, rows, source}`(parse.py:221/268),xlsx 块 text 带 `[sheet: 表名]\n` 前缀(:268),PDF 表格 text 无名;join 进 doc text 后派生面 = doc text 中的 `[sheet: X]` 标记。PDF 表格 v1 不产名(漏判容忍,refinement 挂账,A-β6-⑦ 同款)。

- [ ] **Step 1: 写失败测试**

`test_bid_review_extract.py` 尾部新增:

```python
class TestBidTablesDerived(unittest.TestCase):
    """批六 bid.tables 表格骨架服务端派生(A-β6-⑤,规格 :2165 表格骨架识别 det)。"""

    def test_tables_derived_from_sheet_markers(self):
        from app.extensions.bid_review.engine.extract import _derive_bid_tables
        docs = [
            {"doc_id": "d1", "text": "前言\n[sheet: 报价汇总表]\n|a|b|\n正文\n[sheet: 分项报价表]\n|c|d|"},
            {"doc_id": "d2", "text": "[sheet: 报价汇总表]\n|x|y|"},  # 跨 doc 同名表保留重复(骨架不去重,消费端 set)
        ]
        out = _derive_bid_tables(docs)
        assert out == [
            {"name": "报价汇总表", "source": "d1"},
            {"name": "分项报价表", "source": "d1"},
            {"name": "报价汇总表", "source": "d2"},
        ]

    def test_tables_empty_when_no_markers(self):
        from app.extensions.bid_review.engine.extract import _derive_bid_tables
        # PDF 表格无名 v1 不产(A-β6-⑤ 漏判容忍)
        assert _derive_bid_tables([{"doc_id": "d1", "text": "纯文本无表格标记"}]) == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py::TestBidTablesDerived -v
```
预期:FAIL(`_derive_bid_tables` 不存在)。

- [ ] **Step 3: 实现**

extract.py `SERVER_DERIVED_PATHS`(:146)追加 `"bid.tables"`;`build_baseline` 上方新增:

```python
_SHEET_MARKER = re.compile(r"\[sheet:\s*([^\]]+)\]")


def _derive_bid_tables(docs: list[dict]) -> list[dict]:
    """bid.tables 表格骨架(A-β6-⑤,规格 :2165「表格骨架识别 det」):doc text 中的
    [sheet: X] 标记(xlsx 表格块前缀,parse.py:268)→ {name, source} 骨架行,供
    L2-040 required_tables 匹配;PDF 表格无名 v1 不产(漏判容忍);模型自产同路径
    被 SERVER_DERIVED 闸门在 normalize 源头丢弃。"""
    out: list[dict] = []
    for d in docs:
        seen: set[str] = set()
        for m in _SHEET_MARKER.finditer(str(d.get("text") or "")):
            name = m.group(1).strip()
            if name and name not in seen:  # 同 doc 同 sheet 多段只记一次(跨 doc 保留)
                seen.add(name)
                out.append({"name": name, "source": d.get("doc_id")})
    return out
```

`build_baseline` 内 `fields = derive_joins(fields)`(:854)后接一行:

```python
    fields["bid.tables"] = _derive_bid_tables(docs)  # 批六 A-β6-⑤:表格骨架服务端派生;tender 侧无要求→all-op 零迭代零发话,bid 侧空→要求行全 MISSING(正确语义)
```

- [ ] **Step 4: 跑测试确认通过 + 派生面回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py tests/test_bid_review_worker.py -q
```
预期:全 PASS(worker 既有测试的 fields 断言若 exact-dict 含派生面会被 bid.tables 新键打破——按 additive 键先例随迁并在提交信息声明,像批五 bff6d31aa)。

- [ ] **Step 5: lint + commit**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/extract.py tests/test_bid_review_extract.py
cd D:/eai/eai-flow-main
git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_extract.py
git commit -m "feat(bid-review): 批六T2——bid.tables 表格骨架服务端派生([sheet:X] 标记扫描,SERVER_DERIVED_PATHS+闸门丢弃模型自产,build_baseline :854 接线,A-β6-⑤;PDF 表格无名 v1 漏判容忍挂账)"
```

**Review 分工:** engine diff → agent reviewer(派生闸门语义)。

### Task 3: 五条新 det 规则(rulepack + lint + 规则单测)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(追加 5 条,带批六注释块)
- Test: `backend/tests/test_bid_review_rule_runner.py`(新 det 规则直跑测试;先 grep 该文件既有 det 直跑测试形态)

- [ ] **Step 1: 写失败测试(规则直跑,构造 fields 喂 run_det_rule)**

```python
class TestBeta6DetRules(unittest.TestCase):
    """批六五条 det 规则(A-β6-⑥⑦):L1-017/L2-012/L2-013/L2-014/L2-040。"""

    def _run(self, rule_id, fields):
        # 沿该文件既有 load 方式取规则;实现者按文件现形回填 import/加载行
        ...

    def test_l1017_consortium_precondition_skip(self):
        # 非联合体:SKIP(precondition 不成立→[])A-β6-⑥
        assert self._run("L1-017", {"bid.is_consortium": False, "tender.consortium_allowed": True, "bid.consortium": []}) == []

    def test_l1017_not_allowed_or_no_agreement_fails(self):
        iss = self._run("L1-017", {"bid.is_consortium": True, "tender.consortium_allowed": False, "bid.consortium": [{"lead": "甲", "members": ["乙"]}]})
        assert len(iss) == 1 and iss[0]["verdict"] == "FAIL"
        iss2 = self._run("L1-017", {"bid.is_consortium": True, "tender.consortium_allowed": True, "bid.consortium": []})
        assert len(iss2) == 1 and iss2[0]["verdict"] == "FAIL"

    def test_l2012_missing_required_section_per_row(self):
        fields = {"tender.tech_sections_required": ["总体方案", "应急预案"],
                  "bid.section_tree": [{"code": "1", "title": "第一章 总体方案", "is_empty": False}]}
        iss = self._run("L2-012", fields)
        assert len(iss) == 1 and "应急预案" in iss[0]["message"]  # per-row(A-β6-⑦)

    def test_l2013_commitment_subset(self):
        fields = {"tender.commitment_sections": ["质量承诺"], "bid.section_tree": []}
        iss = self._run("L2-013", fields)
        assert len(iss) == 1 and "质量承诺" in iss[0]["message"]

    def test_l2014_figures_minor(self):
        fields = {"tender.required_figures": [{"id": "F1", "name": "总平面图"}], "bid.figures": []}
        iss = self._run("L2-014", fields)
        assert len(iss) == 1 and iss[0]["severity"] == "minor"

    def test_l2040_tables_fatal(self):
        fields = {"tender.required_tables": ["报价汇总表"], "bid.tables": [{"name": "分项报价表", "source": "d1"}]}
        iss = self._run("L2-040", fields)
        assert len(iss) == 1 and iss[0]["severity"] == "fatal"

    def test_l2040_present_table_passes(self):
        fields = {"tender.required_tables": ["报价汇总表"], "bid.tables": [{"name": "第一章 报价汇总表", "source": "d1"}]}
        assert self._run("L2-040", fields) == []  # contains_any repr 子串命中(A-β6-⑦)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py::TestBeta6DetRules -v
```
预期:FAIL(规则不存在)。**先跑 lint_rules 确认基线干净**:`PYTHONPATH=. uv run python -c "from app.extensions.bid_review.engine.registry import lint_rules, _pack_rules; print(lint_rules(_pack_rules()))"` → `[]`。

- [ ] **Step 3: rulepack 追加(1.0.0.yaml 尾部,带批六注释块)**

```yaml
  # ── P1-β批六 tender 字段实补(spec §6.1 差表,2026-11-08;A-β6-⑥⑦)──
  # L1-017 联合体合规:precondition=非联合体自然 SKIP(规格「非联合体时跳过」);
  # 不造新锚(A-β6-⑥),「各方资质达标」联动挂账。check 形态按实态勘误
  # (op: and 先例 grep;若无 and 分支用 eq+or 单 cond 等价式)。
  - id: L1-017
    name: 联合体投标合规
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.is_consortium, bid.consortium, tender.consortium_allowed]
    check:
      op: and
      left: "tender.consortium_allowed == True"
      right: "count(bid.consortium) >= 1"
      precondition: "bid.is_consortium == True"
    severity: fatal
    evidence: [A-TENDER-NOTICE, A-QUAL-CERT]
    message_tpl: "联合体投标要件不合规:须同时满足招标允许联合体、联合体协议书存在且牵头人明确"
    fix_tpl: "补联合体协议书并明确牵头人与各方职责;若招标不允许联合体,调整投标主体形式"
    confidence_gate: 1.0
    enabled: true
  # L2-012/013 章节 required⊆section_tree,名称匹配惯用式 contains_any+keywords(A-β6-⑦)
  - id: L2-012
    name: 技术方案必备章节齐备
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.tech_sections_required, bid.section_tree]
    check:
      op: all
      target: tender.tech_sections_required
      var: t
      cond: "contains_any(col(bid.section_tree, 'title'), keywords(t))"
    severity: major
    evidence: [A-TOC, A-MAIN-TEXT]
    message_tpl: "技术方案缺必备章节「{t}」"
    fix_tpl: "按招标技术方案要求补齐章节(总体/实施/进度/质量/安全/应急/售后/培训等)"
    confidence_gate: 0.8
    enabled: true
  - id: L2-013
    name: 承诺类章节存在
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.commitment_sections, bid.section_tree]
    check:
      op: all
      target: tender.commitment_sections
      var: t
      cond: "contains_any(col(bid.section_tree, 'title'), keywords(t))"
    severity: major
    evidence: [A-TOC, A-MAIN-TEXT]
    message_tpl: "承诺类章节「{t}」缺失"
    fix_tpl: "补齐承诺类章节(工期/质量/质保/服务响应/廉洁/保密等)"
    confidence_gate: 0.85
    enabled: true
  - id: L2-014
    name: 图纸与图表齐备
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.required_figures, bid.figures]
    check:
      op: all
      target: tender.required_figures
      var: t
      cond: "contains_any(col(bid.figures, 'name'), keywords(t.name))"
    severity: minor
    evidence: [A-MAIN-TEXT, A-TECH-PROPOSAL]
    message_tpl: "要求的图表「{t.name}」未见于投标文件"
    fix_tpl: "按招标附图要求补充图表,图表不得空白占位"
    confidence_gate: 0.8
    enabled: true
  # L2-040 必备表格:bid.tables 服务端派生(T2),规格 :2165 name 经 norm 对齐
  - id: L2-040
    name: 必备表格存在
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.required_tables, bid.tables]
    check:
      op: all
      target: tender.required_tables
      var: t
      cond: "contains_any(col(bid.tables, 'name'), keywords(t))"
    severity: fatal
    evidence: [A-MAIN-TEXT, A-PRICE-SHEET]
    message_tpl: "必备表格「{t}」缺失"
    fix_tpl: "按招标要求编入必备表格(报价汇总/分项报价/清单响应/参数偏离/人员表/设备表)"
    confidence_gate: 0.85
    enabled: true
```

实态勘误落点:L2-012/013/040 cond 若 all-op 分支对 `col(...)` list-hay 求值报 KeyError(str 守卫),改用 `contains_any(str 结串...)` 不可用时的备选——`sum`/`codes` 不适用时,以 `_subset_of` 守卫注释(A-β2-① KeyError→UNKNOWN→need_human 通路)为准实现者按求值器实测调整并在提交信息声明;测试先行保证行为。

- [ ] **Step 4: 跑测试 + lint_rules**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py::TestBeta6DetRules -v
PYTHONPATH=. uv run python -c "from app.extensions.bid_review.engine.registry import lint_rules, _pack_rules; print(lint_rules(_pack_rules()))"
```
预期:测试全 PASS;lint `[]`。

- [ ] **Step 5: lint + commit**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine tests/test_bid_review_rule_runner.py
cd D:/eai/eai-flow-main
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/tests/test_bid_review_rule_runner.py
git commit -m "feat(bid-review): 批六T3——五条新 det 规则:L1-017 联合体(precondition 非联合体 SKIP,不造新锚,A-β6-⑥)+L2-012/013 章节 subset(contains_any+keywords 惯用式,A-β6-⑦)+L2-014 图表 minor+L2-040 必备表格 fatal(bid.tables 派生);lint_rules 零违例"
```

**Review 分工:** rulepack+runner diff = engine core → **agent reviewer**(独立复核 op 形态/precondition 语义/all-op per-row 发话与规格卡逐一对照)。

### Task 4: L1-003/L1-006 扩(⚠️2 兑付)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(L1-003 inputs、L1-006 check steps)
- Test: `backend/tests/test_bid_review_rule_runner.py`

- [ ] **Step 1: 写失败测试**

```python
class TestBeta6RuleExtensions(unittest.TestCase):
    """批六 ⚠️2 兑付(A-β6-⑧):L1-003 inputs 富化 / L1-006 forms step。"""

    def test_l1003_inputs_enriched_unchanged_det(self):
        r = <取规则 "L1-003">
        assert "tender.min_performance_amount" in r["inputs"]
        assert "tender.performance_window_months" in r["inputs"]
        # det_expr/message_tpl 逐字冻结(A-β6-⑧ golden contains 面)
        assert r["check"]["det_expr"] == "count(bid.similar_performances) >= tender.min_similar_performance_count"

    def test_l1006_forms_step_fires_on_mismatch(self):
        fields = {"bid.deposit_amount": 100000, "tender.deposit_required": 100000,
                  "bid.deposit_receipt_present": True,
                  "tender.deposit_forms": ["银行保函"], "bid.deposit_forms": ["现金"]}
        iss = self._run("L1-006", fields)
        assert any("银行保函" in i["message"] or "现金" in i["message"] for i in iss)

    def test_l1006_forms_step_silent_when_fields_absent(self):
        # 夹具无新字段 → 行为不变(golden 数字锁兼容,A-β6-⑧)
        fields = {"bid.deposit_amount": 100000, "tender.deposit_required": 100000, "bid.deposit_receipt_present": True}
        iss = self._run("L1-006", fields)
        assert iss == []  # 金额一致且 forms 前置门未开
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py::TestBeta6RuleExtensions -v
```

- [ ] **Step 3: rulepack 修改**

L1-003 inputs 行扩为:

```yaml
    inputs: [bid.similar_performances, tender.min_similar_performance_count, tender.min_performance_amount, tender.performance_window_months]
```

L1-006 check 改 steps 形态(steps 分支消息机制按实态勘误先读 run_det_rule;若 per-step message 键名不同,按实际键名落):

```yaml
    check:
      - op: eq
        left: bid.deposit_amount
        right: tender.deposit_required
        precondition: "tender.deposit_required > 0 and bid.deposit_receipt_present == True"
      - op: set_eq
        left: "codes(bid.deposit_forms)"
        right: "codes(tender.deposit_forms)"
        precondition: "count(tender.deposit_forms) >= 1 and count(bid.deposit_forms) >= 1"
        message_tpl: "保证金缴纳形式与招标要求不一致:要求 {tender.deposit_forms} / 实际 {bid.deposit_forms}"
```

若 steps 分支不支持 per-step message:A-β6-⑧ 授权回退形态 = forms 判定单独消息必须成立,实现者按 steps 分支实态选用其支持的每步消息键(以 `grep -n "steps" rule_runner.py` 实测为准),禁止合并回单消息(会破坏金额判定消息逐字冻结)。

- [ ] **Step 4: 跑测试 + 全 det 回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py tests/test_bid_review_worker.py -q
```

- [ ] **Step 5: lint + commit**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml tests/test_bid_review_rule_runner.py
cd D:/eai/eai-flow-main
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/tests/test_bid_review_rule_runner.py
git commit -m "feat(bid-review): 批六T4——⚠️2 兑付:L1-003 inputs 富化(min_performance_amount/performance_window_months,hyb prompt 自动富化,det_expr/tpl 逐字冻结,A-β6-⑧)+L1-006 forms set_eq step(前置门 count≥1 双侧,夹具无新字段行为不变);spec §6.1 performance_req/deposit 窄化收口"
```

**Review 分工:** rulepack diff → controller inline review(重点:steps 分支消息机制与 A-β6-⑧ 冻结令)。

### Task 5: 五锁显式 bump(非 golden 四锁)

**Files:**
- Modify: `backend/tests/test_bid_review_rule_families.py`(:134 universe 钉 + det 计数钉 + EXPECTED_V1_IDS)
- Modify: `backend/tests/test_bid_review_registry.py`(universe/det 钉点,先 grep 92)
- Test: 同文件(数字变更即测试)

- [ ] **Step 1: 移除 T1 skip + 确认首段请求面**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py::TestBeta6FieldContracts -v
```
移除 `@unittest.skip` 后 `test_new_paths_enter_first_stage_request` 应转绿(13 新路径含 bid.tables 全入 universe=105)。

- [ ] **Step 2: 五锁数字更新**

先 grep 全部钉点再改:

```bash
cd backend && grep -rn "== 92\|det.*44\|44.*det\|EXPECTED_V1_IDS" tests/test_bid_review_rule_families.py tests/test_bid_review_registry.py | head -10
```

更新:universe 92→**105**、det 44→**49**、包 50→**55**、EXPECTED_V1_IDS 追加 L1-017/L2-012/L2-013/L2-014/L2-040(A-β6-④)。

- [ ] **Step 3: family 全量门(非 golden 面)**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q --deselect tests/test_bid_review_golden.py --deselect tests/test_bid_review_golden_extract.py
```
预期:全绿(包 55/宇宙 105/det 49;新增测试数跑出后报 controller)。

- [ ] **Step 4: lint + commit**

```bash
cd backend && uv run ruff check tests/test_bid_review_rule_families.py tests/test_bid_review_registry.py tests/test_bid_review_extract.py
cd D:/eai/eai-flow-main
git add backend/tests/test_bid_review_rule_families.py backend/tests/test_bid_review_registry.py backend/tests/test_bid_review_extract.py
git commit -m "test(bid-review): 批六T5——五锁显式 bump:宇宙92→105(det44→49/包50→55,EXPECTED_V1_IDS+5,A-β6-④);T1 首段请求面 skip 解除全绿;golden 面(EXPECTED_COVERAGE/题库)留 T6 controller(A-β6-⑨)"
```

**Review 分工:** controller inline review(数字核对)。

### Task 6: golden 面(controller 直办,不派实现者)

**Files:**
- Modify: `backend/tests/test_bid_review_golden.py`(EXPECTED_COVERAGE +5 题库行;:376-379 三方精确相等)
- Modify: golden 夹具期望值(73 案例中受新规则影响者)

- [ ] **Step 1: EXPECTED_COVERAGE 追加 5 id + 题库行(每新规则一题,选受影响夹具)**
- [ ] **Step 2: 跑 golden 全量,逐条审新 issue 真阳性(禁止无脑快照;误报→修规则/惯例式,真阳性→更新期望)**
- [ ] **Step 3: 全量门**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_golden_extract.py -q
cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q
```
预期:golden 73/0;family 全绿(数字 T5 跑出值)。

- [ ] **Step 4: commit(controller)**

### Task 7: spec §6.1 差表更新 + 兑付段 + 台账(controller 直办)

- [ ] **Step 1: spec §6.1 差表落批六结果**(❌11→❌4: pm_req/subcontract_limit/format_requirements/required_signatures 挂批七;sample_required 无卡纯挂账;⚠️2→✅;attachment_count_reqs→挂账注记 L2-024 已担份数主责)
- [ ] **Step 2: P1 段批六兑付段**(commit hash/裁决兑付/挂账)
- [ ] **Step 3: .wolf 三件 + buglog(如有)+ plan 勾选 + 最终报告**

---

## 验收口径(批六收官数字)

- 宇宙 **105** / det **49** / 包 **55** / golden **73/0** / family 全绿(695 基线 + 新增测试数)
- ❌11 → ❌4(批七清单:pm_req、subcontract_limit、format_requirements、required_signatures)+ 挂账 2(sample_required、attachment_count_reqs 年份)+ ⚠️2→✅
- 新规则零 lint 违例;L1-003/L1-006 既有消息逐字冻结
