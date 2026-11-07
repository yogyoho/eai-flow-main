# P1-β批二续(文件级/要件级抽取面 + L4 激活)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地文件级 L2-001/002/003/004/050/051 与要件级 L2-030/032/033 共 9 条 det 规则(13 条新抽取路径/派生布尔+3 对主责折叠),并把 L4 竞争力包从离线态激活为 advisory 面(worker 合包/报告独立分节/gate 排除/不计正式问题数)。

**Architecture:** 引擎同一打法:路径与规则卡同任务落地(契约⊆宇宙锁强制);抑制走 eval_core 聚合后单插入位泛化 helper(W9 本体不动);L4 激活用**并列常量**不动 `RULEPACK_PATH` 单包语义(打桩 fixture 不破),合并 rules 单次 `evaluate_fields`(W9/折叠天然作用于合并面);golden loader/runner 与 worker 面解耦,主 golden 冻结面零触碰。

**Tech Stack:** Python 3.12 / FastAPI / pytest(backend);Next.js 16 / React 19 / rstest(frontend);规则卡 YAML。

**基线(2026-11-07,d23e1fe25 实测,勘误链:627→628→629→632→633→639 皆为 family 口径演进):**
- family:`uv run pytest tests/ -k bid_review -q` → **639 passed, 6 skipped, 0 failed**
- golden CLI:`uv run python -m app.extensions.bid_review.golden` → **62 题 0 失败**;core 包 **41 条**(det 35 / hyb 5 / sem 1)
- registry 宇宙 **78**;`worker.py`/`routers.py` 本批将首次被改动(L4 激活),改动面以本 plan 为准

**终点预期:** pack **50 条**(det 44 / hyb 5 / sem 1);golden **73 题 0 失败**(62+11);宇宙 **91**(78+13);family 639+Δ 全绿零新 skip;L4 advisory 上线且 `counts_toward_bid_gate` 结构化消费。

**规格来源:** `D:\knowbase\技术知识库\投标方案审查_整合版.md`(v1.0-integrated):§4.4 规则表 :835-856、§4.7.2 主责表 :940-961、§6.6/6.7 抽取映射表 :2126-2133。

---

## 裁决表(A-续,实现者不得擅改;与规格冲突处以此为准)

| # | 裁决 | 依据 |
|---|---|---|
| A-续-① | **L2-030 方向从 §4.7.2 矩阵**:L1-007 主责(签章位存在性+有效性合并),L2-030 violation 仅在 L1-007 无 definite violation 时保留——实现为 eval_core 条件折叠 `_fold_issues_by_primary(out, "L1-007", ("L2-030",))`;规则卡「抑制 L1-007」字样不采纳(规格内矛盾,矩阵为准)。折叠为 rule 级(无 entity 条件,L1-007 无 entity_keys;entity 级细化挂账)。 | §4.7.2 :949;L1-007 卡实际用 bid.missing_signature_pages(repo 名,A-β2-④) |
| A-续-② | **L2-032 v1 = 两件存在性**(legal_id_proof_present + id_copy_present);授权委托书件的存在性主责留 repo 既有 L1-008(fatal,**禁改 L1-008 检查体**)——spec「授权书缺失→L2-032 主责」场景由 L1-008 fatal 承接,gate 不软化,不引入折叠。三件套 presence 布尔**一律服务端派生**(bid.attachment_index 名称归一匹配),模型自产一律丢弃(换算禁令同款,先例 derive_joins matched/present)。 | C-17 同构;A-β2-④ repo 名优先;禁模型换算铁律 extract.py:113-119 |
| A-续-③ | **L1-006 加 precondition 兑付 C-17**:`tender.deposit_required > 0 and bid.deposit_receipt_present == True`——凭证缺失场景 L1-006 不适用,L2-033(fatal)主责独报,gate 不软化;present=None(清单缺失)同样不适用,L2-033 need_human 兜底。L1-006 金额比对逻辑零改动。 | C-17(规格 :69);§4.7.2 :947-948 |
| A-续-④ | **L2-002 v1 = 册数下限**(`count(bid.volume_index) >= count(tender.volume_specs)`),逐册份数/名称对齐挂账抽取面成熟后;**L2-050 v1 = 零字节+不可读**,MIME-扩展名一致性挂账(需映射表,规格能力挂账同 W2 OCR 先例)。 | det 算子面现状;W2 挂账先例 |
| A-续-⑤ | **抑制引擎**:W9 `_suppress_l3012_by_l2021` 本体不动(6 变异钉在案);新增泛化 `_fold_issues_by_primary(issues, primary_rule_id, folded_rule_ids)` 服务两对新对(L2-051→L3-016/L3-018;L1-007→L2-030),语义=primary 存在 verdict=violation 时折叠 folded 的 violation(need_human 不折叠,suppressed_by 记账,同 W9);rule 级无 entity 条件。 | T4 W9 先例 eval_core.py:60-90 |
| A-续-⑥ | **L4 激活形态**:worker 新增并列常量 `ADVISORY_RULEPACK_PATH`(**不改 RULEPACK_PATH 语义**,三处 fixture 打桩点同步补钉);合包后**单次** `evaluate_fields`(W9/折叠作用于合并面);`RulePack` 增 `meta: dict`(dataclass 尾部默认字段),L4 yaml 注释 meta 升结构化 `meta:` 块;`counts_toward_bid_gate` 消费点=routers `_fatal_hits` 显式 L4 守卫 + worker summarize 排除;现有测试打桩面把 `ADVISORY_RULEPACK_PATH` 一并置 None。 | 侦察报告(L4 激活面);A-β2-⑤ |
| A-续-⑦ | **golden/评测冻结**:golden loader/runner 默认 core 面不动(禁把 merged pack 传入 run_case);cases-l4/ 已隔离;`run_eval.py` 走 worker 全链会见 L4 行,manifest 标注 L4 附带即可,评测门以 golden CLI+family 为准(run_eval 非门禁)。 | golden/loader.py:12 与 worker 解耦实证 |

