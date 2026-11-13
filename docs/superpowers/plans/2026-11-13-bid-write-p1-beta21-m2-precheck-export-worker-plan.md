# bid_write 批廿一(M2)预审查+导出前置校验+worker 接线 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec §7 M2 = F6 规则层预审查(bid_review 同尺投影)+ 导出前置校验(D0+L1 fatal 阻断/水印恒加)+ worker 接线(fields 持久化/自动预审查/生成与导出端点)。

**Architecture:** 写侧生成产物即"标书本体"——`project_bid_fields(ctx)` 把 products 投影到 bid.* 平面字段,复用 bid_review `rule_runner.load_rulepack`/`eval_core.evaluate_fields` 跑 **det-only scope**(sem 规则不喂模型→零伪 ERROR;L4 全语义→det 视角零 issue→水印「商务风险未确认」恒加)。未投影路径缺席→UNKNOWN(诚实计预审查待确认,不阻断)。导出门禁 = `gate_verdict(run_assertions(ctx))` OR L1 fatal det FAIL。纯函数层(precheck.py)零 IO,worker 层接线 DB。

**Tech Stack:** Python 3.12 / SQLAlchemy async / FastAPI / pytest-asyncio。测试口径 `-k bid_write`;lint `uv run ruff check app/extensions/bid_write`。

**已验证锚点(2026-11-13 smoke 实测,勿重推导):**
- det-only:core 60 规则中 51 det;L4 包 10 规则**全 semantic**→det scope 恒零 L4 issue。
- green 夹具投影 + det precheck = 45 UNKNOWN + 1 FAIL(L2-033 保证金凭证缺失,severity=fatal 但 **L2 不在阻断层**,spec §8 只 L1 fatal 阻断——诚实信号,非阻断)。
- issue dict 键:`rule_id/layer/severity/verdict/message/evidence/fix/need_human/source/entity_keys/matched_expected`。
- `gate_verdict(report)` → `{"blocked": bool, "reasons": [D0 FAIL/ERROR assertion_id 排序], "watermark": False}`(executor/gate.py:11)。
- `crud.record_skill_run(db, task_id, owner_id, verdict: dict, *, skills=None, schema_version="", blocked=False)`;`latest_skill_run` 同参过滤。
- ps 产物键:`amount_cn/detail_total/open_letter_total/price_mode/rows(id,name,qty,unit,unit_price,amount)/summary_total/tax_rate`;bl slots 11 键含 `valid_days/deposit_amount/deposit_form/bidder_name`。
- 规则严重度实查:L1 fatal det=L1-001/002/005/006/008/009/010/011/012/014/015/016/017/019/026;L2-033 fatal det。
- **已知尺差(挂账,不本批修)**:审查端 `expr._number_to_words` 整元截断 vs 写侧 `num_to_cn` 含角分(123456.78 → 审查「壹拾贰万叁仟肆佰伍拾柒元整」vs 写侧「壹拾贰万零叁仟肆佰伍拾陆元柒角捌分」)→ 含分总额 L1-010 大写步会判 FAIL。本批投影**原样透传** ps.amount_cn,挂账方向=审查端 number_to_words 升级角分感知。
- L1-009 输入含 `tender.max_price`+`tender.price_includes_tax`(商务子集外)→ 恒 UNKNOWN,不误伤。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/extensions/bid_write/precheck.py` | 新建 | 纯函数:project_bid_fields / run_rule_precheck / run_export_gate(零 IO 零 DB) |
| `backend/app/extensions/bid_write/contracts.py` | 追加 | BLOCK_EXPORT_LEVELS + EXPORT_RISK_WATERMARK 常量 |
| `backend/app/extensions/bid_write/worker.py` | 修改 | meta["fields"] 持久化;build_task_ctx / generate_and_record;matrix_ready 后自动预审查 |
| `backend/app/extensions/bid_write/schemas.py` | 追加 | GenerateKnobs |
| `backend/app/extensions/bid_write/routers.py` | 修改 | POST /tasks/{id}/generate、POST /tasks/{id}/export-precheck |
| `backend/tests/test_bid_write_precheck.py` | 新建 | M2-a/M2-b 纯函数测试 |
| `backend/tests/test_bid_write_m2_worker.py` | 新建 | M2-c 接线测试 |

---

### Task 1: M2-a precheck.py — 投影+规则层预审查

**Files:**
- Create: `backend/app/extensions/bid_write/precheck.py`
- Test: `backend/tests/test_bid_write_precheck.py`

- [x] **Step 1: 写失败测试(投影面)**

```python
"""批廿一 M2-a/M2-b:F6 规则层预审查+导出前置校验(纯函数面)。

投影契约:products→bid.* 平面字段(同尺);det-only scope;缺口=UNKNOWN 诚实。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tests.bid_write_generate_fixtures import closure_inputs

from app.extensions.bid_write.generate import build_ctx
from app.extensions.bid_write.precheck import project_bid_fields, run_export_gate, run_rule_precheck


def _green_ctx():
    t, rows, mat, knobs = closure_inputs()
    return build_ctx(t, rows, mat, **knobs)


def test_projection_green_shape():
    """green 产物→bid.* 平面字段:金额三键同源/大写透传/boq 保 id/无凭证诚实 False。"""
    fields = project_bid_fields(_green_ctx())
    assert fields["bid.total_price"] == fields["bid.subtotal"] == 2400000
    assert fields["bid.total_price_words"] == "贰佰万元整"
    assert fields["bid.validity_days"] == 90
    assert {r["id"] for r in fields["bid.boq_items"]} == {"1.1", "1.2"}
    assert len(fields["bid.detail_rows"]) == 2
    assert fields["bid.deposit_amount"] == 100000
    assert fields["bid.deposit_forms"] == ["银行保函"]
    assert fields["bid.deposit_receipt_present"] is False  # M0 无凭证面,诚实
    assert fields["bid.alternative_price_offers"] == []  # 生成器不造替代方案
    assert fields["bid.tax_rate_occurrences"][0]["value"] is not None


def test_projection_omits_absent():
    """缺件不投影:bidder_name 空→bid.entity_name_occurrences 缺席(UNKNOWN 面)。"""
    t, rows, _mat, knobs = closure_inputs()
    ctx = build_ctx(t, rows, {}, **knobs)  # 素材清空
    fields = project_bid_fields(ctx)
    assert "bid.entity_name_occurrences" not in fields
```

- [x] **Step 2: 跑测试确认失败** — `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_precheck.py -q`(ModuleNotFoundError: precheck)

- [x] **Step 3: 实现 precheck.py**

```python
"""F6 规则层预审查(批廿一 M2,EAI-CUSTOM 2026-11-13)——bid_review 同尺投影。

