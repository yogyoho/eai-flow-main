"""批廿三 P1-β:policy 配置面(owner 单例 letter_defaults/tax_rate/调价开关)+
埋点六指标(verdict.metrics+owner 聚合 p95)。

夹具形态同 test_bid_write_materials(独立子应用+双 override+定点建表)。"""

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


async def _seed(db, monkeypatch, *, omit_validity=False):
    """推进桩(同 materials._seed 简形):created→matrix_ready;omit_validity=
    抽取面不给 tender.required_validity_days(letter_defaults 兜底测试面)。"""
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

    fields = {
        "tender.boq_items": [
            {"id": "1.1", "name": "设备安装", "qty": 2, "unit": "套"},
            {"id": "1.2", "name": "调试", "qty": 1, "unit": "项"},
        ],
        "tender.deposit_required": True,
        "tender.deposit_forms": ["银行保函"],
        "tender.purchaser_name": "华源矿业集团有限公司",
        "tender.project_name": "某矿井智能化建设项目",
        "tender.tender_no": "TB-2026-001",
        "tender.bid_deadline": "2026-12-01",
        "tender.attachment_requirements": [
            {"no": "1", "name": "营业执照", "mandatory": "★", "clause": "3.1"},
            {"no": "2", "name": "矿用产品安全标志证书", "mandatory": "必需", "clause": "3.2"},
        ],
    }
    if not omit_validity:
        fields["tender.required_validity_days"] = 90

    def fake_extract(docs, field_paths):
        return {"fields": fields, "provenance": {}, "confidence": {}}

    return await worker.advance_write_task(db, task.id, "u1", extract_fn=fake_extract)


# ── Task 1: policy 配置面 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_upsert_merge(client):
    """PUT 合并语义(只改键不清他键);GET 回读;ghost 键/越界税率 422。"""
    r = await client.put("/api/extensions/bid-write/policy", json={"tax_rate": 0.09})
    assert r.json()["policy"] == {"tax_rate": 0.09}
    r = await client.put("/api/extensions/bid-write/policy", json={"price_adjust_mechanism": False})
    assert r.json()["policy"] == {"tax_rate": 0.09, "price_adjust_mechanism": False}
    assert (await client.get("/api/extensions/bid-write/policy")).json()["policy"] == {"tax_rate": 0.09, "price_adjust_mechanism": False}
    assert (await client.put("/api/extensions/bid-write/policy", json={"ghost_key": 1})).status_code == 422
    assert (await client.put("/api/extensions/bid-write/policy", json={"tax_rate": 1.5})).status_code == 422
    assert (await client.put("/api/extensions/bid-write/policy", json={"letter_defaults": {"ghost": 1}})).status_code == 422
