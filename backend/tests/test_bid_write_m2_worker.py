"""批廿一 M2-c:worker 接线(fields 持久化/自动预审查/generate_and_record)
+ generate / export-precheck 端点。夹具形态同 test_bid_write_routers(独立子
应用+双 override;两表+SkillRun 定点建)。"""

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
        await c.run_sync(Base.metadata.create_all, tables=[models.WriteTask.__table__, models.MatrixRow.__table__, R._SkillRun.__table__, models.MaterialEntity.__table__, models.MaterialProfile.__table__])
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


async def _ready_task(db, monkeypatch):
    """推进到 matrix_ready 的任务(engine_meta.fields 已持久化+自动预审查已跑)。"""
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
    material 缺→blocked True 诚实,BL-001 D0 首败短路进 reasons)。"""
    task = await _ready_task(db, monkeypatch)
    assert task.status == "matrix_ready"
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed.engine_meta["fields"]["tender.required_validity_days"] == 90
    run = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    assert run is not None and run.blocked is True  # 素材缺→BL-001 D0 阻断=诚实
    assert "SK-BL-001" in (run.verdict or {}).get("reasons", [])
    assert (run.verdict or {}).get("results")  # gaps 断言维度消费面


@pytest.mark.asyncio
async def test_generate_endpoint_records(client, db, monkeypatch):
    """POST generate(knobs 入 meta)+ verdict 落库;409=未就绪面。"""
    task = await _ready_task(db, monkeypatch)
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/generate", json={"unit_prices": {"1.1": "800000", "1.2": "400000"}, "sign_date": "2026-11-20"})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is True and "SK-BL-001" in body["verdict"]["reasons"]  # material 缺=诚实
    assert body["verdict"]["watermark"] == "商务风险未确认"
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed.engine_meta["knobs"]["unit_prices"] == {"1.1": "800000", "1.2": "400000"}
    # 未就绪 409
    t2 = await crud.create_task(db, "u1")
    r2 = await client.post(f"/api/extensions/bid-write/tasks/{t2.id}/generate", json={})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_export_precheck_readonly(client, db, monkeypatch):
    """export-precheck 只读重算:不落新 skill_run;watermark/reasons/计数面齐。"""
    task = await _ready_task(db, monkeypatch)
    before = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/export-precheck")
    assert r.status_code == 200
    body = r.json()
    assert body["watermark"] == "商务风险未确认"
    assert "SK-BL-001" in body["reasons"] and body["blocked"] is True
    assert body["assertion_counts"]
    after = await crud.latest_skill_run(db, task_id=task.id, owner_id="u1")
    assert (before.id,) == (after.id,)  # 只读无新行
