# bid-review L2-P3 附件匹配负证据 + 同义词归一 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 平件附件行的归一化变体不再直接判 fatal MISSING——近似命中的降 UNKNOWN(near_miss) 交人工，真缺失的携带行级负证据；normalize_name 增同义词折叠。

**Architecture:** 全部改动集中在匹配器纯函数层（`attachments.py`）+ 其唯一消费方（`rule_runner.py` att_check 分支措辞分流）+ checklist 投影新键透传；rulepack 零改动、34 条不动、EXPECTED_COVERAGE 不变。金标准新增 2 题（synonym 命中 FP 探针 / near-miss 降级），near-miss 题 red-first。spec：`docs/superpowers/specs/2026-11-03-bid-review-l2-p3-negative-evidence-synonym-design.md`（commit 05d32c92f）。

**Tech Stack:** Python 3.12 / pytest / PyYAML / difflib（stdlib，零新依赖）。

**执行约束（每个子代理必读）**：
- 只提交 `main-dev-fork`，**永不 push**（controller 收口时统一 push 重试）。
- `.wolf/` 对子代理禁触（controller 专属协议）。
- `git add` 只用显式路径，禁 `-A`/`.`。
- 金标准铁律：既有 49 题必须保持全绿，任何翻红=回归证据，**禁止改标注迁就**。
- 改动文件须带 EAI-CUSTOM 注释（引用 L2-P3 spec §），沿用 `_match_composite` docstring 先例。
- ruff line ≤240，E/F/I；跑分域只查自己改的文件（全树已有 format 债务）。
- PS5.1 写中文文件用 Write/Edit 工具或 node 脚本，禁 `Get-Content|Set-Content` 回写。
- `'no'` 键与数字形 no 值（"3"/"3-1"）在 YAML 一律加引号（bug-3938 类）。

---

### Task 1: 同义词归一（normalize_name 折叠 + 单测 + 金标准 synonym 题 red-first）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`（常量 + 折叠函数 + normalize_name 收尾一行）
- Modify: `backend/tests/test_bid_review_attachments.py`（追加 3 测）
- Create: `backend/app/extensions/bid_review/golden/cases/L2-020-synonym-name-match.yaml`
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`（新增批D节）

- [ ] **Step 1.1: 写失败单测**

在 `backend/tests/test_bid_review_attachments.py` 的 `test_normalize_junk_inputs` 之后追加（保持既有内容零改动）：

```python
# ── L2 P3:同义词归一(spec 2026-11-03 §3.1) ───────────────────────────


def test_normalize_synonym_folds_variants():
    """同义词组折叠到规范形(组首元素);子串语义,组内最长变体优先。"""
    assert normalize_name("企业法人营业执照") == "营业执照"
    assert normalize_name("附件一、企业法人营业执照：") == "营业执照"
    assert normalize_name("年度审计报告") == "审计报告"
    assert normalize_name("2024年度审计报告及财务报表") == "2024审计报告及财务报表"


def test_normalize_copy_suffixes_not_folded():
    """副本/复印件/回执/正本不入同义词表——方向不明变体走 near-miss 门降 UNKNOWN,
    不得经等值通道静默升级 MATCHED(spec §2 决策)。"""
    assert normalize_name("营业执照副本") == "营业执照副本"
    assert normalize_name("中标通知书回执") == "中标通知书回执"