同源一把尺:bid_review L1/L2 规则消费 bid.* 字段,写侧生成产物即标书本体。
project_bid_fields 把 products 投影到 bid.* 平面字段,复用 rule_runner/eval_core
跑确定性规则子集(det-only:sem 规则不喂模型→零伪 ERROR;L4 全语义→det 视角
零 issue→水印恒加=写侧未跑模型审查的诚实语义)。缺口诚实:未投影路径缺席→
UNKNOWN(计预审查待确认,不阻断)。纯函数零 IO 零时钟。

已知尺差(挂账):审查端 number_to_words 整元截断 vs 写侧 num_to_cn 含角分→
含分总额 L1-010 大写步判 FAIL;本批投影原样透传 amount_cn,修复方向=审查端
升级角分感知。"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path

from app.extensions.bid_review.engine.eval_core import evaluate_fields
from app.extensions.bid_review.engine.rule_runner import load_rulepack

_CORE_PATH = Path(__file__).parents[2] / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml"
_L4_PATH = Path(__file__).parents[2] / "bid_review" / "engine" / "rulepacks" / "bid-review-l4" / "1.0.0.yaml"
_det_pack = None


def _det_only_pack():
    """core+L4 合包裁到 det-only(module 级缓存;包文件仓库内静态)。"""
    global _det_pack
    if _det_pack is None:
        core = load_rulepack(_CORE_PATH)
        packs = [core]
        if _L4_PATH.exists():
            packs.append(load_rulepack(_L4_PATH))
        rules = [r for p in packs for r in p.rules if r.enabled and r.type == "deterministic"]
        _det_pack = dataclasses.replace(core, rules=rules)
    return _det_pack


