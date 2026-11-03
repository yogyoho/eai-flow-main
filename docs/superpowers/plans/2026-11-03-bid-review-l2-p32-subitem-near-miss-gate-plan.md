# L2-P3.2 复合子行 near-miss 状态门 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复合附件 MISSING 子行同入 P3 近似门——sim≥NEAR_MISS_GATE 降子行 UNKNOWN(near_miss),父行上卷 UNKNOWN,att_check 逐子行 need_human 点名父件+子件+候选;伪缺失不得 fatal。

**Architecture:** delta 切片,沿用 P3 spec 机制(门常量/负证据模式/金标准纪律)。attachments.py 子行门(只读后处理,零 taken 触碰)+父行 unknown_reason 戳记;rule_runner.py UNKNOWN 循环改三分支(子近似/平件近似/grouping),平件与 grouping 措辞逐字节不变。投影与 att_count 零改动(已证明,spec §3/§4)。

**Tech Stack:** Python 3.12 + pytest + ruff;金标准 CLI(`python -m app.extensions.bid_review.golden`)。

**Spec:** `docs/superpowers/specs/2026-11-03-bid-review-l2-p32-subitem-near-miss-gate-design.md`(commits a9a01210e + 504cb4f37 勘误)

---

## 执行约束(每个 implementer 必读)

1. **分支**: 只提交 `main-dev-fork`。**子代理绝不 push**——controller 收尾时统一 push,重试直至 `git rev-list --left-right --count origin/main-dev-fork...main-dev-fork` 输出 `0\t0`。
2. **git add 只用显式路径**;`docs/superpowers/` 在 .gitignore,须 `git add -f`;**禁止** `git add -A` / `git add .`。
3. **他人 WIP 不碰**: `backend/app/extensions/contract_price/service.py`、`backend/app/extensions/settings/routers.py`、全部 frontend 文件。
4. **`.wolf/` 对子代理禁入**(controller 收尾统一记账)。
5. **EAI-CUSTOM 注释**: 引擎改动处必须注释引用本切片 spec 日期+章节(样例见代码块)。
6. **ruff**: line-length 240,只对**本计划触碰的文件**跑 check+format(全树存量 format 债不修)。
7. **金标准铁律**: 标注错改标注、引擎错先修引擎;新题 red-first;既有 51 题**零翻红**;禁止改标注迁就引擎。
8. **中文文件一律用 Write/Edit 工具**(PS5.1 管道回写会乱码)。
9. **YAML**: 'no' 键一律单引号、值按既有 case 风格(bug-3938);新 case 模仿 `L2-020-near-miss-unknown.yaml`。
10. **命令**从 `backend/` 目录取,前缀 `PYTHONPATH=.`: `cd backend && PYTHONPATH=. uv run pytest ...` / `PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md --out <path>`。
11. **计数口径**(cerebrum 三数): `cases/*.yaml` 文件数 = CLI total = `test_golden_case[*]` 参数化数。当前 51,本切片后 **52**。

## 影响面审计结论(已核,implementer 勿重推)

- 既有单测**恰一处按设计翻红**: `test_composite_sub_row_evidence_only_no_status_change`(attachments 测试 :373,夹具正是 sim≈0.8333 可降级对)→ 按设计重写。其余复合夹具(rolls_up/group_failure/zero_reference/orphan_by_parent_name/mixed_pool/checklist_unknown/sub_dot_form)的未占用池为空或候选门外,**全部零翻红**。
- rule_runner 既有夹具 COMP_FIELDS/COMP2_FIELDS 孤儿吸干池子,NEAR_FIELDS 是平件——既有 21 测全零翻红。
- 金标准 51 题: group-failure/three-channel 无 MISSING 子行,门不触发——零翻红预期,Task 3 全量证。

---

### Task 1: 金标准题 red-first + 引擎子行门/父行戳记

**Files:**
- Create: `backend/app/extensions/bid_review/golden/cases/L2-020-subitem-near-miss-unknown.yaml`
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`(`_match_composite` 尾块 :160-171、`match_attachments` 复合分支 :220-228、`match_attachments` docstring、模块 docstring)
- Modify: `backend/tests/test_bid_review_attachments.py`(重写 :373-390 一测;文件尾追加 4 测)
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`(批D +2 行)

