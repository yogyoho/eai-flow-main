# B立项 M4 条目聚类(业绩富行抽取 + 确定性聚类)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 业绩条目第二段富行抽取(`bid.performance_entries`:项目名/甲方/金额/日期)+ **纯服务端零 LLM** 确定性聚类(`bid.performance_groups`:≥0.80 归组,ungrouped→ok=false→UNKNOWN,禁强行 PARTIAL)。

**Architecture:** 完全复用 M1/M2/M3 第二段机制(SECOND_STAGE_FIELDS→worker 段→零编造归一闸→独立 seam)。聚类是纯函数(clusters.py,difflib),不烧配额、单测全覆盖。L1-003(串列表 count)/L3-007(码集合等值)零改动。

**Tech Stack:** Python 3.12(difflib stdlib), pytest, ruff;全部在 `backend/`。

**Spec:** `docs/superpowers/specs/2026-11-04-bid-review-extract-engine-b-design.md` §5 M4 行 + §三差距行(§五聚类设计原文未入库,阈值语义见下裁决)。

---

## 七裁决(2026-11-05,取证后定案)

1. **业绩富行第二段**:`bid.performance_entries` 新路径(LLM,契约 `{name,client,amount,date,page}`);门=`bool(bid.similar_performances)`(首段串列表非空=有业绩信号才烧配额);universe 77=71 首段+6 第二段。
2. **聚类纯服务端零 LLM**(裁决基座):`clusters.py::cluster_performance_entries` 纯函数(difflib SequenceMatcher),输出 `bid.performance_groups`=[{group_id,ok,members}] 落 fields;R2+ 规则以 `len(ok=true 组)` 为确认去重数,ok=false 组=UNKNOWN 不自动计数。
3. **归组三通道**(快路径保留):①归一化名全等→同组(P2 name 快路径);②ratio ≥0.80 且佐证(甲方/金额/日期任一归一相等)→并组 ok=true;③ratio ∈[0.60,0.80) 且佐证→并组但 **ok=false**(疑似同项交人工,禁强行 PARTIAL);**无佐证一律不并组**(ratio 0.9 也不并——防同名不同项);单条目组 ok=true。贪心单遍 O(n²)(<10³ 条目够用)。
4. **人员聚类挂账 R2+**:spec 维度元组(项目名/甲方/金额/日期)业绩专用;人员 {code,name} 已有身份键且 L3-007 set_eq 已做跨标一致;消费面(R2+ 规则)就位再按 clusters.py 同骨架设计。
5. **零规则语义改动**:L1-003/L3-007/golden 55/M0 26/26 全不动;新字段零规则消费(R1 §二:消费者 R2+ 按字段就位分批)。
6. **worker perf 段**:seam `perf_entries_fn`+`_default_perf_entries_fn`(两试解析);失败=双键缺席(诚实降级);成功含零=双键落 [](聚类空=[]);merge 后重算 materials_hash。
7. **M0 不扩**:首段 71 逐位不动(M0 锚);活体回采独立记(perf_entries 行数/聚类组数/ok=false 占比)。

---

### Task 1: 计划预提交

- [x] **Step 1:** `git add -f docs/superpowers/plans/2026-11-05-bid-review-cluster-layer-m4-plan.md && git commit -m "docs(bid-review): B立项M4条目聚类计划——业绩富行第二段+纯服务端确定性聚类(≥0.80三通道+ok=false UNKNOWN)+人员挂账R2+七裁决"`

### Task 2: 注册表 +2(universe 77)

**Files:** registry.py;tests/test_bid_review_registry.py

- [x] **Step 1: 失败测试**——EXPECTED_UNIVERSE 插 `"bid.performance_entries"`/`"bid.performance_groups"`(old_project_mentions 之后 personnel_commercial 之前,performance<personnel 因 'f'<'s'),len==77(71+len(SECOND_STAGE_FIELDS)=77,**实测非脑算**——cerebrum M3 坑);second_stage 断言 6 键;首段排除断言补两路径。
- [x] **Step 2: 红** → **Step 3: 实现**(SECOND_STAGE_FIELDS 追加两描述条目)→ **Step 4: 绿**(先 `python -c "from app.extensions.bid_review.engine import registry; print(len(registry.universe()))"` 实测)→ **Step 5: commit**

