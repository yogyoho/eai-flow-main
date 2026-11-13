# bid_write 批廿三(P1-β)policy 配置面 + 埋点 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec §3/§7 P1-β 两件:①`project.policy.*` 配置面(owner 单例 letter_defaults/tax_rate/price_adjust_mechanism,plumb 进 build_ctx→生成器,零 policy=现行为逐字节不变);②埋点六指标(slot_fill_rate/assertion_pass_rate/D0·D1_count/manual_edit_ratio/latency/retry_count)落 verdict.metrics + owner 聚合端点(latency_p95)。

**Architecture:** policy=第三张 owner 单例小表(镜像 MaterialProfile 律:owner_id PK+JSON),pydantic `extra="forbid"` 白名单校验 422;plumb 走 build_task_ctx→`build_ctx` 新 kwargs(**签名缺省=零行为变更**,golden 闭环不动);调价开关消费面已就绪(PS-009 无机制命中升 D0,`validators/ps.py:174`),只接配置源。埋点=纯函数 `compute_metrics(ctx, export, duration_ms)`(无新表:verdict JSON 增 `metrics` 键,gaps results 面零影响)+GET 聚合端点;manual_edit_ratio=None/retry_count=0 诚实(编辑面 P1-δ、重投面挂 γ)。

**Tech Stack:** 同前批。测试 `-k bid_write`;lint ruff。

**锚点:** ps 产物已有 `tax_rate=0.13`/`price_adjust_mechanism=True` 硬缺省(`price_sheet.py:28`)但 build_ctx 不透传——本批只接线不新增词汇;SK-PS-009 语义「无机制命中升 D0」已实现,blocks_export 由 levels 表按 final 级分派(D0→阻断,gate 零改动);bl slots 来源:`valid_days`=tender.required_validity_days、`sign_date`=knob——letter_defaults 只在**来源缺席**时兜底填+`defaults_used` 标黄(SK-BL-003 对缺席 requirement 仍 CtxMissing→ERROR 诚实,不因兜底变绿)。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/extensions/bid_write/models.py` | 追加 | BidWritePolicy(owner 单例) |
| `backend/app/extensions/bid_write/crud.py` | 追加 | get_policy/upsert_policy(合并语义)+list_skill_runs(owner 聚合源) |
| `backend/app/extensions/bid_write/schemas.py` | 追加 | PolicyBody/LetterDefaults(extra="forbid") |
| `backend/app/extensions/bid_write/routers.py` | 追加 | GET/PUT /policy;GET /tasks/{id}/metrics;GET /metrics 聚合 |
| `backend/app/extensions/bid_write/generate/__init__.py` | 修改 | build_ctx +3 kwargs 透传 |
| `backend/app/extensions/bid_write/generate/bid_letter.py` | 修改 | letter_defaults 兜底+defaults_used 标黄 |
| `backend/app/extensions/bid_write/worker.py` | 修改 | build_task_ctx 读 policy;generate_and_record 计时+metrics 落 verdict |
| `backend/app/extensions/bid_write/metrics.py` | 新建 | compute_metrics 纯函数 |
| `backend/tests/test_bid_write_policy.py` | 新建 | 配置面/plumb/埋点 全测试 |

---

### Task 1: policy 配置面(models+crud+schemas+routers)

**Files:** models/crud/schemas/routers;Test: test_bid_write_policy.py(crud+端点)

- [x] Step 1 失败测试:

```python
@pytest.mark.asyncio
async def test_policy_upsert_merge(client):
    """PUT 合并语义(只改键不清他键);GET 回读;非法键 422(extra=forbid)。"""
    r = await client.put("/api/extensions/bid-write/policy", json={"tax_rate": 0.09})
    assert r.json()["policy"] == {"tax_rate": 0.09}
    r = await client.put("/api/extensions/bid-write/policy", json={"price_adjust_mechanism": False})
    assert r.json()["policy"] == {"tax_rate": 0.09, "price_adjust_mechanism": False}
    assert (await client.get("/api/extensions/bid-write/policy")).json()["policy"] == {"tax_rate": 0.09, "price_adjust_mechanism": False}
    assert (await client.put("/api/extensions/bid-write/policy", json={"ghost_key": 1})).status_code == 422
    assert (await client.put("/api/extensions/bid-write/policy", json={"tax_rate": 1.5})).status_code == 422
```

- [x] Step 2 models.py 追加:

```python
class BidWritePolicy(Base):
    """project.policy.* 配置面(P1-β 批廿三;owner 单例,镜像 MaterialProfile 律)。
    letter_defaults/tax_rate/price_adjust_mechanism;键词汇=contracts.POLICY_KEYS。"""
    __tablename__ = "bid_write_policies"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
