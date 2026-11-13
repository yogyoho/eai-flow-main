# bid_write 批廿二(P1-α)素材库六类实体 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec §7 P1 首批 = 素材库六类实体(models+CRUD+owner 库)——gaps 三态兑现(有且可佐证/有但缺佐证/无对应素材)+ build_task_ctx material 从素材库装配 + 端到端绿(素材齐→generate→blocked=False)。

**Architecture:** 两张小表(实体+投标主体 profile 单例);实体=type∈MATERIAL_ENTITY_TYPES/name/fields JSON/evidence_refs JSON(**verifiable=bool(evidence_refs) 派生不落列**,spec「verifiable=有可佐证附件」);build_ctx 纯函数零改动——material 形不变(`entities`/`bidder_profile`/`price_history`),worker 层从库收集;price_history 从 performance 实体 fields.amount 派生;gaps attachment 行按名归一匹配(与 attachment_index._match_entity 同律),clause 行 material_state=null(素材不适用面)。

**Tech Stack:** 同前批。测试 `-k bid_write`;lint ruff。

**锚点:** material 形=`{"entities": {"ent:<id>": {type,name,fields}}, "bidder_profile": {name,legal_rep}, "price_history": [{project,amount}]}`(夹具实测);gaps 现 items 只含 attachment/clause 行且 material_state 恒「无对应素材」;create_all 启动序承接新表(bug-4303 律:共享 Base);BL-001 消费 bidder_profile.name/legal_rep;AI 行匹配消费 entities[*].name 归一。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/extensions/bid_write/models.py` | 追加 | MaterialEntity + MaterialProfile |
| `backend/app/extensions/bid_write/crud.py` | 追加 | 实体 CRUD + profile upsert + collect_material |
| `backend/app/extensions/bid_write/routers.py` | 修改 | /materials CRUD+profile 两端点;gaps 三态兑现 |
| `backend/app/extensions/bid_write/worker.py` | 修改 | build_task_ctx material←collect_material |
| `backend/tests/test_bid_write_materials.py` | 新建 | CRUD/三态/e2e 绿 |
| `backend/tests/test_bid_write_m2_worker.py` + `test_bid_write_routers.py` | 修改 | 夹具表清单加两新表 |

---

### Task 1: models + crud + collect_material

**Files:** Modify models.py / crud.py;Test: test_bid_write_materials.py(crud 面)

- [x] Step 1 失败测试(crud 面):create/list/update/delete+owner 隔离+type 校验在 routers;profile upsert 幂等;collect_material 形(空库→三空键;两实体+profile+performance amount→price_history 派生)。
- [x] Step 2 models.py 追加:

```python
class MaterialEntity(Base):
    """素材实体(F2/P1-α;contracts.MATERIAL_ENTITY_TYPES 六类)。verifiable 不落
    列=派生 bool(evidence_refs)(spec「有可佐证附件」);fields JSON=实体自由面
    (资质有效期/业绩合同额等)。owner 库(跨任务复用)。"""
    __tablename__ = "bid_write_material_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(24))  # MATERIAL_ENTITY_TYPES
    name: Mapped[str] = mapped_column(String(255))
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)  # 佐证附件引用(doc_id/路径)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MaterialProfile(Base):
    """投标主体 profile(F2 单例面;BL bidder_name/legal_rep_name 唯一素材源)。"""
    __tablename__ = "bid_write_material_profiles"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
```

- [x] Step 3 crud.py 追加:create_material(类型校验 raise ValueError)/list_material(owner,可选 type)/update_material(404 面 None)/delete_material→bool/get_profile/upsert_profile/collect_material:

```python
async def collect_material(session, owner_id: str) -> dict:
    """owner 素材库→build_ctx material 形(entities 键=ent:<id>;bidder_profile
    单例缺→{};price_history=performance 实体 fields.amount 派生)。"""
    rows = await list_material(session, owner_id)
    prof = await get_profile(session, owner_id)
    return {
        "entities": {f"ent:{r.id}": {"type": r.entity_type, "name": r.name, "fields": dict(r.fields or {})} for r in rows},
        "bidder_profile": dict(prof.profile or {}) if prof is not None else {},
        "price_history": [{"project": r.name, "amount": (r.fields or {}).get("amount")} for r in rows if r.entity_type == "performance" and (r.fields or {}).get("amount") is not None],
    }