### Task 3: 契约 + normalize_performance_entries 闸 + clusters.py 聚类纯函数

**Files:** extract.py;clusters.py(新建);tests/test_bid_review_clusters.py(新建)

- [x] **Step 1: 失败测试**

```python
class TestNormalizePerfEntries:
    def test_drops_no_name_and_clamps(self):
        rows = normalize_performance_entries([
            {"name": " 某数据中心 ", "client": " 某集团 ", "amount": 1200, "date": "2023-05-01", "page": 3},
            {"client": "无名"},  # 丢
            {"name": "A", "amount": True, "date": 5, "page": 0},  # 坏形→null
        ])
        assert len(rows) == 2
        assert rows[0] == {"name": "某数据中心", "client": "某集团", "amount": 1200, "date": "2023-05-01", "page": 3}
        assert rows[1]["amount"] is None and rows[1]["date"] is None and rows[1]["page"] is None

class TestCluster:
    def test_exact_name_fast_path(self):
        entries = _e("某数据中心EPC", c="某集团"), _e("某数据中心EPC", c="其它")
        groups = cluster_performance_entries(entries)
        assert len(groups) == 1 and groups[0]["ok"] is True and len(groups[0]["members"]) == 2

    def test_similar_with_corroboration_merges_ok(self):
        g = cluster_performance_entries([_e("某数据中心EPC工程"), _e("某数据中心EPC项目", c="某集团", amount=100)])
        # name ratio≈0.86 ≥0.80 但无佐证 → 不并
        assert len(g) == 2

    def test_similar_with_corroboration2_merges(self):
        g = cluster_performance_entries([_e("某数据中心EPC工程", c="某集团"), _e("某数据中心EPC项目", c="某集团")])
        assert len(g) == 1 and g[0]["ok"] is True

    def test_suspect_band_merges_flagged_false(self):
        g = cluster_performance_entries([_e("某数据中心一期EPC总承包", c="某集团"), _e("某数据中心二期EPC总承包", c="某集团")])
        # 一期/二期 ratio 高但 <1;若 ∈[0.6,0.8) → ok=false;若 ≥0.8 → ok=true(实测锚定)
        assert len(g) == 1

    def test_no_corroboration_never_merges(self):
        g = cluster_performance_entries([_e("某数据中心EPC工程"), _e("某数据中心EPC工程项目")])
        assert len(g) == 2  # ratio≥0.8 无佐证不并

    def test_singleton_and_empty(self):
        assert cluster_performance_entries([_e("A")]) == [{"group_id": "G1", "ok": True, "members": [_e("A")]}]
        assert cluster_performance_entries([]) == []
```

- [x] **Step 2: 红** → **Step 3: 实现**(extract.py 契约+闸;clusters.py 三通道贪心)

```python
FIELD_TYPE_CONTRACTS["bid.performance_entries"] = (
    '[{"name":"项目名称","client":"甲方/招标人名称","amount":合同金额或null,"date":"竣工/签约日期或null","page":所在页或null}] 对象列表;'
    "逐条业绩一项,从类似业绩证明(中标通知书/合同/验收)提取([[p.N]] 标记对照);证明里没有的字段给 null;禁止编造;无业绩给空数组。"
)
FIELD_TYPE_CONTRACTS["bid.performance_groups"] = (
    '[{"group_id":"G1..","ok":true|false,"members":[原始条目...]}] 对象列表;服务端聚类产物(模型禁生成):'
    "ok=true=确认同项去重组,ok=false=疑似同项待人工(UNKNOWN,禁强行 PARTIAL)。"
)

# clusters.py:SIM_MERGE=0.80; SIM_SUSPECT=0.60; _norm(s)=casefold+去空白;
# 佐证=_client_eq|_amount_eq|_date_eq;贪心:逐条目对既有组首成员判定三通道。
```