def project_bid_fields(ctx: dict) -> dict:
    """products→bid.* 投影(仅产物可推导路径;None/空串=缺席→UNKNOWN 诚实)。"""
    p = (ctx or {}).get("products") or {}
    ps = p.get("price_sheet") or {}
    bl = p.get("bid_letter") or {}
    slots = bl.get("slots") or {}
    rows = [r for r in ps.get("rows") or [] if isinstance(r, dict)]
    out: dict = {}
    if slots.get("valid_days") is not None:
        out["bid.validity_days"] = slots["valid_days"]
    if ps.get("detail_total") is not None:
        out["bid.total_price"] = ps["detail_total"]
    if ps.get("amount_cn"):
        out["bid.total_price_words"] = ps["amount_cn"]  # 原样透传(尺差挂账见模块头)
    if ps.get("summary_total") is not None:
        out["bid.subtotal"] = ps["summary_total"]
    priced = [r for r in rows if r.get("amount") is not None]
    if priced:
        out["bid.detail_rows"] = [{"name": r.get("name"), "amount": r.get("amount")} for r in priced]
    if rows:
        out["bid.boq_items"] = [{"id": r.get("id"), "name": r.get("name"), "qty": r.get("qty"), "unit": r.get("unit")} for r in rows]
    if slots.get("deposit_amount") is not None:
        out["bid.deposit_amount"] = slots["deposit_amount"]
    if slots.get("deposit_form"):
        out["bid.deposit_forms"] = [slots["deposit_form"]]
    out["bid.deposit_receipt_present"] = False  # M0 无凭证;素材联动挂 P1+
    if ps.get("tax_rate") is not None:
        out["bid.tax_rate_occurrences"] = [{"value": ps["tax_rate"]}]
    if ps.get("price_mode"):
        out["bid.price_includes_tax"] = ps["price_mode"] == "含税"
    out["bid.alternative_price_offers"] = []  # 生成器不造替代方案(L1-019 判定面)
    if slots.get("bidder_name"):
        out["bid.entity_name_occurrences"] = [slots["bidder_name"]]
    return out


async def run_rule_precheck(fields: dict) -> dict:
    """det-only 预审查:issues/counts/l1_fatal_fail/blocked/scope_note。
    blocked=∃ L1∧fatal∧FAIL(UNKNOWN 不阻断;L2 fatal 同不阻断,spec §8)。"""
    issues = await evaluate_fields(_det_only_pack(), dict(fields or {}), model_fn=None)
    counts = Counter(i.get("verdict") for i in issues)
    l1_fatal = sorted({i["rule_id"] for i in issues if i.get("layer") == "L1" and i.get("severity") == "fatal" and i.get("verdict") == "FAIL"})
    return {
        "issues": issues,
        "counts": {k: counts[k] for k in sorted(counts)},
        "l1_fatal_fail": l1_fatal,
        "blocked": bool(l1_fatal),
        "scope_note": {"det_rules": len(_det_only_pack().rules), "sem_excluded": "模型规则不预审(L4 全语义→水印恒加)", "packs": ["bid-review-core/1.0.0", "bid-review-l4/1.0.0"]},
    }
```

- [x] **Step 4: 追加规则面测试(同文件)**

```python
async def test_precheck_green_no_l1_fatal():
    """green 产物:无 L1 fatal FAIL→不阻断;UNKNOWN 计数>0(缺口诚实)。"""
    pre = await run_rule_precheck(project_bid_fields(_green_ctx()))
    assert pre["blocked"] is False and pre["l1_fatal_fail"] == []
    assert pre["counts"].get("UNKNOWN", 0) > 0
    assert pre["scope_note"]["det_rules"] == 51  # smoke 实测锚