```

- [x] Step 4 测试绿 + commit `feat(bid-write): 批廿二 P1-a——素材库六类实体 models+crud(…)`。

### Task 2: routers /materials CRUD + profile

**Files:** Modify routers.py;Test: 同新测试文件

- [x] Step 1 失败测试:POST(422 非法 type)/GET list(type 过滤)/PATCH(404+改 fields/evidence)/DELETE(404 后查无)/owner 隔离(u2 不可见)/profile PUT→GET 幂等。
- [x] Step 2 实现:GET /materials、POST /materials、PATCH /materials/{id}、DELETE /materials/{id}、GET /materials/profile、PUT /materials/profile;schemas: MaterialIn(entity_type/name/fields/evidence_refs)、MaterialPatch(全 optional)、ProfileIn(profile dict)。
- [x] Step 3 测试绿 + commit。

### Task 3: gaps 三态兑现 + build_task_ctx 接线 + e2e 绿

**Files:** Modify routers.py(gaps)/worker.py;Test: 同文件

- [x] Step 1 失败测试:①种子实体「营业执照」evidence_refs 齐→gaps 该行 material_state=有且可佐证+entity_ref;②无佐证→有但缺佐证;③未匹配→无对应素材;clause 行 material_state=None;summary.material_ready 真值;④e2e:_ready_task(advance)→PUT profile+POST 两实体→POST generate(unit_prices+sign_date)→**blocked=False**(SK-BL-001 过,水印恒在)。
- [x] Step 2 实现:
  - worker.build_task_ctx:`material=dict(meta.get("material") or {})` → `material=await crud.collect_material(db, owner_id)`(meta 面废除;M1-i golden 纯函数直调不受影响)。
  - gaps:attachment 行经名归一匹配(`_norm` 对齐 attachment_index)+evidence→三态;clause 行 material_state=None;summary.material_ready=有且可佐证数;pending_note 换真值语义。
- [x] Step 3 既有两测试文件夹具表清单加 `MaterialEntity.__table__`/`MaterialProfile.__table__`(collect_material 查询面);跑 m2+routers 回归(m2 测试仍 blocked=True——空素材库诚实)。
- [x] Step 4 测试绿 + commit `feat(bid-write): 批廿二 P1-b——gaps 三态兑现+build_task_ctx 素材库接线(…)`。

### Task 4: 收口

- [x] Step 1 全子集 `-k bid_write`(基线 196p/6s+新增)+ lint。
- [x] Step 2 plan 勾兑+spec §7 P1-α 落地态段+wolf 三件套+memory。
- [x] Step 3 commit `docs(bid-write): 批廿二收口…`。

## 落地态勘误(执行时修正)

- att 行 requirement=「no=.. name=.. clause=..」拼接摘录 → 三态匹配用**名归一包含**(n in req or req in n),非全等。
- 执行发现 BL-001 槽位 purchaser/project/tender_no 无抽取源(COMMERCIAL_TENDER_SUBSET 21 路径缺三)→ subset +3(extract 引擎 FIELD_TYPE_CONTRACTS 外路径零改动兼容:prompt 裸路径/normalize 按 subset 白名单,已实测);全量回归抓契约钉违例(bug-4350)→三路径改经 `SUBSET_EXTRACT_EXTENSIONS` 显式扩面表登记后并入,主路径零新增契约铁律照旧。
- e2e 绿注意点:fake_extract 须含 purchaser_name/project_name/tender_no/deposit_forms,否则 BL-001 首败(诚实降级面)。
- 新表进既有测试夹具表清单(m2_worker/routers 两文件)。

## Self-Review

- spec F2 三态全部有测试;六类枚举校验 422;verifiable 派生不落列;e2e 绿=BL-001 首败面解除的最短路径。
- 类型一致:MaterialIn/collect_material/material 形与夹具逐键同;gaps 行键沿用现形+entity_ref 增量。