---

### Task 1: 文件级 subset 三规则 L2-001/002/003(6 条新路径+卡片+golden+三锁)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(LIST_PATHS +4;契约 +2)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(包头注释 41→44;+3 卡)
- Modify: `backend/tests/test_bid_review_registry.py`(EXPECTED_UNIVERSE +6)
- Modify: `backend/tests/test_bid_review_rule_runner.py`(det 计数 35→38+注释;EXPECTED_V1_IDS +3)
- Modify: `backend/tests/test_bid_review_golden.py`(EXPECTED_COVERAGE +3)
- Create: `backend/app/extensions/bid_review/golden/cases/L2-001-composition-missing.yaml`、`L2-002-volume-count-short.yaml`、`L2-003-electronic-files-missing.yaml`
- Modify: `backend/tests/test_bid_review_extract.py`(+2 形状/契约测试)
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`(+3 裁决行)

- [ ] **Step 1: extract.py 路径契约**——`LIST_PATHS`(extract.py:88-106)追加 4 条(纯串列表闸,自动得 `_LIST_CONTRACT`):
```python
        "tender.file_composition",   # L2-001(P1-β批二续,spec §6.6 :2126)
        "bid.file_index",            # L2-001(spec §6.7 :2131)
        "tender.electronic_files",   # L2-003(spec §6.6 :2128)
        "bid.electronic_files",      # L2-003(spec §6.7 :2133)