async def test_precheck_tampered_total_blocks():
    """破坏总额→L1-010 fatal FAIL→阻断(明细和≠总价面)。"""
    fields = project_bid_fields(_green_ctx())
    fields["bid.total_price"] = 2400001
    pre = await run_rule_precheck(fields)
    assert pre["blocked"] is True and "L1-010" in pre["l1_fatal_fail"]


async def test_precheck_no_error_verdicts():
    """det-only scope:零 ERROR(sem 规则整体排除,不喂模型零伪 ERROR)。"""
    pre = await run_rule_precheck(project_bid_fields(_green_ctx()))
    assert pre["counts"].get("ERROR", 0) == 0
```

- [x] **Step 5: 跑测试全绿** — 同 Step 2 命令,4 passed。

- [x] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_write/precheck.py backend/tests/test_bid_write_precheck.py
git commit -m "feat(bid-write): 批廿一 M2-a——F6 规则层预审查纯函数件(precheck.py:project_bid_fields products→bid.* 平面投影=同尺,ps 三金额键+大写透传+boq 保 id+deposit_receipt_present=False 诚实+alternative=[] 判定面;run_rule_precheck det-only scope=core+L4 合包裁 51 det 规则 model_fn=None 零伪 ERROR,blocked=∃L1∧fatal∧FAIL,UNKNOWN 不阻断,scope_note 面源标注;挂账=审查端 number_to_words 整元截断 vs 写侧含角分尺差,含分总额 L1-010 大写步 FAIL 方向=审查端升级;green 夹具 4 测试)"
```

---

### Task 2: M2-b 导出前置校验 — contracts 常量 + run_export_gate

**Files:**
- Modify: `backend/app/extensions/bid_write/contracts.py`(常量区,SCHEMA_VERSION 之后)
- Modify: `backend/app/extensions/bid_write/precheck.py`(追加 run_export_gate)
- Test: `backend/tests/test_bid_write_precheck.py`(追加)

- [x] **Step 1: 写失败测试**

```python
def test_block_export_levels_pinned():
    """口径钉死:阻断层级=D0(gate_verdict 同律);水印常量存在。"""
    from app.extensions.bid_write.contracts import BLOCK_EXPORT_LEVELS, EXPORT_RISK_WATERMARK
    assert BLOCK_EXPORT_LEVELS == ("D0",)
    assert EXPORT_RISK_WATERMARK == "商务风险未确认"


async def test_export_gate_green():
    """green 闭环:43 断言全 PASS→不阻断;水印恒加(L4 未跑模型=未确认语义)。"""
    from collections import Counter
    ctx = _green_ctx()
    export = await run_export_gate(ctx)
    assert export["blocked"] is False and export["reasons"] == []
    assert export["watermark"] == "商务风险未确认"
    assert export["assertion_counts"]["PASS"] == 43
    assert export["rule_counts"].get("FAIL", 0) <= 1  # L2-033 诚实非阻断
    assert export["l1_fatal_fail"] == []


async def test_export_gate_d0_blocks():
    """D0 面阻断:缺单价→PS-007 FAIL→blocked+reasons;水印仍在。"""
    t, rows, mat, knobs = closure_inputs()
    knobs = dict(knobs)
    knobs["unit_prices"] = {"1.1": "800000"}  # 缺 1.2
    export = await run_export_gate(build_ctx(t, rows, mat, **knobs))
    assert export["blocked"] is True and "PS-007" in export["reasons"]


async def test_export_gate_rule_layer_blocks():
    """规则层阻断:产物总额被篡改→L1-010 fatal FAIL→blocked 并入 reasons。"""
    ctx = _green_ctx()
    ctx["products"]["price_sheet"]["detail_total"] = 2400001
    export = await run_export_gate(ctx)
    assert export["blocked"] is True and "L1-010" in export["reasons"]
```

- [x] **Step 2: 跑失败** — ImportError: run_export_gate。

- [x] **Step 3: contracts.py 追加(SCHEMA_VERSION 块后)**

