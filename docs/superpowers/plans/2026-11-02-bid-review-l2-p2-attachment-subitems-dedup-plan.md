# 投标审查 L2-P2(复合附件子件分组 + 跨层实体去重)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 P1 spec §7 挂账的两件 P2:① 复合附件子件分组(分组失败降 UNKNOWN,禁强行 PARTIAL);② 跨层实体去重(L1>L2>L3,keep most_severe + related_issues)。

**Architecture:** 子件分组在 `engine/attachments.py` 纯函数层实现(复合 req 跳过两级贪心主匹配,第三段按子件独立归组;提供项引用父件却归属不了任何子件 → 父行 UNKNOWN);UNKNOWN 经 att_check 分支降 need_human(待人工,不进违规数)。跨层去重走**投影现算不落库**先例(deviations/checklist 同款):`ReviewIssue` 加 `entity_keys` JSON 列(幂等 ALTER),att 算子产实体键,`GET /tasks/{id}/issues` 现算归并——同实体键跨层 violation keep most_severe,其余行 `grouped_into` 标记(条目不删,items 全量返回),keep 行带 `related_issues` 摘要;前端隐藏 grouped 行并在 keep 卡渲染关联 chip。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy(extensions 库,create_all + 幂等 ALTER);前端 rstest(happy-dom 走 `.dom.test.tsx`)。

**Spec:** `docs/superpowers/specs/2026-11-02-bid-review-l2-p1-attachment-checklist-design.md` §0/§7(P2 挂账行:子件分组失败降 UNKNOWN 禁强行 PARTIAL;跨层去重 keep most_severe+related_issues)。

---

## 设计定版(自 spec 约束 + 本计划锁定)

| # | 决策 | 定案 |
|---|---|---|
| D1 | 子件契约 | `tender.attachment_requirements` 行新增可选 `sub_items: [{no?, name, mandatory?, min_count?}]`;`bid.attachment_index` 契约不变 |
| D2 | 子件匹配通道 | 子件从「未被其它 req 取走」的池独立归组:① provided.no == sub.no ② provided.no == `{父号}-{序}` 或 `{父号}.{序}`(序=sub_items 1-based 下标)③ normalize_name 全等 |
| D3 | 分组失败→UNKNOWN | 提供项**引用了父件**(no 以 `{父号}+分隔符(-–—.、)` 开头,或名称命中父名)却归属不了任何子件 → 父行 UNKNOWN → att_check 产 need_human。零引用=诚实 MISSING,不算分组失败。禁强行 PARTIAL/MATCHED |
| D4 | 父行状态上卷 | UNKNOWN > MISSING(任一子件缺) > PARTIAL(任一子件份数不足) > MATCHED;父 `found` = 子件命中数之和;父级 min_count 对复合件忽略(子件粒度判定) |
| D5 | counts 契约 | `attachment_checklist` counts 新增 `unknown` 格;items 行新增 `sub_results: [{no,name,found,status}]`(平件恒 `[]`) |
| D6 | 实体键 | `attachment:{no}`(无 no 用 `attachment:name:{normalize_name}`);att_check(att_check missing+unknown)/att_count(PARTIAL)issue 携带 |
| D7 | 去重挂投影 | `list_task_issues` 现算:同实体键 + **跨 ≥2 层** + 双方均为 violation(非 need_human)才归并;keep = severity 升序 → 层序 L1>L2>L3 → created_at 稳定;need_human 永不隐藏 |
| D8 | 审计不删条目 | items 全量返回,grouped 行带 `grouped_into=keep.id`;summary 口径不变(全量计);前端隐藏 grouped 行 + keep 卡渲染关联 chip(只读,无独立裁决入口——挂账) |
| D9 | 落库方式 | `ReviewIssue.entity_keys JSON` 列 + `database.py` 幂等 `ADD COLUMN IF NOT EXISTS`(extensions 先例,无 alembic) |

**Non-goals(P3,不做):** 类型指纹 sem 规则(semantic_confirm)、4 套行业模板、gates 门禁(依赖金标准集)、L1 语义实体抽取、年份连续性、zip 解包、L2 其余 24 条规则、related_issues 行级独立裁决。

**约束(全程有效):** 只提交 `main-dev-fork`;push flaky 用 until 循环重试到 `git rev-list --left-right --count origin/main-dev-fork...main-dev-fork` 为 `0	0`;`docs/superpowers/` 在 .gitignore,计划/spec 文件须 `git add -f`;**不碰他人 WIP**(`contract_price/service.py`、`settings/routers.py`、`bid-review.css`、`TaskStepper.tsx`、`TaskTitleTag.tsx` 等 git status 既有脏文件);后端测试 `cd backend && PYTHONPATH=. uv run pytest <file> -v`(Bash 工具);前端单文件 `npx rstest run <path>`(`pnpm test -- <file>` 不过滤);typecheck 门 `pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"` = 0;`make lint` 含全树 format --check(33 文件既有债务)只定向 format 自己的文件;改动加 EAI-CUSTOM 注释。

---

### Task 1: 匹配器——复合附件子件归组 + UNKNOWN

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`
- Test: `backend/tests/test_bid_review_attachments.py`

- [ ] **Step 1: 写失败测试**(追加到 `test_bid_review_attachments.py` 文件末尾)

```python
# ── L2 P2:复合附件子件分组(spec 2026-11-02 §7 挂账行) ──

def test_composite_matched_by_sub_channels():
    """子件三通道命中:no 全等 / {父号}-{序} / {父号}.{序} → 父行 MATCHED。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [
        {"no": "3.1", "name": "营业执照"},
        {"no": "", "name": "资质证书"},
    ]}
    prov = [
        {"no": "3.1", "name": "营业执照", "page": 5},
        {"no": "3-2", "name": "资质证书", "page": 9},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "MATCHED"
    assert e["found"] == 2
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MATCHED"]


def test_composite_missing_sub_rolls_up():
    """一子件缺 → 父行 MISSING(非 UNKNOWN);sub_results 指认缺口。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [
        {"no": "3.1", "name": "营业执照"},
        {"no": "3.2", "name": "资质证书"},
    ]}
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "MISSING"
    assert e["found"] == 1
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MISSING"]


