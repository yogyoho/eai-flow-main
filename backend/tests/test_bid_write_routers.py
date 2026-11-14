"""批十九 T5/T4 测试:bid_write 端点(独立子应用+双 override,同 test_bid_review_
routers 夹具形态)+ advance_write_task 管线(stub extract_fn;parse 链 monkeypatch)。

偏离点:两表定点建(bid_write_tasks/bid_write_matrix_rows);_enqueue 后台旁路。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import crud, models, worker
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.WriteTask.__table__,
                models.MatrixRow.__table__,
                R._SkillRun.__table__,
                models.MaterialEntity.__table__,
                models.MaterialProfile.__table__,
                models.BidWritePolicy.__table__,
                SA.WorkflowSubjectInstance.__table__,
                SA.WorkflowSubjectReview.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _noop_enqueue(task):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_enqueue", _noop_enqueue)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.asyncio
async def test_create_task_with_files(client, db):
    """multipart 招标文件→raw 落盘清单(复用审查端 parse.save_raw),任务 created。"""
    r = await client.post("/api/extensions/bid-write/tasks", data={"project_name": "某煤矿项目"}, files=[("tender_files", ("t.txt", b"TENDER", "text/plain"))])
    assert r.status_code == 200 and r.json()["status"] == "created"
    tid = r.json()["id"]
    assert r.json()["biz_no"].startswith("TBW-") and r.json()["project_name"] == "某煤矿项目"
    t = await crud.get_task(db, task_id=tid, owner_id="u1")
    docs = t.engine_meta["docs"]
    assert docs[0]["role"] == "tender" and docs[0]["status"] == "raw" and docs[0]["doc_id"] == "t.txt"
    assert t.engine_meta["schema_version"].count(".") == 2


@pytest.mark.asyncio
async def test_owner_isolation(client, db):
    """owner 过滤:u2 不可见 u1 任务。"""
    r = await client.post("/api/extensions/bid-write/tasks", files=[("tender_files", ("t.txt", b"T", "text/plain"))])
    tid = r.json()["id"]
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u2"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c2:
        assert (await c2.get(f"/api/extensions/bid-write/tasks/{tid}")).status_code == 404
        assert (await c2.get("/api/extensions/bid-write/tasks")).json()["items"] == []


async def _seed_matrix(db, *, star=False, status="draft"):
    task = await crud.create_task(db, "u1")
    rows = [
        {
            "clause_id": "att:1",
            "kind": "attachment",
            "source_path": "tender.attachment_requirements",
            "requirement": "营业执照",
            "star": star,
            "target_section": "",
            "evidence_refs": [],
            "status": status,
        }
    ]
    await crud.replace_matrix(db, task.id, rows)
    return task.id


@pytest.mark.asyncio
async def test_matrix_read_and_patch(client, db):
    """矩阵读(词汇表回显)+ 行级卡点:合法 patch 200;非法 strategy/status 422。"""
    tid = await _seed_matrix(db)
    r = await client.get(f"/api/extensions/bid-write/tasks/{tid}/matrix")
    body = r.json()
    assert body["items"][0]["clause_id"] == "att:1" and body["vocab"]["strategies"] == ["pending", "full", "positive", "negative"]
    r2 = await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"strategy": "full", "status": "confirmed", "note": "确认"})
    assert r2.status_code == 200 and r2.json()["strategy"] == "full" and r2.json()["status"] == "confirmed"
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"strategy": "bogus"})).status_code == 422
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"status": "bogus"})).status_code == 422
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/nope", json={"note": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_star_negative_requires_note(client, db):
    """★行负偏离卡点(SK-RT-005 前置):无 note 422;带理由放行。"""
    tid = await _seed_matrix(db, star=True)
    r = await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"strategy": "negative"})
    assert r.status_code == 422 and "★" in r.json()["detail"]
    r2 = await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"strategy": "negative", "note": "替代方案:提供同等级 KA 证书"})
    assert r2.status_code == 200
    # 非星行 negative 无 note 合法(M0;响应表生成面批二十再收紧)
    tid2 = await _seed_matrix(db, star=False)
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid2}/matrix/att:1", json={"strategy": "negative"})).status_code == 200


@pytest.mark.asyncio
async def test_blocked_confirm_requires_note(client, db):
    """blocked(低置信)行确认须带依据:无 note 422,带 note 放行。"""
    tid = await _seed_matrix(db, status="blocked")
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"status": "confirmed"})).status_code == 422
    assert (await client.patch(f"/api/extensions/bid-write/tasks/{tid}/matrix/att:1", json={"status": "confirmed", "note": "已对照原文 3.1 条确认"})).status_code == 200


@pytest.mark.asyncio
async def test_gaps_honest_zero(client, db):
    """缺口三态 M0 诚实伪零:全部「无对应素材」,material_ready=0。"""
    tid = await _seed_matrix(db)
    r = await client.get(f"/api/extensions/bid-write/tasks/{tid}/gaps")
    body = r.json()
    assert body["items"][0]["material_state"] == "无对应素材"
    assert body["summary"]["material_ready"] == 0 and body["summary"]["total"] == 1


@pytest.mark.asyncio
async def test_registry_readonly_projection(client):
    """注册表只读投影:前端「断言注册表」页消费;返回 p0.yaml 全量断言 +
    levels 行为表 + schema_version,D0 必须阻断导出。"""
    r = await client.get("/api/extensions/bid-write/registry")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"].count(".") == 2
    assert len(body["items"]) == 43
    assert {item["id"] for item in body["items"]} >= {"SK-PS-003", "SK-RT-002"}
    assert {"D0", "D1", "D2", "D3"} <= set(body["levels"])
    assert all(item["level"] == "D0" and item["blocks_export"] for item in body["items"] if item["level"] == "D0")
    assert all({"id", "skill", "name", "level", "blocks_export", "rule_ref", "expr", "human_action"} <= set(item) for item in body["items"])


# ── advance_write_task 管线(stub extract;parse 链 monkeypatch)───────────────


@pytest.mark.asyncio
async def test_advance_pipeline_happy_path(db, monkeypatch):
    """created→parsing→extracting→matrix_ready;矩阵落库含 ★/聚合行;engine_meta
    带 schema_version/provenance/fields_conf。"""
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

    def fake_docs_from_entries(owner, task_id, entries):
        # 全文含 quote 片段→verify_quotes 命中(verified=True 快乐路径)
        return [{"doc_id": "t.txt", "role": "tender", "text": "投标截止时间:2026-12-01 09:00"}]

    monkeypatch.setattr(parse, "build_ocr_fn", fake_ocr)
    monkeypatch.setattr(parse, "parse_raw", fake_parse_raw)
    monkeypatch.setattr(parse, "docs_from_entries", fake_docs_from_entries)

    def fake_extract(docs, field_paths):
        assert "tender.attachment_requirements" in field_paths and "tender.bid_deadline" in field_paths
        assert all(p.startswith("tender.") for p in field_paths)  # tender-only
        return {
            "fields": {"tender.attachment_requirements": [{"no": "1", "name": "营业执照", "mandatory": "★", "clause": "3.1"}], "tender.bid_deadline": "2026-12-01"},
            "provenance": {"tender.bid_deadline": {"doc_id": "t.txt", "page": 3, "quote": "2026-12-01"}},
            "confidence": {"tender.bid_deadline": 0.95},
        }

    out = await worker.advance_write_task(db, task.id, "u1", extract_fn=fake_extract)
    assert out.status == "matrix_ready"
    assert "★1" in out.progress["msg"] or "★" in out.progress["msg"]
    rows = await crud.list_matrix(db, task.id, "u1")
    by_id = {r.clause_id: r for r in rows}
    assert by_id["att:1"].star is True
    assert by_id["deadline"].requirement.startswith("投标截止:")
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed.engine_meta["schema_version"] == "1.0.0"
    assert refreshed.engine_meta["fields_conf"]["tender.bid_deadline"]["verified"] is True


@pytest.mark.asyncio
async def test_advance_pipeline_failure_lands_failed(db, monkeypatch):
    """抽取抛错→终态 failed 落因(单跑无重投,重投面挂批二十);状态守卫:
    非 created 二跑直接返回。"""
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

    def fake_docs_from_entries(owner, task_id, entries):
        return [{"doc_id": "t.txt", "role": "tender", "text": "全文"}]

    monkeypatch.setattr(parse, "build_ocr_fn", fake_ocr)
    monkeypatch.setattr(parse, "parse_raw", fake_parse_raw)
    monkeypatch.setattr(parse, "docs_from_entries", fake_docs_from_entries)

    def boom(docs, field_paths):
        raise RuntimeError("模型炸了")

    out = await worker.advance_write_task(db, task.id, "u1", extract_fn=boom)
    assert out.status == "failed" and "模型炸了" in (out.error or "")
    again = await worker.advance_write_task(db, task.id, "u1", extract_fn=boom)
    assert again.status == "failed"  # 非 created 守卫:不重跑


@pytest.mark.asyncio
async def test_advance_no_docs_fails(db):
    """无 raw 条目(空上传绕过面)→ failed 落因,不假交付。"""
    task = await crud.create_task(db, "u1")
    out = await worker.advance_write_task(db, task.id, "u1", extract_fn=lambda d, f: {"fields": {}})
    assert out.status == "failed" and "raw" in (out.error or "")
