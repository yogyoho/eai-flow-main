# L2 完整性层 P1：附件清单核对 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 投标审查 L2 完整性层 P1 —— 招标附件要求集/投标附件清单两字段抽取契约 + 两级精确匹配器 + L2-020/L2-024 两条 det 规则 + `/attachment_checklist` 投影端点 + BaselineView/ResultsView 双卡。

**Architecture:** 匹配器为纯函数 `engine/attachments.py`（pytest 全覆盖）；`att_check`/`att_count` 新算子镜像 `set_eq` 专用分支先例（rule_runner）；核对表端点照 `/deviations` `/score_coverage` 投影先例（基线字段现算不落库，零投影诚实空态）；UI 双卡归宿既有两页，不加导航页。规则文件名 `1.0.0.yaml` 不动（= `RULEPACK_PATH` 加载路径契约，`collect_field_paths` 按目录 glob 双文件会双装），规则 32→34 条。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy async（后端）；Next.js 16 + React 19 + TanStack Query + rstest（前端）。

**Spec:** `docs/superpowers/specs/2026-11-02-bid-review-l2-p1-attachment-checklist-design.md`（commit 24c334359）

**硬约束（每个任务都适用）：**
- 提交只进 `main-dev-fork`，绝不 main；每次 commit 后 push 并验证 `git rev-list --left-right --count origin/main-dev-fork...main-dev-fork` 输出 `0	0`（push 偶发 flaky，失败就重试）。
- 改后端代码后：`docker compose -p eai-docker restart gateway`（最后一个任务统一做也行，但别忘）。
- 后端测试命令：`cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_<file>.py -v`（Bash 工具跑，别用 PowerShell——它没有 `&&`）。
- 前端测试命令：`cd /d/eai/eai-flow-main/frontend && pnpm test -- tests/unit/extensions/<file>`；typecheck 门：`pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"` 必须输出 0。
- 不碰与本计划无关的 WIP（`backend/app/extensions/contract_price/service.py`、`backend/app/extensions/settings/routers.py` 等）。
- `docs/superpowers/` 在 .gitignore 里——本计划文件本身提交要 `git add -f`；代码文件正常 add。

---

### Task 1: 匹配器 `engine/attachments.py` —— normalize_name + match_attachments

**Files:**
- Create: `backend/app/extensions/bid_review/engine/attachments.py`
- Test: `backend/tests/test_bid_review_attachments.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_bid_review_attachments.py`：

```python
"""L2 P1 附件清单匹配器测试(spec 2026-11-02 §2):normalize_name 归一 +
match_attachments 两级精确匹配(①编号精确双方非空 ②规范化名称全等,非包含——
防「报价表」吞「分项报价表」),贪心一对一;found==0→MISSING,min_count 且
found<min_count→PARTIAL,否则 MATCHED;未匹配提供项→extra。"""

from app.extensions.bid_review.engine.attachments import normalize_name, match_attachments


def _req(no="", name="", min_count=None, **kw):
    d = {"no": no, "name": name, "mandatory": "★", "min_count": min_count}
    d.update(kw)
    return d


def _prov(no="", name="", page=None, **kw):
    d = {"no": no, "name": name, "page": page}
    d.update(kw)
    return d


# ── normalize_name ────────────────────────────────────────────────────


def test_normalize_strips_prefix_and_colon():
    assert normalize_name("附件三、资质证明文件：") == "资质证明文件"
    assert normalize_name("附件3-1 营业执照副本") == "营业执照副本"
    assert normalize_name("附件十二授权委托书") == "授权委托书"


def test_normalize_fullwidth_and_spaces():
    assert normalize_name("投 标 函（正本）") == "投标函(正本)"
    assert normalize_name("ｂｏｍ清单") == "bom清单"


def test_normalize_junk_inputs():
    assert normalize_name(None) == ""
    assert normalize_name(123) == ""
    assert normalize_name("   ") == ""


# ── match_attachments:编号匹配 ───────────────────────────────────────


def test_match_by_no_exact():
    out = match_attachments([_req(no="ATT-E-008", name="类似业绩证明")],
                            [_prov(no="ATT-E-008", name="业绩合同扫描件", page=118)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["per_req"][0]["found"] == 1
    assert out["extra"] == []


def test_no_match_requires_both_nonempty():
    """req 无编号时不走编号通道(空串不得匹配一切)。"""
    out = match_attachments([_req(no="", name="投标函")], [_prov(no="X-1", name="别的附件")])
    assert out["per_req"][0]["status"] == "MISSING"
    assert len(out["extra"]) == 1


# ── match_attachments:名称全等(非包含) ───────────────────────────────


def test_name_match_is_full_equality_after_normalize():
    out = match_attachments([_req(name="投标函（正本）")], [_prov(name="附件1 投标函(正本):", page=2)])
    assert out["per_req"][0]["status"] == "MATCHED"


def test_name_match_is_not_substring():
    """「报价表」不得吞「分项报价表」——归一后全等,非包含(spec §2)。"""
    out = match_attachments(
        [_req(no="A-1", name="报价表"), _req(no="A-2", name="分项报价表")],
        [_prov(no="A-2", name="分项报价表", page=40)],
    )
    by_no = {r["req"]["no"]: r for r in out["per_req"]}
    assert by_no["A-2"]["status"] == "MATCHED"
    assert by_no["A-1"]["status"] == "MISSING"
    assert by_no["A-1"]["found"] == 0


# ── 贪心一对一 + 份数 ─────────────────────────────────────────────────


def test_greedy_one_to_one_no_double_take():
    """一份提供项只归属一个 req;第二 req 靠名称通道也拿不到已占用的。"""
    out = match_attachments(
        [_req(no="A-1", name="营业执照"), _req(no="", name="营业执照")],
        [_prov(no="A-1", name="营业执照", page=9)],
    )
    assert out["per_req"][0]["found"] == 1
    assert out["per_req"][1]["status"] == "MISSING"
    assert out["extra"] == []


def test_min_count_partial():
    """同一附件交了 2 份(两行同编号)→ found=2;要求 3 份 → PARTIAL。"""
    out = match_attachments(
        [_req(no="B-1", name="业绩证明", min_count=3)],
        [_prov(no="B-1", name="业绩证明", page=118), _prov(no="B-1", name="业绩证明", page=121)],
    )
    assert out["per_req"][0]["found"] == 2
    assert out["per_req"][0]["status"] == "PARTIAL"


def test_min_count_null_treated_as_one():
    out = match_attachments([_req(no="C-1", name="投标函")], [_prov(no="C-1", name="投标函", page=1)])
    assert out["per_req"][0]["status"] == "MATCHED"


# ── EXTRA 与鲁棒性 ────────────────────────────────────────────────────


def test_unmatched_provided_is_extra():
    out = match_attachments([_req(no="D-1", name="投标函")],
                            [_prov(no="D-1", name="投标函", page=1), _prov(no="", name="企业宣传册", page=310)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["extra"] == [{"no": "", "name": "企业宣传册", "page": 310}]


def test_junk_and_none_inputs():
    out = match_attachments(None, None)
    assert out == {"per_req": [], "extra": []}
    out = match_attachments(["垃圾", {"no": "E-1", "name": "授权书"}], ["垃圾", {"no": "E-1", "name": "授权书"}])
    assert out["per_req"][0]["status"] == "MATCHED"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.bid_review.engine.attachments'`