def test_composite_group_failure_unknown():
    """提供项引用父号(no 前缀)却归属不了任何子件 → 父行 UNKNOWN,禁强行 PARTIAL/MISSING。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [
        {"no": "3.1", "name": "营业执照"},
        {"no": "3.2", "name": "资质证书"},
    ]}
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 40},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["found"] == 1  # 可归属部分仍计数
    assert match_attachments([req], prov)["extra"] == []  # 完税证明归组进父件,不再计 extra


def test_composite_zero_reference_is_missing_not_unknown():
    """完全没提供(零引用)→ 诚实 MISSING,不算分组失败。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]}
    e = match_attachments([req], [])["per_req"][0]
    assert e["status"] == "MISSING"


def test_composite_orphan_by_parent_name():
    """无父号时名称命中父名却归属不了子件 → UNKNOWN。"""
    req = {"no": "", "name": "资格审查文件", "sub_items": [{"no": "", "name": "营业执照"}]}
    prov = [{"no": "", "name": "资格审查文件（合并版）", "page": 7}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"


def test_flat_and_composite_mixed_pool_no_steal():
    """平件两级贪心先行,复合件只从剩余池归组;互不偷项。"""
    reqs = [
        {"no": "A-1", "name": "营业执照"},  # 平件,名称与 3 的子件同名
        {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]},
    ]
    prov = [
        {"no": "A-1", "name": "营业执照", "page": 2},
        {"no": "3-1", "name": "营业执照", "page": 5},
    ]
    out = match_attachments(reqs, prov)
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["per_req"][1]["status"] == "MATCHED"
    assert out["extra"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v -k composite`
Expected: FAIL(`KeyError: 'sub_results'` / 状态不是 UNKNOWN)

- [ ] **Step 3: 实现**——`attachments.py` 重构 `match_attachments` 并加两个助手:

```python
_SUB_STATUS_ORDER = {"UNKNOWN": 0, "MISSING": 1, "PARTIAL": 2, "MATCHED": 3}


def _status_for(found: int, min_count: int) -> str:
    """单项状态:0 份 MISSING;min_count>1 且不足 PARTIAL;其余 MATCHED。"""
    if found == 0:
        return "MISSING"
    if min_count > 1 and found < min_count:
        return "PARTIAL"
    return "MATCHED"


def _match_composite(req: dict, prov: list[dict], taken: set[int]) -> dict:
    """复合附件子件归组(L2 P2,spec 2026-11-02 §7 挂账行,EAI-CUSTOM):子件从
    「未被其它 req 两级匹配取走」的池独立归组(三通道:no 全等 / {父号}-{序} /
    {父号}.{序} / 名称归一全等)。提供项引用了父件(no 以 {父号}+分隔符开头,或名称
    命中父名)却归属不了任何子件 → 分组失败,父行 UNKNOWN(禁强行 PARTIAL)。
    零引用(什么都没提供)→ 诚实 MISSING,不算分组失败。"""
    subs = [s for s in (req.get("sub_items") or []) if isinstance(s, dict)]
    parent_no = str(req.get("no") or "").strip()
    parent_nm = normalize_name(req.get("name"))
    used: set[int] = set()
    sub_results = []
    for idx, s in enumerate(subs, start=1):
        s_no = str(s.get("no") or "").strip()
        s_nm = normalize_name(s.get("name"))
        hits = 0
        for i, p in enumerate(prov):
            if i in taken or i in used:
                continue
            p_no = str(p.get("no") or "").strip()
            hit = (s_no and p_no == s_no) or (s_nm and normalize_name(p.get("name")) == s_nm)
            if not hit and parent_no and p_no:
                hit = p_no == f"{parent_no}-{idx}" or p_no == f"{parent_no}.{idx}"
            if hit:
                used.add(i)
                hits += 1
        try:
            s_min = int(s.get("min_count") or 0)
        except (TypeError, ValueError):
            s_min = 0
        sub_results.append({"no": s_no, "name": str(s.get("name") or ""), "found": hits, "status": _status_for(hits, s_min)})
    orphan = False
    for i, p in enumerate(prov):
        if i in used:
            continue
        p_no = str(p.get("no") or "").strip()
        refs_parent = bool(parent_no and p_no and re.match(rf"^{re.escape(parent_no)}[-–—.、]", p_no))
        if not refs_parent and parent_nm:
            refs_parent = normalize_name(p.get("name")) == parent_nm
        if refs_parent:
            orphan = True
    return {"sub_results": sub_results, "orphan": orphan}
```

`match_attachments` 改为:两级贪心主匹配**跳过复合 req**(有非空 sub_items 的),复合 req 在其后走 `_match_composite`;状态上卷(D4)。整体替换为:

```python
def match_attachments(requirements: Any, provided: Any) -> dict:
    """两级精确匹配,贪心一对一:① no 全等(双方非空) ② normalize_name 全等。
    同一 req 可命中多份提供项(份数语义:min_count>1 且 found<min_count → PARTIAL)。
    状态:found==0→MISSING;否则见上;未匹配提供项→extra。
    P2 复合附件(spec 2026-11-02 §7):带非空 sub_items 的 req 跳过两级主匹配,
    子件独立归组(_match_composite);父行状态 = UNKNOWN > MISSING > PARTIAL >
    MATCHED 上卷,found=子件命中数之和,父级 min_count 忽略。"""
    reqs = [r for r in (requirements or []) if isinstance(r, dict)]
    prov = [p for p in (provided or []) if isinstance(p, dict)]
    taken: set[int] = set()
    matched: list[list[int]] = [[] for _ in reqs]
    # ① 编号精确(双方非空;O(n²) 对几十行清单足够);复合 req 不参与,防父名/父号偷走子件
    for ri, r in enumerate(reqs):
        if r.get("sub_items"):
            continue
        no = str(r.get("no") or "").strip()
        if not no:
            continue
        for i, p in enumerate(prov):
            if i not in taken and str(p.get("no") or "").strip() == no:
                taken.add(i)
                matched[ri].append(i)
    # ② 规范化名称全等(非包含)
    for ri, r in enumerate(reqs):
        if r.get("sub_items"):
            continue
        nm = normalize_name(r.get("name"))
        if not nm:
            continue
        for i, p in enumerate(prov):
            if i not in taken and normalize_name(p.get("name")) == nm:
                taken.add(i)
                matched[ri].append(i)

    per_req = []
    for ri, r in enumerate(reqs):
        if r.get("sub_items"):
            comp = _match_composite(r, prov, taken)
            found = sum(s["found"] for s in comp["sub_results"])
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            status = "UNKNOWN" if comp["orphan"] else worst
            per_req.append({"req": r, "matched": [], "found": found, "status": status, "sub_results": comp["sub_results"]})
            continue
        hits = [prov[i] for i in matched[ri]]
        found = len(hits)
        try:
            min_count = int(r.get("min_count") or 0)
        except (TypeError, ValueError):
            min_count = 0
        per_req.append({"req": r, "matched": hits, "found": found, "status": _status_for(found, min_count)})
    return {"per_req": per_req, "extra": [p for i, p in enumerate(prov) if i not in taken]}
```

模块 docstring 首段补一句:`P2 复合附件:带 sub_items 的 req 子件独立归组,分组失败降 UNKNOWN(spec §7)。`

- [ ] **Step 4: 跑全文件确认绿 + 既有 14 测试无回归**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py -v`
Expected: 全 PASS(旧 14 + 新 6)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py
git commit -m "feat(bid-review): L2-P2 匹配器复合附件子件归组——三通道子件匹配+父行 UNKNOWN(分组失败降级,禁强行 PARTIAL,spec §7)"
```

---

### Task 2: build_checklist——counts.unknown + sub_results

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`(build_checklist)
- Test: `backend/tests/test_bid_review_attachments.py`(投影单测)+ `backend/tests/test_bid_review_checklist.py`(端点契约)

- [ ] **Step 1: 写失败测试**

`test_bid_review_attachments.py` 追加:

```python
def test_build_checklist_unknown_and_sub_results():
    """投影:UNKNOWN 进 counts.unknown;复合行带 sub_results;平件 sub_results=[]。"""
    reqs = [
        {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]},
        {"no": "A-1", "name": "投标函"},
    ]
    prov = [{"no": "3-9", "name": "完税证明", "page": 40}, {"no": "A-1", "name": "投标函", "page": 2}]
    out = build_checklist(reqs, prov, bid_doc_id="投标文件.docx")
    assert out["counts"]["unknown"] == 1
    assert out["counts"]["required"] == 2
    assert out["items"][0]["sub_results"] == [{"no": "3.1", "name": "营业执照", "found": 0, "status": "MISSING"}]
    assert out["items"][1]["sub_results"] == []
```

`test_bid_review_checklist.py` 追加(夹具沿用文件内 db/client fixture):

```python
@pytest.mark.asyncio
async def test_endpoint_composite_unknown_passthrough(db, client):
    """端点透传 counts.unknown + items[].sub_results(build_checklist 原样出)。"""
    from app.extensions.bid_review.engine.attachments import build_checklist  # noqa: F401  端点同源
    comp_fields = {
        "tender.attachment_requirements": [
            {"no": "3", "name": "资格审查文件", "clause": "第三章3.1", "mandatory": "★", "min_count": None,
             "sub_items": [{"no": "3.1", "name": "营业执照"}]},
        ],
        "bid.attachment_index": [{"no": "3-9", "name": "完税证明", "page": 40, "pages": None}],
    }
    from app.extensions.bid_review import crud as C
    task = await C.create_task(db, owner_id="u1", mode="deep", materials_hash="h-p2")
    from app.extensions.bid_review.models import BaselinePackage
    db.add(BaselinePackage(task_id=task.id, kind="tender", doc_id="招标文件.pdf", fields=comp_fields, provenance={}, materials_hash="h-p2"))
    db.add(BaselinePackage(task_id=task.id, kind="bid", doc_id="投标文件.docx", fields=comp_fields, provenance={}, materials_hash="h-p2"))
    await db.commit()
    r = await client.get(f"/tasks/{task.id}/attachment_checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["unknown"] == 1
    assert body["items"][0]["status"] == "UNKNOWN"
    assert body["items"][0]["sub_results"][0]["name"] == "营业执照"
```

> 注:`create_task` 签名以 `crud.py` 实际为准(本文件既有测试已用同款夹具——写前先看一眼同文件既有用例怎么建 task/baseline,完全照抄其构造方式,只换 fields)。

- [ ] **Step 2: 跑测试确认失败**(`KeyError: 'unknown'`)

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py::test_build_checklist_unknown_and_sub_results tests/test_bid_review_checklist.py -v`

- [ ] **Step 3: 实现**——`build_checklist` items 行加 `"sub_results": e.get("sub_results") or []`(放 `refs` 之后),counts 加 `"unknown": sum(1 for i in items if i["status"] == "UNKNOWN")`(放 `missing` 与 `extra` 之间)。docstring 补:`P2:复合行带 sub_results,分组失败行 status=UNKNOWN 进 counts.unknown。`

- [ ] **Step 4: 跑两文件确认绿**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_attachments.py tests/test_bid_review_checklist.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_attachments.py backend/tests/test_bid_review_checklist.py
git commit -m "feat(bid-review): L2-P2 核对表投影 counts.unknown+sub_results——端点透传零改动(现算不落库)"
```

---

### Task 3: rule_runner——att UNKNOWN→need_human + entity_keys

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`
- Test: `backend/tests/test_bid_review_rule_runner.py`

- [ ] **Step 1: 写失败测试**(追加到该文件 att 测试区之后)

```python
# ── L2 P2:UNKNOWN→need_human + 实体键(spec 2026-11-02 §7 挂账行) ──

COMP_REQS = [
    {"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None,
     "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "资质证书"}]},
]
COMP_FIELDS = {
    "tender.attachment_requirements": COMP_REQS,
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 40},  # 引用父号,归属不了 → 分组失败
    ],
}