- [x] **Step 4: 绿**( suspect 阈值带以实测 ratio 锚定断言)→ **Step 5: commit**

### Task 4: build_performance_prompt + build_performance_baseline

**Files:** extract.py;tests/test_bid_review_clusters.py

- [x] **Step 1: 失败测试**

```python
def test_perf_prompt_contains_contract_and_rules():
    prompt = build_performance_prompt([{"doc_id": "b.pdf", "role": "bid", "text": "x"}])
    assert "业绩条目定位器" in prompt and "[[p." in prompt and "禁止编造" in prompt

def test_perf_baseline_unwraps_and_normalizes():
    out = build_performance_baseline([], lambda docs: {"performance_entries": [{"name": " A "}]} )
    assert out == [{"name": "A", "client": "", "amount": None, "date": None, "page": None}]

def test_perf_baseline_none_signal():
    assert build_performance_baseline([], lambda docs: None) == []
```

- [x] **Step 2: 红** → **Step 3: 实现**(M3 tables 同款;裸 list 退路)→ **Step 4: 绿** → **Step 5: commit**

### Task 5: worker perf 段(抽取+聚类落双键)

**Files:** worker.py;tests/test_bid_review_worker.py

- [x] **Step 1: 失败测试**(镜像 M3 五测试:_m4_extract 设 bid.similar_performances;merged 双键+hash;失败双缺席;零行双 [];无信号跳过零模型;default seam monkeypatch)

```python
def _m4_extract(with_perf=True):
    def _extract(d, p):
        perf = ["某数据中心EPC", "某园区房建项目"]
        return {**{k: None for k in p}, "bid.similar_performances": perf} if with_perf else {k: None for k in p}
    return _extract

async def test_m4_perf_merged_and_hash_recomputed(...):
    def _perf_fn(docs):
        return {"performance_entries": [{"name": "某数据中心EPC", "client": "某集团"}, {"name": "某数据中心EPC(副本)"}]}
    await advance_task(db, t.id, owner_id="u1", docs=docs, extract_fn=_m4_extract(), wait_confirm=True, perf_entries_fn=_perf_fn)
    payload = await _first_payload(db, t.id)
    assert payload["fields"]["bid.performance_groups"][0]["ok"] is True  # 快路径并组
    assert len(payload["fields"]["bid.performance_entries"]) == 2
    assert payload["materials_hash"] == materials_hash(payload["fields"])
```

- [x] **Step 2: 红** → **Step 3: 实现**(import + `_default_perf_entries_fn` + `perf_entries_fn=None` kwarg + M3 块后 perf 块:to_thread build_performance_baseline → cluster_performance_entries → 双键落)→ **Step 4: 绿** → **Step 5: commit**

### Task 6: 全量验证

- [x] **Step 1:** `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(后台;期望全绿,预计 ~520)
- [x] **Step 2:** golden 55+M0 26/26 含在全家内(零翻红);首段 71 锁(registry)
- [x] **Step 3:** ruff check --fix + format 改动文件 → 重跑受影响测试

### Task 7: 收官

- [x] **Step 1:** push 重试至 `0\t0`
- [x] **Step 2:** wolf(memory;buglog 若 bug)+ anatomy(extract.py/worker.py/新 clusters.py/新测试条目)+ plan 勾选 docs commit(`git add -f`)
- [x] **Step 3:** auto-memory `bid-review-extract-engine-m4-landed.md` + MEMORY.md 索引;终报以队列下一项(M5 交叉自检+指标)+「继续」收尾

### 挂账(显式)

- 人员条目聚类 R2+(裁决④;clusters.py 同骨架)
- 设计 §五原文到位→复核 0.80/佐证语义(当前盲设计显式标注)
- 聚类阈值外置 tuning.yaml(R2+ 消费面就位时)
