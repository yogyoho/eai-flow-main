# L2 候选→确认条目 entity 继承(join key) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行,429 配额裁决沿前例)。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-l2-candidate-entity-join-design.md`

**Goal:** hyb det 候选经模型确认后 entity_keys 不再丢失——候选 id 注入+模型回显 join,确认条目继承实体。

**Architecture:** 候选段 JSON 加 id + 指令加回显要求 → run_sem_rule 回条按 clause_id 查 cand_map 继承;查不回=现状(弱而非坏)。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档

- [ ] spec + plan 落盘提交(git add -f docs/superpowers)。

### Task 2: llm_verify +2(TDD)

**Files:**
- Modify: `backend/tests/test_bid_review_llm_verify.py`(+2)

- [ ] **Step 2.1: 先写测试**(文件尾指纹区之后;夹具复用 FP_RULE/FP_FIELDS/_isolate_fp_dict;证据用 DOCS 可对齐文本防七道误翻):

```python
@pytest.mark.asyncio
async def test_candidate_entity_inherited_on_echoed_cand_id(tmp_path, monkeypatch):
    """模型回显候选 id(C1)→ 确认条目继承 det 候选 entity_keys(spec 2026-11-04 §1)。"""
    _isolate_fp_dict(tmp_path, monkeypatch)
    resp = {"verdicts": [{"clause_id": "C1", "verdict": "partial", "confidence": 0.9, "reason": "疑似改名提供", "evidence": [{"doc_id": "t.pdf", "page": 5, "text": "★ 投标工期不得超 180 日历天"}]}]}
    issues = await run_sem_rule(FP_RULE, fields=FP_FIELDS, materials="…", model_fn=_fake(json.dumps(resp)), docs_text=DOCS)
    assert issues and issues[0]["verdict"] == "violation"
    assert issues[0]["entity_keys"] == ["attachment:5"], "候选实体经 join key 继承到确认条目"


@pytest.mark.asyncio
async def test_candidate_entity_dropped_when_clause_id_not_echoed(tmp_path, monkeypatch):
    """模型自造 clause_id 查不回候选 → 无 entity_keys(=现状,弱而非坏)。"""
    _isolate_fp_dict(tmp_path, monkeypatch)
    resp = {"verdicts": [{"clause_id": "自造-1", "verdict": "partial", "confidence": 0.9, "reason": "疑似改名提供", "evidence": [{"doc_id": "t.pdf", "page": 5, "text": "★ 投标工期不得超 180 日历天"}]}]}
    issues = await run_sem_rule(FP_RULE, fields=FP_FIELDS, materials="…", model_fn=_fake(json.dumps(resp)), docs_text=DOCS)
    assert issues and not issues[0].get("entity_keys"), "join 不中不硬造实体"
```

- [ ] **Step 2.2: 验红** 两测红(继承测试 entity_keys 空;降级测试本应绿?——降级测试是现状钉,预期绿;继承测试红)。

- [ ] **Step 2.3: 实现** llm_runner.py 三处:
  ①run_sem_rule 候选分裂循环:分桶后建 `cand_map = {f"C{i}": c for i, c in enumerate(candidates, 1)}`;
  ②build_rule_card 候选段:`{"id": f"C{i}", "verdict": …, "message": …}` 枚举注入,指令追加「回显 clause_id 用候选 id;」(保留 "det 粗筛候选"/"驳回候选"/"unclear" 断言串);
  ③verdict 循环 `issue = _verdict_to_issue(...)` 后:

```python
        if candidates:
            c = cand_map.get(str(entry.get("clause_id") or ""))
            if c and c.get("entity_keys"):
                issue["entity_keys"] = list(c["entity_keys"])  # L2 候选实体继承(spec 2026-11-04 §1,EAI-CUSTOM):join key=模型回显候选 id;查不回=无 entity(弱而非坏)
```

  ④`PROMPT_VERSION = "bid-review-rule-card-2026-11-04"`。

- [ ] **Step 2.4: 验绿** llm_verify 44。

### Task 3: golden case 1 回填 + 全量验证

**Files:**
- Modify: `backend/app/extensions/bid_review/golden/cases/L2-021-fp-confirm-partial.yaml`

- [ ] **Step 3.1**: script clause_id "安全生产许可证"→"C1";expect 恢复 `entity: "attachment:5"`;desc 去挂账注记。

- [ ] **Step 3.2**: golden CLI 55/55 exit 0;全家 pytest 394/6;ruff 触碰文件。

- [ ] **Step 3.3**: commit(显式路径)。

### Task 4: 收尾

- [ ] **Step 4.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`。
- [ ] **Step 4.2**: .wolf/memory+buglog+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