def test_att_check_unknown_degrades_need_human():
    """分组失败 → 父行产 need_human(禁强行 PARTIAL/MISSING);不进 missing 列表。"""
    issues = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "need_human"
    assert "资格审查文件" in issues[0]["message"]


def test_att_issues_carry_entity_keys():
    """att issue 携带实体键 attachment:{no};无 no 用 name 通道。"""
    issues = run_det_rule(_att_rule("att_check"), ATT_FIELDS)
    assert issues[0]["entity_keys"] == ["attachment:A-2"]  # 只 MISSING 的 A-2
    nh = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert nh[0]["entity_keys"] == ["attachment:3"]


def test_att_issue_entity_keys_default_empty():
    """非 att 算子 issue 也带 entity_keys=[](形状统一,worker 透传零分支)。"""
    from app.extensions.bid_review.engine.rule_runner import _issue
    iss = _issue(_att_rule("att_check"), {}, {"missing": ["x"]})
    assert iss["entity_keys"] == []
```

- [ ] **Step 2: 跑测试确认失败**(`KeyError: 'entity_keys'`)

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py -v -k "unknown or entity"`

- [ ] **Step 3: 实现**——`rule_runner.py`:

① 文件头 import 区补(与 `match_attachments` 同源):

```python
from app.extensions.bid_review.engine.attachments import match_attachments, normalize_name
```