```
对象列表路径给逐字段契约(追加在 appendix_references 契约附近,:111 区):
```python
FIELD_TYPE_CONTRACTS["tender.volume_specs"] = '[{name:"分册名称", min_copies:"最少份数,数字"}] 对象列表;招标份数要求逐册一行;禁止纯值列表/标量。'
FIELD_TYPE_CONTRACTS["bid.volume_index"] = '[{name:"分册名称(正本/副本 第X册)", copies:"实际份数,数字或null"}] 对象列表;投标分册封面逐册一行;禁止纯值列表/标量。'
```
并更新 :228-230 首段请求计数注释(71→77)。
- [ ] **Step 2: 三张规则卡**(追加在 core yaml L2 段;severity 过 L2 白名单 {fatal,major,minor};evidence 用已注册锚——动手前 grep `anchors.py` 确认 A-TENDER-NOTICE/A-MAIN-TEXT/A-SCHEDULE 已注册,未注册即拒载):
```yaml
  # ── L2-001 投标文件组成齐备(P1-β批二续,spec §4.4 :835;det fatal;文件级第一批)──
  - id: L2-001
    name: 投标文件组成齐备
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.file_composition, bid.file_index]
    check:
      steps:
        - "subset_of(tender.file_composition, bid.file_index)"
    severity: fatal
    evidence: [A-TENDER-NOTICE, A-MAIN-TEXT]
    message_tpl: "投标文件组成缺项:招标要求组成与投标文件索引逐项比对未全部命中"
    fix_tpl: "按招标『投标文件组成』逐项核对分册/正副本/电子版,补齐缺失分册后重新生成索引"
    confidence_gate: 1.0
    enabled: true
  # ── L2-002 分册与份数齐全(spec :836;v1=册数下限,A-续-④;逐册份数对齐挂账)──
  - id: L2-002
    name: 分册与份数齐全
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.volume_specs, bid.volume_index]
    check:
      op: gte
      left: "count(bid.volume_index)"
      right: "count(tender.volume_specs)"
    severity: major
    evidence: [A-MAIN-TEXT, A-TENDER-NOTICE]
    message_tpl: "投标分册数({bid.volume_index})少于招标份数要求册数({tender.volume_specs})"
    fix_tpl: "按招标份数要求补齐分册,每册核对封面与页码"
    confidence_gate: 1.0
    enabled: true
  # ── L2-003 电子标书文件齐备(spec :837)──
  - id: L2-003
    name: 电子标书文件齐备
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.electronic_files, bid.electronic_files]
    check:
      steps:
        - "subset_of(tender.electronic_files, bid.electronic_files)"
    severity: major
    evidence: [A-MAIN-TEXT, A-TENDER-NOTICE]
    message_tpl: "电子标书要求文件未全部提供(加密标书/签章文件/清单源文件比对缺项)"
    fix_tpl: "按招标电子标书要求补齐加密标书、签章文件与清单源文件"
    confidence_gate: 1.0
    enabled: true
```
包头注释条数 41→44(det 35→38 注记)。steps 语义=任一步失败即违例(rule_runner.py:256-257);subset_of 已有 str 守卫(T1 β批二),两侧为列表。
- [ ] **Step 3: golden 三题**(命名正则 `^[A-Z0-9]+-[0-9]+-[a-z0-9-]+$`;fields 键 ⊆ inputs;`'no'` 类歧义键加引号;strict 单规则触发):
`L2-001-composition-missing.yaml`:
```yaml
case: L2-001-composition-missing
desc: 招标要求组成三项,投标索引仅两项→ L2-001 fatal violation(subset_of 缺项)
fields:
  tender.file_composition: [投标函, 授权委托书, 开标一览表]
  bid.file_index: [投标函, 开标一览表]
expect_issues:
  - rule_id: L2-001
    severity: fatal
    contains: ["组成缺项"]