- [ ] **Step 3: 实现匹配器**

创建 `backend/app/extensions/bid_review/engine/attachments.py`：

```python
"""L2 P1 附件清单匹配器(spec 2026-11-02 §2,EAI-CUSTOM):招标要求集 × 投标
提供集两级精确匹配。covers() 是子串语义不复用(spec §7)——名称通道要求归一后
**全等**,非包含,防「报价表」吞「分项报价表」;贪心一对一,一份提供项只归属
一个 req(先编号后名称)。纯函数,pytest 全覆盖(test_bid_review_attachments.py)。"""

import re
from typing import Any

# 全角 ASCII(！-～)与表意空格 → 半角
_FULLWIDTH = {0x3000: 0x20, **{0xFF01 + i: 0x21 + i for i in range(94)}}
# 「附件N」「附件N-M」(阿拉伯/中文数字)序号前缀 + 紧随分隔符
_PREFIX_RE = re.compile(r"^附件[\d一二三四五六七八九十]+(?:[-–—][\d一二三四五六七八九十]+)?[、..::．]?\s*")


def normalize_name(value: Any) -> str:
    """全半角归一/去空白/剥「附件N」序号前缀/去尾冒号(spec §2)。非字符串 → 空串。"""
    if not isinstance(value, str):
        return ""
    t = value.strip().translate(_FULLWIDTH)
    t = re.sub(r"\s+", "", t)
    t = _PREFIX_RE.sub("", t)
    return t.rstrip(":：..。")


def match_attachments(requirements: Any, provided: Any) -> dict:
    """两级精确匹配,贪心一对一:① no 全等(双方非空) ② normalize_name 全等。
    同一 req 可命中多份提供项(份数语义:min_count>1 且 found<min_count → PARTIAL)。
    状态:found==0→MISSING;否则见上;未匹配提供项→extra。"""
    reqs = [r for r in (requirements or []) if isinstance(r, dict)]
    prov = [p for p in (provided or []) if isinstance(p, dict)]
    taken: set[int] = set()
    matched: list[list[int]] = [[] for _ in reqs]
    # ① 编号精确(双方非空;O(n²) 对几十行清单足够)
    for ri, r in enumerate(reqs):
        no = str(r.get("no") or "").strip()
        if not no:
            continue
        for i, p in enumerate(prov):
            if i not in taken and str(p.get("no") or "").strip() == no:
                taken.add(i)
                matched[ri].append(i)
    # ② 规范化名称全等(非包含)
    for ri, r in enumerate(reqs):
        nm = normalize_name(r.get("name"))
        if not nm:
            continue
        for i, p in enumerate(prov):
            if i not in taken and normalize_name(p.get("name")) == nm:
                taken.add(i)
                matched[ri].append(i)

    per_req = []
    for ri, r in enumerate(reqs):
        hits = [prov[i] for i in matched[ri]]
        found = len(hits)
        try:
            min_count = int(r.get("min_count") or 0)
        except (TypeError, ValueError):
            min_count = 0
        if found == 0:
            status = "MISSING"
        elif min_count > 1 and found < min_count:
            status = "PARTIAL"
        else:
            status = "MATCHED"
        per_req.append({"req": r, "matched": hits, "found": found, "status": status})
    return {"per_req": per_req, "extra": [p for i, p in enumerate(prov) if i not in taken]}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py && git commit -m "feat(bid-review): L2-P1 附件匹配器——normalize_name(全半角/剥附件N前缀/尾冒号)+match_attachments 两级精确匹配(编号/名称全等非包含,贪心一对一,min_count→PARTIAL,EXTRA)(spec 2026-11-02 §2)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`(否则重试 push)

---

### Task 2: `build_checklist` 投影纯函数（counts/items/extra_items）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`（追加函数）
- Test: `backend/tests/test_bid_review_attachments.py`（追加用例）

- [ ] **Step 1: 写失败测试（追加到 test_bid_review_attachments.py 末尾）**

```python
# ── build_checklist(端点投影原料) ─────────────────────────────────────

from app.extensions.bid_review.engine.attachments import build_checklist


def test_build_checklist_counts_and_refs():
    reqs = [
        _req(no="ATT-E-008", name="类似业绩证明", min_count=3, clause="第三章3.4"),
        _req(no="ATT-F-001", name="投标函"),
        _req(no="", name=" never-matched "),
    ]
    prov = [
        _prov(no="ATT-E-008", name="类似业绩证明", page=118),
        _prov(no="ATT-E-008", name="类似业绩证明", page=121),
        _prov(no="ATT-F-001", name="附件1 投标函", page=2),
        _prov(no="", name="企业宣传册", page=310),
    ]
    out = build_checklist(reqs, prov, bid_doc_id="bid.pdf")
    assert out["counts"] == {"required": 3, "matched": 1, "partial": 1, "missing": 1, "extra": 1}
    it008 = next(i for i in out["items"] if i["no"] == "ATT-E-008")
    assert it008["status"] == "PARTIAL" and it008["found"] == 2 and it008["min_count"] == 3
    assert it008["refs"] == [{"doc_id": "bid.pdf", "page": 118}, {"doc_id": "bid.pdf", "page": 121}]
    assert it008["clause"] == "第三章3.4"
    itf = next(i for i in out["items"] if i["no"] == "ATT-F-001")
    assert itf["status"] == "MATCHED"
    assert out["extra_items"] == [{"name": "企业宣传册", "doc_id": "bid.pdf", "page": 310}]


def test_build_checklist_null_doc_and_empty():
    out = build_checklist([], [], bid_doc_id=None)
    assert out == {"counts": {"required": 0, "matched": 0, "partial": 0, "missing": 0, "extra": 0},
                   "items": [], "extra_items": []}
    one = build_checklist([_req(no="X", name="营业执照")], [_prov(no="X", name="营业执照", page=5)], bid_doc_id=None)
    assert one["items"][0]["refs"] == [{"doc_id": None, "page": 5}]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v -k checklist`
Expected: FAIL — `ImportError: cannot import name 'build_checklist'`

- [ ] **Step 3: 实现（追加到 attachments.py 末尾）**