```

- [x] Step 3 crud.py 追加:

```python
async def get_policy(session: AsyncSession, owner_id: str) -> dict:
    row = await session.get(BidWritePolicy, owner_id)
    return dict(row.policy or {}) if row is not None else {}


async def upsert_policy(session: AsyncSession, owner_id: str, patch: dict) -> dict:
    """合并语义(只改传入键);白名单校验在 schemas(extra=forbid)。"""
    row = await session.get(BidWritePolicy, owner_id)
    if row is None:
        row = BidWritePolicy(owner_id=owner_id, policy=dict(patch))
    else:
        row.policy = {**dict(row.policy or {}), **dict(patch)}
    await session.commit()
    await session.refresh(row)
    return dict(row.policy or {})
```

- [x] Step 4 schemas.py 追加(pydantic 422 面):

```python
class LetterDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    validity_days: int | None = None
    sign_date: str | None = None


class PolicyBody(BaseModel):
    """project.policy.* 键词汇钉(extra=forbid→ghost 键 422;tax_rate 0..1)。"""
    model_config = ConfigDict(extra="forbid")
    letter_defaults: LetterDefaults | None = None
    tax_rate: float | None = Field(default=None, ge=0, le=1)
    price_adjust_mechanism: bool | None = None
```

- [x] Step 5 routers.py 追加(镜像 profile 两端点):

```python
@router.get("/policy")
async def get_policy(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    return {"policy": await crud.get_policy(db, owner_id)}


@router.put("/policy")
async def put_policy(body: schemas.PolicyBody, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    policy = await crud.upsert_policy(db, owner_id, patch)
    return {"policy": policy}
```

- [x] Step 6 测试绿 + commit `feat(bid-write): 批廿三 P1-β——policy 配置面 owner 单例(…)`。

### Task 2: policy plumb → build_ctx/生成器

**Files:** generate/__init__.py、generate/bid_letter.py、worker.py;Test: 同文件

- [x] Step 1 失败测试:

```python
@pytest.mark.asyncio
async def test_policy_plumb(client, db, monkeypatch):
    """tax_rate→ps 产物;调价关→PS-009 命中升 D0(note=暂估);letter_defaults
    兜底缺席 validity→slot 填充+defaults_used 标黄。"""
    task = await _seed(db, monkeypatch, omit_validity=True, note_hit=True)  # fake_extract 无 required_validity_days
    await client.put("/api/extensions/bid-write/policy", json={"tax_rate": 0.09, "price_adjust_mechanism": False, "letter_defaults": {"validity_days": 90}})
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/generate", json={"unit_prices": {"1.1": "800000", "1.2": "400000"}, "sign_date": "2026-11-20", "price_note": "暂估待调"})
    body = r.json()
    ps = body["verdict"]["results"]  # 断言面见 metrics;产物面直查 ctx 难——经 precheck 只读端点验证
    pre = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/export-precheck")
    # 产物验证走 build_task_ctx 直查(db 会话):
    ctx = await worker.build_task_ctx(db, task, "u1")
    assert ctx["products"]["price_sheet"]["tax_rate"] == 0.09
    assert ctx["products"]["price_sheet"]["price_adjust_mechanism"] is False
    assert ctx["products"]["bid_letter"]["slots"]["valid_days"] == 90
    assert "valid_days" in ctx["products"]["bid_letter"]["defaults_used"]
    ps009 = [x for x in body["verdict"]["results"] if x["assertion_id"] == "SK-PS-009"][0]
    assert ps009["status"] == "FAIL" and ps009["level"] == "D0"  # 调价关→升 D0
```

(注:上形示意;实际写测试时按 _seed 夹具既有形落笔,产物面经 `worker.build_task_ctx` 直查。)

- [x] Step 2 generate/__init__.py build_ctx 签名追加(**缺省=现行为**):`tax_rate: float = 0.13, price_adjust_mechanism: bool = True, letter_defaults: dict | None = None`;`calc_price_sheet(..., tax_rate=tax_rate, price_adjust_mechanism=price_adjust_mechanism)`;`render_bid_letter(..., letter_defaults=letter_defaults)`。
- [x] Step 3 bid_letter.py:slots 装配改兜底形,`defaults_used` 列表标黄:

```python
defaults = letter_defaults or {}
defaults_used: list[str] = []
raw_valid = t.get("tender.required_validity_days")
if raw_valid is not None:
    valid_days = raw_valid
elif defaults.get("validity_days") is not None:
    valid_days = defaults["validity_days"]
    defaults_used.append("valid_days")  # D1 标黄:抽取缺席,配置兜底(SK-BL-003 对缺席仍 ERROR 诚实)
else:
    valid_days = None
raw_sign = str(sign_date or "")
if raw_sign:
    sign = raw_sign
elif defaults.get("sign_date"):
    sign = str(defaults["sign_date"])
    defaults_used.append("sign_date")
else:
    sign = ""
```

返回 dict 增 `"defaults_used": defaults_used`(缺省空表=零行为变更)。
- [x] Step 4 worker.build_task_ctx:读 policy 透传:

```python
pol = await crud.get_policy(db, owner_id)
ld = pol.get("letter_defaults") or {}
return assemble_ctx(
    ...,
    tax_rate=float(pol.get("tax_rate")) if pol.get("tax_rate") is not None else 0.13,
    price_adjust_mechanism=bool(pol["price_adjust_mechanism"]) if "price_adjust_mechanism" in pol else True,
    letter_defaults=ld or None,
)
```

- [x] Step 5 测试绿(既有 e2e green 全绿=零 policy 缺省路径回归面)+ commit `feat(bid-write): 批廿三 P1-β——policy plumb 税率/调价开关/函默认值(…)`。

### Task 3: 埋点(metrics 落 verdict + 聚合端点)

**Files:** metrics.py(新)、worker.py、crud.py、routers.py;Test: 同文件

- [x] Step 1 失败测试:

```python
@pytest.mark.asyncio
async def test_metrics_green_and_degraded(client, db, monkeypatch):
    """绿跑:pass_rate=1.0、retry=0、manual=None、latency int、slot_fill_rate 形;
    缺单价跑:D0 计数≥1、pass_rate<1。"""
    task = await _seed(db, monkeypatch)
    await client.put("/api/extensions/bid-write/materials/profile", json={"profile": {"name": "YY装备", "legal_rep": "张三"}})
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "营业执照", "evidence_refs": ["doc:1"]})
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "矿用产品安全标志证书", "evidence_refs": ["doc:2"]})
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/generate", json={"unit_prices": {"1.1": "800000", "1.2": "400000"}, "sign_date": "2026-11-20"})
    m = r.json()["verdict"]["metrics"]
    assert m["assertion_pass_rate"] == 1.0 and m["retry_count"] == 0 and m["manual_edit_ratio"] is None
    assert isinstance(m["latency_ms"], int) and m["latency_ms"] >= 0
    assert 0.0 <= m["slot_fill_rate"] <= 1.0
    # 缺单价→SK-PS-007 D0 FAIL
    task2 = await _seed(db, monkeypatch)
    r2 = await client.post(f"/api/extensions/bid-write/tasks/{task2.id}/generate", json={})
    m2 = r2.json()["verdict"]["metrics"]
    assert m2["d0_count"] >= 1 and m2["assertion_pass_rate"] < 1.0