expect_absent: []
strict: true
```
`L2-002-volume-count-short.yaml`:tender.volume_specs 两行 `[{name: 正本, min_copies: 1}, {name: 副本, min_copies: 2}]`,bid.volume_index 一行 `[{name: 正本, copies: 1}]` → L2-002 major violation,contains ["分册数"]。
`L2-003-electronic-files-missing.yaml`:tender.electronic_files `[加密标书, 签章文件, 清单源文件]`,bid.electronic_files `[加密标书, 签章文件]` → L2-003 major violation,contains ["电子标书"]。
- [ ] **Step 4: 三锁同步**——`test_bid_review_rule_runner.py:133` det 计数 `== 35` → `== 38`(:134 注释「L1 13+L2 10+L3 15」),EXPECTED_V1_IDS(+3,按文件现有排序);`test_bid_review_golden.py` EXPECTED_COVERAGE +3(排序插入);`test_bid_review_registry.py` EXPECTED_UNIVERSE +6(保持文件现有排序风格,universe 78→84)。
- [ ] **Step 5: extract 形状测试**(先例 test_bid_review_extract.py:202-213):file_composition 合法列表透传/标量拦平/bool·dict→None 四断言;volume_specs 契约文本含 "min_copies" 断言(先例 :188-189)。
- [ ] **Step 6: CALIBRATION.md** 新增「批P1-β2续 Task1」裁决表段:3 行(引擎对/标注对+结论),rulepack 条数陈述 41→44。
- [ ] **Step 7: 跑绿**:`uv run pytest tests/test_bid_review_extract.py tests/test_bid_review_rule_runner.py tests/test_bid_review_registry.py tests/test_bid_review_golden.py -q` 全绿;golden CLI 65 题 0 失败。
- [ ] **Step 8: Commit**
```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/tests/test_bid_review_registry.py backend/tests/test_bid_review_rule_runner.py backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_extract.py backend/app/extensions/bid_review/golden/cases/L2-001-*.yaml backend/app/extensions/bid_review/golden/cases/L2-002-*.yaml backend/app/extensions/bid_review/golden/cases/L2-003-*.yaml backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): 批二续T1——文件级subset三规则L2-001/002/003落地(file_composition/file_index/volume_specs/volume_index/electronic_files×2六路径;L2-002 v1册数下限A-续-④);包41→44;golden62→65"
```

### Task 2: 文件级完好性三规则 L2-004/050/051(+2 路径+泛化折叠 helper)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(+2 契约)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(44→47;+3 卡)
- Modify: `backend/app/extensions/bid_review/engine/eval_core.py`(+`_fold_issues_by_primary`;聚合后两处调用其一)
- Modify: `backend/tests/test_bid_review_eval_core.py`(+折叠单测)
- Modify: `backend/tests/test_bid_review_registry.py`(+2)/`test_bid_review_rule_runner.py`(det 38→41)/`test_bid_review_golden.py`(+4 case id)
- Create: `golden/cases/L2-004-archive-broken-row.yaml`、`L2-050-empty-unreadable-file.yaml`、`L2-051-draft-marker-hit.yaml`、`L3-016-l2051-folded.yaml`

- [ ] **Step 1: 契约**:
```python
FIELD_TYPE_CONTRACTS["bid.archive_files"] = '[{name:"文件名", size_bytes:"字节数,数字", readable:"是否可读,布尔", encrypted:"是否加密,布尔"}] 对象列表;压缩包内文件逐个一行;禁止纯值列表/标量。'
FIELD_TYPE_CONTRACTS["bid.files"] = '[{name:"文件名", size_bytes:"字节数,数字", readable:"是否可读,布尔"}] 对象列表;全量文件逐个一行;MIME 与扩展名一致性列挂账(A-续-④)不产该键;禁止纯值列表/标量。'
```
- [ ] **Step 2: 折叠 helper**(eval_core,W9 函数之后;泛化但不迁移 W9,A-续-⑤):
```python
def _fold_issues_by_primary(issues, primary_rule_id, folded_rule_ids):
    """主责折叠泛化(A-续-⑤,P1-β批二续):primary 存在 verdict=violation(definite)时,
    折叠 folded 规则的 violation(need_human 不折叠;suppressed_by 记账同 W9)。
    rule 级折叠无 entity 条件(W9 的 entity 交集是 L2-021/L3-012 特化;entity 级细化挂账)。"""
    primary_keys = [i["dedup_key"] for i in issues
                    if i.get("rule_id") == primary_rule_id
                    and i.get("verdict") == "violation" and not i.get("need_human")]
    if not primary_keys:
        return issues
    folded = set(folded_rule_ids)
    kept, folded_n = [], 0
    for it in issues:
        if it.get("rule_id") in folded and it.get("verdict") == "violation" and not it.get("need_human"):
            folded_n += 1
            for pk in primary_keys:
                ...  # 在 primary issue 上记 suppressed_by(读 W9 实现照抄记账形态)
            continue
        kept.append(it)
    if folded_n:
        logger.info("fold_by_primary %s -> %s: %d", primary_rule_id, folded_rule_ids, folded_n)
    return kept