```python
def build_checklist(requirements: Any, provided: Any, bid_doc_id: str | None = None) -> dict:
    """核对表投影原料(spec §4):match_attachments 结果摊平成 items 行(refs 注入
    bid 侧 doc_id——P1 refs=bid 侧首文档,调用方解析;解不到 → doc_id null,前端
    chip 降级纯文本)。counts 单一事实源;extra 提供项只进 extra_items 不产 issue。"""
    out = match_attachments(requirements, provided)
    items = []
    for e in out["per_req"]:
        req = e["req"]
        items.append(
            {
                "no": str(req.get("no") or ""),
                "name": str(req.get("name") or ""),
                "mandatory": req.get("mandatory"),
                "min_count": req.get("min_count"),
                "found": e["found"],
                "status": e["status"],
                "clause": req.get("clause"),
                "refs": [{"doc_id": bid_doc_id, "page": p.get("page")} for p in e["matched"]],
            }
        )
    counts = {
        "required": len(items),
        "matched": sum(1 for i in items if i["status"] == "MATCHED"),
        "partial": sum(1 for i in items if i["status"] == "PARTIAL"),
        "missing": sum(1 for i in items if i["status"] == "MISSING"),
        "extra": len(out["extra"]),
    }
    extra_items = [{"name": str(p.get("name") or ""), "doc_id": bid_doc_id, "page": p.get("page")} for p in out["extra"]]
    return {"counts": counts, "items": items, "extra_items": extra_items}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py && git commit -m "feat(bid-review): L2-P1 build_checklist 投影纯函数——counts 五格/摊平 items(refs 注入 bid 侧 doc_id,P1=首文档)/EXTRA 只进 extra_items 不产 issue(spec §4)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 3: 字段契约 —— FIELD_DICTIONARY + FIELD_TYPE_CONTRACTS 两字段

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`（FIELD_DICTIONARY ~line 46 区域 + FIELD_TYPE_CONTRACTS ~line 58-80 区域）
- Test: `backend/tests/test_bid_review_extract.py`（追加用例）

- [ ] **Step 1: 写失败测试（追加到 test_bid_review_extract.py 末尾）**

```python
def test_attachment_fields_in_dictionary_and_contracts():
    """L2 P1(spec §1):附件两字段进字典(进抽取请求)+ 类型契约(原文只抄不编)。"""
    from app.extensions.bid_review.engine.extract import FIELD_DICTIONARY, FIELD_TYPE_CONTRACTS, collect_field_paths

    assert "tender.attachment_requirements" in FIELD_DICTIONARY
    assert "bid.attachment_index" in FIELD_DICTIONARY
    for path in ("tender.attachment_requirements", "bid.attachment_index"):
        c = FIELD_TYPE_CONTRACTS[path]
        assert "禁止编造" in c
        if path.startswith("tender."):
            assert "min_count" in c and "mandatory" in c
        else:
            assert "page" in c and "pages" in c
    assert "tender.attachment_requirements" in collect_field_paths()
    assert "bid.attachment_index" in collect_field_paths()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py::test_attachment_fields_in_dictionary_and_contracts -v`
Expected: FAIL — `AssertionError: assert 'tender.attachment_requirements' in frozenset(...)`

- [ ] **Step 3: 实现**

在 `extract.py` 的 FIELD_DICTIONARY 里（`"deviation.items",` 行附近，保持字母序就近）加两项：

```python
        "tender.attachment_requirements",
        "bid.attachment_index",
```

在 FIELD_TYPE_CONTRACTS 定义块（`FIELD_TYPE_CONTRACTS["deviation.items"] = (...)` 之后）追加两条契约，口径同 deviation.items「原文只抄不编」：

```python
# L2 P1 附件契约(spec 2026-11-02 §1):招标要求集只从「投标文件格式/组成」及资格
# 审查条款逐条抄录;投标侧从附件清单/目录/附件标题逐条抄录。无编号填空串。
FIELD_TYPE_CONTRACTS["tender.attachment_requirements"] = (
    '[{no:"附件编号或空串", name:"附件名称", clause:"要求出处条款号", '
    'mandatory:"★|必需|建议", min_count:最少份数数字或null, year_span:年份数字或null}]。'
    "只从招标文件的投标文件组成/格式条款及资格审查条款逐条抄录附件要求,禁止编造;无编号填空串。"
)
FIELD_TYPE_CONTRACTS["bid.attachment_index"] = (
    '[{no:"附件编号或空串", name:"附件名称", page:起始页码数字, pages:页数数字或null}]。'
    "从投标文件的附件清单/目录/附件标题逐条抄录,禁止编造。"
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py -v`
Expected: 全部 PASS（既有用例不受影响——字段字典是追加式）

- [ ] **Step 5: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_extract.py && git commit -m "feat(bid-review): L2-P1 附件字段契约——tender.attachment_requirements/bid.attachment_index 进 FIELD_DICTIONARY+FIELD_TYPE_CONTRACTS(原文只抄不编,三方同步 spec §1)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 4: rule_runner 新算子 `att_check` / `att_count`

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`（`_KNOWN_OPS` 白名单 + `run_det_rule` 的 `set_eq` 分支后追加两分支）
- Test: `backend/tests/test_bid_review_rule_runner.py`（追加用例）

- [ ] **Step 1: 写失败测试（追加到 test_bid_review_rule_runner.py 末尾）**

```python
# ── L2 P1:att_check / att_count 专用分支(spec 2026-11-02 §3,镜像 set_eq 先例) ──

from app.extensions.bid_review.engine.rule_runner import Rule

ATT_REQS = [
    {"no": "A-1", "name": "投标函", "mandatory": "★", "min_count": None},
    {"no": "A-2", "name": "业绩证明", "mandatory": "★", "min_count": 3},
    {"no": "", "name": "不出席也行", "mandatory": "建议", "min_count": None},
]
ATT_PROV = [
    {"no": "A-1", "name": "投标函", "page": 2},
    {"no": "A-2", "name": "业绩证明", "page": 118},
    {"no": "A-2", "name": "业绩证明", "page": 121},
    {"no": "", "name": "企业宣传册", "page": 310},
]


def _att_rule(op):
    return Rule(
        id="L2-020" if op == "att_check" else "L2-024",
        name="附件",
        layer="L2",
        type="deterministic",
        severity="fatal" if op == "att_check" else "major",
        inputs=["tender.attachment_requirements", "bid.attachment_index"],
        check={"op": op, "left": "tender.attachment_requirements", "right": "bid.attachment_index"},
        message_tpl="附件问题:{missing}{insufficient}",
        fix_tpl=None,
        enabled=True,
    )


ATT_FIELDS = {"tender.attachment_requirements": ATT_REQS, "bid.attachment_index": ATT_PROV}


def test_att_check_reports_missing_only():
    """att_check 只列 MISSING req(编号+名称);PARTIAL/MATCHED 不进 message。"""
    issues = run_det_rule(_att_rule("att_check"), ATT_FIELDS)
    assert len(issues) == 1
    assert issues[0]["verdict"] == "violation"
    assert "不出席也行" in issues[0]["message"]


