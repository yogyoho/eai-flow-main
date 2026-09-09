"""投标资料管理 bid_materials：资质 MinIO 版本库 + 样例台账测试。

真库语义（sqlite+aiosqlite 内存库 + 真实 Service），镜像 test_eia_samples.py 夹具；
MinIO 单测见 TestStorage（monkeypatch _client，不连真桶）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.extensions.bid_materials.models import (
    BidQualification,
    BidQualificationVersion,
    BidSample,
)


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: BidQualification.__table__.metadata.create_all(sync_conn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_models_create_and_roundtrip(db: AsyncSession):
    q = BidQualification(
        qual_type="CMMI",
        cert_no="CMMI-2024-001",
        issuer="CMMI Institute",
        current_version=1,
    )
    db.add(q)
    await db.flush()
    v = BidQualificationVersion(
        qualification_id=q.id,
        version=1,
        minio_key=f"{q.id}/v1.png",
        sha256="a" * 64,
        file_ext="png",
        file_size=1024,
        note="初次登记",
    )
    db.add(v)
    s = BidSample(
        title="江西师范大学课堂观测系统",
        source_path="samples_bank/jiangxi_normed.md",
        file_hash=uuid.uuid4().hex,
        industry="信息技术",
        project_category="IT软件平台",
        scenario="bid_sample",
    )
    db.add(s)
    await db.flush()

    # roundtrip：回读三行，验证主键/外键/列级 default 真落在库上
    await db.refresh(q)
    await db.refresh(v)
    await db.refresh(s)

    assert q.id is not None
    assert q.cert_no == "CMMI-2024-001"
    assert q.disabled is False  # 软删标记 default
    assert q.current_version == 1
    assert q.created_at is not None and q.updated_at is not None

    assert v.id is not None
    assert v.qualification_id == q.id  # FK 指向资质行
    assert v.sha256 == "a" * 64 and v.file_ext == "png" and v.file_size == 1024
    assert v.uploaded_at is not None

    assert s.id is not None
    assert s.scenario == "bid_sample"
    assert s.status == "indexed"  # 状态轴 default
    assert s.industry == "信息技术" and s.project_category == "IT软件平台"
    assert s.created_at is not None