- [ ] **Step 1.1: 写金标准题(最终期望一次到位)**

```yaml
case: L2-020-subitem-near-miss-unknown
desc: 复合子件近似命中——父件「资格审查文件」子件 3.2「中标通知书」vs 池内「中标通知书回执」(no 留空避开 _refs_parent 孤儿池),子行 sim≈0.83≥门限 → 子行 UNKNOWN(near_miss) → 父行上卷 UNKNOWN → L2-020 need_human 点名父件+子件+候选(P3.2;spec 2026-11-03 §5)
fields:
  tender.attachment_requirements:
    - {'no': "3", name: 资格审查文件, mandatory: true, sub_items: [{'no': "3.1", name: 营业执照}, {'no': "3.2", name: 中标通知书}]}
  bid.attachment_index:
    - {'no': "3-1", name: 营业执照}
    - {'no': "", name: 中标通知书回执}
expect_issues:
  - rule_id: L2-020
    severity: fatal
    verdict: "need_human"
    contains: ["子件", "3.2", "中标通知书", "近似候选"]
    entity: "3.2"
expect_absent: [L2-024]
strict: true
checklist:
  unknown_count: 1
  status_by_no: {"3": "UNKNOWN"}
```

夹具要点(注释已入 desc): `{no: "", name: 中标通知书回执}` 刻意不写成 `3-2回执`——那会命中 `_refs_parent` 进孤儿池被 taken 吸走,证据池就被污染了。子件 3.2 三通道皆空(①no 不等 ②位置 `3-2` 不等 ③名称归一不等),落 MISSING → 门降级。

- [ ] **Step 1.2: 跑 CLI 取落红证据**

```bash
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md --out "$CLAUDE_JOB_DIR/tmp/p32-red1.json"; echo "exit=$?"
```

预期: `total=52, failed=1`(新题)——现引擎子行 MISSING → 父行 MISSING → L2-020 **fatal violation**,与 `verdict: need_human` 期望背离。其余 51 题零翻红。**把这份输出存好,Step 1.8 入 CALIBRATION。** 若 failed≠1 或失败的是别的题: 停,回报 controller(夹具事故或预期错)。

- [ ] **Step 1.3: 重写翻红钉 + 追加 4 新测**(test_bid_review_attachments.py)

删除 `test_composite_sub_row_evidence_only_no_status_change`(:373-390,P3 v1 证据钉,行为按设计消失),原位放:

```python
def test_composite_sub_row_near_miss_downgrades():
    """P3.2:复合子行 MISSING 同入近似门——sim≥0.75 → 子行 UNKNOWN(near_miss),
    父行经 _SUB_STATUS_ORDER 上卷 UNKNOWN 且 unknown_reason="near_miss";
    子行负证据仍在;父行 negative_evidence=None(证据在子行,父级不混用)。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}],
    }
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "X-7", "name": "中标通知书回执", "page": 40},  # 不引用父号 3 → 不 orphan,留池
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "UNKNOWN"]
    assert e["sub_results"][1]["unknown_reason"] == "near_miss"
    assert e["sub_results"][1]["negative_evidence"]["closest"][0]["name"] == "中标通知书回执"
    assert e["sub_results"][1]["negative_evidence"]["pool"] == 1
    assert e["status"] == "UNKNOWN"
    assert e["unknown_reason"] == "near_miss"
    assert e["negative_evidence"] is None
```

文件尾追加:

