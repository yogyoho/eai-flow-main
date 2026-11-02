"""L2 P1 附件核对表(spec 2026-11-02 §4):GET /tasks/{id}/attachment_checklist。

基线 fields tender.attachment_requirements × bid.attachment_index 经
build_checklist 投影(不落库);基线每行同全量快照 → 要求按 (no,name) 跨行去重,
提供项逐行收集。refs 注入 bid 侧首 doc_id(engine_meta.docs role=bid;解不到 →
null)。零投影(旧任务无 tender.attachment_requirements)→ counts 全 0 + items []
(诚实,不装数据)。夹具照 test_bid_review_deviations.py。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db

REQS = [
    {"no": "ATT-E-008", "name": "类似业绩证明", "clause": "第三章3.4", "mandatory": "★", "min_count": 3},
    {"no": "ATT-F-001", "name": "投标函", "clause": None, "mandatory": "★", "min_count": None},
]
PROV = [
    {"no": "ATT-E-008", "name": "类似业绩证明", "page": 118, "pages": None},
    {"no": "ATT-E-008", "name": "类似业绩证明", "page": 121, "pages": None},
    {"no": "ATT-F-001", "name": "投标函", "page": 2, "pages": 3},
    {"no": "", "name": "企业宣传册", "page": 310, "pages": None},
]
FIELDS = {"tender.attachment_requirements": REQS, "bid.attachment_index": PROV}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.ReviewTask.__table__,
                models.ReviewIssue.__table__,
                models.BaselinePackage.__table__,
                models.RulePackMeta.__table__,
                models.ReviewFeedback.__table__,
            ],
        )
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


async def _mk_baseline(db, task_id: str, fields: dict) -> models.BaselinePackage:
    row = models.BaselinePackage(task_id=task_id, kind="bid", payload={"fields": fields})
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_checklist_projection_dedup_and_refs(db, client):
    """真投影:要求跨行 (no,name) 去重;counts 六格;refs 注 bid 侧首 doc_id。"""
    t = await crud.create_task(db, owner_id="u1")
    t.engine_meta = {"docs": [{"doc_id": "tender.pdf", "role": "tender"}, {"doc_id": "bid.pdf", "role": "bid"}]}
    await db.commit()
    await _mk_baseline(db, t.id, FIELDS)
    await _mk_baseline(db, t.id, FIELDS)  # 第二行同快照 → 要求去重不翻倍;提供项本实现逐行收集
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    assert r.status_code == 200
    body = r.json()
    # 提供项逐行收集 → 份数翻倍(2 行 × 2 份业绩):PARTIAL(2/3)→ 实际 found=4 ≥ 3 → MATCHED
    assert body["counts"] == {"required": 2, "matched": 2, "partial": 0, "missing": 0, "unknown": 0, "extra": 2}
    it = next(i for i in body["items"] if i["no"] == "ATT-E-008")
    assert it["status"] == "MATCHED" and it["found"] == 4
    assert it["refs"] == [
        {"doc_id": "bid.pdf", "page": 118},
        {"doc_id": "bid.pdf", "page": 121},
        {"doc_id": "bid.pdf", "page": 118},
        {"doc_id": "bid.pdf", "page": 121},
    ]
    assert {e["name"] for e in body["extra_items"]} == {"企业宣传册"}
    assert all(e["doc_id"] == "bid.pdf" for e in body["extra_items"])


@pytest.mark.asyncio
async def test_checklist_single_row_full_flow(db, client):
    """单行快照(常规路径):PARTIAL/MATCHED/EXTRA 三态齐;doc_id 解析不到 → null。"""
    t = await crud.create_task(db, owner_id="u1")  # 无 engine_meta.docs → bid_doc null
    await _mk_baseline(db, t.id, FIELDS)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    body = r.json()
    assert body["counts"] == {"required": 2, "matched": 1, "partial": 1, "missing": 0, "unknown": 0, "extra": 1}
    it = next(i for i in body["items"] if i["no"] == "ATT-E-008")
    assert it["status"] == "PARTIAL" and it["found"] == 2 and it["min_count"] == 3 and it["clause"] == "第三章3.4"
    assert it["refs"] == [{"doc_id": None, "page": 118}, {"doc_id": None, "page": 121}]


@pytest.mark.asyncio
async def test_checklist_zero_projection(db, client):
    """旧任务无附件字段(或无基线)→ counts 全 0 + items [](诚实空态)。"""
    t = await crud.create_task(db, owner_id="u1")
    await _mk_baseline(db, t.id, {"tender.max_price": 100})
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    assert r.status_code == 200
    assert r.json() == {
        "counts": {"required": 0, "matched": 0, "partial": 0, "missing": 0, "unknown": 0, "extra": 0},
        "items": [],
        "extra_items": [],
    }
    t2 = await crud.create_task(db, owner_id="u1")  # 连基线都没有
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{t2.id}/attachment_checklist")
    assert r2.status_code == 200 and r2.json()["items"] == []


@pytest.mark.asyncio
async def test_checklist_ghost_404(client):
    r = await client.get("/api/extensions/bid-review/tasks/ghost/attachment_checklist")
    assert r.status_code == 404


COMP_FIELDS = {
    "tender.attachment_requirements": [
        {
            "no": "3",
            "name": "资格审查文件",
            "clause": "第三章3.1",
            "mandatory": "★",
            "min_count": None,
            "sub_items": [{"no": "3.1", "name": "营业执照"}],
        },
    ],
    "bid.attachment_index": [{"no": "3-9", "name": "完税证明", "page": 40, "pages": None}],
}


@pytest.mark.asyncio
async def test_endpoint_composite_unknown_passthrough(db, client):
    """端点透传 counts.unknown + items[].sub_results(build_checklist 原样出)。"""
    t = await crud.create_task(db, owner_id="u1")
    await _mk_baseline(db, t.id, COMP_FIELDS)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/attachment_checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["unknown"] == 1
    assert body["items"][0]["status"] == "UNKNOWN"
    assert body["items"][0]["sub_results"][0]["name"] == "营业执照"
    assert body["extra_items"] == []
