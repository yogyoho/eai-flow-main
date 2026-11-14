"""批廿二 P1-α:素材库六类实体——crud collect_material 形/端点 CRUD+profile/
gaps 三态兑现/build_task_ctx 素材库接线 e2e(素材齐→generate→blocked=False)。

夹具形态同 test_bid_write_m2_worker(独立子应用+双 override+定点建表)。"""

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

_TABLES = [
    models.WriteTask.__table__,
    models.MatrixRow.__table__,
    R._SkillRun.__table__,
    models.MaterialEntity.__table__,
    models.MaterialProfile.__table__,
    models.BidWritePolicy.__table__,
    models.TaskDocument.__table__,
    models.BidWriteDocumentRevision.__table__,
]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
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


# ── Task 1: crud + collect_material ────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_material_type_validated(db):
    """六类枚举外→ValueError(端点转 422 面)。"""
    with pytest.raises(ValueError, match="非法素材类型"):
        await crud.create_material(db, "u1", "pokemon", "皮卡丘")
    row = await crud.create_material(db, "u1", "qualification", "营业执照", fields={"有效期": "2028-01-01"}, evidence_refs=["doc:1"])
    assert row.fields == {"有效期": "2028-01-01"}  # verifiable 是派生面(router 序列化),ORM 无此列


@pytest.mark.asyncio
async def test_collect_material_shape(db):
    """空库→三空键;实体+profile+performance amount→price_history 派生。"""
    empty = await crud.collect_material(db, "u1")
    assert empty == {"entities": {}, "bidder_profile": {}, "price_history": []}
    await crud.create_material(db, "u1", "qualification", "营业执照", evidence_refs=["doc:1"])
    await crud.create_material(db, "u1", "performance", "同类A", fields={"amount": 2100000})
    await crud.upsert_profile(db, "u1", {"name": "YY装备", "legal_rep": "张三"})
    mat = await crud.collect_material(db, "u1")
    assert set(mat["entities"].keys()) == {"ent:1", "ent:2"} or len(mat["entities"]) == 2
    assert all(set(v.keys()) == {"type", "name", "fields", "evidence_refs"} for v in mat["entities"].values())
    assert mat["bidder_profile"] == {"name": "YY装备", "legal_rep": "张三"}
    assert mat["price_history"] == [{"project": "同类A", "amount": 2100000}]


# ── Task 2: 端点 CRUD + profile ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_material_endpoints_crud(client):
    """POST(422 非法类型)/GET list+type 过滤/PATCH(404)/DELETE(404 后查无)。"""
    r = await client.post("/api/extensions/bid-write/materials", json={"entity_type": "pokemon", "name": "x"})
    assert r.status_code == 422
    r = await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "营业执照", "evidence_refs": ["doc:1"]})
    assert r.status_code == 200
    mid = r.json()["id"]
    assert r.json()["verifiable"] is True
    r = await client.get("/api/extensions/bid-write/materials")
    assert len(r.json()["items"]) == 1
    r = await client.get("/api/extensions/bid-write/materials", params={"entity_type": "performance"})
    assert r.json()["items"] == []
    r = await client.patch(f"/api/extensions/bid-write/materials/{mid}", json={"name": "营业执照(新)"})
    assert r.json()["name"] == "营业执照(新)"
    assert r.json()["verifiable"] is True
    r = await client.patch("/api/extensions/bid-write/materials/nope", json={"name": "x"})
    assert r.status_code == 404
    r = await client.delete(f"/api/extensions/bid-write/materials/{mid}")
    assert r.json() == {"deleted": True}
    assert (await client.delete(f"/api/extensions/bid-write/materials/{mid}")).status_code == 404