```python
def test_composite_sub_near_miss_gate_threshold_honored(monkeypatch):
    """门限是模块常量:调高后子行回落 MISSING、父行 MISSING(阈值真实生效,非恒降级);
    父行形状归一——unknown_reason 键在场且为 None(P3.2 §1.2)。"""
    import app.extensions.bid_review.engine.attachments as att

    monkeypatch.setattr(att, "NEAR_MISS_GATE", 0.90)
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}],
    }
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}, {"no": "X-7", "name": "中标通知书回执", "page": 40}]
    e = att.match_attachments([req], prov)["per_req"][0]
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MISSING"]
    assert "unknown_reason" not in e["sub_results"][1]
    assert e["status"] == "MISSING"
    assert e.get("unknown_reason") is None


def test_composite_orphan_and_sub_near_miss_coexist():
    """孤儿(3-9)与子行近似(X-7)并存:父行戳 grouping(孤儿是父级事实,不被覆盖),
    子行各自 near_miss——两因各自成话的引擎侧前提(P3.2 §1.2 优先级裁决)。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}],
    }
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 39},
        {"no": "X-7", "name": "中标通知书回执", "page": 40},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["unknown_reason"] == "grouping"
    assert e["sub_results"][1]["status"] == "UNKNOWN"
    assert e["sub_results"][1]["unknown_reason"] == "near_miss"
    assert e["sub_results"][1]["negative_evidence"]["pool"] == 1  # 3-9 归孤儿池,X-7 才在证据池


def test_composite_sub_empty_name_short_circuit():
    """子件名归一为空 → _sim_cands 空 → 不进门,保持 MISSING;证据 channels 只记 no。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "  "}],
    }
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}, {"no": "X-7", "name": "中标通知书回执", "page": 40}]
    e = match_attachments([req], prov)["per_req"][0]
    s = e["sub_results"][1]
    assert s["status"] == "MISSING"
    assert s["negative_evidence"] == {"channels": ["no"], "pool": 1, "closest": []}


def test_build_checklist_sub_row_p32_keys_passthrough():
    """投影:子行 UNKNOWN(near_miss) 键原样透传(sub_results 不触碰);counts.unknown
    收父行,missing 不收(P3.2 §3 零改动证明的测试面)。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}],
    }
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}, {"no": "X-7", "name": "中标通知书回执", "page": 40}]
    out = build_checklist([req], prov, bid_doc_id="bid.pdf")
    sub = out["items"][0]["sub_results"][1]
    assert sub["status"] == "UNKNOWN"
    assert sub["unknown_reason"] == "near_miss"
    assert sub["negative_evidence"]["closest"][0]["sim"] >= 0.75
    assert out["counts"]["unknown"] == 1
    assert out["counts"]["missing"] == 0
```

- [ ] **Step 1.4: 跑模块验红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v
```

预期: **38 测中 5 FAIL**(重写钉 + 4 新)、33 PASS。引擎未动,红是预期。

- [ ] **Step 1.5: 实现引擎(attachments.py)**

(a) `_match_composite` 尾块(:160-171)整块替换为:

```python
    # L2 P3 (spec 2026-11-03 §3.3,EAI-CUSTOM):子行 MISSING 记负证据;P3.2 (spec
    # 2026-11-03 §1.1,EAI-CUSTOM):同入近似门——sim≥NEAR_MISS_GATE 降 UNKNOWN(near_miss),
    # 父行经 _SUB_STATUS_ORDER 上卷。只读后处理不回写 taken,占用记账零触碰;
    # 真缺失(门外)仍 MISSING。证据池=orphan 归组后仍未占用者;父行
    # negative_evidence=None(分组失败是另一种证据形态,不混用)。
    untaken = [p for i, p in enumerate(prov) if i not in taken]
    for s in sub_results:
        if s["status"] == "MISSING":
            channels = (["no"] if s.get("no") else []) + (["name"] if normalize_name(s.get("name")) else [])
            cands = _sim_cands(normalize_name(s.get("name")), untaken)
            if cands and cands[0][0] >= NEAR_MISS_GATE:  # 门判定用 raw ratio,与平件门同规
                s["status"] = "UNKNOWN"
                s["unknown_reason"] = "near_miss"
            s["negative_evidence"] = _evidence(channels, untaken, cands)