(按现有 import 实际样式合并,勿重复导入 `match_attachments`)

② `_issue` 与 `_need_human` 返回 dict 各加一行 `"entity_keys": []`(放 `"source"` 之前)。

③ 模块级助手(放 `_need_human` 之后):

```python
def _entity_key(req: dict) -> str:
    """附件实体键(L2 P2 D6):no 优先,无 no 用归一名称通道——跨层去重的归并依据。"""
    no = str(req.get("no") or "").strip()
    return f"attachment:{no}" if no else f"attachment:name:{normalize_name(req.get('name'))}"
```

④ att 分支整体替换为:

```python
        elif chk["op"] in ("att_check", "att_count"):  # L2 P1 附件核对(spec 2026-11-02 §3);P2:UNKNOWN→need_human+实体键(§7)
            reqs, prov = _val(chk["left"], fields), _val(chk["right"], fields)
            if not isinstance(reqs, list) or not isinstance(prov, list):
                issues.append(_need_human(rule, "附件字段缺失或类型非法(need_human)"))
            else:
                out = match_attachments(reqs, prov)

                def _label(r: dict) -> str:
                    no = str(r.get("no") or "").strip()
                    return f"{no} {r.get('name')}" if no else str(r.get("name") or "")

                if chk["op"] == "att_check":
                    miss = [r for r in out["per_req"] if r["status"] == "MISSING"]
                    unknown = [r for r in out["per_req"] if r["status"] == "UNKNOWN"]
                    if miss:
                        iss = _issue(rule, fields, {"missing": [_label(r["req"]) for r in miss]})
                        iss["entity_keys"] = [_entity_key(r["req"]) for r in miss]
                        issues.append(iss)
                    for r in unknown:  # 分组失败降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                        nh["entity_keys"] = [_entity_key(r["req"])]
                        issues.append(nh)
                else:
                    partial = [r for r in out["per_req"] if r["status"] == "PARTIAL"]
                    if partial:
                        iss = _issue(
                            rule,
                            fields,
                            {"insufficient": [f"{_label(r['req'])}: 要求{r['req'].get('min_count')}份/提供{r['found']}份" for r in partial]},
                        )
                        iss["entity_keys"] = [_entity_key(r["req"]) for r in partial]
                        issues.append(iss)
```

- [ ] **Step 4: 跑全文件确认绿**(既有 att 测试无回归——ATT_FIELDS 无复合件、无 UNKNOWN)

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py tests/test_bid_review_metrics.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rule_runner.py backend/tests/test_bid_review_rule_runner.py
git commit -m "feat(bid-review): L2-P2 att 算子 UNKNOWN 降 need_human+实体键——分组失败禁强行 PARTIAL(spec §7)"
```

---

### Task 4: entity_keys 落库链(models + 幂等列 + crud + worker + IssueOut)

**Files:**
- Modify: `backend/app/extensions/bid_review/models.py:77`(evidence 行后)
- Modify: `backend/app/extensions/database.py`(EAI-CUSTOM 幂等补列区,`tlt_translation_tasks ... draft_edited_by` 行之后)
- Modify: `backend/app/extensions/bid_review/crud.py:118`(add_issue 签名+赋值)
- Modify: `backend/app/extensions/bid_review/worker.py:370`(add_issue 调用)
- Modify: `backend/app/extensions/bid_review/schemas.py:52`(IssueOut)
- Test: `backend/tests/test_bid_review_grouping.py`(新建,Task 5 一并跑)

- [ ] **Step 1: 写失败测试**(新文件 `backend/tests/test_bid_review_grouping.py`——先只放落库断言,Task 5 补投影用例)

```python
"""L2 P2 跨层实体去重(spec 2026-11-02 §7 挂账行):entity_keys 落库链 +
list_task_issues 投影归并(_cross_layer_group 纯函数直验,先例=checklist 现算不落库)。

归并规则(D7):同实体键 + 跨 ≥2 层 + 双方 violation(非 need_human)才归并;
keep = severity 升序 → 层序 L1>L2>L3 → created_at 稳定;need_human 永不隐藏。
条目不删:grouped 行标 grouped_into=keep.id(items 全量返回),keep 行带 related_issues。
"""

from types import SimpleNamespace

from app.extensions.bid_review.routers import _cross_layer_group


def _iss(id, rule_id, layer, severity, *, verdict="violation", need_human=False, keys=None, created_at="2026-11-02T00:00:00Z", message="m"):
    return SimpleNamespace(
        id=id, rule_id=rule_id, layer=layer, severity=severity, verdict=verdict,
        need_human=need_human, entity_keys=keys or [], created_at=created_at, message=message,
    )


def test_cross_layer_group_keeps_most_severe():
    """L2 fatal 与 L3 minor 同实体 → keep L2;L3 行 grouped_into,keep 带 related。"""
    a = _iss("a", "L2-020", "L2", "fatal", keys=["attachment:A-2"])
    b = _iss("b", "L3-005", "L3", "minor", keys=["attachment:A-2"])
    info = _cross_layer_group([a, b])
    assert info["b"]["grouped_into"] == "a"
    assert info["a"]["grouped_into"] is None
    assert info["a"]["related"] == [
        {"id": "b", "rule_id": "L3-005", "layer": "L3", "severity": "minor", "message": "m"},
    ]
    assert info["b"]["related"] == []


def test_cross_layer_severity_tie_prefers_layer_order():
    """同 severity → L1>L2>L3 层序定 keep(spec:跨层去重 L1>L2>L3)。"""
    l3 = _iss("x", "L3-010", "L3", "major", keys=["attachment:A-1"])
    l2 = _iss("y", "L2-024", "L2", "major", keys=["attachment:A-1"])
    info = _cross_layer_group([l3, l2])
    assert info["x"]["grouped_into"] == "y"  # L2 胜出
    assert info["y"]["grouped_into"] is None