```
(实现照抄 W9 的 suppressed_by 记账形态与零折叠快路径;上为语义规格,以 W9 实代码为准。)
- [ ] **Step 3: 三张卡**——L2-004(op:all,target bid.archive_files,var f,cond `"f.size_bytes > 0 and f.readable == True and f.encrypted == False"`,major,evidence [A-MAIN-TEXT],逐行 violation,entity_keys 自动 [f.name]);L2-050(op:all,target bid.files,var f,cond `"f.size_bytes > 0 and f.readable == True"`,major,同形);L2-051(op:eq,left `"regex(bid.full_text, '草稿|内部版|勿外传|待补充|TBD|XXX|略')"`,right false,major,evidence [A-MAIN-TEXT],message "全文命中草稿/内部标记残留词";卡注释记 A-续-⑤ 抑制 L3-016/018)。expr 原生支持 and/or/not(expr.py:360-364)。
- [ ] **Step 4: 聚合后接线**——eval_core evaluate_fields return 前现有 `out = _suppress_l3012_by_l2021(out)` 之后加 `out = _fold_issues_by_primary(out, "L2-051", ("L3-016", "L3-018"))`(L1-007→L2-030 那行 Task 3 加)。
- [ ] **Step 5: 折叠单测**(先例 w9 六断言形,eval_core 测试):①L2-051 violation 存在→同面 L3-016 violation 折叠、L3-016 need_human 保留;②L2-051 仅 need_human 不武装(照抄 w9⑤ 钉形);③L3-018 同测;④零折叠快路径。Rule 构造 kwargs 全字段(fix_tpl/confidence_gate 必填,β批二教训)。
- [ ] **Step 6: golden 四题**——L2-004(archive_files 一行 size_bytes:0 → major violation contains ["文件"]+一行正常零发声,strict);L2-050(files 一行 readable:false → violation);L2-051(full_text 含 "草稿" → violation contains ["草稿"]);L3-016-l2051-folded(fields 同 L2-051 + L3-016 需要的字段使 L3-016 也发 violation;model_script 按 loader 契约;expect_issues 仅 L2-051,strict:true=零残留证明,先例 L3-012-w9-suppressed)。L3-016 需要的字段先读其卡 inputs。
- [ ] **Step 7: 三锁**——det 38→41+注释;EXPECTED_COVERAGE +3(L3-016 已在表内不重复);EXPECTED_UNIVERSE +2(86)。CALIBRATION 裁决 4 行。
- [ ] **Step 8: 跑绿+Commit**
```bash
git commit -m "feat(bid-review): 批二续T2——文件级完好性三规则L2-004/050/051(archive_files/files路径;MIME挂账A-续-④)+泛化折叠_fold_issues_by_primary(L2-051→L3-016/018,A-续-⑤,W9不动);包44→47;golden65→69"
```

### Task 3: 要件级三规则 L2-030/032/033(5 路径+派生布尔+L1-006 precondition+条件折叠)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(SERVER_DERIVED_PATHS +3;derive_joins +派生块)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(47→50;+3 卡;L1-006 precondition 改一行)
- Modify: `backend/app/extensions/bid_review/engine/eval_core.py`(+L1-007→L2-030 折叠行)
- Modify: `backend/tests/test_bid_review_eval_core.py`(+条件折叠单测)、`test_bid_review_extract.py`(+派生测试,先例 :242)、`test_bid_review_registry.py`(+5,91)、`test_bid_review_rule_runner.py`(det 41→44)、`test_bid_review_golden.py`(+4)
- Create: `golden/cases/L2-030-signature-slot-missing.yaml`、`L2-032-id-pieces-missing.yaml`、`L2-033-deposit-receipt-missing.yaml`、`L2-030-l1007-folded.yaml`

- [ ] **Step 1: 派生布尔**——`SERVER_DERIVED_PATHS`(extract.py:119)加 `"bid.legal_id_proof_present"`、`"bid.id_copy_present"`、`"bid.deposit_receipt_present"`;derive_joins 末尾加块(照 device_model_mismatches 块形;attachment_index 名称 `_normalize_name` 归一后匹配;清单缺失/名称集空→不落键,规则 need_human 诚实降级):
```python
    # 三件套/凭证存在性布尔(A-续-②③,P1-β批二续):bid.attachment_index 名称归一匹配
    # 服务端派生,模型自产一律丢弃(换算禁令同款);缺来源不落键→need_human。
    idx = out.get("bid.attachment_index")
    names = []
    if isinstance(idx, list):
        for item in idx:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                n = _normalize_name(item["name"])
                if n:
                    names.append(n)
    if names:
        def _any_name(patterns):
            return any(re.search(p, n) for n in names for p in patterns)
        out["bid.legal_id_proof_present"] = _any_name((r"法人身份证明", r"法定代表人身份证明"))
        out["bid.id_copy_present"] = _any_name((r"身份证复印", r"身份证件"))
        out["bid.deposit_receipt_present"] = _any_name((r"保证金", r"保函", r"回单"))