```

(b) `match_attachments` 复合分支(:222-228)整块替换为:

```python
        if _sub_items(r):
            comp = _match_composite(r, prov, taken)
            found = sum(s["found"] for s in comp["sub_results"])
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            if comp["orphan"]:
                per_req.append({"req": r, "matched": [], "found": found, "status": "UNKNOWN", "unknown_reason": "grouping", "negative_evidence": None, "sub_results": comp["sub_results"]})
            else:
                # L2 P3.2 (spec 2026-11-03 §1.2,EAI-CUSTOM):父行戳记=子行 near_miss 传播,
                # 供投影/att_check 分流消费;orphan 优先 grouping 不被覆盖(孤儿是父级事实)。
                sub_nm = any(s.get("unknown_reason") == "near_miss" for s in comp["sub_results"])
                per_req.append({"req": r, "matched": [], "found": found, "status": worst, "unknown_reason": "near_miss" if sub_nm else None, "negative_evidence": None, "sub_results": comp["sub_results"]})
            continue
```

(c) `match_attachments` docstring 末行追加一句:

```python
    P3.2 (spec 2026-11-03):复合子行 MISSING 同入近似门降 UNKNOWN(near_miss),
    父行上卷 UNKNOWN 并带 unknown_reason 戳记(orphan 优先 grouping)。
```

(d) 模块 docstring(:1-4)「P2 复合附件…」句后追加:

```python
P3.2:子行 MISSING 同入近似门降 UNKNOWN,父行上卷+unknown_reason 戳记(spec 2026-11-03)。
```

- [ ] **Step 1.6: 跑模块验绿**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v
```

预期: **38 passed**。

- [ ] **Step 1.7: 跑 CLI——预期中间态红**

```bash
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md --out "$CLAUDE_JOB_DIR/tmp/p32-red2.json"; echo "exit=$?"
```

预期: `total=52, failed=1`(仅新题,**contains 断言红**: 父行已带 `unknown_reason="near_miss"`,但 rule_runner 仍走平件 near-miss 分支 → 消息渲染「近似候选「无近似候选记录」」,不含「子件」「3.2」)。verdict/checklist 应已绿。**这是预期中间态,本任务禁止碰 rule_runner.py**——Task 2 收口。

- [ ] **Step 1.8: CALIBRATION 批D +2 行**(读该文件批D节,按既有行格式追加;内容如下)

行1: `L2-020-subitem-near-miss-unknown | red-first 落红(引擎变更前):子行 MISSING→父行 MISSING→L2-020 fatal violation,期望 need_human | 2026-11-03 P3.2 Task1`
行2: `L2-020-subitem-near-miss-unknown | 中间态落红(Task1 引擎后):父行 near_miss 误入平件分支→消息「无近似候选记录」,contains 缺「子件」「3.2」;Task2 三分支收口 | 2026-11-03 P3.2 Task1`

- [ ] **Step 1.9: ruff**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/attachments.py tests/test_bid_review_attachments.py && uv run ruff format --check app/extensions/bid_review/engine/attachments.py tests/test_bid_review_attachments.py
```

预期: 双绿。format --check 红则 `uv run ruff format <文件>` 后重跑测试。

- [ ] **Step 1.10: Commit**

```bash
git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py backend/app/extensions/bid_review/golden/cases/L2-020-subitem-near-miss-unknown.yaml backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-P3.2① 复合子行 near-miss 状态门——子行 MISSING 同入近似门降 UNKNOWN(near_miss,只读不碰 taken),父行 worst 上卷+unknown_reason 戳记(orphan 优先 grouping);金标准复合题 red-first 入库;单测 1 按设计翻红重写+4 新增"
```

---

### Task 2: att_check 三分支 + 金标闭环

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(:254-267 UNKNOWN 循环整块替换)
- Modify: `backend/tests/test_bid_review_rule_runner.py`(:350 文件尾追加 2 夹具+2 测)

- [ ] **Step 2.1: 追加 red 测试**(test_bid_review_rule_runner.py 尾部,紧跟 `test_att_check_grouping_wording_unchanged` 之后)

```python
# ── L2 P3.2:复合子行 near-miss 分流(spec 2026-11-03 §2) ──────────────────

SUB_NEAR_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "", "name": "中标通知书回执", "page": 40},  # 不引用父号,留池;sim≈0.83≥0.75
    ],
}

SUB_NEAR_ORPHAN_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 39},  # 引用父号,归属不了 → 孤儿
        {"no": "X-7", "name": "中标通知书回执", "page": 40},
    ],
}