def test_synonym_variant_matches_via_name_channel():
    """招标「营业执照」vs 投标「企业法人营业执照」:折叠后通道②等值命中 MATCHED。"""
    out = match_attachments([_req(no="A-1", name="营业执照")], [_prov(no="", name="企业法人营业执照", page=9)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["extra"] == []
```

- [ ] **Step 1.2: 写失败金标准题（red-first）**

Create `backend/app/extensions/bid_review/golden/cases/L2-020-synonym-name-match.yaml`：

```yaml
case: L2-020-synonym-name-match
desc: 同义词归一——招标「营业执照」vs 投标「企业法人营业执照」,折叠后名称通道②等值命中 MATCHED → 零 L2 条目(变体不假缺失;strict FP 探针,E 族形态)
fields:
  tender.attachment_requirements:
    - {'no': A-1, name: 营业执照, mandatory: true}
  bid.attachment_index:
    - {'no': "", name: 企业法人营业执照}
expect_issues: []
expect_absent: [L2-020, L2-024]
strict: true
checklist:
  unknown_count: 0
  status_by_no: {"A-1": "MATCHED"}
```

- [ ] **Step 1.3: 跑红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v
```
预期：`test_normalize_synonym_folds_variants` / `test_normalize_copy_suffixes_not_folded`（后三条断言对，前两条对——copy 后缀现在就不折叠,该测试本步应绿,作守卫负例）/ `test_synonym_variant_matches_via_name_channel` 红。

```bash
cd backend && PYTHONPATH=. uv run pytest "tests/test_bid_review_golden.py::test_case_L2_020_synonym_name_match" -v 2>&1 | tail -5
```
（用 `-k synonym` 定位实际参数化测试名）预期：RED——变体名双通道落空 → fatal MISSING → strict FP 探针报 unexpected issue。**留红输出作 red-first 证据**（贴入 CALIBRATION 裁决行）。

- [ ] **Step 1.4: 实现**

`backend/app/extensions/bid_review/engine/attachments.py`——`_PREFIX_RE` 定义之后、`def normalize_name` 之前插入：

```python
# L2 P3 同义词组(spec 2026-11-03 §3.1,EAI-CUSTOM):首元素=规范形;子串替换,
# 组内最长变体优先(防部分重叠吞字)。副本/复印件/回执/正本等方向不明变体**不入表**
# ——折叠进等值通道=静默升级 MATCHED,它们由 near-miss 门降 UNKNOWN 交人工。
# ponytail: 模块常量起步,>20 组外置 engine/dicts/synonyms.yaml。
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("营业执照", "企业法人营业执照"),
    ("审计报告", "年度审计报告"),
)


def _fold_synonyms(t: str) -> str:
    for group in _SYNONYM_GROUPS:
        for variant in sorted(group[1:], key=len, reverse=True):
            if variant in t:
                t = t.replace(variant, group[0])
    return t
```

`normalize_name` 收尾行（原 `return t.rstrip(":：..。")`）改为：

```python
    return _fold_synonyms(t.rstrip(":：..。"))
```

- [ ] **Step 1.5: 跑绿 + 金标准零翻红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py tests/test_bid_review_golden.py -v 2>&1 | tail -8
```
预期：attachments 全绿（含新 3 测）；golden **51 题全绿**（49 既有 + synonym 新题）——49 既有零翻红是本步硬门槛，任何翻红停手上报。

- [ ] **Step 1.6: lint 自查**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/attachments.py tests/test_bid_review_attachments.py && uv run ruff format --check app/extensions/bid_review/engine/attachments.py tests/test_bid_review_attachments.py
```

- [ ] **Step 1.7: CALIBRATION 批D节 + 提交**

`CALIBRATION.md` 末尾追加：

```markdown

## 批D(L2-P3 负证据+同义词归一)裁决表

spec docs/superpowers/specs/2026-11-03-bid-review-l2-p3-negative-evidence-synonym-design.md(05d32c92f);引擎能力增强切片——新行为用新题钉,既有 49 题零翻红为回归证据(金标准铁律)。

| case | 裁决 | 结论 |
|---|---|---|
| L2-020-synonym-name-match | red-first→引擎增强 | 落库先红(变体名双通道落空→fatal MISSING→strict FP 探针红);normalize_name 同义词折叠(_SYNONYM_GROUPS 子串替换,组内最长变体优先)后通道② MATCHED→绿;副本/复印件/回执不入表(方向不明,走 near-miss 门降 UNKNOWN) |
```

```bash
git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py backend/app/extensions/bid_review/golden/cases/L2-020-synonym-name-match.yaml backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-P3① 同义词归一——normalize_name 折叠 _SYNONYM_GROUPS(企业法人营业执照/年度审计报告→规范形,子串替换最长优先);金标准 synonym FP 探针 red-first 入库;副本/回执不入表留 near-miss 门"
```

---

### Task 2: 近似命中门 + 行级负证据（match_attachments post-pass + 复合子行证据 + checklist 透传 + 金标准 near-miss 题 red-first）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`（NEAR_MISS_GATE + _sim_cands/_evidence/_near_miss_pass + match_attachments 收尾重构 + _match_composite 证据 + composite 分支 unknown_reason）
- Modify: `backend/tests/test_bid_review_attachments.py`（追加 7 测 + 更新 1 处既有断言）
- Create: `backend/app/extensions/bid_review/golden/cases/L2-020-near-miss-unknown.yaml`
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`

- [ ] **Step 2.1: 写失败单测**

追加到 `test_bid_review_attachments.py` 末尾：

```python
# ── L2 P3:近似命中门 + 行级负证据(spec 2026-11-03 §3.2/§3.3) ───────────


def test_near_miss_downgrades_to_unknown_with_evidence():
    """平件 MISSING 行近似候选 sim≥0.75 → UNKNOWN(near_miss),负证据三键齐。"""
    out = match_attachments(
        [_req(no="E-2", name="中标通知书")],
        [_prov(no="E-1", name="业绩合同", page=3), _prov(no="", name="中标通知书回执", page=40)],
    )
    e = out["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["unknown_reason"] == "near_miss"
    ev = e["negative_evidence"]
    assert ev["channels"] == ["no", "name"]
    assert ev["pool"] == 2
    assert ev["closest"][0]["name"] == "中标通知书回执"
    assert 0.75 <= ev["closest"][0]["sim"] <= 1.0


def test_near_miss_gate_threshold_honored(monkeypatch):
    """门限是模块常量:调高后同一夹具回落 MISSING(阈值真实生效,非恒降级)。"""
    import app.extensions.bid_review.engine.attachments as att

    monkeypatch.setattr(att, "NEAR_MISS_GATE", 0.90)
    out = att.match_attachments([_req(no="E-2", name="中标通知书")], [_prov(no="", name="中标通知书回执", page=40)])
    e = out["per_req"][0]
    assert e["status"] == "MISSING"
    assert e["negative_evidence"]["closest"][0]["sim"] < 0.90
    assert "unknown_reason" not in e


def test_true_missing_records_evidence_without_downgrade():
    """真缺失(跨附件名对):状态不降级,负证据仍记录;closest 滤噪(sim<0.30 不入)。"""
    out = match_attachments([_req(no="E-2", name="中标通知书")], [_prov(no="E-1", name="业绩合同", page=3)])
    e = out["per_req"][0]
    assert e["status"] == "MISSING"
    ev = e["negative_evidence"]
    assert ev["pool"] == 1
    assert ev["closest"] == []  # 中标通知书 vs 业绩合同 零公共字符,sim=0.0 被滤
    assert "unknown_reason" not in e


def test_near_miss_empty_name_short_circuit():
    """req 名归一为空(纯空白)→ 不进门扫描,保持 MISSING;channels 只记实际尝试的。"""
    out = match_attachments([_req(no="Z-9", name="  ")], [_prov(no="", name="营业执照", page=1)])
    e = out["per_req"][0]
    assert e["status"] == "MISSING"
    assert e["negative_evidence"] == {"channels": ["no"], "pool": 1, "closest": []}


def test_composite_sub_row_evidence_only_no_status_change():
    """复合子行 MISSING 只记负证据,状态与父行上卷不变(P3.2 状态门挂账);
    父行零引用诚实 MISSING、negative_evidence=None;子证据池=orphan 归组后未占用者。"""
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
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MISSING"]
    assert e["status"] == "MISSING"
    assert e["negative_evidence"] is None
    assert e["sub_results"][1]["negative_evidence"]["closest"][0]["name"] == "中标通知书回执"
    assert e["sub_results"][1]["negative_evidence"]["pool"] == 1


def test_grouping_failure_row_has_no_negative_evidence():
    """分组失败(orphan)行 unknown_reason=grouping、evidence=None——两种 UNKNOWN 证据形态不混用。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]}
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}, {"no": "3-9", "name": "完税证明", "page": 40}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["unknown_reason"] == "grouping"
    assert e["negative_evidence"] is None


def test_build_checklist_p3_keys_passthrough():
    """投影行携带 unknown_reason/negative_evidence;near-miss 进 counts.unknown 不进 missing。"""
    out = build_checklist(
        [_req(no="E-2", name="中标通知书")],
        [_prov(no="", name="中标通知书回执", page=40)],
        bid_doc_id="bid.pdf",
    )
    it = out["items"][0]
    assert it["status"] == "UNKNOWN"
    assert it["unknown_reason"] == "near_miss"
    assert it["negative_evidence"]["closest"][0]["sim"] >= 0.75
    assert out["counts"]["unknown"] == 1
    assert out["counts"]["missing"] == 0
```

**并更新既有断言一处**——`test_build_checklist_unknown_and_sub_results` 中（子行 evidence 是 schema 扩展,如实更新）：

```python
    assert out["items"][0]["sub_results"] == [
        {"no": "3.1", "name": "营业执照", "found": 0, "status": "MISSING", "negative_evidence": {"channels": ["no", "name"], "pool": 0, "closest": []}}
    ]
```

（3-9 完税证明已归组进父件 taken → 子件证据池 pool=0。）

- [ ] **Step 2.2: 写失败金标准题（red-first）**

Create `backend/app/extensions/bid_review/golden/cases/L2-020-near-miss-unknown.yaml`：

```yaml
case: L2-020-near-miss-unknown
desc: 平件近似命中——招标「中标通知书」vs 投标「中标通知书回执」(方向不明变体),两级精确双落空但近似候选 sim≈0.83≥门限 → UNKNOWN(near_miss) → L2-020 need_human(变体不得直接 fatal 缺失;spec 2026-11-03 §3.2)
fields:
  tender.attachment_requirements:
    - {'no': E-2, name: 中标通知书, mandatory: true}
  bid.attachment_index:
    - {'no': "", name: 中标通知书回执}
expect_issues:
  - rule_id: L2-020
    severity: fatal
    verdict: "need_human"
    contains: ["E-2", "中标通知书"]
    entity: "E-2"
expect_absent: []
strict: true
checklist:
  unknown_count: 1
  status_by_no: {"E-2": "UNKNOWN"}
```

（contains 的「近似候选」由 Task 3 措辞分流落地后补强——本步先钉 verdict+实体。）

- [ ] **Step 2.3: 跑红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -k "near_miss or true_missing or composite_sub_row_evidence or grouping_failure_row or p3_keys" -v
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py -k near_miss -v
```
预期：新 7 测红（negative_evidence/unknown_reason 键不存在）；`test_build_checklist_unknown_and_sub_results` 红（子行 dict 新键）；golden near-miss 题红（现状 fatal violation ≠ need_human verdict）。**留红输出。**

- [ ] **Step 2.4: 实现**

`attachments.py` 顶部 import 区（`import re` 之前按字母序）：

```python
import difflib
```

`_fold_synonyms` 之后追加（门常量 + 三个助手 + 就地降级扫描）：

```python
# L2 P3 近似命中门(spec 2026-11-03 §3.2,EAI-CUSTOM):平件 MISSING 行 × extra 池
# SequenceMatcher 相似度,≥门限降 UNKNOWN(near_miss)——归一化变体不得直接 fatal
# 缺失,交人工;真缺失仍 MISSING 但携带负证据佐证。标定:「中标通知书」vs
# 「中标通知书回执」ratio≈0.83 须入门,跨附件名对(中标通知书 vs 业绩合同)≈0.0
# 须门外;金标准 L2-020-near-miss 题 + 单测(含 monkeypatch 阈值生效钉)双向锁。
NEAR_MISS_GATE = 0.75


def _sim_cands(nm: str, pool: list[dict]) -> list[tuple[float, dict]]:
    """候选相似度降序;nm 或候选名归一为空则不参与(与通道②空名跳过同语义)。"""
    if not nm:
        return []
    return sorted(
        ((difflib.SequenceMatcher(None, nm, normalize_name(p.get("name"))).ratio(), p) for p in pool if normalize_name(p.get("name"))),
        key=lambda t: t[0],
        reverse=True,
    )


def _evidence(channels: list[str], pool: list[dict], cands: list[tuple[float, dict]]) -> dict:
    """行级负证据(spec §3.3):channels=实际尝试通道,pool=未占用提供项数,
    closest=相似度 top-3(≥0.30 滤噪)。"""
    return {
        "channels": channels,
        "pool": len(pool),
        "closest": [
            {"no": str(p.get("no") or ""), "name": str(p.get("name") or ""), "sim": round(s, 4)}
            for s, p in cands[:3]
            if s >= 0.30
        ],
    }


def _near_miss_pass(per_req: list[dict], extra: list[dict]) -> None:
    """就地降级扫描(spec §3.2):只读 extra 池不回写占用;复合父行(sub_results 在场)
    与 found>0 行跳过;req 名归一为空不进门,保持 MISSING。"""
    for e in per_req:
        if e.get("sub_results") is not None or e["found"] > 0:
            continue
        req = e["req"]
        no = str(req.get("no") or "").strip()
        nm = normalize_name(req.get("name"))
        channels = (["no"] if no else []) + (["name"] if nm else [])
        cands = _sim_cands(nm, extra)
        e["negative_evidence"] = _evidence(channels, extra, cands)
        if cands and cands[0][0] >= NEAR_MISS_GATE:
            e["status"] = "UNKNOWN"
            e["unknown_reason"] = "near_miss"
```

`match_attachments` 尾部——原逐 req 循环保持不变，仅把最后两行：

```python
        per_req.append({"req": r, "matched": hits, "found": found, "status": _status_for(found, min_count)})
    return {"per_req": per_req, "extra": [p for i, p in enumerate(prov) if i not in taken]}
```

改为（extra 提前命名 + 降级扫描 + docstring 补 P3 段）：

```python
        per_req.append({"req": r, "matched": hits, "found": found, "status": _status_for(found, min_count)})
    extra = [p for i, p in enumerate(prov) if i not in taken]
    _near_miss_pass(per_req, extra)  # L2 P3:近似命中降 UNKNOWN+行级负证据(spec 2026-11-03 §3.2,EAI-CUSTOM)
    return {"per_req": per_req, "extra": extra}
```

`match_attachments` docstring 末尾补一行：

```
    P3 (spec 2026-11-03):平件 found==0 行经 _near_miss_pass——近似候选 sim≥
    NEAR_MISS_GATE 降 UNKNOWN(near_miss),负证据(negative_evidence)一律记录。
```

复合分支 unknown_reason 标记——原：

```python
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            status = "UNKNOWN" if comp["orphan"] else worst
            per_req.append({"req": r, "matched": [], "found": found, "status": status, "sub_results": comp["sub_results"]})
```

改为：

```python
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            if comp["orphan"]:
                per_req.append({"req": r, "matched": [], "found": found, "status": "UNKNOWN", "unknown_reason": "grouping", "sub_results": comp["sub_results"]})
            else:
                per_req.append({"req": r, "matched": [], "found": found, "status": worst, "sub_results": comp["sub_results"]})
```

`_match_composite`——orphan 归组循环之后、`return` 之前追加（子行只记证据不改状态,P3.2 状态门挂账）：

```python
    # L2 P3 (spec 2026-11-03 §3.3,EAI-CUSTOM):子行 MISSING 只记负证据,不改状态
    # (P3.2 子行状态门挂账——子件走 taken 池,改命中语义会扰动占用记账);
    # 证据池=orphan 归组后仍未占用者;父行 negative_evidence=None(分组失败是
    # 另一种证据形态,不混用)。
    untaken = [p for i, p in enumerate(prov) if i not in taken]
    for s in sub_results:
        if s["status"] == "MISSING":
            s["negative_evidence"] = _evidence(
                (["no"] if s.get("no") else []) + (["name"] if normalize_name(s.get("name")) else []),
                untaken,
                _sim_cands(normalize_name(s.get("name")), untaken),
            )
```

`build_checklist` items 行——`"sub_results": e.get("sub_results") or [],` 之后追加两键：

```python
                "unknown_reason": e.get("unknown_reason"),
                "negative_evidence": e.get("negative_evidence"),
```

并把 `build_checklist` docstring P2 段后补：`P3:行级 unknown_reason/negative_evidence 透传,counts.unknown 含 near_miss 降级。`

- [ ] **Step 2.5: 跑绿 + 金标准零翻红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py tests/test_bid_review_golden.py tests/test_bid_review_rule_runner.py -v 2>&1 | tail -8
```
预期：attachments 全绿（52 测）；golden **52 题全绿**（49+2 新,zero flip）；rule_runner 既有全绿（UNKNOWN 行为未变,措辞分流在 Task 3）。任何既有题翻红停手上报（怀疑 near-miss 门误伤既有夹具→按铁律查引擎,不得改标注）。

- [ ] **Step 2.6: lint 自查**（同 Task 1 Step 1.6 范围）

- [ ] **Step 2.7: CALIBRATION + 提交**

批D节追加两行 + 备忘：

```markdown
| L2-020-near-miss-unknown | red-first→引擎增强 | 落库先红(现状两级精确双落空→fatal MISSING,expect verdict need_human 不符);_near_miss_pass 门(0.75,SequenceMatcher × extra 池)后 UNKNOWN(near_miss)→need_human→绿;门限标定:中标通知书 vs 回执≈0.83 入门/中标通知书 vs 业绩合同≈0.0 门外(单测 monkeypatch 钉阈值真实生效);Task 3 将补强 contains「近似候选」 |
```

```markdown
3. **P3 负证据备忘**:negative_evidence={channels,pool,closest(top3,≥0.30)} 双写面——per_req(rule_runner 消费)+items(端点透传);分组失败行 evidence=None/unknown_reason=grouping,与 near_miss 不混用;复合子行 v1 只记证据不改状态(P3.2 挂账)。
```

```bash
git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py backend/app/extensions/bid_review/golden/cases/L2-020-near-miss-unknown.yaml backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-P3② 近似命中门+行级负证据——平件 MISSING×extra 池 sim≥0.75 降 UNKNOWN(near_miss),负证据{channels,pool,closest} per_req/checklist 双写;复合子行只记证据(状态门 P3.2 挂账);金标准 near-miss 题 red-first 入库"
```

---

### Task 3: att_check 消费分流（unknown_reason 措辞 + 单测 + 金标准 contains 补强）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`（att_check UNKNOWN 循环分流,约 :254-258）
- Modify: `backend/tests/test_bid_review_rule_runner.py`（追加 2 测 + 夹具）
- Modify: `backend/app/extensions/bid_review/golden/cases/L2-020-near-miss-unknown.yaml`（contains 补强）
- Modify: `backend/app/extensions/bid_review/golden/CALIBRATION.md`

- [ ] **Step 3.1: 写失败单测**

追加到 `test_bid_review_rule_runner.py` 末尾（紧随 `test_att_issue_entity_keys_default_empty`）：

```python
# ── L2 P3:UNKNOWN 成因分流措辞(spec 2026-11-03 §3.4) ──────────────────

NEAR_FIELDS = {
    "tender.attachment_requirements": [{"no": "E-2", "name": "中标通知书", "mandatory": "★", "min_count": None}],
    "bid.attachment_index": [{"no": "", "name": "中标通知书回执", "page": 40}],
}


def test_att_check_near_miss_message_mentions_candidate():
    """near_miss UNKNOWN → need_human,措辞带近似候选;entity/dedup 沿用实体键(I-1)。"""
    issues = run_det_rule(_att_rule("att_check"), NEAR_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "need_human"
    assert "近似候选" in issues[0]["message"]
    assert "中标通知书回执" in issues[0]["message"]
    assert issues[0]["entity_keys"] == ["attachment:E-2"]
    assert issues[0]["dedup_key"] == "L2-020|-|attachment:E-2"


def test_att_check_grouping_wording_unchanged():
    """回归面:分组失败措辞不变(golden L2-020-unknown-group-failure contains 依赖)。"""
    issues = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert issues[0]["need_human"] is True
    assert "无法自动分组" in issues[0]["message"]
```

- [ ] **Step 3.2: 跑红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -k "near_miss_message or grouping_wording" -v
```
预期：near_miss 测红（现状统一走「无法自动分组」措辞,「近似候选」不在 message）；grouping 回归测绿（措辞未动）。

- [ ] **Step 3.3: 实现**

`rule_runner.py` att_check 分支——原（:254-258）：

```python
                    for r in unknown:  # 分组失败降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                        nh["entity_keys"] = [_entity_key(r["req"])]
                        nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"  # 审查 I-1:按实体键派生,多复合件不再互吞
                        issues.append(nh)
```

改为：

```python
                    for r in unknown:  # UNKNOWN 降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        # P3 成因分流(spec 2026-11-03 §3.4,EAI-CUSTOM):缺键向后兼容→grouping
                        if r.get("unknown_reason") == "near_miss":
                            cands = (r.get("negative_evidence") or {}).get("closest") or []
                            c0 = cands[0] if cands else {}
                            cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                            sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                            nh = _need_human(rule, f"附件「{_label(r['req'])}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                        else:
                            nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                        nh["entity_keys"] = [_entity_key(r["req"])]
                        nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"  # 审查 I-1:按实体键派生,多行不再互吞
                        issues.append(nh)
```

- [ ] **Step 3.4: 金标准 contains 补强**

`L2-020-near-miss-unknown.yaml` 的 `contains` 行改为：

```yaml
    contains: ["近似候选", "E-2", "中标通知书"]
```

- [ ] **Step 3.5: 跑绿**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py tests/test_bid_review_golden.py -v 2>&1 | tail -6
```
预期：rule_runner 全绿；golden 52 题全绿（near-miss 题措辞补强后仍绿）。

- [ ] **Step 3.6: lint 自查 + CALIBRATION + 提交**

```bash
cd backend && uv run ruff check app/extensions/bid_review/engine/rule_runner.py tests/test_bid_review_rule_runner.py && uv run ruff format --check app/extensions/bid_review/engine/rule_runner.py tests/test_bid_review_rule_runner.py
```

批D节追加：

```markdown
| (L2-020-near-miss-unknown 补强) | 引擎对+题补强 | att_check UNKNOWN 按 unknown_reason 分流措辞——near_miss 带「近似候选」+相似度,grouping 维持原文(golden 分组失败题 contains 依赖回归面);entity/dedup 键两形态同构(I-1);contains 补「近似候选」钉措辞 |
```

```bash
git add backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_rule_runner.py backend/app/extensions/bid_review/golden/cases/L2-020-near-miss-unknown.yaml backend/app/extensions/bid_review/golden/CALIBRATION.md
git commit -m "feat(bid-review): L2-P3③ att_check UNKNOWN 成因分流——near_miss 措辞带近似候选+相似度,grouping 原文不变(回归面);金标准 near-miss 题 contains 补强;缺键向后兼容视同 grouping"
```

---

### Task 4: 收尾（controller 执行——全量回归 + CLI 成绩单 + lint 终查）

- [ ] **Step 4.1: bid_review 全测试族**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_attachments.py tests/test_bid_review_rule_runner.py tests/test_bid_review_metrics.py tests/test_bid_review_worker_pipeline.py tests/test_bid_review_grouping.py -v 2>&1 | tail -5
```
预期：全绿 0 failed（总数较 344 基线 +12 左右）。

- [ ] **Step 4.2: CLI 成绩单**

```bash
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden --report md --out "$CLAUDE_JOB_DIR/tmp/p3-golden-report.json"
```
预期：题数 51（49+2）、失败 0、exit 0；zero_hit 列无 L2-020/L2-024。

- [ ] **Step 4.3: 终检 + push（controller 专属）**

```bash
git rev-list --left-right --count origin/main-dev-fork...main-dev-fork   # push 后须 0\t0
```
- push 重试循环（origin flaky,先例 http.postBuffer=524288000 已配）。
- gateway 容器**不重启**（并发会话在跑;engine 代码改动生效须重启,挂账项,由用户择机）。
- `.wolf/` 收口：memory.md 会话行、anatomy.md 增量（2 个新 golden case）、buglog 无新增（零 bug 修复,能力增强）。

---

## 验收（对照 spec §7）

1. 全 49 金标准题 + bid_review 全测试族绿（Task 2.5/4.1）。
2. 新 2 题入库,near-miss 题 red-first 证据留档 CALIBRATION 批D（Step 2.3 红 → 2.5 绿）。
3. checklist 投影携带 negative_evidence/unknown_reason 且端点透传（test_build_checklist_p3_keys_passthrough;端点 routers.py:802 直接返回 build_checklist dict,无需改路由）。
4. near-miss need_human 措辞带近似候选,entity/dedup 键不互吞（test_att_check_near_miss_message_mentions_candidate）。
5. 既有 MISSING 语义零漂移（49 既有题零翻红为证）。

## 挂账（本计划不做）

复合件子行 near-miss **状态门**（P3.2）｜前端核对表卡近似候选/负证据展示｜同义词表 YAML 外置（>20 组）｜阈值 rulepack 级可配置｜指纹通道 / L0-L5 分层抽取管线（二期抽取引擎立项）。