```
(extract.py 如未 import re 则补。)
- [ ] **Step 2: 两张 slots 契约**:
```python
FIELD_TYPE_CONTRACTS["tender.signature_slots"] = '[{no:"签署位编号或名称", name:"签署方", page:"页码,数字或null"}] 对象列表;格式文件『签字盖章处』逐位一行;禁止纯值列表/标量。'
FIELD_TYPE_CONTRACTS["bid.signature_slots"] = '[{no:"签署位编号或名称", name:"签署方", page:"页码,数字或null"}] 对象列表;实际签署位逐位一行;禁止纯值列表/标量。'
```
- [ ] **Step 3: 三张卡+L1-006 precondition**——L2-030(op:all,target tender.signature_slots,var t,cond `"t.no in col(bid.signature_slots, 'no')"`,fatal,evidence 用已注册锚(grep anchors.py;A-STAMP/A-BID-LETTER 类),卡注释记 A-续-① 方向);L2-032(steps 两行 `"bid.legal_id_proof_present == True"`/`"bid.id_copy_present == True"`,major,卡注释记 A-续-② 授权件主责留 L1-008);L2-033(op:eq,left `bid.deposit_receipt_present`,right true,fatal,卡注释记 C-17);L1-006 precondition 改 `"tender.deposit_required > 0 and bid.deposit_receipt_present == True"`+注释(A-续-③)。L1-006 的 inputs 加 `bid.deposit_receipt_present`(precondition 字段须在 fields_used)。
- [ ] **Step 4: 条件折叠**——eval_core 聚合后加 `out = _fold_issues_by_primary(out, "L1-007", ("L2-030",))`(A-续-①)。
- [ ] **Step 5: 单测**——派生三布尔(有/无命中/清单缺失不落键,先例 :242);条件折叠(L1-007 violation→L2-030 violation 折叠;L1-007 need_human→L2-030 保留;L1-007 PASS→保留);L2-032 steps 双断言(任一 False→violation;全 True→PASS)。
- [ ] **Step 6: golden 四题**——L2-030(tender 两行 no:[法人章,公章],bid 一行 no:[法人章]→fatal violation contains ["签署位"]+strict);L2-032(attachment_index 名含"法定代表人身份证明"不含身份证复印→legal_id_proof_present=true,id_copy_present=false→major violation);L2-033(deposit_amount=tender.deposit_required=10000 且 attachment_index 无保证金/保函类→L1-006 precondition 不适用零发声+L2-033 fatal violation,strict 钉双规则面);L2-030-l1007-folded(构造 L1-007 violation(bid.missing_signature_pages 非空,hyb 需 model_script full 应答?——L1-007 det 粗筛候选交模型,给 model_script 判 violation 的应答)+L2-030 同面 violation;expect_issues 仅 L1-007,strict=true)。
- [ ] **Step 7: 三锁**——det 41→44;EXPECTED_COVERAGE +3;EXPECTED_UNIVERSE +5(91)。CALIBRATION 4 行。
- [ ] **Step 8: 跑绿+Commit**
```bash
git commit -m "feat(bid-review): 批二续T3——要件级三规则L2-030/032/033(signature_slots双路径+三presence布尔服务端派生禁模型自产A-续-②;L1-006 precondition兑付C-17 A-续-③;L1-007→L2-030条件折叠A-续-①);包47→50(det44);golden69→73;宇宙91"
```

### Task 4: L4 激活后端(meta 结构化+worker 合包+advisory 面)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(RulePack +meta 字段;load_rulepack 读 meta)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml`(注释 meta 升结构化 `meta:` 块,注释保留)
- Modify: `backend/app/extensions/bid_review/worker.py`(+ADVISORY_RULEPACK_PATH;_run_review_stage 合包;summarize advisory)
- Modify: `backend/app/extensions/bid_review/routers.py`(_fatal_hits L4 守卫;_LAYER_RANK +L4;_cross_layer_group 排 L4;list_task_issues +advisory;两渲染器 advisory 节 cap 10;RULEPACK_NAME 归属按前缀;rulepacks 三端点多包)
- Modify: `backend/app/extensions/bid_review/mcp.py`(_handle_rulepacks 两 item;归属前缀)
- Modify: `backend/tests/test_bid_review_worker.py`/`test_bid_review_worker_sem.py`(三处 fixture 同步钉 ADVISORY_RULEPACK_PATH=None)
- Create: `backend/tests/test_bid_review_l4_activation.py`