def test_att_check_sub_near_miss_message_names_subitem():
    """P3.2:子行 near_miss → need_human 点名父件+子件+候选;dedup 按子行实体键
    (I-1 同规);不得走 grouping 话术,不得渲染「无近似候选记录」(候选在场)。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_NEAR_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "need_human"
    assert "子件" in issues[0]["message"]
    assert "3.2" in issues[0]["message"]
    assert "中标通知书" in issues[0]["message"]
    assert "近似候选" in issues[0]["message"]
    assert "0.83" in issues[0]["message"]  # .2f 渲染钉(fixture ratio≈0.8333 确定性)
    assert "无法自动分组" not in issues[0]["message"]
    assert "无近似候选记录" not in issues[0]["message"]
    assert issues[0]["entity_keys"] == ["attachment:3.2"]
    assert issues[0]["dedup_key"] == "L2-020|-|attachment:3.2"


def test_att_check_orphan_and_sub_near_miss_both_messages():
    """孤儿+子近似并存:子近似消息+grouping 消息各自成话,dedup 键互异不互吞。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_NEAR_ORPHAN_FIELDS)
    assert len(issues) == 2
    assert keys := {i["dedup_key"] for i in issues}
    assert keys == {"L2-020|-|attachment:3.2", "L2-020|-|attachment:3"}
    assert any("近似候选" in i["message"] for i in issues)
    assert any("无法自动分组" in i["message"] for i in issues)
    assert all(i["need_human"] is True for i in issues)
```

- [ ] **Step 2.2: 跑模块验红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v
```

预期: **23 测中 2 FAIL**(新 2 测;Task-1 引擎态下父行走平件 near-miss 分支/entity_keys 是 attachment:3)、21 PASS(含 grouping 措辞钉与 COMP2 dedup 钉——引擎已动它们不红)。

- [ ] **Step 2.3: 实现三分支(rule_runner.py)**

`for r in unknown:` 循环(:254-267)整块替换为:

```python
                    for r in unknown:  # UNKNOWN 降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        # P3/P3.2 成因分流(spec 2026-11-03 §2,EAI-CUSTOM):行形状异构
                        # (旧数据缺键/grouping 行 evidence=None),消费一律 .get();
                        # 子行近似→逐子行 need_human 点名父件+子件+候选,grouping 孤儿另发,
                        # 两因不互吞;平件/grouping 措辞与 P3 逐字节一致(golden contains 回归面)。
                        subs_nm = [s for s in (r.get("sub_results") or []) if s.get("unknown_reason") == "near_miss"]
                        if subs_nm:
                            for s in subs_nm:
                                cands = (s.get("negative_evidence") or {}).get("closest") or []
                                c0 = cands[0] if cands else {}
                                cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                                sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                                nh["entity_keys"] = [_entity_key(s)]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"  # 按子行实体键派生(I-1 同规)
                                issues.append(nh)
                            if r.get("unknown_reason") == "grouping":  # 孤儿+子近似并存:两因各自成话
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                                nh["entity_keys"] = [_entity_key(r["req"])]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                                issues.append(nh)
                        elif r.get("unknown_reason") == "near_miss":
                            cands = (r.get("negative_evidence") or {}).get("closest") or []
                            c0 = cands[0] if cands else {}
                            cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                            sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                            nh = _need_human(rule, f"附件「{_label(r['req'])}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                            nh["entity_keys"] = [_entity_key(r["req"])]
                            nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                            issues.append(nh)
                        else:
                            nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                            nh["entity_keys"] = [_entity_key(r["req"])]
                            nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                            issues.append(nh)
```

话术钉: 子行消息 `复合附件「3 资格审查文件」子件「3.2 中标通知书」未精确命中,近似候选「中标通知书回执」(相似度 0.83),需人工核对`;平件 elif 与 grouping else 两分支的 f-string **与 P3 现行逐字节一致**,不得顺手改写。