```python
# ── 导出前置校验(F6/批廿一 M2;P0 规格 §8)────────────────────────────────
# 阻断层级口径钉死:D0 断言 FAIL/ERROR 或规则层 L1 fatal det FAIL→禁导出。
# gate_verdict(executor/gate.py)消费同口径,本常量=防漂移钉(测试对锁)。
BLOCK_EXPORT_LEVELS = ("D0",)
# 风险水印:L4 竞争力包全语义规则,写侧预审查不喂模型→L4 恒未评估→导出物
# 恒带水印(诚实:商务风险未经模型确认)。M2 后接模型审查再评估摘除条件。
EXPORT_RISK_WATERMARK = "商务风险未确认"
```

- [x] **Step 4: precheck.py 追加 run_export_gate**

```python
async def run_export_gate(ctx: dict) -> dict:
    """导出前置校验(P0 规格 §8):重跑全量 D0 断言 + det 规则层预审查。
    blocked=gate_verdict D0 FAIL/ERROR 或 L1 fatal det FAIL;reasons 并集排序;
    watermark 恒加(L4 未评估语义,contracts.EXPORT_RISK_WATERMARK)。"""
    from app.extensions.bid_write.contracts import EXPORT_RISK_WATERMARK
    from app.extensions.bid_write.executor.gate import gate_verdict
    from app.extensions.bid_write.executor import run_assertions

    report = run_assertions(ctx)
    gate = gate_verdict(report)
    pre = await run_rule_precheck(project_bid_fields(ctx))
    a_counts = Counter(r.status for r in report.results)
    reasons = sorted(set(gate["reasons"]) | set(pre["l1_fatal_fail"]))
    return {
        "blocked": bool(gate["blocked"] or pre["blocked"]),
        "reasons": reasons,
        "watermark": EXPORT_RISK_WATERMARK,
        "assertion_counts": {k: a_counts[k] for k in sorted(a_counts)},
        "rule_counts": pre["counts"],
        "l1_fatal_fail": pre["l1_fatal_fail"],
        "scope_note": pre["scope_note"],
        "schema_version": _schema_version(),
    }


def _schema_version() -> str:
    from app.extensions.bid_write import contracts
    return contracts.SCHEMA_VERSION
```

(注:`run_assertions`/`gate_verdict` 真实 import 路径以 executor 包现行导出为准——M1-i golden 测试已有 import 面,实现时对齐,勿臆造。)

- [x] **Step 5: 跑全文件绿** — 8 passed。

- [x] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_write/contracts.py backend/app/extensions/bid_write/precheck.py backend/tests/test_bid_write_precheck.py
git commit -m "feat(bid-write): 批廿一 M2-b——导出前置校验(contracts.BLOCK_EXPORT_LEVELS=('D0',) 口径钉+EXPORT_RISK_WATERMARK=商务风险未确认(L4 全语义不预审→恒加诚实语义,摘除条件挂模型审查接入);precheck.run_export_gate=重跑全量 D0 断言 gate_verdict+det 规则层并集 reasons 排序,assertion/rule 双计数+scope_note+schema_version;green 43 PASS 不阻断+缺单价 PS-007 阻断+篡改总额 L1-010 规则层阻断三面测试)"
```

---

### Task 3: M2-c worker 接线 + 生成/导出端点

**Files:**
- Modify: `backend/app/extensions/bid_write/worker.py`(fields 持久化 + build_task_ctx + generate_and_record + matrix_ready 自动预审查)
- Modify: `backend/app/extensions/bid_write/schemas.py`(GenerateKnobs)
- Modify: `backend/app/extensions/bid_write/routers.py`(两端点)
- Test: `backend/tests/test_bid_write_m2_worker.py`

- [x] **Step 1: 写失败测试**

```python
"""批廿一 M2-c:worker 接线(fields 持久化/自动预审查/generate_and_record)
+ generate / export-precheck 端点。夹具形态同 test_bid_write_routers。"""

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent))

from app.extensions.bid_write import crud, models, worker
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=[models.WriteTask.__table__, models.MatrixRow.__table__, R._SkillRun.__table__])
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