- [ ] **Step 1: meta 结构化**——RulePack 尾加 `meta: dict = field(default_factory=dict)`(dataclass 默认字段须在尾部,import field);load_rulepack 读 `meta=dict(data.get("meta") or {})`;L4 yaml 顶层加:
```yaml
meta:
  counts_toward_bid_gate: false   # L4 永不入门禁(整合版 §15)
  max_issues_per_report: 10       # advisory 每报告上限
  gate_effect: info               # 门禁效应=纯提示
```
- [ ] **Step 2: worker 合包**——worker.py:58 后加 `ADVISORY_RULEPACK_PATH = Path(__file__).parent / "engine" / "rulepacks" / "bid-review-l4" / "1.0.0.yaml"`;`_run_review_stage`(:512 区)改为:core pack 照旧加载;`ADVISORY_RULEPACK_PATH` 真值时加载 l4 包并 `rules = list(core.rules) + list(l4.rules)` 合一列表走**原单次** `evaluate_fields`(quick 裁剪自动排 L4 全 sem;overrides 作用于合一列表;rule_id 全局唯一已由 lint 保证);RulePackMeta 分母 rules_total=Σ。ADVISORY_RULEPACK_PATH 为 None/不存在时行为=现状(core 单包),fixture 依赖此语义。
- [ ] **Step 3: summarize advisory**——`summarize_issues`(:207-227)正式 fatal/major/minor/info 计数排除 `layer=="L4"`;新增 `"advisory": {"total": N, "by_severity": {...}}`(L4 条目单列;need_human 口径照旧单列)。done 帧 progress.summary 自动携带。
- [ ] **Step 4: routers**——`_fatal_hits`(:570-573)加 `layer != "L4"` 显式守卫;`_LAYER_RANK`(:428)补 `"L4": 3` 且 `_cross_layer_group`(:431-460)整体跳过 L4 条目(advisory 不参与归并、不被 formal 折叠);`list_task_issues`(:463-485)响应加 `"advisory": {"items": [...], "total": N, "by_severity": {...}}`;两渲染器(md :678-691/html :619-634)severity 分节循环外新增「竞争力建议(L4,advisory)」独立尾节(先例 :692-701 偏离表节),条数受包 meta `max_issues_per_report` 封顶(从 ADVISORY_RULEPACK_PATH 读 meta,读不到默认 10);`apply_false_positive`(:393-394)/feedback confirm(:522)/mcp.py:322 的 RulePackMeta 归属改 `_rulepack_name_for(rule_id)`(新小函数:`"bid-review-l4" if rule_id.startswith("L4-") else RULEPACK_NAME`);`list_rulepacks`(:979-996)遍历两包;`rulepack_rule_details`/`set_rule_enabled`(:999-1059)`name != pack.name` 单包判定改按包名查两包表(未知名 404 语义不变)。
- [ ] **Step 5: mcp**——`_handle_rulepacks`(:356-384)两包各一 item;`bid_review_issues` layer 枚举已含 L4 零改。
- [ ] **Step 6: fixture 同步**——test_bid_review_worker.py:127,174 与 test_bid_review_worker_sem.py:143 的 monkeypatch 处补 `monkeypatch.setattr(worker, "ADVISORY_RULEPACK_PATH", None)`(tmp 包测试不吃真 L4)。
- [ ] **Step 7: 激活测试**(新文件):①l4 包 meta 读得 counts_toward_bid_gate=False/max=10;②worker 全链(tmp 库)合并跑产出 L4 issue 且 summarize.advisory.total≥1 而正式 fatal/major 不含 L4;③_fatal_hits 对 L4 fatal(构造)返回空;④_cross_layer_group 不折叠 L4;⑤list_task_issues advisory 分节形状;⑥报告 md/html 含「竞争力建议」节且 ≤10 条;⑦归属:apply_false_positive 到 L4 issue 记入 bid-review-l4 meta 行;⑧rulepacks 端点两 item;set_rule_enabled 可作用于 L4 包;⑨golden 面回归:test_bid_review_golden.py 全量照旧跑(73 题)证明冻结面零触碰。
- [ ] **Step 8: 跑绿+Commit**
```bash
git commit -m "feat(bid-review): 批二续T4——L4激活后端:RulePack.meta结构化+worker并列ADVISORY_RULEPACK_PATH合包单次evaluate(W9/折叠作用于合并面)+summarize排L4出正式计数+advisory分节/report尾节cap10+gate显式守卫+反馈归属按前缀+rulepacks端点双包(A-续-⑥⑦)"
```