def test_att_check_all_matched_no_issue():
    fields = {
        "tender.attachment_requirements": [{"no": "A-1", "name": "投标函"}],
        "bid.attachment_index": [{"no": "A-1", "name": "投标函", "page": 2}],
    }
    assert run_det_rule(_att_rule("att_check"), fields) == []


def test_att_count_reports_partial_only():
    issues = run_det_rule(_att_rule("att_count"), ATT_FIELDS)
    assert len(issues) == 1
    assert "业绩证明" in issues[0]["message"]


def test_att_ops_missing_field_need_human():
    """字段缺失 → need_human(既有 inputs 缺字段链路;这里直接验 run_det_rule 层)。"""
    issues = run_det_rule(_att_rule("att_check"), {})
    assert len(issues) == 1 and issues[0]["need_human"] is True


def test_att_ops_whitelisted_at_load():
    """载入期白名单放行 att_check/att_count(canonical 包可加载)。"""
    import re
    from app.extensions.bid_review.engine.rule_runner import RulePackError, load_rulepack

    pack = load_rulepack(PACK)
    ops = {r.id: r.check.get("op") for r in pack.rules if r.layer == "L2"}
    assert ops == {"L2-020": "att_check", "L2-024": "att_count"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v -k att_`
Expected: FAIL —— `att_check` 走到 `raise RulePackError(...未支持算子)` 或载入期拒载（本步预期 L2-020 还没进 rulepack，`test_att_ops_whitelisted_at_load` 失败属预期；前 4 个测试失败于未支持算子）

- [ ] **Step 3: 实现**

在 `rule_runner.py` 找到 `_KNOWN_OPS = {*_OPS, "and", "all", "set_eq"}`，改为：

```python
_KNOWN_OPS = {*_OPS, "and", "all", "set_eq", "att_check", "att_count"}
```

文件顶部 import 区加（跟随该文件既有 import 风格）：

```python
from app.extensions.bid_review.engine.attachments import match_attachments
```

在 `run_det_rule` 里 `elif chk["op"] == "set_eq":` 块（`rule_runner.py:222-226`）之后、`elif chk["op"] in _OPS:` 之前，插入：

```python
        elif chk["op"] in ("att_check", "att_count"):  # L2 P1 附件核对(spec 2026-11-02 §3):镜像 set_eq 专用分支
            reqs, prov = _val(chk["left"], fields), _val(chk["right"], fields)
            if not isinstance(reqs, list) or not isinstance(prov, list):
                issues.append(_need_human(rule, "附件字段缺失或类型非法(need_human)"))
            else:
                out = match_attachments(reqs, prov)
                if chk["op"] == "att_check":
                    miss = [f"{(r['req'].get('no') or '') + ' ' if r['req'].get('no') else ''}{r['req'].get('name')}"
                            for r in out["per_req"] if r["status"] == "MISSING"]
                    if miss:
                        issues.append(_issue(rule, fields, {"missing": miss}))
                else:
                    ins = [
                        f"{(r['req'].get('no') or '') + ' ' if r['req'].get('no') else ''}{r['req'].get('name')}: 要求{r['req'].get('min_count')}份/提供{r['found']}份"
                        for r in out["per_req"] if r["status"] == "PARTIAL"
                    ]
                    if ins:
                        issues.append(_issue(rule, fields, {"insufficient": ins}))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v`
Expected: 新 5 个 PASS；`test_att_ops_whitelisted_at_load` 仍 FAIL（L2-020 未进包，Task 5 补）——其余既有用例全部 PASS

- [ ] **Step 5: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_rule_runner.py && git commit -m "feat(bid-review): L2-P1 rule_runner 新算子 att_check/att_count——白名单+专用分支镜像 set_eq 先例,复用 match_attachments;missing/insufficient 分列(字段缺失→need_human,spec §3)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 5: 规则包 +L2-020/L2-024（32→34 条）

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`（末尾追加两条；文件名不动——= `worker.RULEPACK_PATH` 加载契约，`collect_field_paths` 按目录 glob，双文件会双装）
- Test: 复用 `backend/tests/test_bid_review_rule_runner.py` 的转录门（已有 `ids >= 32` + `len(ids) == len(pack.rules)` 断言，34 条自然通过）

- [ ] **Step 1: 追加 YAML（文件末尾，`rules:` 列表缩进对齐既有条目——`- id:` 顶层两空格缩进，与 L1-009 等同级）**

```yaml
  # ── L2 完整性层 P1(spec 2026-11-02 §3):附件清单核对两规则;算子 att_check/
  # att_count 镜像 set_eq 专用分支先例;字段缺失走 conventions on_missing_input: need_human ──
  - id: L2-020
    name: 附件清单逐项对照
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.attachment_requirements, bid.attachment_index]
    check:
      op: att_check
      left: tender.attachment_requirements
      right: bid.attachment_index
    severity: fatal
    evidence: [A-TENDER-NOTICE, A-BOQ]
    message_tpl: "附件缺失：{missing}"
    fix_tpl: "补齐缺失附件并在投标文件附件清单中按编号顺序编排：{missing}"
    enabled: true
  - id: L2-024
    name: 附件份数达标
    layer: L2
    type: deterministic
    applies_to: ["*"]
    inputs: [tender.attachment_requirements, bid.attachment_index]
    check:
      op: att_count
      left: tender.attachment_requirements
      right: bid.attachment_index
    severity: major
    evidence: [A-TENDER-NOTICE, A-BOQ]
    message_tpl: "附件份数不足：{insufficient}"
    fix_tpl: "按要求份数补齐附件或附情况说明：{insufficient}"
    enabled: true
```

- [ ] **Step 2: 跑 rule_runner 全量测试（含转录门）**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v`
Expected: 全部 PASS（含 Task 4 遗留的 `test_att_ops_whitelisted_at_load` 与既有转录门 34 条）

- [ ] **Step 3: 跑全量 bid_review 后端测试防回归**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/ -v -k bid_review`
Expected: 全部 PASS（抽取请求现在多 2 个字段路径——`collect_field_paths` 消费方按 set 处理，无数量断言）

- [ ] **Step 4: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml && git commit -m "feat(bid-review): L2-P1 规则包 32→34——L2-020 附件清单逐项对照(fatal,att_check)+L2-024 附件份数达标(major,att_count);文件名 1.0.0.yaml 不动(RULEPACK_PATH 加载契约)(spec §3)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 6: 投影端点 `GET /tasks/{id}/attachment_checklist`

**Files:**
- Modify: `backend/app/extensions/bid_review/routers.py`（`task_deviations` 之后，~line 724）
- Test: Create `backend/tests/test_bid_review_checklist.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_bid_review_checklist.py`（夹具照 test_bid_review_deviations.py）：

```python
"""L2 P1 附件核对表(spec 2026-11-02 §4):GET /tasks/{id}/attachment_checklist。

基线 fields tender.attachment_requirements × bid.attachment_index 经
build_checklist 投影(不落库);基线每行同全量快照 → 要求按 (no,name) 跨行去重,
提供项逐行收集。零投影(旧任务无 tender.attachment_requirements)→ counts 全 0 +
items [](诚实,不装数据)。夹具照 test_bid_review_deviations.py。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db

REQS = [
    {"no": "ATT-E-008", "name": "类似业绩证明", "clause": "第三章3.4", "mandatory": "★", "min_count": 3},
    {"no": "ATT-F-001", "name": "投标函", "clause": None, "mandatory": "★", "min_count": None},
]
PROV = [
    {"no": "ATT-E-008", "name": "类似业绩证明", "page": 118, "pages": None},
    {"no": "ATT-E-008", "name": "类似业绩证明", "page": 121, "pages": None},
    {"no": "ATT-F-001", "name": "投标函", "page": 2, "pages": 3},
    {"no": "", "name": "企业宣传册", "page": 310, "pages": None},
]
FIELDS = {"tender.attachment_requirements": REQS, "bid.attachment_index": PROV}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.ReviewTask.__table__,
                models.ReviewIssue.__table__,
                models.BaselinePackage.__table__,
                models.RulePackMeta.__table__,
                models.ReviewFeedback.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _mk_task(db, task_id="t1", engine_meta=None):
    return await crud.create_task(db, owner_id="u1", mode="quick", biz_no=f"B-{task_id}",
                                  engine_meta=engine_meta or {})


async def _mk_baseline(db, task_id, fields, kind="bid"):
    from app.extensions.bid_review.worker import _write_baselines

    await _write_baselines(db, task_id, [{"role": kind, "doc_id": f"{kind}.pdf"}], fields, "h")


# crud.create_task 签名以 crud.py 实际为准——若上面 _mk_task 与实际签名不符,
# 照 test_bid_review_deviations.py 里既有建任务写法照抄替换(本测试文件唯一需对表处)。


@pytest.mark.asyncio
async def test_checklist_projection(db, client):
    t = await _mk_task(db)
    await _mk_baseline(db, t.id, FIELDS)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"required": 2, "matched": 1, "partial": 1, "missing": 0, "extra": 1}
    it = next(i for i in body["items"] if i["no"] == "ATT-E-008")
    assert it["status"] == "PARTIAL" and it["found"] == 2
    assert it["refs"] == [{"doc_id": "bid.pdf", "page": 118}, {"doc_id": "bid.pdf", "page": 121}]
    assert body["extra_items"] == [{"name": "企业宣传册", "doc_id": "bid.pdf", "page": 310}]


@pytest.mark.asyncio
async def test_checklist_zero_projection(db, client):
    """旧任务无附件字段 → counts 全 0 + items [](诚实空态)。"""
    t = await _mk_task(db)
    await _mk_baseline(db, t.id, {"project.total_price": "1,000,000"})
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    assert r.status_code == 200
    assert r.json() == {
        "counts": {"required": 0, "matched": 0, "partial": 0, "missing": 0, "extra": 0},
        "items": [],
        "extra_items": [],
    }


@pytest.mark.asyncio
async def test_checklist_404(db, client):
    r = await client.get("/api/extensions/bid-review/tasks/nope/attachment_checklist")
    assert r.status_code == 404
```

注意：`_mk_task` 里的 `crud.create_task(...)` 调用签名必须先打开 `backend/app/extensions/bid_review/crud.py` 核对；`_mk_baseline` 直接复用 worker 的 `_write_baselines`（deviations/score_coverage 测试同手法——若那两个文件用的是别的手法，照抄它们的）。路由前缀以 `R.router` 实际 `prefix` 为准，与 deviations 测试保持一致。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_checklist.py -v`
Expected: FAIL —— 404（端点不存在）

- [ ] **Step 3: 实现端点（routers.py，`task_deviations` 函数后插入；import 区加 `from app.extensions.bid_review.engine.attachments import build_checklist`，风格随既有 import 块）**

```python
@router.get("/tasks/{task_id}/attachment_checklist")
async def task_attachment_checklist(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """附件核对表(L2 P1 spec 2026-11-02 §4):基线 fields tender.attachment_requirements
    × bid.attachment_index 经 engine.attachments.build_checklist 两级精确匹配投影
    (现算不落库,先例=/deviations /score_coverage)。要求按 (no,name) 跨行去重,提供项
    逐行收集;refs 注入 bid 侧首 doc_id(engine_meta.docs role=bid;解不到 → null,前端
    chip 降级纯文本)。零投影(旧任务无附件维度)→ counts 全 0 + items [](诚实空态)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    reqs: list[dict] = []
    seen_req: set[tuple[str, str]] = set()
    provided: list[dict] = []
    for row in baselines:
        fields = (row.payload or {}).get("fields", {})
        for item in fields.get("tender.attachment_requirements") or []:
            if isinstance(item, dict):
                key = (str(item.get("no") or "").strip(), str(item.get("name") or "").strip())
                if key not in seen_req:
                    seen_req.add(key)
                    reqs.append(item)
        for item in fields.get("bid.attachment_index") or []:
            if isinstance(item, dict):
                provided.append(item)
    if not reqs:
        return {
            "counts": {"required": 0, "matched": 0, "partial": 0, "missing": 0, "extra": 0},
            "items": [],
            "extra_items": [],
        }
    docs = (task.engine_meta or {}).get("docs") or []
    bid_doc = next(
        (str(d.get("doc_id")) for d in docs if isinstance(d, dict) and d.get("role") == "bid" and d.get("doc_id")),
        None,
    )
    return build_checklist(reqs, provided, bid_doc_id=bid_doc)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_checklist.py -v`
Expected: 全部 PASS。再跑 `PYTHONPATH=. uv run pytest tests/ -v -k bid_review` 防回归。

- [ ] **Step 5: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_checklist.py && git commit -m "feat(bid-review): L2-P1 GET /tasks/{id}/attachment_checklist——基线字段两级匹配投影(现算不落库,先例=deviations);refs 注 bid 侧首 doc_id,零投影诚实空态(spec §4)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 7: 前端 api.ts 类型 + fetcher + hooks

**Files:**
- Modify: `frontend/src/extensions/bid-review/api.ts`（deviations 类型/请求器区，~line 131-230）
- Modify: `frontend/src/extensions/bid-review/hooks.ts`（keys + useBidDeviations 旁）

- [ ] **Step 1: api.ts 追加类型（`BidDeviationsOut` 之后）**

```ts
/** GET /tasks/{id}/attachment_checklist ref(L2 P1 spec §4;doc_id=bid 侧首文档,解不到 null → chip 纯文本)。 */
export interface BidAttachmentRef {
  doc_id: string | null;
  page: number | null;
}

/** GET /tasks/{id}/attachment_checklist 行(要求项;status 四态之 P1 三态,UNKNOWN 由 need_human 兜底)。 */
export interface BidChecklistItem {
  no: string;
  name: string;
  mandatory: string | null;
  min_count: number | null;
  found: number;
  status: "MATCHED" | "PARTIAL" | "MISSING";
  clause: string | null;
  refs: BidAttachmentRef[];
}

/** 未被任何要求匹配的提供项(EXTRA——info 行提示,不产 issue 不进问题数)。 */
export interface BidChecklistExtra {
  name: string;
  doc_id: string | null;
  page: number | null;
}

/** GET /tasks/{id}/attachment_checklist 响应;零投影 → counts 全 0 + items [](旧任务无附件维度)。 */
export interface BidAttachmentChecklistOut {
  counts: { required: number; matched: number; partial: number; missing: number; extra: number };
  items: BidChecklistItem[];
  extra_items: BidChecklistExtra[];
}
```

api.ts 请求器区（`fetchDeviations` 旁）追加：

```ts
/** GET /tasks/{id}/attachment_checklist —— L2 P1 附件核对表(spec 2026-11-02 §4)。 */
export async function fetchAttachmentChecklist(taskId: string): Promise<BidAttachmentChecklistOut> {
  return request<BidAttachmentChecklistOut>(`/tasks/${taskId}/attachment_checklist`);
}
```

（若该文件既有 deviations fetcher 不叫 `request<T>` 而是别的内部帮助名，照抄它的实际写法。）

- [ ] **Step 2: hooks.ts 追加（`bidReviewKeys` 加一项 + hook 函数，紧挨 `useBidDeviations`）**

```ts
  attachmentChecklist: (taskId: string) =>
    ["bid-review", "attachment-checklist", taskId] as const,
```

```ts
/** GET /tasks/{id}/attachment_checklist —— L2 P1 附件核对表(spec §4);零投影 → 前端诚实空态。 */
export function useBidAttachmentChecklist(taskId: string | null | undefined) {
  return useQuery({
    queryKey: bidReviewKeys.attachmentChecklist(taskId ?? ""),
    queryFn: () => fetchAttachmentChecklist(taskId ?? ""),
    enabled: Boolean(taskId),
  });
}
```

（`enabled`/queryFn 写法与 `useBidDeviations` 逐行对齐。）

- [ ] **Step 3: 验证**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"`
Expected: `0`

- [ ] **Step 4: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add frontend/src/extensions/bid-review/api.ts frontend/src/extensions/bid-review/hooks.ts && git commit -m "feat(bid-review): L2-P1 前端契约——BidAttachmentChecklistOut 类型+fetchAttachmentChecklist+useBidAttachmentChecklist(spec §4)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 8: BaselineView 双卡 —— 附件要求（tender）+ 附件清单（bid 只读）

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`（「基准字段对照」卡之后、冲突裁定卡注释 `~306` 之前插入两卡）
- Test: extend `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`

数据源：`rows[0]?.fields`（基线行携带全量快照）。裁决不改卡——两字段已进 FIELD_DICTIONARY，自动出现在「基准字段对照」字段卡里，走既有 adjudicate 通道（spec §5「复用既有通道」的落点）；双卡是友好只读摘要。

- [ ] **Step 1: BaselineView 插入两卡**

组件体内（`rows`/`locate` 已有的作用域）加派生：

```tsx
  // L2 P1 附件双卡(spec 2026-11-02 §5):基线快照直读,只读摘要;改错走「基准字段
  // 对照」字段卡既有 adjudicate 通道(两字段已在字段字典,自动出现在字段表)。
  const attachReqs = useMemo(
    () => ((rows[0]?.fields as Record<string, unknown> | undefined)?.["tender.attachment_requirements"] as
      | Array<{ no?: string; name?: string; mandatory?: string | null; min_count?: number | null; clause?: string | null }>
      | undefined) ?? [],
    [rows],
  );
  const attachIdx = useMemo(
    () => ((rows[0]?.fields as Record<string, unknown> | undefined)?.["bid.attachment_index"] as
      | Array<{ no?: string; name?: string; page?: number | null }>
      | undefined) ?? [],
    [rows],
  );
```

「基准字段对照」卡关闭标签之后（冲突裁定卡 `{/* ── 冲突裁定卡` 注释之前）插入：

```tsx
            {/* ── L2 P1 附件要求卡(tender)/附件清单卡(bid 只读,spec §5);
                空数组 → 卡不渲染(任务未抽出该维度时不装空壳) ── */}
            {attachReqs.length > 0 ? (
              <div className="card">
                <div className="card-hd">
                  <h3>附件要求</h3>
                  <span className="hd-sub">招标方要求随附材料 {attachReqs.length} 项 · 核对与份数见审查结果页</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>附件名称</th>
                      <th>强制</th>
                      <th>份数</th>
                      <th>条款</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attachReqs.map((a, i) => (
                      <tr key={`${a.no}-${i}`}>
                        <td className="mono">{a.no || "—"}</td>
                        <td>{a.name}</td>
                        <td>{a.mandatory === "★" || a.mandatory === "必需" ? "必需" : a.mandatory || "—"}</td>
                        <td>{a.min_count ?? "—"}</td>
                        <td className="mono">{a.clause || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="tbl-foot">改错请到上方「基准字段对照」字段卡裁决（tender.attachment_requirements）。</div>
              </div>
            ) : null}
            {attachIdx.length > 0 ? (
              <div className="card">
                <div className="card-hd">
                  <h3>投标附件清单</h3>
                  <span className="hd-sub">投标方提供 {attachIdx.length} 项 · 只读</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>附件名称</th>
                      <th>起始页</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attachIdx.map((a, i) => (
                      <tr key={`${a.no}-${i}`}>
                        <td className="mono">{a.no || "—"}</td>
                        <td>{a.name}</td>
                        <td>{a.page ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="tbl-foot">改错请到上方「基准字段对照」字段卡裁决（bid.attachment_index）。</div>
              </div>
            ) : null}
```

- [ ] **Step 2: dom 测试（extend bid-review-baseline.dom.test.tsx）**

先读该测试文件，复用其 fetcher mock 与基线 rows 夹具；在其中加用例（`FIELDS` 换成该文件实际夹具结构，往基线 payload.fields 注入两字段）：

```tsx
  it("L2-P1 附件要求/附件清单双卡:快照直读渲染,字段缺失不渲染卡", async () => {
    // 基线 payload.fields 注入 tender.attachment_requirements + bid.attachment_index
    // (沿用本文件既有基线 rows 夹具结构,在该测试的 baseline payload 上加两键)
    renderView();
    await waitFor(() => expect(screen.getByText("附件要求")).toBeTruthy());
    expect(screen.getByText("类似业绩证明")).toBeTruthy();
    expect(screen.getByText("投标附件清单")).toBeTruthy();
    // 无附件字段的任务:两卡零渲染(零装空壳)
  });
```

具体做法：在该测试文件里找到构造 baseline 响应的夹具，往 `payload.fields` 加：

```ts
      "tender.attachment_requirements": [
        { no: "ATT-E-008", name: "类似业绩证明", clause: "第三章3.4", mandatory: "★", min_count: 3 },
      ],
      "bid.attachment_index": [{ no: "ATT-E-008", name: "类似业绩证明", page: 118, pages: null }],
```

再写一个「无字段不渲染」的 `it`：基线 fields 不含两键 → `screen.queryByText("附件要求")` 为 null。

- [ ] **Step 3: 跑测试 + typecheck**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm test -- tests/unit/extensions/bid-review-baseline.dom.test.tsx && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"`
Expected: 测试 PASS + typecheck `0`

- [ ] **Step 4: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add frontend/src/extensions/bid-review/components/BaselineView.tsx frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx && git commit -m "feat(bid-review): L2-P1 BaselineView 附件要求/投标附件清单双卡——基线快照只读直读,裁决走既有字段卡通道(两字段已在字段字典);空维度零渲染(spec §5)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 9: ResultsView 附件核对表卡

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`（「规则执行」卡 `~956` 之后插入）
- Test: extend `frontend/tests/unit/extensions/bid-review-results-evidence.dom.test.tsx`

- [ ] **Step 1: ResultsView 插入核对表卡**

组件体加查询与派生（import 区加 `useBidAttachmentChecklist`）：

```tsx
  const checklistQuery = useBidAttachmentChecklist(taskId);
  const checklist = checklistQuery.data;
  const clItems = useMemo(() => {
    const rank = { MISSING: 0, PARTIAL: 1, MATCHED: 2 } as const;
    return [...(checklist?.items ?? [])].sort((a, b) => rank[a.status] - rank[b.status]);
  }, [checklist]);
```

状态 pill 映射（组件文件内辅助函数，与 DeviationsView deviationPill 同风格）：

```tsx
/** 核对状态 → pill(MATCHED ok / PARTIAL warn / MISSING err;spec §5)。 */
function checklistPill(status: string): { label: string; cls: string } {
  switch (status) {
    case "MATCHED":
      return { label: "已提供", cls: "pill pill-ok" };
    case "PARTIAL":
      return { label: "份数不足", cls: "pill pill-warn" };
    default:
      return { label: "缺失", cls: "pill pill-err" };
  }
}
```

「规则执行」卡（`<h3>规则执行</h3>` 所在卡的闭合标签）之后插入：

```tsx
            {/* ── L2 P1 附件核对表卡(spec §5):五格 counts + 明细(pill 映射/页码 chip
                复用 DocLocate role=bid 首文档)/EXTRA info 灰行不进问题数 ── */}
            {checklist && checklist.counts.required > 0 ? (
              <div className="card">
                <div className="card-hd">
                  <h3>附件核对表</h3>
                  <span className="hd-sub">招标要求 {checklist.counts.required} 项 · 两级精确匹配(编号/名称)</span>
                </div>
                <div className="metric-strip">
                  <div className="metric-cell"><div className="m-lb">要求附件</div><div className="m-v">{checklist.counts.required}</div></div>
                  <div className="metric-cell ok"><div className="m-lb">已提供</div><div className="m-v">{checklist.counts.matched}</div></div>
                  <div className="metric-cell warn"><div className="m-lb">份数不足</div><div className="m-v">{checklist.counts.partial}</div></div>
                  <div className="metric-cell err"><div className="m-lb">缺失</div><div className="m-v">{checklist.counts.missing}</div></div>
                  <div className="metric-cell"><div className="m-lb">多余附件</div><div className="m-v">{checklist.counts.extra}</div></div>
                </div>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>要求附件</th>
                      <th>强制</th>
                      <th>份数</th>
                      <th>提供情况</th>
                      <th>页码</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clItems
                      .filter((it) => it.status !== "MATCHED" || it.found > 0)
                      .map((it, i) => {
                        const pill = checklistPill(it.status);
                        const first = it.refs[0];
                        return (
                          <tr key={`${it.no}-${it.name}-${i}`}>
                            <td className="num">{i + 1}</td>
                            <td>{it.no ? <span className="mono">{it.no} </span> : null}{it.name}{it.clause ? <span className="hd-sub">（{it.clause}）</span> : null}</td>
                            <td>{it.mandatory === "★" || it.mandatory === "必需" ? "必需" : it.mandatory || "—"}</td>
                            <td>{it.min_count ? `${it.found}/${it.min_count}` : it.found}</td>
                            <td>{it.found > 0 ? `已提供 ${it.found} 份` : "未提供"}</td>
                            <td>
                              {first && first.doc_id && taskId ? (
                                <button
                                  type="button"
                                  className="src-chip"
                                  onClick={() => setLocate({ docId: first.doc_id as string, page: first.page, quote: null })}
                                >
                                  {first.doc_id}{first.page != null ? ` p.${first.page}` : ""}
                                </button>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td><span className={pill.cls}>{pill.label}</span></td>
                          </tr>
                        );
                      })}
                    {checklist.extra_items.map((ex, i) => (
                      <tr key={`extra-${i}`} className="unmapped-row">
                        <td className="num">+</td>
                        <td className="unmapped-cell">{ex.name}</td>
                        <td>—</td>
                        <td>—</td>
                        <td>招标要求外</td>
                        <td>
                          {ex.doc_id && taskId ? (
                            <button
                              type="button"
                              className="src-chip"
                              onClick={() => setLocate({ docId: ex.doc_id as string, page: ex.page, quote: null })}
                            >
                              {ex.doc_id}{ex.page != null ? ` p.${ex.page}` : ""}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td><span className="pill pill-gray">多余</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="tbl-foot">
                  口径：EXTRA 多余附件仅提示不判错不进问题数；MATCHED 全提供项默认收起，缺失/份数不足优先展示（L2-020/L2-024 规则组）。
                </div>
              </div>
            ) : checklist && checklist.counts.required === 0 ? (
              <div className="card">
                <div className="tbl-foot">本任务抽取时未包含附件要求维度——重新抽取后即可生成附件核对表（旧任务无此数据，不回填）。</div>
              </div>
            ) : null}
```

注意：`taskId`/`setLocate`/`unmapped-row`/`unmapped-cell`/`src-chip`/`metric-strip`/`metric-cell` 均为该文件/`bid-review.css` 既有词汇（DeviationsView 同款）；若 ResultsView 的定位状态变量名不是 `setLocate`（读文件确认，可能叫 `locate` state），照该文件实际命名替换。`metric-cell` 的 `ok/warn/err` 修饰类若 CSS 里没有，用 `bid-review.css` 已有等价类替换（`err` 在 DeviationsView 五格用过，`ok`/`warn` 若缺省就复用中性 `metric-cell` + pill 表达）。

- [ ] **Step 2: dom 测试（extend bid-review-results-evidence.dom.test.tsx）**

读该测试文件复用其路由 mock 骨架；加路由 `/api/extensions/bid-review/tasks/t1/attachment_checklist` 返回：

```ts
const CHECKLIST = {
  counts: { required: 3, matched: 1, partial: 1, missing: 1, extra: 1 },
  items: [
    { no: "ATT-E-008", name: "类似业绩证明", mandatory: "★", min_count: 3, found: 2, status: "PARTIAL", clause: "第三章3.4", refs: [{ doc_id: "bid.pdf", page: 118 }] },
    { no: "ATT-G-002", name: "安全生产许可证", mandatory: "★", min_count: null, found: 0, status: "MISSING", clause: null, refs: [] },
    { no: "ATT-F-001", name: "投标函", mandatory: "★", min_count: null, found: 1, status: "MATCHED", clause: null, refs: [{ doc_id: "bid.pdf", page: 2 }] },
  ],
  extra_items: [{ name: "企业宣传册", doc_id: "bid.pdf", page: 310 }],
};
```

用例（完整断言）：

```tsx
  it("L2-P1 附件核对表卡:五格/排序 MISSING 前/pill 映射/EXTRA 灰行/页码 chip", async () => {
    // 路由注册:tasks/t1/attachment_checklist → CHECKLIST(复用本文件 tasksQuery 等
    // 既有 mock,taskId 选 t1)
    renderView();
    await waitFor(() => expect(screen.getByText("附件核对表")).toBeTruthy());
    expect(screen.getByText("缺失")).toBeTruthy();           // pill-err MISSING
    expect(screen.getByText("份数不足")).toBeTruthy();        // pill-warn PARTIAL
    // MISSING 行排最前
    const missRow = screen.getByText("安全生产许可证").closest("tr") as HTMLElement;
    const partRow = screen.getByText("类似业绩证明").closest("tr") as HTMLElement;
    const rows = Array.from(partRow.parentElement?.children ?? []);
    expect(rows.indexOf(missRow)).toBeLessThan(rows.indexOf(partRow));
    expect(missRow.querySelectorAll(".pill-err").length).toBeGreaterThan(0);
    // EXTRA 灰行不产 issue:多余 pill + 页码 chip
    expect(screen.getByText("企业宣传册").closest("tr")?.textContent).toContain("p.310");
    expect(screen.getByText("多余")).toBeTruthy();
  });

  it("L2-P1 零投影:counts.required=0 → 诚实空态引导", async () => {
    // attachment_checklist 路由返回 counts 全 0 + items [] + extra_items []
    renderView();
    await waitFor(() =>
      expect(screen.getByText(/本任务抽取时未包含附件要求维度/)).toBeTruthy(),
    );
  });
```

- [ ] **Step 3: 跑测试 + typecheck + 全量单测防回归**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm test -- tests/unit/extensions/bid-review-results-evidence.dom.test.tsx && pnpm test 2>&1 | tail -20 && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"`
Expected: PASS；全量单测除既有挂账 `scheduled-task-form-dialog.dom.test.tsx`（full-suite 竞态,upstream #6903,已挂账不修）外全绿；typecheck `0`

- [ ] **Step 4: 提交 + push**

```bash
cd /d/eai/eai-flow-main && git add frontend/src/extensions/bid-review/components/ResultsView.tsx frontend/tests/unit/extensions/bid-review-results-evidence.dom.test.tsx && git commit -m "feat(bid-review): L2-P1 ResultsView 附件核对表卡——五格 counts strip+明细(MISSING 优先/pill 三态/页码 chip 复用 DocLocate)/EXTRA info 灰行不进问题数/零投影诚实空态(spec §5)" && git push origin main-dev-fork; git rev-list --left-right --count origin/main-dev-fork...main-dev-fork
```
Expected: push 成功 + `0	0`

---

### Task 10: 收尾 —— 重启 gateway、live 验证、wolf 记账

**Files:** 无代码改动（`.wolf/memory.md`、`.wolf/anatomy.md` 记账）

- [ ] **Step 1: 重启 gateway 加载新规则包/端点**

```bash
docker compose -p eai-docker restart gateway
```
等 30s 后验证端点进 openapi：`curl -s http://localhost:8001/openapi.json | grep -o attachment_checklist | head -1`（若 gateway 在 Docker 内另需容器内 curl——按既有手法 `docker exec deer-flow-gateway curl -s localhost:8001/openapi.json | grep -o attachment_checklist | head -1`）。
Expected: 输出 `attachment_checklist`

- [ ] **Step 2: 后端 lint + 全量 bid_review 测试终验**

```bash
cd /d/eai/eai-flow-main/backend && make lint && PYTHONPATH=. uv run pytest tests/ -v -k bid_review
```
Expected: lint 干净（新文件行宽 ≤240、import 排序）+ 测试全绿

- [ ] **Step 3: 记账**

- `.wolf/anatomy.md`：加 `attachments.py`、`test_bid_review_attachments.py`、`test_bid_review_checklist.py` 条目。
- `.wolf/memory.md`：追加本计划落地一行（任务清单+commits）。
- `.wolf/buglog.json`：仅当过程中修了 bug 才记。
- 更新 auto-memory：`bid-review-l2-p1-attachment-checklist-landed.md` + MEMORY.md 索引行。

- [ ] **Step 4: 汇报**

向用户汇报：N 个 commit 列表、live 端点验证结果、挂账（P2 子件分组/跨层去重、P3 类型指纹/4 套模板/gates 门禁、金标准评测集、附件抽取质量需真实扫描件走查）。

---

## Self-Review 记录

- **Spec 覆盖**：§1 字段契约→Task 3；§2 匹配器→Task 1/2；§3 规则包+算子→Task 4/5；§4 端点→Task 6；§5 UI 双卡→Task 8/9（不加导航页=无任务,正确）；§6 测试→各任务 TDD 步骤;§7 风险(covers 不复用/模板不做)已在 Task 1 注释与范围外。✅ 无缺口。
- **占位符**：无 TBD/「适当处理」；Task 6/8/9 各有一处「以实际文件签名为准对表」标注——那是对既有代码锚点的核对指令,不是实现占位,新代码全部给全。
- **类型一致**：`build_checklist(reqs, provided, bid_doc_id)` 签名 Task 2 定义、Task 6 消费一致；`BidChecklistItem.status` 三态与后端 `"MATCHED"|"PARTIAL"|"MISSING"` 一致；`fetchAttachmentChecklist`/`useBidAttachmentChecklist` 命名前后一致。
