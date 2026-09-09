"""样例库 kf_samples CRUD / 批量导入幂等 / 场景过滤测试（EAI-CUSTOM: coal-eia v2 BS3 MVP）。

真库语义（sqlite+aiosqlite 内存库 + 真实 SampleService），非 AsyncMock——
upsert 幂等与 scenario 过滤依赖 SQL 行为，mock 无法证明。只建 kf_samples 单表
（users FK 引用表可缺席：SQLite 默认不强制外键），不触发 init_db/migrate_db。
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.extensions.knowledge_factory.models import KFSample
from app.extensions.knowledge_factory.sample_service import SampleHashConflictError, SampleService
from app.extensions.knowledge_factory.schemas import (
    SampleBatchUpdate,
    SampleBulkImportRequest,
    SampleBulkItem,
    SampleCreate,
    SampleScenario,
    SampleStatus,
    SampleUpdate,
)

SEED_PATH = Path(__file__).resolve().parents[1] / "app" / "extensions" / "knowledge_factory" / "data" / "kf_samples_seed.json"


def _item(**overrides) -> dict:
    base = {
        "title": f"测试样例 {uuid4().hex[:8]}",
        "source_path": "D:/corpus/测试样例.docx",
        "file_hash": uuid4().hex,
        "scenario": "planning_eia",
        "variant": "修编·报批版",
        "status": "parsed",
        "confidence": 0.9,
        "notes": None,
    }
    base.update(overrides)
    return base


def json_items() -> list[dict]:
    """种子台账 JSON 条目（同时验证全部条目满足 SampleBulkItem 契约）。"""
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))["items"]


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(KFSample.__table__.create)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── CRUD ──


@pytest.mark.asyncio
async def test_create_and_get_roundtrip(db):
    data = SampleCreate(**_item(confidence=0.55, notes="n1"))
    sample = await SampleService.create_sample(db, data)
    assert sample.scenario == "planning_eia"
    assert sample.status == "parsed"
    assert sample.confidence == 0.55

    fetched = await SampleService.get_sample(db, sample.id)
    assert fetched is not None and fetched.file_hash == sample.file_hash
    by_hash = await SampleService.get_by_hash(db, sample.file_hash)
    assert by_hash is not None and by_hash.id == sample.id


@pytest.mark.asyncio
async def test_create_duplicate_hash_conflicts(db):
    item = _item()
    await SampleService.create_sample(db, SampleCreate(**item))
    with pytest.raises(SampleHashConflictError):
        await SampleService.create_sample(db, SampleCreate(**_item(file_hash=item["file_hash"], title="同哈希另一条")))


@pytest.mark.asyncio
async def test_update_patch_semantics(db):
    sample = await SampleService.create_sample(db, SampleCreate(**_item()))
    updated = await SampleService.update_sample(db, sample, SampleUpdate(scenario=SampleScenario.PROJECT_EIA_OPENPIT, confidence=0.5))
    assert updated.scenario == "project_eia_openpit"
    assert updated.confidence == 0.5
    assert updated.status == "parsed"  # 未触碰字段保持
    assert updated.title == sample.title


@pytest.mark.asyncio
async def test_delete_removes_row(db):
    sample = await SampleService.create_sample(db, SampleCreate(**_item()))
    await SampleService.delete_sample(db, sample)
    assert await SampleService.get_sample(db, sample.id) is None
    samples, total = await SampleService.list_samples(db)
    assert samples == [] and total == 0


# ── 批量导入幂等 ──


@pytest.mark.asyncio
async def test_bulk_import_seed_then_rerun_is_idempotent(db):
    first = await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()))
    assert first == {"created": 29, "updated": 0, "total": 29}

    again = await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()))
    assert again == {"created": 0, "updated": 29, "total": 29}

    _, total = await SampleService.list_samples(db, limit=1)
    assert total == 29  # 不产生重复行

    # 覆盖语义：重导入条目字段生效（post_eia 两条姊妹互证）
    samples, _ = await SampleService.list_samples(db, scenario=SampleScenario.POST_EIA, limit=10)
    assert len(samples) == 2 and all(s.status == "parsed" for s in samples)


@pytest.mark.asyncio
async def test_bulk_import_mixed_create_update(db):
    await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()[:5]))
    items = json_items()
    items[2] = {**items[2], "status": "converted_failed"}  # 既有哈希 → 覆盖
    result = await SampleService.bulk_import(db, SampleService.make_bulk_payload(items))
    assert result == {"created": 24, "updated": 5, "total": 29}
    target = await SampleService.get_by_hash(db, items[2]["file_hash"])
    assert target is not None and target.status == "converted_failed"


# ── 场景过滤 + 分页 ──


@pytest.mark.asyncio
async def test_scenario_filter_and_pagination(db):
    rows = [
        _item(scenario="planning_eia"),
        _item(scenario="planning_eia"),
        _item(scenario="project_eia_underground"),
        _item(scenario="project_eia_openpit", status="converted"),
    ]
    await SampleService.bulk_import(db, SampleBulkImportRequest(items=[SampleBulkItem.model_validate(r) for r in rows]))

    samples, total = await SampleService.list_samples(db, scenario=SampleScenario.PLANNING_EIA)
    assert total == 2 and {s.scenario for s in samples} == {"planning_eia"}

    samples, total = await SampleService.list_samples(db, scenario=SampleScenario.PROJECT_EIA_OPENPIT, status=SampleStatus.CONVERTED)
    assert total == 1 and samples[0].status == "converted"

    page1, total = await SampleService.list_samples(db, page=1, limit=2)
    page2, _ = await SampleService.list_samples(db, page=2, limit=2)
    assert total == 4
    assert {s.id for s in page1}.isdisjoint({s.id for s in page2}) and len(page2) == 2

    found, total = await SampleService.list_samples(db, search=rows[0]["title"][5:])
    assert total == 1 and found[0].file_hash == rows[0]["file_hash"]


# ── 批量归类 ──


@pytest.mark.asyncio
async def test_batch_update_scenario_status(db):
    await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()[:6]))
    samples, _ = await SampleService.list_samples(db, limit=10)
    ids = [s.id for s in samples[:4]]

    updated = await SampleService.batch_update(db, SampleBatchUpdate(ids=ids, scenario=SampleScenario.OTHER, status=SampleStatus.FILENAME_ONLY))
    assert updated == 4
    after, _ = await SampleService.list_samples(db, scenario=SampleScenario.OTHER, limit=10)
    assert {s.id for s in after} == set(ids) and all(s.status == "filename_only" for s in after)


# ── 契约校验 ──


def test_schema_rejects_unknown_scenario_and_bad_values():
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(scenario="not_a_scenario"))
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(confidence=1.5))
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(file_hash="short"))  # <8 字符
    with pytest.raises(ValidationError):
        SampleBatchUpdate(ids=[uuid4()])  # 全空更新被拒