def test_need_human_and_single_layer_never_group():
    """need_human 不参与归并(待人工必须可见);同层/无共享键/单实体不归并。"""
    nh = _iss("n", "L2-020", "L2", "fatal", verdict="need_human", need_human=True, keys=["attachment:A-1"])
    v_same_layer = _iss("s", "L2-024", "L2", "major", keys=["attachment:A-1"])
    v_other_key = _iss("o", "L3-010", "L3", "minor", keys=["attachment:B-1"])
    v_no_keys = _iss("k", "L1-001", "L1", "fatal", keys=[])
    info = _cross_layer_group([nh, v_same_layer, v_other_key, v_no_keys])
    assert info == {}
```

- [ ] **Step 2: 跑测试确认失败**(`ImportError: _cross_layer_group`)

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_grouping.py -v`

- [ ] **Step 3: 实现**(本 Task 先落 `_cross_layer_group` + 存储链,投影接线在 Task 5)

`models.py` ReviewIssue(evidence 行之后、dedup_key 之前)加:

```python
    entity_keys: Mapped[list] = mapped_column(JSON, default=list)  # EAI-CUSTOM(L2 P2):附件实体键 attachment:{no|name:归一名};跨层去重投影依据
```

`database.py` 幂等补列区(EAI-CUSTOM 区块内,tlt draft_edited_by 行后)加:

```python
        # EAI-CUSTOM (bid-review L2 P2): 问题实体键列(create_all 不 ALTER 已有表,幂等加列)
        await conn.execute(text("ALTER TABLE bid_review_issues ADD COLUMN IF NOT EXISTS entity_keys JSONB"))
```

`crud.py` add_issue:签名 keyword-only 区(`confidence: float = 1.0` 旁)加 `entity_keys: list | None = None,`;函数体 INSERT/构造处与其它列同样式赋值 `entity_keys=list(entity_keys or [])`(照 evidence 行的实际构造写法)。

`worker.py` add_issue 调用(约 :370)在 `confidence=` 行后加:

```python
                entity_keys=list(_issue_get(issue, "entity_keys") or []),
```

`schemas.py` IssueOut 在 `review_state` 之前加:

```python
    # EAI-CUSTOM(L2 P2):附件实体键(落库);grouped_into/related_issues 为投影现算
    # (list_task_issues 跨层去重,先例=deviations/checklist 不落库),旧网关缺省。
    entity_keys: list = []
    grouped_into: str | None = None
    related_issues: list = []
```

`routers.py` 模块级(list_task_issues 之前)加纯函数:

```python
_SEV_RANK = {"fatal": 0, "major": 1, "minor": 2, "info": 3}
_LAYER_RANK = {"L1": 0, "L2": 1, "L3": 2}


def _cross_layer_group(issues: list) -> dict[str, dict]:
    """跨层实体去重投影(L2 P2,spec 2026-11-02 §7 挂账行,EAI-CUSTOM;现算不落库,
    先例=deviations/attachment_checklist):同一实体键(entity_keys 交集)且跨 ≥2 层的
    violation(非 need_human)归并——keep most_severe(并列取层序 L1>L2>L3,再取
    created_at 稳定),其余行标 grouped_into=keep.id,keep 行带 related_issues 摘要。
    条目不删:items 仍全量返回(前端隐藏 grouped 行),summary 口径不变。
    need_human 不参与归并(待人工必须可见)。多实体键行按键名字序迭代保稳定。"""
    info: dict[str, dict] = {}
    keyed: dict[str, list] = {}
    for i in issues:
        if getattr(i, "verdict", "") != "violation" or getattr(i, "need_human", False):
            continue
        for k in getattr(i, "entity_keys", None) or []:
            keyed.setdefault(k, []).append(i)
    for key in sorted(keyed):
        group = keyed[key]
        layers = {getattr(i, "layer", "") for i in group}
        if len(layers) < 2 or len({i.id for i in group}) < 2:
            continue
        ranked = sorted(group, key=lambda i: (_SEV_RANK.get(getattr(i, "severity", ""), 9), _LAYER_RANK.get(getattr(i, "layer", ""), 9), getattr(i, "created_at", "")))
        keep = ranked[0]
        for i in ranked[1:]:
            if i.id == keep.id:
                continue
            info.setdefault(i.id, {"grouped_into": None, "related": []})["grouped_into"] = keep.id
            kentry = info.setdefault(keep.id, {"grouped_into": None, "related": []})
            if all(r["id"] != i.id for r in kentry["related"]):
                kentry["related"].append(
                    {"id": i.id, "rule_id": i.rule_id, "layer": i.layer, "severity": i.severity, "message": i.message}
                )
    return info
```

- [ ] **Step 4: 跑测试确认绿**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_grouping.py tests/test_bid_review_checklist.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/models.py backend/app/extensions/database.py backend/app/extensions/bid_review/crud.py backend/app/extensions/bid_review/worker.py backend/app/extensions/bid_review/schemas.py backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_grouping.py
git commit -m "feat(bid-review): L2-P2 实体键落库链+跨层归并纯函数——entity_keys JSON 列幂等补列,_cross_layer_group 现算(D6/D7/D9)"
```

---

### Task 5: 投影接线——list_task_issues 归并

**Files:**
- Modify: `backend/app/extensions/bid_review/routers.py:423`(list_task_issues)
- Test: `backend/tests/test_bid_review_grouping.py`

- [ ] **Step 1: 写失败测试**(追加到 `test_bid_review_grouping.py`;复用 checklist 文件同款 sqlite+httpx 夹具——把 `test_bid_review_checklist.py` 的 `db`/`client` 两个 fixture 原样复制到本文件顶部)

```python
import httpx  # noqa: F401  (夹具同 test_bid_review_checklist.py)
import pytest_asyncio  # noqa: F401
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db