@pytest.mark.asyncio
async def test_metrics_aggregate_p95(client, db, monkeypatch):
    """owner 聚合:runs 计数、latency_p95≥median、无跑 owner 恒等诚实零。"""
    await test_metrics_green_and_degraded(client, db, monkeypatch)  # 造 2 run
    r = await client.get("/api/extensions/bid-write/metrics")
    agg = r.json()
    assert agg["runs"] >= 2 and agg["latency_p95_ms"] >= agg["latency_median_ms"]
    assert (await client.get("/api/extensions/bid-write/tasks/nonexistent/metrics")).status_code == 404
```

- [x] Step 2 metrics.py 新建(纯函数):

```python
"""埋点六指标(P1-β 批廿三,spec §3)——纯函数,generate_and_record 计时后调用,
落 verdict["metrics"](无新表;gaps results 面零影响)。manual_edit_ratio=None
诚实(编辑面 P1-δ);retry_count=0 诚实(重投循环未建);D0/D1 计数=断言维度
(规则层维度挂 L4 激活批)。"""

def compute_metrics(ctx: dict, export: dict, *, duration_ms: int) -> dict:
    slots = ((ctx.get("products") or {}).get("bid_letter") or {}).get("slots") or {}
    total = len(slots)
    filled = sum(1 for v in slots.values() if v not in (None, "", []))
    results = export.get("results") or []
    decided = [r for r in results if r.get("status") in ("PASS", "FAIL", "ERROR")]
    return {
        "slot_fill_rate": round(filled / total, 4) if total else None,
        "assertion_pass_rate": round(sum(1 for r in decided if r["status"] == "PASS") / len(decided), 4) if decided else None,
        "d0_count": sum(1 for r in results if r.get("status") != "PASS" and r.get("level") == "D0"),
        "d1_count": sum(1 for r in results if r.get("status") != "PASS" and r.get("level") == "D1"),
        "manual_edit_ratio": None,  # ponytail: 编辑面 P1-δ 才有采样源,现挂 None 诚实
        "latency_ms": int(duration_ms),
        "retry_count": 0,  # ponytail: 重投循环未建,恒 0 诚实
        "note": "断言维度计数;规则层维度挂 L4 激活批;manual/retry 诚实零待对应面落地",
    }