def _fake_extract_with_boq(docs, field_paths):
    """带 boq 的抽取桩:matrix+生成都有实体面(金额链可走通)。"""
    return {
        "fields": {
            "tender.boq_items": [
                {"id": "1.1", "name": "设备安装", "qty": 2, "unit": "套"},
                {"id": "1.2", "name": "调试", "qty": 1, "unit": "项"},
            ],
            "tender.required_validity_days": 90,
            "tender.deposit_required": True,
            "tender.attachment_requirements": [{"no": "1", "name": "营业执照", "mandatory": "★", "clause": "3.1"}],
            "tender.bid_deadline": "2026-12-01",
        },
        "provenance": {},
        "confidence": {},
    }


async def _ready_task(db, monkeypatch) -> object:
    """推进到 matrix_ready 的任务(engine_meta.fields 已持久化)。"""
    from app.extensions.bid_review import parse

    task = await crud.create_task(db, "u1")
    meta = dict(task.engine_meta or {})
    meta["docs"] = [{"doc_id": "t.txt", "role": "tender", "kind": "text", "slug": "t", "status": "raw"}]
    task.engine_meta = meta
    await db.commit()

    async def fake_ocr(db_):
        return None

    async def fake_parse_raw(owner, task_id, entry, ocr_fn):
        return {**entry, "status": "parsed"}

    monkeypatch.setattr(parse, "build_ocr_fn", fake_ocr)
    monkeypatch.setattr(parse, "parse_raw", fake_parse_raw)
    monkeypatch.setattr(parse, "docs_from_entries", lambda o, t_, e: [{"doc_id": "t.txt", "role": "tender", "text": "全文"}])
    return await worker.advance_write_task(db, task.id, "u1", extract_fn=_fake_extract_with_boq)


@pytest.mark.asyncio
async def test_advance_persists_fields_and_autoruns(db, monkeypatch):
    """meta["fields"] 持久化;matrix_ready 落库即自动预审查(skill_run 行存在,
    material 缺→blocked True 诚实)。"""
    task = await _ready_task(db, monkeypatch)
    assert task.status == "matrix_ready"
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed.engine_meta["fields"]["tender.required_validity_days"] == 90
    run = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    assert run is not None and run.blocked is True  # 素材缺→BL-001 D0 阻断=诚实
    assert "BL-001" in (run.verdict or {}).get("reasons", [])


@pytest.mark.asyncio
async def test_generate_endpoint_records(db, monkeypatch):
    """POST generate(knobs 入 meta)+ verdict 落库;409=未就绪面。"""
    task = await _ready_task(db, monkeypatch)
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/generate", json={"unit_prices": {"1.1": "800000", "1.2": "400000"}, "sign_date": "2026-11-20"})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is True and "BL-001" in body["verdict"]["reasons"]  # material 缺
    assert body["verdict"]["watermark"] == "商务风险未确认"
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed.engine_meta["knobs"]["unit_prices"] == {"1.1": "800000", "1.2": "400000"}
    # 未就绪 409
    t2 = await crud.create_task(db, "u1")
    assert (await client.post(f"/api/extensions/bid-write/tasks/{t2.id}/generate", json={})).status_code == 409


@pytest.mark.asyncio
async def test_export_precheck_readonly(db, monkeypatch):
    """export-precheck 只读重算:不落新 skill_run;watermark/计数面齐。"""
    task = await _ready_task(db, monkeypatch)
    before = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/export-precheck")
    assert r.status_code == 200
    body = r.json()
    assert body["watermark"] == "商务风险未确认"
    assert "BL-001" in body["reasons"] and body["blocked"] is True
    assert body["assertion_counts"]
    after = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    assert (before.created_at, before.id) == (after.created_at, after.id)  # 只读无新行
```

- [x] **Step 2: 跑失败** — generate 端点 404 / meta["fields"] KeyError。

- [x] **Step 3: worker.py 三处修改**

(a) fields 持久化(现 `meta["fields_conf"] = fields_conf` 行后加一行):

```python
        meta["fields"] = fields  # M2:生成/预审查消费面(抽取快照持久化)