@pytest.mark.asyncio
async def test_issues_endpoint_grouping_wiring(db, client):
    """端点接线:同实体跨层两 violation → grouped 行带 grouped_into,keep 带 related;
    平凡单层行零字段(IssueOut 缺省)。summary 口径不变(全量计)。"""
    task = await crud.create_task(db, owner_id="u1", mode="deep", materials_hash="h-g")
    await crud.add_issue(
        db, task_id=task.id, owner_id="u1", rule_id="L2-020", layer="L2", severity="fatal",
        verdict="violation", message="缺少附件 A-2 业绩证明", dedup_key="L2-020|-|k1",
        entity_keys=["attachment:A-2"],
    )
    await crud.add_issue(
        db, task_id=task.id, owner_id="u1", rule_id="L3-005", layer="L3", severity="minor",
        verdict="violation", message="业绩证明表述不一致", dedup_key="L3-005|-|k2",
        entity_keys=["attachment:A-2"],
    )
    await crud.add_issue(
        db, task_id=task.id, owner_id="u1", rule_id="L2-024", layer="L2", severity="major",
        verdict="violation", message="无关问题", dedup_key="L2-024|-|k3",
    )
    r = await client.get(f"/tasks/{task.id}/issues")
    assert r.status_code == 200
    items = {i["rule_id"]: i for i in r.json()["items"]}
    assert items["L3-005"]["grouped_into"] == items["L2-020"]["id"]
    assert items["L2-020"]["grouped_into"] is None
    assert items["L2-020"]["related_issues"][0]["rule_id"] == "L3-005"
    assert items["L2-024"]["grouped_into"] is None and items["L2-024"]["related_issues"] == []
    assert len(r.json()["items"]) == 3  # 条目不删(D8)
```

> 同样:`create_task`/夹具写前照抄 `test_bid_review_checklist.py` 实际构造。

- [ ] **Step 2: 跑测试确认失败**(grouped_into 全 None)

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_grouping.py -v`

- [ ] **Step 3: 实现**——`list_task_issues` 中段替换:

```python
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    states = await crud.latest_feedback_actions(db, [i.id for i in issues])
    grouping = _cross_layer_group(issues)  # L2 P2 跨层实体去重(现算,不落库)
    items = []
    for i in issues:
        out = _with_review_state(i, states)
        g = grouping.get(i.id)
        if g:
            out.grouped_into = g["grouped_into"]
            out.related_issues = g["related"]
        items.append(out)
    return {
        "items": items,
        # 汇总分级(A12 T14 集成约束①):口径不变——全量计(grouped 行仍计,前端隐藏由展示层负责)
        "summary": worker.summarize_issues(issues),
    }
```

- [ ] **Step 4: 跑 bid_review 全域测试确认绿**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_grouping.py tests/ -k "bid_review" -q`
Expected: 全 PASS(237+ 新增)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_grouping.py
git commit -m "feat(bid-review): L2-P2 issues 端点跨层去重投影——keep most_severe+related_issues,条目不删 summary 口径不变(D7/D8)"
```

---

### Task 6: 前端契约——types + api

**Files:**
- Modify: `frontend/src/extensions/bid-review/types.ts:44`(IssueOut)
- Modify: `frontend/src/extensions/bid-review/api.ts:168-204`(附件三类型)

- [ ] **Step 1: 类型先行(无独立测试,typecheck 即门)**

`types.ts` IssueOut 在 `review_state?` 行后加:

```typescript
  /** EAI-CUSTOM(L2 P2):实体键(落库)/跨层去重投影(grouped_into+related,现算);旧网关缺省。 */
  entity_keys?: string[];
  grouped_into?: string | null;
  related_issues?: Array<{
    id: string;
    rule_id: string;
    layer: string;
    severity: string;
    message: string;
  }>;
```

`api.ts`:

`BidChecklistItem` 的 `status` 改 `"MATCHED" | "PARTIAL" | "MISSING" | "UNKNOWN"`,行尾(`refs` 后)加:

```typescript
  /** 复合附件子件核对(P2);平件恒 []。 */
  sub_results: Array<{ no: string; name: string; found: number; status: "MATCHED" | "PARTIAL" | "MISSING" }>;
```

`BidAttachmentChecklistOut.counts` 在 `missing` 后加 `unknown: number;`。两处注释里「P1 三态,UNKNOWN 由 need_human 兜底不进表」改为「P1 三态 + P2 UNKNOWN(子件分组失败→需人工)」。

- [ ] **Step 2: typecheck**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"`
Expected: 非 0(sub_results/unknown 使 ResultsView 旧取值报错——先记下报错文件,Task 7 修零);若 ResultView 因 optional/新增键不报错则直接 0 也接受(新键全部向后兼容加法)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/bid-review/types.ts frontend/src/extensions/bid-review/api.ts
git commit -m "feat(bid-review): L2-P2 前端契约——BidChecklistItem+UNKNOWN/sub_results/counts.unknown,IssueOut+entity_keys/grouped_into/related_issues"
```

---

### Task 7: ResultsView 渲染(UNKNOWN 格/子件行/关联折叠)+ BaselineView 子件注

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`

- [ ] **Step 1: ResultsView 五处小改**

① `checklistPill`(约 :247)加 UNKNOWN 分支(default 之上):

```typescript
    case "UNKNOWN":
      return { label: "需人工", cls: "pill pill-gray" };
```

② `clItems` 排序(约 :317)rank 改 `{ MISSING: 0, UNKNOWN: 1, PARTIAL: 2, MATCHED: 3 }`,注释补「UNKNOWN 次于 MISSING(分组失败,待人工)」。

③ issues 基础列表(约 :342)过滤 grouped 行(隐藏由展示层负责,summary 随之只计可见——与后端全量 summary 并存,后端口径注在 tbl-foot):

```typescript
  const issues = useMemo(
    () => (issuesQuery.data ?? []).filter((i) => !i.grouped_into),
    [issuesQuery.data],
  );
```

④ metric-strip(约 :1084)在「缺失」格之后、「多余附件」格之前插一格:

```tsx
                <div className="metric-cell">
                  <div className="m-lb">需人工</div>
                  <div className="m-v">{checklist.counts.unknown}</div>
                </div>
```

⑤ 明细表 name 单元格(`{it.name}` 之后、clause span 之前)插子件行;提供情况列 UNKNOWN 显示「无法自动分组」:

```tsx
                            {(it.sub_results?.length ?? 0) > 0 ? (
                              <div className="hd-sub">
                                子件:
                                {it.sub_results
                                  .map(
                                    (s) =>
                                      `${s.no ? `${s.no} ` : ""}${s.name} ${s.found > 0 ? "✓" : "✗"}`,
                                  )
                                  .join(" · ")}
                              </div>
                            ) : null}
```