```

- [x] Step 3 worker.generate_and_record:`t0 = time.perf_counter()` → export 后 `export["metrics"] = compute_metrics(ctx, export, duration_ms=round((time.perf_counter()-t0)*1000))` 再 record_skill_run(verdict JSON 整体落库,gaps 读 results 面零影响)。
- [x] Step 4 crud.list_skill_runs:

```python
async def list_skill_runs(session: AsyncSession, owner_id: str, limit: int = 100) -> list:
    """owner 全任务 skill_runs 倒序(owner 隔离经 task join;聚合端点消费)。"""
    from sqlalchemy import select
    stmt = select(SkillRun).join(WriteTask, WriteTask.id == SkillRun.task_id).where(WriteTask.owner_id == owner_id).order_by(SkillRun.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())
```

- [x] Step 5 routers 两端点:

```python
@router.get("/tasks/{task_id}/metrics")
async def get_task_metrics(task_id: str, db=Depends(get_db), owner_id: str = Depends(current_owner)):
    """最近一次执行的埋点面;未执行过=null(不造空绿,同 gaps 断言维度口径)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    run = await crud.latest_skill_run(db, task_id=task_id, owner_id=owner_id)
    return {"metrics": (run.verdict or {}).get("metrics") if run is not None else None, "run_at": run.created_at.isoformat() if run is not None and run.created_at else None}


@router.get("/metrics")
async def get_metrics_aggregate(db=Depends(get_db), owner_id: str = Depends(current_owner)):
    """owner 聚合(P1-β):runs/latency p95·median/断言通过率均值/D0·D1 总计;
    manual_edit_ratio 聚合=全部 None 诚实。"""
    runs = await crud.list_skill_runs(db, owner_id)
    lat = sorted((r.verdict or {}).get("metrics", {}).get("latency_ms") for r in runs if (r.verdict or {}).get("metrics"))
    rates = [m["assertion_pass_rate"] for r in runs if (m := (r.verdict or {}).get("metrics")) and m.get("assertion_pass_rate") is not None]

    def _pct(seq, q):
        if not seq:
            return None
        i = max(0, math.ceil(q * len(seq)) - 1)
        return seq[i]

    return {
        "runs": len(runs),
        "latency_p95_ms": _pct(lat, 0.95),
        "latency_median_ms": _pct(lat, 0.5),
        "assertion_pass_rate_mean": round(sum(rates) / len(rates), 4) if rates else None,
        "d0_total": sum((r.verdict or {}).get("metrics", {}).get("d0_count") or 0 for r in runs),
        "d1_total": sum((r.verdict or {}).get("metrics", {}).get("d1_count") or 0 for r in runs),
    }
```

- [x] Step 6 测试绿 + commit `feat(bid-write): 批廿三 P1-β——埋点六指标 verdict.metrics+owner 聚合 p95(…)`。

### Task 4: 收口

- [x] Step 1 全子集 `-k bid_write`(基线 203p/6s+新增)+ lint。**全量必跑(bug-4350 律:局部跑漏跨钉文件)。**
- [x] Step 2 plan 勾兑+spec §7 P1-β 落地态段+wolf 三件套+buglog+memory。
- [x] Step 3 commit `docs(bid-write): 批廿三收口…`。


## 落地态勘误(执行时修正)

- 夹具表清单实为**三处**(plan 写两处):m2_worker/routers 之外,materials 测试自带 `_TABLES` 也须加 BidWritePolicy(build_task_ctx 现查 policy 表,漏建表=no such table)。
- `assertion_counts` 只含有值状态(缺键=零,无零值条目)——测试取 FAIL 计数须 `.get("FAIL", 0)`。
- 绿跑平台既有 **1 条 CtxMissing ERROR**(两 seed 共有的 tender 缺席面;materials e2e 只钉 FAIL==0 故未暴露)——pass_rate 分母含 ERROR 是诚实面,绿跑测试改钉 metric 语义(d0_count==0+FAIL==0+pass_rate≥0.9),不过钉 ERROR 平台。
- PS-009 调价关升 D0 消费面实证:policy price_adjust_mechanism=False + note 命中「暂估」→FAIL level=D0(levels 表 blk 按 final 级分派→进阻断面,gate 零改动)。

## Self-Review

- spec 六指标全落:slot_fill_rate/assertion_pass_rate/d0·d1_count 有真值,manual/retry 诚实零挂账,latency p95 聚合面。
- 零 policy=现行为:build_ctx 缺省形逐键同(golden 闭环/既有 e2e 不动);policy 表 owner 单例镜像 profile 律(bug-4303 律:共享 Base 注册,夹具表清单两文件同改)。
- 类型一致:PolicyBody→policy dict→build_ctx kwargs→calc_price_sheet 形参名对齐;defaults_used 只增不改 slots 键集(SK-BL-* 断言面零漂移)。
