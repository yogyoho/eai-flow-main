# L2 指纹通道(L2-021) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行,429 配额裁决沿前例)。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-l2-fingerprint-channel-design.md`

**Goal:** L2-021 hyb 规则——att_missing_rows 逐行候选 + 外置指纹字典进卡 + 模型确认(永不自动 MATCHED),纯增量零翻红。

**Architecture:** 新 det 算子出候选 → run_sem_rule 单点合并字典进卡 → 既有规则卡管线确认;既有 34 规则/52 题零触碰。

**Tech Stack:** Python 3.12/PyYAML/pytest。

---

### Task 1: 文档

- [x] spec + plan 落盘提交。

### Task 2: det 算子 + 字典 loader(TDD)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(_KNOWN_OPS+att 族门+新分支)
- Create: `backend/app/extensions/bid_review/engine/fingerprints.py`
- Create: `backend/app/extensions/bid_review/engine/dicts/fingerprints.yaml`
- Modify: `backend/tests/test_bid_review_rule_runner.py`(+3)
- Create: `backend/tests/test_bid_review_fingerprints.py`(+3)

- [x] **Step 2.1: 先写测试**

rule_runner 追加(文件尾混合态区之后):

```python
# ── L2-021 指纹通道:att_missing_rows 粗筛(spec 2026-11-04 §2.1) ──────────────────

FP_MISS_FIELDS = {
    "tender.attachment_requirements": [
        {"no": "5", "name": "安全生产许可证", "mandatory": "★", "min_count": None},
        {"no": "6", "name": "社保缴纳证明", "mandatory": "★", "min_count": None},
    ],
    "bid.attachment_index": [{"no": "", "name": "业绩合同", "page": 9}],
}


def _fp_rule() -> dict:
    return {
        "id": "L2-021",
        "name": "附件类型指纹核对",
        "layer": "L2",
        "type": "hybrid",
        "applies_to": ["*"],
        "inputs": ["tender.attachment_requirements", "bid.attachment_index"],
        "check": {
            "op": "att_missing_rows",
            "left": "tender.attachment_requirements",
            "right": "bid.attachment_index",
            "candidate_tpl": "附件「{missing}」未见于投标提供清单",
        },
        "severity": "major",
        "evidence": [],
        "message_tpl": "附件「{clause_id}」疑似以其它名称提供(类型指纹命中):{reason}",
        "fix_tpl": "核对材料中疑似文件",
        "confidence_gate": 0.75,
        "enabled": True,
    }


def test_att_missing_rows_per_row_candidates():
    """L2-021 粗筛(spec 2026-11-04 §2.1):MISSING 行逐行 violation 候选,candidate_tpl
    渲染候选消息,entity/dedup 按行实体键。"""
    issues = run_det_rule(_to_rule(_fp_rule()), FP_MISS_FIELDS)
    assert len(issues) == 2
    assert all(i["verdict"] == "violation" for i in issues)
    assert "安全生产许可证" in issues[0]["message"]
    assert issues[0]["entity_keys"] == ["attachment:5"]
    assert issues[0]["dedup_key"] != issues[1]["dedup_key"]
    assert issues[1]["entity_keys"] == ["attachment:6"]


def test_att_missing_rows_unknown_rows_silent():
    """UNKNOWN 行零发声(spec §2.1):近似行已有 L2-020 need_human 面,双规则重复=噪音。"""
    issues = run_det_rule(_to_rule(_fp_rule()), SUB_NEAR_FIELDS)
    assert issues == []


def test_att_missing_rows_whitelisted_at_load():
    """算子入白名单:含 candidate_tpl 的规则包可载入(load_rulepack 不拒)。"""
    pack_yaml = tmp_rulepack(_fp_rule())
    pack = load_rulepack(pack_yaml)
    assert pack.rules[0].id == "L2-021"
```

(辅手 `_to_rule`/`tmp_rulepack` 沿文件内既有测试辅手形态,落地时对齐现名。)

fingerprints 新测试文件:

```python
"""指纹字典 loader 单测(L2 指纹通道 spec 2026-11-04 §2.2)。seam=monkeypatch _FILE+_cache。"""
from pathlib import Path
import pytest
from app.extensions.bid_review.engine import fingerprints as fp


@pytest.fixture()
def isolated_fp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fp, "_FILE", tmp_path / "fingerprints.yaml")
    monkeypatch.setattr(fp, "_cache", None)
    return tmp_path / "fingerprints.yaml"


def test_default_empty_when_missing(isolated_fp):
    assert fp.load() == {}


def test_valid_yaml_loaded(isolated_fp):
    isolated_fp.write_text("营业执照: [统一社会信用代码, 注册资本]\n安全生产许可证: [许可证编号]\n", encoding="utf-8")
    assert fp.load() == {"营业执照": ["统一社会信用代码", "注册资本"], "安全生产许可证": ["许可证编号"]}


def test_bad_entries_dropped(isolated_fp):
    isolated_fp.write_text("营业执照: [统一社会信用代码, 123]\n坏组: 不是列表\n空组: []\n合规: [许可证编号]\n", encoding="utf-8")
    assert fp.load() == {"合规": ["许可证编号"]}
```

- [x] **Step 2.2: 验红** 三测全红(UnknownOp/AttributeError)。

- [x] **Step 2.3: 实现** fingerprints.py(仿 tuning loader,mtime+锁,值=非空串列表校验,坏条目丢弃,坏/缺文件 `{}`)+dicts/fingerprints.yaml 种子 8 组;rule_runner:`_KNOWN_OPS`+`"att_missing_rows"`,att 族门加员,新分支(见 spec §2.1:逐行 `_issue`+candidate_tpl 覆写 message+重算 dedup_key+entity_keys)。

- [x] **Step 2.4: 验绿** rule_runner 27 / fingerprints 3。

### Task 3: 合并进卡 + 规则包(TDD)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/llm_runner.py`(run_sem_rule 合并块)
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`(L2-021)
- Modify: `backend/tests/test_bid_review_llm_verify.py`(+2)

- [x] **Step 3.1: 先写测试** llm_verify 追加:

```python
@pytest.mark.anyio
async def test_fingerprint_marker_merges_into_card():
    """check.fingerprints==external → loader 产物+候选进卡片文本(spec §2.3)。"""
    rule = {...L2-021 dict, check.fingerprints: "external"...}  # 落地对齐文件内既有 rule dict 形态
    card = ...build/拦截...
    assert "统一社会信用代码" in card and "安全生产许可证" in card
    # 无 marker → check 原样(零注入)
```

(落地时对齐 llm_verify 既有 fixture:fake model 捕获 prompt 文本断言;模式沿既有 sem/hyb 测。)

- [x] **Step 3.2: 验红 → 实现** run_sem_rule 入口归一后:

```python
    chk = rule.get("check") or {}
    if chk.get("fingerprints") == "external":  # L2-021 指纹字典外置(spec 2026-11-04 §2.3,EAI-CUSTOM)
        from . import fingerprints
        rule = {**rule, "check": {**chk, "fingerprints": fingerprints.load()}}
```

- [x] **Step 3.3: 规则包 L2-021**(spec §2.4 全文;插在 L2-020 附近,L2 层区块)。

- [x] **Step 3.4: 验绿** llm_verify 41;rulepack 全家载入测试(test_full_pack_loads)零红。

### Task 4: golden 三题 + 全量验证

**Files:**
- Create: `backend/app/extensions/bid_review/golden/cases/L2-021-fp-confirm-partial.yaml` / `L2-021-fp-reject-full.yaml` / `L2-021-fp-unclear.yaml`

- [x] **Step 4.1: 三题**(model_script 路由 L2-021;fields 造 MISSING 行;partial 题带疑似别名+证据;full 题零条目+L2-020 MISSING 在场;unclear 题判 need_human)。

- [x] **Step 4.2: golden CLI** 55/55 exit 0(52 存量零翻红)。

- [x] **Step 4.3: 全家 pytest** 387/6;ruff 触碰文件。

- [x] **Step 4.4: commit**(显式路径,feat(bid-review): L2-指纹① …)。

### Task 5: 收尾

- [x] **Step 5.1**: spec 状态落定+plan 勾选 commit;push 重试至 `0\t0`。
- [x] **Step 5.2**: .wolf/memory+buglog+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;行号快照先读现场;默认零翻红铁律(标注错改标注/引擎错先修引擎)。