提供情况列 `{it.found > 0 ? \`已提供 ${it.found} 份\` : "未提供"}` 改:

```tsx
                            {it.status === "UNKNOWN"
                              ? "无法自动分组"
                              : it.found > 0
                                ? `已提供 ${it.found} 份`
                                : "未提供"}
```

- [ ] **Step 2: 关联问题 chip——问题卡渲染**

`grep -n "issues.map\|\.map((it" frontend/src/extensions/bid-review/components/ResultsView.tsx` 定位问题列表 map;在问题消息渲染节点之后追加(保持该文件现有 JSX 缩进风格):

```tsx
                          {(it.related_issues?.length ?? 0) > 0 ? (
                            <div className="hd-sub">
                              关联问题 {it.related_issues!.length}:
                              {it.related_issues!
                                .map((r) => `[${r.rule_id} ${r.severity}] ${r.message}`)
                                .join(";")}
                            </div>
                          ) : null}
```

(若 map 变量名不是 `it`,以实际为准替换。)

- [ ] **Step 3: BaselineView 附件要求卡子件注**——`attachReqs` 行内类型(`mandatory` 后)加 `sub_items?: Array<{ no?: string; name?: string } | null>;`;要求卡名称单元格 clause span 之后加:

```tsx
                              {r.sub_items?.length ? (
                                <div className="hd-sub">
                                  子件:
                                  {r.sub_items
                                    .map((s) => `${s.no ? `${s.no} ` : ""}${s.name ?? ""}`)
                                    .join(" / ")}
                                </div>
                              ) : null}
```

- [ ] **Step 4: typecheck + 既有 dom 测试回归**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"` → 0
Run: `cd /d/eai/eai-flow-main/frontend && npx rstest run tests/unit/extensions/bid-review-results-evidence.dom.test.tsx tests/unit/extensions/bid-review-baseline.dom.test.tsx`
Expected: 绿(若旧 checklist 断言硬编码五格/三态 pill 失败,按新六格/四态如实更新断言)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/bid-review/components/ResultsView.tsx frontend/src/extensions/bid-review/components/BaselineView.tsx
git commit -m "feat(bid-review): L2-P2 ResultsView UNKNOWN 需人工格+子件行+关联问题折叠;BaselineView 子件注(spec §5 P2 增量)"
```

---

### Task 8: dom 测试(RESULTS 夹具 + BASELINE fixture 增列)

**Files:**
- Modify: `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`(ATTACH_BASELINES 夹具 + 断言)
- Modify: `frontend/tests/unit/extensions/bid-review-results-evidence.dom.test.tsx`(追加自足 describe)

- [ ] **Step 1: BaselineView dom——夹具第一 req 加 sub_items,断言子件行**

`ATTACH_BASELINES[0].fields["tender.attachment_requirements"]` 的 `ATT-E-008` 行加:

```typescript
        sub_items: [{ no: "E-1", name: "业绩合同" }, { no: "E-2", name: "中标通知书" }],
```

既有用例「附件要求/投标附件清单双卡」内在 `getAllByText("类似业绩证明")` 断言后加:

```typescript
    expect(screen.getByText(/子件:E-1 业绩合同 \/ E-2 中标通知书/)).toBeTruthy();
```

- [ ] **Step 2: ResultsView dom——新 describe(自足夹具,文件末追加;模块顶部 rs.mock 已共享)**

```tsx
// ── L2 P2 附件子件分组 + 跨层去重(EAI-CUSTOM 2026-11-02 spec §7) ──

const P2_CHECKLIST = {
  counts: { required: 2, matched: 1, partial: 0, missing: 0, unknown: 1, extra: 0 },
  items: [
    {
      no: "3",
      name: "资格审查文件",
      mandatory: "★",
      min_count: null,
      found: 1,
      status: "UNKNOWN",
      clause: "第三章3.1",
      refs: [],
      sub_results: [
        { no: "3.1", name: "营业执照", found: 1, status: "MATCHED" },
        { no: "3.2", name: "资质证书", found: 0, status: "MISSING" },
      ],
    },
    {
      no: "A-1",
      name: "投标函",
      mandatory: "★",
      min_count: null,
      found: 1,
      status: "MATCHED",
      clause: null,
      refs: [],
      sub_results: [],
    },
  ],
  extra_items: [],
};

const P2_ISSUES = [
  {
    id: "i1", task_id: "t1", rule_id: "L2-020", layer: "L2", severity: "fatal",
    verdict: "violation", clause_id: null, message: "缺少附件 A-2", fix: "", evidence: [],
    dedup_key: "k1", need_human: false, confidence: 1, review_state: "unresolved",
    created_at: "2026-11-02T00:00:00Z", entity_keys: ["attachment:A-2"],
    grouped_into: null,
    related_issues: [
      { id: "i2", rule_id: "L3-005", layer: "L3", severity: "minor", message: "业绩证明表述不一致" },
    ],
  },
  {
    id: "i2", task_id: "t1", rule_id: "L3-005", layer: "L3", severity: "minor",
    verdict: "violation", clause_id: null, message: "业绩证明表述不一致", fix: "", evidence: [],
    dedup_key: "k2", need_human: false, confidence: 1, review_state: "unresolved",
    created_at: "2026-11-02T00:01:00Z", entity_keys: ["attachment:A-2"],
    grouped_into: "i1", related_issues: [],
  },
];