@pytest.mark.asyncio
async def test_material_owner_isolation(client, db):
    """u2 不可见 u1 素材(404 面与清单过滤)。"""
    r = await client.post("/api/extensions/bid-write/materials", json={"entity_type": "past_bid", "name": "历史标书A"})
    mid = r.json()["id"]
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u2"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c2:
        assert (await c2.get("/api/extensions/bid-write/materials")).json()["items"] == []
        assert (await c2.patch(f"/api/extensions/bid-write/materials/{mid}", json={"name": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_profile_upsert_idempotent(client):
    """PUT 幂等(单例 upsert);GET 回读。"""
    body = {"profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"}}
    assert (await client.put("/api/extensions/bid-write/materials/profile", json=body)).json() == body
    assert (await client.put("/api/extensions/bid-write/materials/profile", json=body)).json() == body
    assert (await client.get("/api/extensions/bid-write/materials/profile")).json() == body


# ── Task 3: gaps 三态 + e2e 绿 ─────────────────────────────────────────────


async def _seed(db, monkeypatch):
    """复用 m2 测试的推进桩:created→matrix_ready(fields 含 att:营业执照/安标)。"""
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

    def fake_extract(docs, field_paths):
        return {
            "fields": {
                "tender.boq_items": [{"id": "1.1", "name": "设备安装", "qty": 2, "unit": "套"}, {"id": "1.2", "name": "调试", "qty": 1, "unit": "项"}],
                "tender.required_validity_days": 90,
                "tender.deposit_required": True,
                "tender.deposit_forms": ["银行保函"],
                "tender.purchaser_name": "华源矿业集团有限公司",
                "tender.project_name": "某矿井智能化建设项目",
                "tender.tender_no": "TB-2026-001",
                "tender.attachment_requirements": [
                    {"no": "1", "name": "营业执照", "mandatory": "★", "clause": "3.1"},
                    {"no": "2", "name": "矿用产品安全标志证书", "mandatory": "必需", "clause": "3.2"},
                    {"no": "3", "name": "审计报告", "mandatory": "必需", "clause": "3.3"},
                ],
                "tender.bid_deadline": "2026-12-01",
            },
            "provenance": {},
            "confidence": {},
        }

    return await worker.advance_write_task(db, task.id, "u1", extract_fn=fake_extract)


@pytest.mark.asyncio
async def test_gaps_three_states(client, db, monkeypatch):
    """三态兑现:佐证齐→有且可佐证/实体无佐证→有但缺佐证/未匹配→无对应素材;
    clause 行 material_state=null;summary 三计数真值。"""
    task = await _seed(db, monkeypatch)
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "营业执照", "evidence_refs": ["doc:1"]})
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "矿用产品安全标志证书"})
    r = await client.get(f"/api/extensions/bid-write/tasks/{task.id}/gaps")
    assert r.status_code == 200
    by_state = {}
    for i in r.json()["items"]:
        if i["kind"] == "attachment":
            by_state[i["material_state"]] = by_state.get(i["material_state"], 0) + 1
        else:
            assert i["material_state"] is None  # clause 行素材不适用
    assert by_state == {"有且可佐证": 1, "有但缺佐证": 1, "无对应素材": 1}
    s = r.json()["summary"]
    assert s["material_ready"] == 1 and s["material_missing"] == 1 and s["material_unverified"] == 1


@pytest.mark.asyncio
async def test_generate_green_with_materials(client, db, monkeypatch):
    """e2e 端到端绿:素材齐(营业执照+安标+profile)→generate→blocked=False,
    SK-BL-001 过,水印恒在;gaps 断言维度落库。"""
    task = await _seed(db, monkeypatch)
    await client.put("/api/extensions/bid-write/materials/profile", json={"profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"}})
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "营业执照", "evidence_refs": ["doc:1"]})
    await client.post("/api/extensions/bid-write/materials", json={"entity_type": "qualification", "name": "矿用产品安全标志证书", "evidence_refs": ["doc:2"]})
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/generate", json={"unit_prices": {"1.1": "800000", "1.2": "400000"}, "sign_date": "2026-11-20"})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is False, body["verdict"]["reasons"]
    assert body["verdict"]["watermark"] is None  # 批廿五 P1-δ:L4-008 参与(响应表投影)hyb det 零命中→摘除;advisory 面,blocked False 不受影响
    assert body["verdict"]["assertion_counts"].get("FAIL", 0) == 0