### Task 5: L4 激活前端(RulesView 多包+ResultsView advisory 节)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/RulesView.tsx`(data[0] 单包取用→遍历聚合;LAYER_FILTERS + "L4")
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`(advisory 分节消费)

- [ ] **Step 1: RulesView**——:57-58 `data[0]` 改为 `items` 聚合(rules 数组拼接,包名标注);:34 LAYER_FILTERS 加 `"L4"`(pill 复用现有 layer pill 先例 ReviewQueueView.tsx:382)。
- [ ] **Step 2: ResultsView**——severity 分节(:454-462)不动(L4 已被 summarize 排除出正式计数);新增 advisory 折叠节(收 `issues.advisory.items`,空则不渲染;条目复用现有 issue 行组件;标注「竞争力建议 · 不影响提交判定」);verdict-band(:891-935)零改(summary.fatal 已不含 L4)。
- [ ] **Step 3: 测试**——`frontend/tests/unit/`(rstest,镜像 src 结构)加 RulesView 聚合与 ResultsView advisory 节两测;`pnpm lint && pnpm typecheck && pnpm test` 过。人工走查挂账(需登录态,不在本批门禁)。
- [ ] **Step 4: Commit**
```bash
git commit -m "feat(bid-review): 批二续T5——L4激活前端:RulesView多包聚合+L4过滤档+ResultsView竞争力建议advisory分节(不影响提交判定标注)"
```

### Task 6: 台账同步 + CALIBRATION + 全量验收

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`
- Modify: `.wolf/buglog.json` / `.wolf/memory.md`(controller 负责,实现者不碰)

- [ ] **Step 1: 台账**——§0 速览 41/90→**50/90**(L1 16/29 不变;L2 8/26→**17/26**;L3 17/25 不变;L4 结构落地注记更新为「已激活 advisory 面」);§2 矩阵 §4/§11 行同步;§3.1 迁移表零新增(本批无迁移);§4 表:L2 行 8/26→17/26(待建清单移除文件级 -001~004/-050/-051 与要件级 -030/-032/-033,余章节级 -010~014/-011(hyb)、字段级 -040/-042/-043、复合 -025;兑付注记含 A-续-①②③④ 挂账细目);§4 缺口段零变化(本批无新算子);§6 批次注记追加批二续兑付清单+批三排队。
- [ ] **Step 2: 全量验收**
```
uv run pytest tests/ -k bid_review -q            # 全绿零翻转零新 skip
uv run python -m app.extensions.bid_review.golden # 73/73
uv run python -c "from app.extensions.bid_review.engine import registry; print(len(registry.universe()))"  # 91
cd frontend && pnpm lint && pnpm typecheck && pnpm test
```
验收门:①family 绿;②golden 73/0+三方相等 50;③宇宙 91;④commit 链每任务独立;⑤七裁决(A-续-①..⑦)未擅改;⑥`git diff d23e1fe25..HEAD -- backend/app/extensions/bid_review/worker.py backend/app/extensions/bid_review/routers.py` 非空但**逐 hunk 落在 Task 4 Step 4 清单内**(A-β2-⑤ 在本批兑付,红线解除但改动面受控);⑦golden loader/runner 与 cases/(主面新增除外)零意外 diff。
- [ ] **Step 3: Commit**
```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): β批二续账本同步——50/90+L2 17/26+L4激活注记+A-续裁决兑付清单+批三排队"
```