- [ ] **Step 2.4: 跑模块验绿**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v
```

预期: **23 passed**(含 `test_att_check_grouping_wording_unchanged`、`test_att_check_near_miss_message_mentions_candidate`、`test_att_unknown_issues_unique_dedup_keys` 三个零改动守护钉)。

- [ ] **Step 2.5: 金标闭环**

```bash
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md --out "$CLAUDE_JOB_DIR/tmp/p32-green.json"; echo "exit=$?"
```

预期: `total=52, failed=0, exit=0`。若新题仍红: 对照消息实际输出 vs contains 逐词排差;禁止改标注迁就。

- [ ] **Step 2.6: CALIBRATION 批D +1 行**

行: `L2-020-subitem-near-miss-unknown | contains 断言转绿:三分支后消息点名「3.2 中标通知书」+「近似候选」+0.83;既有 51 题零翻红 | 2026-11-03 P3.2 Task2`

- [ ] **Step 2.7: ruff + Commit**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/rule_runner.py tests/test_bid_review_rule_runner.py && uv run ruff format --check app/extensions/bid_review/engine/rule_runner.py tests/test_bid_review_rule_runner.py
git add backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_rule_runner.py backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-P3.2② att_check 三分支——子行 near_miss 逐子行 need_human 点名父件+子件+候选(dedup 按子行实体键),孤儿+子近似并存各自成话;平件/grouping 措辞逐字节不变;金标准 52/52 闭环"
```

---

### Task 3: 全量验证收尾

**Files:** 无代码改动(验证门;仅当发现漂移时修复并说明)。