```

(b) 模块尾(advance 之后)追加 build_task_ctx + generate_and_record:

```python
async def build_task_ctx(db: AsyncSession, task: WriteTask, owner_id: str, *, knobs: dict | None = None) -> dict:
    """meta.fields+矩阵行(排除 status=blocked 卡点行,批十九禁入生成面)+knobs
    → executor 契约 ctx(纯装配;material=M0 缺省空=诚实降级面)。"""
    from app.extensions.bid_write.generate import build_ctx as assemble_ctx

    meta = dict(task.engine_meta or {})
    rows = await crud.list_matrix(db, task.id, owner_id)
    row_dicts = [
        {
            "clause_id": r.clause_id,
            "kind": r.kind,
            "source_path": r.source_path,
            "requirement": r.requirement,
            "star": r.star,
            "strategy": r.strategy,
            "target_section": r.target_section,
            "evidence_refs": r.evidence_refs or [],
            "status": r.status,
        }
        for r in rows
        if r.status != "blocked"
    ]
    k = dict(meta.get("knobs") or {})
    k.update(knobs or {})
    return assemble_ctx(
        dict(meta.get("fields") or {}),
        row_dicts,
        dict(meta.get("material") or {}),
        unit_prices=k.get("unit_prices"),
        sign_date=k.get("sign_date") or "",
        price_note=k.get("price_note") or "",
        general_commitments=k.get("general_commitments"),
        page_estimates=k.get("page_estimates"),
        total_pages=k.get("total_pages"),
    )


async def generate_and_record(db: AsyncSession, task: WriteTask, owner_id: str, *, knobs: dict | None = None) -> dict:
    """装配→断言+规则预审查→导出门禁→skill_run 落库。verdict=导出门禁 dict
    (blocked/reasons/watermark/双计数)。"""
    from app.extensions.bid_write.precheck import run_export_gate

    ctx = await build_task_ctx(db, task, owner_id, knobs=knobs)
    export = await run_export_gate(ctx)
    await crud.record_skill_run(db, task.id, owner_id, verdict=export, skills="ALL", schema_version=contracts.SCHEMA_VERSION, blocked=export["blocked"])
    return export
```

(c) advance matrix_ready 前(现 `n_star = ...` 之前)插自动预审查:

```python
        try:
            await generate_and_record(db, task, owner_id, knobs=meta.get("knobs") or {})
        except Exception:  # noqa: BLE001  预审查/生成非致命:主状态不回滚,failed 面不触发
            logger.exception("bid_write task %s auto precheck failed (non-fatal)", task_id)
```

- [x] **Step 4: schemas.py 追加**

```python
class GenerateKnobs(BaseModel):
    """生成旋钮(POST /generate body;None 键不覆盖 meta.knobs 已存值)。"""

    unit_prices: dict[str, str] | None = None
    sign_date: str | None = None
    price_note: str | None = None
    general_commitments: list[dict] | None = None
    page_estimates: dict[str, int] | None = None
    total_pages: int | None = None
```

- [x] **Step 5: routers.py 追加两端点(gaps 端点后)**

```python
class GenerateKnobs(S.GenerateKnobs):
    pass


