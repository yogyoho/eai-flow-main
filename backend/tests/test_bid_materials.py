"""投标资料管理 bid_materials：资质 MinIO 版本库 + 样例台账测试。

真库语义（sqlite+aiosqlite 内存库 + 真实模型），镜像 test_eia_samples.py 夹具。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.extensions.models  # noqa: F401  — 注册 users 等表进共享 Base.metadata 供 FK 解析（只 import，不建表）
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
        # 显式只建本扩展三张表（不走全量 Base.metadata——防未来 import 面膨胀拉入 PG-only 类型）；
        # users FK 引用表可缺席：SQLite 默认不强制外键（eia_samples 先例）。
        await conn.run_sync(
            lambda sync_conn: BidQualification.__table__.metadata.create_all(
                sync_conn,
                tables=[
                    BidQualification.__table__,
                    BidQualificationVersion.__table__,
                    BidSample.__table__,
                ],
            )
        )
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


@pytest.mark.asyncio
async def test_version_unique_per_qualification(db: AsyncSession):
    """同资质同 version 二次登记必须被 DB 唯一约束拒绝（防并发上传铸重复版本号）。

    两条重复行仅 (qualification_id, version) 相同——minio_key/sha256 均不同，
    命中且仅命中 uq_bid_qualification_version 约束。
    """
    q = BidQualification(qual_type="ISO9001", cert_no="ISO-2026-001", current_version=1)
    db.add(q)
    await db.flush()
    db.add(
        BidQualificationVersion(
            qualification_id=q.id,
            version=1,
            minio_key=f"{q.id}/v1.png",
            sha256="b" * 64,
            file_ext="png",
            file_size=2048,
        )
    )
    await db.flush()
    db.add(
        BidQualificationVersion(
            qualification_id=q.id,
            version=1,
            minio_key=f"{q.id}/v1-dup.png",
            sha256="c" * 64,
            file_ext="png",
            file_size=4096,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
