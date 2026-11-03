# L2 混合态真缺失子件枚举 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行,429 配额裁决见 spec §6)。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-03-bid-review-l2-mixed-missing-enum-design.md`

**Goal:** 混合成因父行(子近似+子真缺失)的真缺失子件逐个独立 need_human 点名,纯增量零翻红。

**Architecture:** rule_runner.py `subs_nm` 分支尾追加真缺失子件循环(entity/dedup 按子行实体键);既有消息零改。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档

- [x] spec + plan 落盘提交。

### Task 2: 测试 + 实现(TDD)

**Files:**
- Modify: `backend/tests/test_bid_review_rule_runner.py`(+1 混合态枚举测)
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(`subs_nm` 分支尾 +循环)

- [x] **Step 2.1: 先写测试**(文件尾 P3.2 区之后追加):

```python
# ── L2 混合态:子近似+子真缺失 issue 面枚举(spec 2026-11-03 §4) ──────────────────

SUB_MIXED_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}, {"no": "3.3", "name": "完税证明"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "", "name": "中标通知书回执", "page": 40},  # 3.2 近似(sim≈0.83≥门)
        # 3.3 完税证明:池内零近似 → 真缺失
    ],
}


def test_att_check_mixed_parent_missing_subs_enumerated():
    """L2 混合态(spec 2026-11-03 §1):混合父行(子近似+子真缺失)——近似子件候选话术
    不变,真缺失子件逐个独立 need_human 点名父件+子件;dedup 按子行实体键互异。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_MIXED_FIELDS)
    assert len(issues) == 2
    near = next(i for i in issues if "近似候选" in i["message"])
    assert near["dedup_key"] == "L2-020|-|attachment:3.2"
    miss = next(i for i in issues if "缺失" in i["message"])
    assert miss["need_human"] is True
    assert "资格审查文件" in miss["message"]
    assert "3.3" in miss["message"]
    assert "完税证明" in miss["message"]
    assert miss["entity_keys"] == ["attachment:3.3"]
    assert miss["dedup_key"] == "L2-020|-|attachment:3.3"
```

(纯 near_miss 不多发已由既有 `test_att_check_sub_near_miss_message_names_subitem` len==1 钉住,不重复加测——spec §4。)

- [x] **Step 2.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py::test_att_check_mixed_parent_missing_subs_enumerated -x -q` → len==2 实得 1(3.3 无 issue)。

- [x] **Step 2.3: 实现** `subs_nm` 分支内、近似循环之后、grouping 嵌套判定之前:

```python
                            # L2 混合态子件枚举(spec 2026-11-03 §1,EAI-CUSTOM):混合成因
                            # 父行(子近似+子真缺失)的真缺失子件逐个独立 need_human——
                            # P3.2 起仅近似子件成话,真缺失子件 issue 面零可见;与近似
                            # 子件同构点名,dedup 按子行实体键。纯增量,既有消息零改。
                            for s in (r.get("sub_results") or []):
                                if s.get("status") != "MISSING":
                                    continue
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」缺失,需人工核对")
                                nh["entity_keys"] = [_entity_key(s)]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"  # 按子行实体键派生(I-1/P3.2 同规)
                                issues.append(nh)
```

- [x] **Step 2.4: 验绿** 新测过;rule_runner 全文件 24 全绿(既有孤儿/near_miss/grouping 钉零动)。

- [x] **Step 2.5: 全家+golden+ruff** family 379/6;golden 52/52;`ruff check`+`ruff format` 两文件。

- [x] **Step 2.6: commit**(显式路径)

```bash
git add backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_rule_runner.py
git commit -m "feat(bid-review): L2-混合态① 真缺失子件 issue 面枚举——混合父行(子近似+子真缺失)真缺失子件逐个独立 need_human 点名父件+子件;dedup 按子行实体键;纯增量既有消息零改;1 新测;默认零变(golden 52/52)"
```

### Task 3: 全量验证收尾

- [x] **Step 3.1**: bid_review 全家 pytest(预期 379/6)。
- [x] **Step 3.2**: spec 状态落定+plan 勾选 commit;push 重试至 `0\t0`。
- [x] **Step 3.3**: .wolf/memory+cerebrum、auto-memory、终报。

---

## 执行约束

同前两切片:main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;行号快照先读现场;默认零翻红铁律。
