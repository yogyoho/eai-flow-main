# B立项 M3 表格/清单行(boq_rows 行级 + table_cells)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 工程量清单行级第二段抽取——`bid.boq_rows`({id,name,unit,qty,price,required},required 服务端回填自招标侧)+ `bid.table_cells`(最小诚实形状,零消费面挂 R2+);一次 LLM 调用双路径。

**Architecture:** 完全复用 M1/M2 第二段机制(SECOND_STAGE_FIELDS→worker 段→零编造归一闸→独立 seam)。M3 两路径合一段(单 prompt 双数组输出,省配额)。L1-011/L3-010 与既有 boq_items/boq_unit_checks 零改动。

**Tech Stack:** Python 3.12, pytest, ruff;全部在 `backend/`,`PYTHONPATH=. uv run pytest`。

**Spec:** `docs/superpowers/specs/2026-11-04-bid-review-extract-engine-b-design.md` §5 M3 行(spec 仅纲要;设计稿 §4.5 原文未入库,形状裁决见下)。

---

## 七裁决(2026-11-05,取证后定案)

1. **双路径一段**:boq_rows+table_cells 同一第二段(单 prompt 输出 `{"boq_rows":[...],"table_cells":[...]}`),门=表格信号一次判定,配额零增。
2. **boq_rows 行级形状**:`[{id,name,unit,qty,price,required}]`;required 服务端回填——`required = (id ∈ codes(tender.boq_items))`,**模型禁报该键**(prompt 契约无此键,闸内丢弃模型偷报的 required);设计 §4.5 铁律「必填口径唯一来自招标侧」。
3. **tender.required_fields 不新增路径**:= codes(tender.boq_items) 服务端视图。理由:新增首段路径 71→72 动 M0 零翻红锚+prompt 膨胀;招标 BOQ 本身就是必填口径(L1-011 集合等值语义同源)。挂账:设计稿 §4.5 原文到位再评估是否需要独立路径。
4. **table_cells 最小诚实形状(临时契约)**:`[{table_no,page,row_label,col_label,value}]`;value 空白丢行,page int 非 bool ≥1 否则 null。**零规则消费**(R2+ 补族按消费面定义字段时再演进契约——契约层改起来便宜,先占数据通道防表格拍平缺口恶化)。形状为盲设计,plan 与报告显式标注临时性。
5. **归一闸零编造**:boq_rows 丢行=id/name 双空;id/unit strip、name 保内部空格(M1 先例);qty/price 收 int/float 非 bool ≥0 否则 null;cells 丢行=value 空白。
6. **worker tables 段**:门=`bool(tender.boq_items) or bool(bid.boq_items)`;seam `tables_fn`+`_default_tables_fn`(两试解析);成功=两键独立落(各含零落 []),失败=双缺席;merge 后重算 materials_hash。
7. **零规则语义改动+M0 不扩**:L1-011/L3-010/golden 55/M0 26/26 全不动;活体回采单独记 boq_rows 行数/价格命中率。

---

### Task 1: 计划预提交

- [x] **Step 1:** `git -C /d/eai/eai-flow-main add -f docs/superpowers/plans/2026-11-05-bid-review-table-layer-m3-plan.md && git commit -m "docs(bid-review): B立项M3表格层计划——boq_rows行级+table_cells最小形状一段双路径+required服务端回填(招标侧唯一口径)+七裁决"`

### Task 2: 注册表 SECOND_STAGE_FIELDS +2(universe 74)

**Files:** registry.py;tests/test_bid_review_registry.py

- [x] **Step 1: 失败测试**——EXPECTED_UNIVERSE 72→…:插 `"bid.boq_rows"`(bid.boq_items 之后 boq_unit_checks 之前)与 `"bid.table_cells"`(subtotal 之后 tax_rate_occurrences 之前),len==74;`second_stage_fields` 断言 4 键;首段排除断言补两路径。
- [x] **Step 2: 红** → **Step 3: 实现**(SECOND_STAGE_FIELDS 追加两描述条目)→ **Step 4: 绿** → **Step 5: commit**

### Task 3: 契约 + normalize_boq_rows / normalize_table_cells 闸

**Files:** extract.py;tests/test_bid_review_tables_extract.py(新建)

- [x] **Step 1: 失败测试**

```python
def test_normalize_boq_rows_backfills_required():
    tender_codes = ["1.1", "1.2"]
    rows = normalize_boq_rows([{"id": "1.1", "name": "挖土方", "unit": "m3", "qty": 100, "price": 50}, {"id": "9.9", "name": "自附项", "unit": "项", "qty": 1, "price": 0}], tender_codes)
    assert rows[0]["required"] is True and rows[1]["required"] is False

def test_normalize_boq_rows_drops_and_clamps():
    rows = normalize_boq_rows([{"id": " ", "name": " "}, "junk", {"id": "2", "name": "钢筋", "qty": True, "price": "3", "unit": 1, "required": True}], [])
    assert len(rows) == 1
    r = rows[0]
    assert r["qty"] is None and r["price"] is None and r["unit"] == "" and r["required"] is False  # 模型偷报 required 被闸丢弃重算

def test_normalize_boq_rows_zero_negative_rejected():
    assert normalize_boq_rows([{"id": "1", "name": "A", "price": -5}], [])[0]["price"] is None
    assert normalize_boq_rows([{"id": "1", "name": "A", "qty": 0}], [])[0]["qty"] == 0  # 0 合法

def test_normalize_table_cells_drops_blank_value():
    cells = normalize_table_cells([{"table_no": "表3", "page": 12, "row_label": "总价", "col_label": "金额", "value": "100万"}, {"value": "  "}, {"page": True, "value": "x"}])
    assert len(cells) == 1 and cells[0]["page"] == 12
    assert normalize_table_cells(None) == [] and normalize_table_cells("junk") == []
```