describe("bid-review ResultsView L2 P2 子件分组+跨层去重(EAI-CUSTOM 2026-11-02)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("附件核对表:UNKNOWN→需人工 pill+第六格 counts+子件明细行", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("done"));
      if (path.endsWith("/issues")) return jsonRes({ items: [], summary: {} });
      if (path.endsWith("/rulepacks")) return jsonRes([]);
      if (path.includes("/attachment_checklist")) return jsonRes(P2_CHECKLIST);
      if (path.includes("/score_coverage")) return jsonRes({ total: 0, covered: 0, items: [] });
      if (path.includes("/docs/") && path.includes("/content")) return jsonRes({ segments: [] });
      return jsonRes({}, 404);
    };
    renderResults();

    expect(await screen.findByText("需人工")).toBeTruthy(); // pill
    expect(screen.getByText("需人工").className).toContain("pill-gray");
    expect(screen.getByText(/子件:3.1 营业执照 ✓ · 3.2 资质证书 ✗/)).toBeTruthy();
    expect(screen.getByText("无法自动分组")).toBeTruthy();
    // 第六格:卡内 metric-strip 的需人工值 1(class 限定防与 pill 撞文本)
    const card = screen.getByText("附件核对表").closest(".card");
    expect(card?.querySelector(".metric-cell .m-v")?.textContent).toBeTruthy();
    expect(card?.textContent).toContain("需人工");
  });

  it("问题清单:grouped 行隐藏,keep 卡渲染关联问题 chip", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("done"));
      if (path.endsWith("/issues")) return jsonRes({ items: P2_ISSUES, summary: {} });
      if (path.endsWith("/rulepacks")) return jsonRes([]);
      if (path.includes("/attachment_checklist"))
        return jsonRes({ counts: { required: 0, matched: 0, partial: 0, missing: 0, unknown: 0, extra: 0 }, items: [], extra_items: [] });
      if (path.includes("/score_coverage")) return jsonRes({ total: 0, covered: 0, items: [] });
      if (path.includes("/docs/") && path.includes("/content")) return jsonRes({ segments: [] });
      return jsonRes({}, 404);
    };
    renderResults();

    // keep 卡(L2-020)可见并带关联 chip;grouped 行(L3-005 独立卡)隐藏
    expect(await screen.findByText(/关联问题 1/)).toBeTruthy();
    expect(screen.getByText(/L3-005 minor\] 业绩证明表述不一致/)).toBeTruthy();
    expect(screen.queryByText(/^业绩证明表述不一致$/)).toBeNull(); // 独立卡不在
  });
});
```

> `TASK`/`renderResults`/`calls`/`responder`/`jsonRes` 若与该文件既有助手重名,以文件内既有定义为准复用(本 describe 写在该文件末尾,顶部共享 mock 直接可用);`renderResults` 不存在则按同文件既有用例的 render 写法( QueryClientProvider wrapper + `<ResultsView taskId="t1" />`)落一个。

- [ ] **Step 3: 跑两个 dom 文件**

Run: `cd /d/eai/eai-flow-main/frontend && npx rstest run tests/unit/extensions/bid-review-baseline.dom.test.tsx tests/unit/extensions/bid-review-results-evidence.dom.test.tsx`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx frontend/tests/unit/extensions/bid-review-results-evidence.dom.test.tsx
git commit -m "test(bid-review): L2-P2 dom——需人工 pill/子件行/第六格+grouped 隐藏与关联 chip(baseline 夹具带 sub_items)"
```

---

### Task 9: 收尾——全量验证 + wolf + push

- [ ] **Step 1: 后端全量 bid_review**

Run: `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/ -k "bid_review" -q`
Expected: 全 PASS(237 + 本计划新增约 12)

- [ ] **Step 2: 后端 lint(只自己的文件)**

Run: `cd /d/eai/eai-flow-main/backend && uv run ruff check app/extensions/bid_review/ tests/test_bid_review_attachments.py tests/test_bid_review_checklist.py tests/test_bid_review_rule_runner.py tests/test_bid_review_grouping.py && uv run ruff format app/extensions/bid_review/engine/attachments.py app/extensions/bid_review/engine/rule_runner.py tests/test_bid_review_grouping.py`
Expected: 0 error(全树 33 文件既有 format 债务不动)

- [ ] **Step 3: 前端全量测试 + typecheck**

Run: `cd /d/eai/eai-flow-main/frontend && pnpm test 2>&1 | tail -5`(全量;scheduled-task-form-dialog 既有 flaky #6903 挂账,若仅它挂注记后重跑一次)
Run: `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep -v contract-price | grep -c "error TS"` → 0

- [ ] **Step 4: gateway 重启生效 + openapi 冒烟**

Run: `docker compose -p eai-docker restart gateway`,等健康后:
`docker exec deer-flow-gateway python -c "import json,urllib.request;d=json.load(urllib.request.urlopen('http://127.0.0.1:8001/openapi.json'));print('issues' if '/api/extensions/bid-review/tasks/{{task_id}}/issues' in d['paths'] else 'MISSING')"`
Expected: `issues`(端点已在;P2 字段为响应体增量,openapi 不单列)

- [ ] **Step 5: wolf 记账**

`.wolf/anatomy.md` 追加 `test_bid_review_grouping.py` 条目;`.wolf/memory.md` 追加一行;`.wolf/cerebrum.md` 若有新教训(如 rstest 夹具重名)记 Do-Not-Repeat。

- [ ] **Step 6: push 到 0 0**

```bash
git log --oneline -9  # 确认本计划 8 个 feat/test commit + 本计划文件 commit
until git push origin main-dev-fork 2>&1; do sleep 15; done
git rev-list --left-right --count origin/main-dev-fork...main-dev-fork  # 必须 0	0
```

计划文件本身先单独提交:

```bash
git add -f docs/superpowers/plans/2026-11-02-bid-review-l2-p2-attachment-subitems-dedup-plan.md
git commit -m "docs(bid-review): L2-P2 实施计划——复合附件子件分组+跨层实体去重(spec §7 挂账行)"
```

---

## Self-Review

1. **Spec 覆盖**: §7 挂账行两项——子件分组(失败降 UNKNOWN 禁强行 PARTIAL)= Task 1/2/3;跨层去重(keep most_severe+related_issues,L1>L2>L3)= Task 3(实体键)/4(落库链)/5(投影)/7(前端)。P3 边界(类型指纹/模板/gates)在 Non-goals 显式排除。✓
2. **占位符扫描**: Task 2/5 的「create_task 夹具照抄同文件既有用例」与 Task 7 Step 2 的 grep 定位是**显式核实指令**而非 TBD——执行者有确切锚点;其余步骤全部带完整代码。✓
3. **类型一致性**: `sub_results` 形状 `{no,name,found,status}` 四处一致(attachments/rule_runner 无关/api.ts/dom 夹具);`entity_keys: string[]` 后端 list ↔ 前端 `string[]`;`_cross_layer_group` 返回 `{grouped_into, related}` 与端点接线/IssueOut 字段名一致;`UNKNOWN` 拼写全链一致。✓
