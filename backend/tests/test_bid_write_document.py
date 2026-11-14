"""批廿八 M2 T1:正文 AST 存储(bid_write_task_documents 新表 create_all 零迁移)。
GET 未保存=ast:null(不造空文档冒充生成产物);PUT 幂等全量;ast 根/schema_version
校验 422;owner 过滤 404(routers 先 get_task 卡 owner,put 不会越权插行)。"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import crud, models
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA

DOC = {"type": "doc", "content": [{"type": "para", "attrs": {"slot_id": "s1"}}]}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.WriteTask.__table__,
                models.TaskDocument.__table__,
                models.BidWriteDocumentRevision.__table__,
                SA.WorkflowSubjectInstance.__table__,
                SA.WorkflowSubjectReview.__table__,
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


async def _seed(db):
    return (await crud.create_task(db, "u1")).id


@pytest.mark.asyncio
async def test_get_before_put_returns_null_ast(client, db):
    tid = await _seed(db)
    r = await client.get(f"/api/extensions/bid-write/tasks/{tid}/document")
    assert r.status_code == 200
    body = r.json()
    assert body["ast"] is None and body["updated_at"] is None and body["schema_version"] == ""


@pytest.mark.asyncio
async def test_put_get_roundtrip_and_overwrite(client, db):
    tid = await _seed(db)
    r = await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "0.1.0"})
    assert r.status_code == 200 and r.json()["updated_at"]
    r2 = await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": {**DOC, "content": []}, "schema_version": "0.2.0"})
    assert r2.status_code == 200
    body = (await client.get(f"/api/extensions/bid-write/tasks/{tid}/document")).json()
    assert body["ast"]["content"] == [] and body["schema_version"] == "0.2.0"


@pytest.mark.asyncio
async def test_put_validations(client, db):
    tid = await _seed(db)
    assert (await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": {"type": "para"}, "schema_version": "0.1.0"})).status_code == 422
    assert (await client.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "abc"})).status_code == 422


@pytest.mark.asyncio
async def test_owner_isolation(client, db):
    tid = await _seed(db)
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u2"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c2:
        assert (await c2.get(f"/api/extensions/bid-write/tasks/{tid}/document")).status_code == 404
        assert (await c2.put(f"/api/extensions/bid-write/tasks/{tid}/document", json={"ast": DOC, "schema_version": "0.1.0"})).status_code == 404