- [x] **Step 2: 红** → **Step 3: 实现**(extract.py,normalize_section_tree 之后;FIELD_TYPE_CONTRACTS 两契约)

```python
FIELD_TYPE_CONTRACTS["bid.boq_rows"] = (
    '[{"id":"清单项编号","name":"项目名称","unit":"单位","qty":数量或null,"price":单价或null}] 对象列表;'
    "逐行一项,从投标报价清单逐行提取([[p.N]] 标记对照);清单没有的行不编造;数量单价只引用原文数字,不心算;无清单给空数组。"
)
FIELD_TYPE_CONTRACTS["bid.table_cells"] = (
    '[{"table_no":"表格编号或标题","page":所在页或null,"row_label":"行表头","col_label":"列表头","value":"单元格原文"}] 对象列表;'
    "逐单元格一项;只提取与报价/工期/人员等关键承诺相关的表格;空单元格跳过;禁止编造;无表格给空数组。"
)

def normalize_boq_rows(raw: Any, tender_codes: set[str] | list[str]) -> list[dict]:
    """清单行级归一闸(B立项 M3,spec §5,2026-11-05):id/name 双空丢行零编造;
    qty/price 收 int/float 非 bool ≥0 否则 null;required 服务端回填=(id ∈ 招标 codes)
    ——模型偷报的 required 键丢弃重算(设计 §4.5:必填口径唯一来自招标侧)。"""

def normalize_table_cells(raw: Any) -> list[dict]:
    """单元格归一闸(B立项 M3,临时契约裁决④):value 空白丢行;page int 非 bool ≥1
    否则 null;零规则消费(R2+ 就位后演进契约)。"""
```

- [x] **Step 4: 绿** → **Step 5: commit**

### Task 4: build_tables_prompt + build_tables_baseline(单 prompt 双路径)

**Files:** extract.py;tests/test_bid_review_tables_extract.py

- [x] **Step 1: 失败测试**(prompt 含两契约+tender 清单+[[p.、铁律;baseline 解包双键各自归一,None 信号→双空 dict)

```python
def test_tables_baseline_two_paths():
    def fake_fn(docs, tender_rows):
        return {"boq_rows": [{"id": "1.1", "name": "A"}], "table_cells": [{"value": "v"}]}
    out = build_tables_baseline([{"doc_id": "b.pdf", "role": "bid", "text": "x"}], fake_fn, [{"code": "1.1"}])
    assert out["boq_rows"][0]["required"] is True
    assert out["table_cells"][0]["value"] == "v"

def test_tables_baseline_none_signal():
    assert build_tables_baseline([], lambda *a: None, None) == {"boq_rows": [], "table_cells": []}
```

- [x] **Step 2: 红** → **Step 3: 实现** → **Step 4: 绿** → **Step 5: commit**

### Task 5: worker tables 段

**Files:** worker.py;tests/test_bid_review_worker.py

- [x] **Step 1: 失败测试**(镜像 M1/M2 五测试:_m3_extract 设 tender.boq_items;merged 两键+hash 一致;失败双缺席;零行双 [];无信号跳过零模型;default seam monkeypatch)
- [x] **Step 2: 红** → **Step 3: 实现**(import + `_default_tables_fn` + `tables_fn=None` kwarg + M2 块后追加 tables 块)→ **Step 4: 绿** → **Step 5: commit**

### Task 6: 全量验证

- [x] **Step 1:** `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(后台;期望全绿,预计 ~505)
- [x] **Step 2:** golden 55+M0 快照 26/26 含在全家内(零翻红)
- [x] **Step 3:** ruff check --fix + format 改动文件 → 重跑受影响测试

### Task 7: 收官

- [x] **Step 1:** push 重试至 `0\t0`
- [x] **Step 2:** wolf(memory;buglog 若 bug)+ anatomy(extract.py/worker.py 注记+新测试文件条目)+ plan 勾选 docs commit(`git add -f`)
- [x] **Step 3:** auto-memory `bid-review-extract-engine-m3-landed.md` + MEMORY.md 索引;终报以队列下一项(M4 条目聚类)+「继续」收尾

### 活体回采(独立步骤,烧配额一次,不阻塞 commit)

`--live` 抽取分 ≥0.7308 只升不降 + 单独记 boq_rows(行数/价格命中率/required 回填比)与 table_cells(单元格数)。