- [ ] **Step 3.1: bid_review 全家**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k "bid_review" -q
```

预期: **367 passed / 6 skipped**(P3 收尾基线 359+6,本切片净增 8: attachments +4 净、rule_runner +2、golden 参数化 +1、——注意 attachments 是 -1 重写 +5 新 = +4)。实际数如实报告,偏差须解释。

- [ ] **Step 3.2: 三数口径核**(cerebrum)

```bash
ls backend/app/extensions/bid_review/golden/cases/*.yaml | wc -l
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py -k "golden_case" --collect-only -q | tail -3
```

预期: 三处皆 **52**。

- [ ] **Step 3.3: taken 零触碰核**

```bash
git diff 52cfcb4ce..HEAD -- backend/app/extensions/bid_review/engine/attachments.py | grep -c "^+.*taken\.add" ; true
```

预期: `0`(新增行零 `taken.add`;既有行不计,`^+` 只看新增)。

- [ ] **Step 3.4: ruff 终检**(两引擎文件+两测试文件 check+format --check 全绿)

- [ ] **Step 3.5: 向 controller 报告**(完成/偏差/数据),controller 走 push+收尾协议。

---

## Task 2 补遗（Task 1 双审 Minor 清偿,2026-11-03 质量审查 Minor-1/2/3/6;与 Task 2 同 commit）

- [ ] **A1(Minor-3 断言收紧)**: tests/test_bid_review_attachments.py 阈值钉中 `assert e.get("unknown_reason") is None` 改为 `assert e["unknown_reason"] is None`(缺席即 KeyError,真钉形状归一)。

- [ ] **A2(Minor-6 PARTIAL 前置钉)**: attachments 测试文件尾追加:

```python
def test_composite_sub_partial_not_gated():
    """P3.2 门前置钉:子件 min_count=2 且 found=1(PARTIAL)不入门——池内虽有门内候选
    (营业执照副本 sim≈0.8),保持 PARTIAL、无 unknown_reason/负证据(与平件 found>0 跳过对偶)。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [{"no": "3.1", "name": "营业执照", "min_count": 2}],
    }
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "X-7", "name": "营业执照副本", "page": 40},  # 位置/名称通道外,留池;sim≈0.8 门内
    ]
    e = match_attachments([req], prov)["per_req"][0]
    s = e["sub_results"][0]
    assert s["status"] == "PARTIAL"
    assert "unknown_reason" not in s
    assert "negative_evidence" not in s
    assert e["status"] == "PARTIAL"
    assert e.get("unknown_reason") is None
```

- [ ] **A3(Minor-2 混合态钉;枚举已挂账 spec §8)**: attachments 测试文件尾追加:

```python
def test_composite_mixed_cause_parent_near_miss_stamp():
    """混合成因钉(审查 Minor-2):子 A near_miss + 子 B 真缺失并存 → 父行 UNKNOWN
    unknown_reason="near_miss";A UNKNOWN 带证据,B 保持 MISSING 带证据——
    子级真缺面在 checklist sub_results(issue 面子件枚举已挂账,见 spec §8)。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [
            {"no": "3.1", "name": "营业执照"},
            {"no": "3.2", "name": "中标通知书"},
            {"no": "3.3", "name": "资质证书"},
        ],
    }
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "X-7", "name": "中标通知书回执", "page": 40},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["unknown_reason"] == "near_miss"
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "UNKNOWN", "MISSING"]
    assert e["sub_results"][1]["unknown_reason"] == "near_miss"
    assert e["sub_results"][2]["negative_evidence"]["pool"] == 1
```

- [ ] **A4(Minor-1 连坐注记)**: Task 2 的 CALIBRATION 编辑(Step 2.6)同时把批D 行2 尾部补一句: `;连坐: red 窗口期 test_cli_main_exit_codes 同红(CLI rc=1),非回归`。

## Task 3 补遗

- [ ] **B1(审查 Minor-5)**: CALIBRATION 批D 备忘段「复合子行 v1 只记证据不改状态(P3.2 挂账)」已陈旧——改为「复合子行 P3.2 已同入近似门(见本批 2026-11-03 三行)」。

- [ ] **B2(Task 2 质量审查 Minor-2,断言统一)**: tests/test_bid_review_attachments.py `test_composite_sub_partial_not_gated` 末行 `assert e.get("unknown_reason") is None` 改为 `assert e["unknown_reason"] is None`(引擎非 orphan 复合父行恒写该键,与 A1 钉法统一;子行上的 `"unknown_reason" not in s` / `"negative_evidence" not in s` 两断言**不动**——缺席钉正是其意图)。

- [ ] **B3(Task 2 质量审查 Minor-3,注释归因校正)**: rule_runner.py 三分支注释块中「行形状异构(旧数据缺键/grouping 行 evidence=None),消费一律 .get();」改为「行种类异构(平件/复合/grouping 三形态,键随形态有无)+引擎演进防漂移,消费一律 .get();」——EAI-CUSTOM 头与 spec 引用行不动;**f-string 各行禁碰**(golden contains 回归面)。

- [ ] **B4(Task 2 质量审查 Minor-1,配对钉)**: tests/test_bid_review_rule_runner.py `test_att_check_orphan_and_sub_near_miss_both_messages` 在 dedup 键集合断言后追加配对断言:

```python
    sub_msg = next(i for i in issues if "近似候选" in i["message"])
    assert sub_msg["dedup_key"] == "L2-020|-|attachment:3.2"
    grp_msg = next(i for i in issues if "无法自动分组" in i["message"])
    assert grp_msg["dedup_key"] == "L2-020|-|attachment:3"
```

(消息↔键双向钉死,防配对错位回归。)

---

## Self-Review(已跑)

1. **Spec 覆盖**: §1.1→Task1 Step1.5(a);§1.2→Step1.5(b);§2→Task2 Step2.3;§3→Task1 `test_build_checklist_sub_row_p32_keys_passthrough`;§4 零改动(无任务触碰 att_count,守护钉 `test_att_count_ignores_unknown` 在场);§5→Task1 Step1.1/1.2;§6→各验证步;§7→Task3。
2. **占位扫描**: 无 TBD/TODO;所有代码步骤带完整代码。
3. **类型一致性**: `unknown_reason`/`negative_evidence`/`NEAR_MISS_GATE`/`_sim_cands`/`_evidence`/`_entity_key`/`_label` 各任务间拼写一致,与现库签名一致(已对照源码)。
4. **计数勘误已吸收**: spec 50→52 勘误(504cb4f37),本计划全程用 52。

## 挂账(本计划不做)

前端子行 near-miss 展示(与平件负证据展示并轨的 UI 切片);阈值可配置;同义词 YAML 外置;指纹通道/L0-L5 抽取管线;子行 evidence.channels 位置通道元数据。