@router.post("/tasks/{task_id}/generate")
async def generate_task(task_id: str, body: S.GenerateKnobs | None = None, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.status != "matrix_ready":
        raise HTTPException(409, f"矩阵未就绪(status={task.status})")
    if body is not None:
        meta = dict(task.engine_meta or {})
        knobs = dict(meta.get("knobs") or {})
        knobs.update({k: v for k, v in body.model_dump().items() if v is not None})
        meta["knobs"] = knobs
        task.engine_meta = meta
        await db.commit()
        await db.refresh(task)
    export = await worker.generate_and_record(db, task, owner_id)
    return {"verdict": export, "blocked": export["blocked"], "biz_no": task.biz_no, "status": task.status}


@router.post("/tasks/{task_id}/export-precheck")
async def export_precheck(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.status != "matrix_ready":
        raise HTTPException(409, f"矩阵未就绪(status={task.status})")
    return await worker.generate_and_record(db, task, owner_id, _readonly=True) if False else await _precheck_readonly(db, task, owner_id)


async def _precheck_readonly(db: AsyncSession, task, owner_id: str) -> dict:
    """只读重算:同门禁不落 skill_run(无副作用面)。"""
    from app.extensions.bid_write.precheck import run_export_gate

    ctx = await worker.build_task_ctx(db, task, owner_id)
    return await run_export_gate(ctx)
```

(实现时删掉占位三元;直接调用 `_precheck_readonly`。import 面对齐 routers 现行 `AsyncSession/HTTPException/Depends/S` 别名。)

- [x] **Step 6: 跑 M2 测试 + 既有 router 测试** — `PYTHONPATH=. uv run pytest tests/test_bid_write_m2_worker.py tests/test_bid_write_routers.py -q` 全绿(既有 advance 测试会新增 skill_run 行,断言不冲突)。

- [x] **Step 7: Commit**

```bash
git add backend/app/extensions/bid_write/worker.py backend/app/extensions/bid_write/schemas.py backend/app/extensions/bid_write/routers.py backend/tests/test_bid_write_m2_worker.py
git commit -m "feat(bid-write): 批廿一 M2-c——worker 接线+生成/导出端点(worker.meta fields 持久化=生成/预审查消费面;build_task_ctx=fields+矩阵行(排除 blocked 卡点行禁入生成)+knobs 合并→build_ctx 纯装配;generate_and_record=run_export_gate+record_skill_run(verdict=导出门禁 dict);advance matrix_ready 前自动预审查 try/except 非致命主状态不回滚;POST /tasks/{id}/generate=knobs 入 meta.knobs(None 键不覆盖)+409 未就绪面;POST /tasks/{id}/export-precheck=只读重算零落库;material M0 缺省空→BL-001 blocked 诚实;测试=持久化+自动预审查+端点 409+只读无新行)"
```

---

### Task 4: 收口 — 全量回归+lint+plan/spec/wolf

- [x] **Step 1: 全 bid_write 子集** — `cd backend && PYTHONPATH=. uv run pytest tests -k bid_write -q`(基线 184p/6s,新增 +7;后台跑,~2min)
- [x] **Step 2: lint** — `uv run ruff check app/extensions/bid_write tests/test_bid_write_precheck.py tests/test_bid_write_m2_worker.py`(contract_price/service.py 属他会话不触碰)
- [x] **Step 3: plan 勾兑 + spec §7 落地态段 + wolf 三件套(anatomy/memory/cerebrum+buglog 如有)**
- [x] **Step 4: Commit**

```bash
git add -f docs/superpowers/plans/2026-11-13-bid-write-p1-beta21-m2-precheck-export-worker-plan.md docs/superpowers/specs/2026-11-13-bid-write-p0-skills-spec.md .wolf/anatomy.md .wolf/memory.md .wolf/cerebrum.md
git commit -m "docs(bid-write): 批廿一 M2 收口——plan 全勾+spec §7 M2 落地态+wolf 三件套"
```

---

## 落地态勘误(执行时修正)

- 门禁 reasons 用断言全 id `SK-PS-007`/`SK-BL-001`(非短 id PS-007/BL-001)。
- run_export_gate verdict 增 `"results"`(to_report_dict 序列化)= gaps 断言维度唯一消费面。
- bug-4343:crud.record_skill_run 首真实调用暴露 `list(skills)` 落 String(40) 列绑定炸 → 改 `",".join(skills)`。
- 测试价金:green 总额=2000000(1.6M+0.4M,非计划稿 2400000 算误)。
- import 实测:load_rulepack 在 rule_runner 非 loader;run_assertions 在 executor.runner;pack 路径 parents[1]。

## Self-Review

- **Spec coverage**: F6 预审查(Task 1)、导出前置校验 BLOCK_EXPORT_LEVELS/水印(Task 2)、worker 接线 record_skill_run 进 advance+生成器接线(Task 3)= spec §7 M2 三件全覆盖。
- **Type consistency**: run_rule_precheck(fields)←project_bid_fields(ctx);run_export_gate(ctx) 单参内部自投影;generate_and_record→run_export_gate→record_skill_run(verdict dict, blocked bool) 与 crud 签名一致;GenerateKnobs 键集=build_ctx kwargs 集。
- **No placeholders**: 所有代码块完整;实现时唯一自由度=executor import 别名对齐(已注明对齐现行导出,非臆造)。
