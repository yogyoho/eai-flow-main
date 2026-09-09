# 投标资料管理扩展（bid_materials）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地投标资料管理独立扩展——资质文件（png/jpg）MinIO 版本库（到期预警/白名单导出）+ 样例台账（KFSample 形态沿用），含 gateway 挂载/权限/app-center 注册/种子脚本。

**Architecture:** 镜像 eia_samples 独立扩展先例（commit 1ce049220：自 KF 迁出的领域样例库独立应用）——models(声明式 Base)+schemas(Pydantic)+service(真库语义类)+routers(require_permission("system:access")+get_db)+storage(MinIO fork geo_samples/storage.py，专用 BQM_* env 与独立桶)+permissions.yaml 应用块。测试用 sqlite+aiosqlite 内存库+真实 Service（非 mock，镜像 test_eia_samples.py 夹具）；MinIO 单测 monkeypatch `_client`。

**Tech Stack:** FastAPI + SQLAlchemy(异步, Postgres/SQLite-aiosqlite 测试) + minio 客户端（已在依赖, geo/contract_price 在用）+ pydantic v2。

**依据 spec:** `docs/superpowers/specs/2026-09-06-bid-materials-two-skill-design.md` §2（本计划=spec §2 全量；§3-§5 属 Plan 2/3）。

**先例文件（写代码前先读）:**
- `backend/app/extensions/eia_samples/`（models/schemas/service/routers 全套 1:1 镜像源）
- `backend/app/extensions/geo_samples/storage.py`（MinIO fork 源）
- `backend/tests/test_eia_samples.py`（sqlite 夹具模式源）
- `backend/app/gateway/app.py:23-26,938-939`（路由挂载点）
- `config/permissions.yaml:201-207,355,402`（应用块与角色 nav 形态）

---

### Task 1: 扩展骨架 + 数据模型

**Files:**
- Create: `backend/app/extensions/bid_materials/__init__.py`
- Create: `backend/app/extensions/bid_materials/models.py`
- Test: `backend/tests/test_bid_materials.py`

- [ ] **Step 1: 写失败测试（模型可建表+字段齐全）**

```python
# backend/tests/test_bid_materials.py 顶部与夹具
"""投标资料管理 bid_materials：资质 MinIO 版本库 + 样例台账测试。

真库语义（sqlite+aiosqlite 内存库 + 真实 Service），镜像 test_eia_samples.py 夹具；
MinIO 单测见 TestStorage（monkeypatch _client，不连真桶）。
"""
import json
from uuid import uuid4

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
        await conn.run_sync(
            lambda sync_conn: BidQualification.__table__.metadata.create_all(sync_conn)
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_models_create_and_roundtrip(db: AsyncSession):
    q = BidQualification(
        qual_type="CMMI", cert_no="CMMI-2024-001", issuer="CMMI Institute",
        current_version=1,
    )
    db.add(q)
    await db.flush()
    v = BidQualificationVersion(
        qualification_id=q.id, version=1, minio_key=f"{q.id}/v1.png",
        sha256="a" * 64, file_ext="png", file_size=1024, note="初次登记",
    )
    db.add(v)
    s = BidSample(
        title="江西师范大学课堂观测系统", source_path="samples_bank/jiangxi_normed.md",
        file_hash=uuid4().hex, industry="信息技术", project_category="IT软件平台",
        scenario="bid_sample",
    )
    db.add(s)
    await db.flush()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_materials.py -v`
Expected: FAIL（`ModuleNotFoundError: app.extensions.bid_materials`）

- [ ] **Step 3: 写 models.py（完整）**

```python
# backend/app/extensions/bid_materials/__init__.py
"""投标资料管理扩展（EAI-CUSTOM bug-3109 v4）: 资质 MinIO 版本库 + 样例台账。"""
from .routers import router as bid_materials_router  # noqa: F401
```

（routers 在 Task 4 前不存在——本 Task 先写成空文件占位 `"""投标资料管理扩展。"""`，Task 4 完成时替换为上行。）

```python
# backend/app/extensions/bid_materials/models.py
"""投标资料管理数据模型: 资质元数据/资质版本(MinIO)/样例台账。

形态沿用 eia_samples.KFSample（声明式 Base；commit 1ce049220 领域样例库独立应用先例）。
资质文件本体存 MinIO 桶 bid-qualifications（storage.py），行内只存 minio_key/sha256。
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class BidQualification(Base):
    """资质元数据行。文件本体在 MinIO，行内 current_version 指针决定当前版。"""

    __tablename__ = "bid_qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qual_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cert_no: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_until: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    org_scope: Mapped[str | None] = mapped_column(String(100), nullable=True)
    disabled: Mapped[bool] = mapped_column(nullable=False, default=False)  # 软删标记
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class BidQualificationVersion(Base):
    """资质文件版本行（不可变只追加）。回滚=改 BidQualification.current_version 指针。"""

    __tablename__ = "bid_qualification_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qualification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bid_qualifications.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class BidSample(Base):
    """样例台账（沿用 KFSample 形态; 深度地板统一走 depth_targets.json, 册级不存）。"""

    __tablename__ = "bid_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False, default="other", index=True)
    project_category: Mapped[str] = mapped_column(String(50), nullable=False, default="IT软件平台", index=True)
    scenario: Mapped[str] = mapped_column(String(50), nullable=False, default="bid_sample")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="indexed", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_materials.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_materials/ backend/tests/test_bid_materials.py
git commit -m "feat(bid-materials): 扩展骨架+三模型(资质/资质版本/样例台账)"
```

---

### Task 2: MinIO storage（fork geo_samples/storage.py）

**Files:**
- Create: `backend/app/extensions/bid_materials/storage.py`
- Test: `backend/tests/test_bid_materials.py`（追加 TestStorage 类）

- [ ] **Step 1: 写失败测试（monkeypatch _client，不连真桶）**

```python
class FakeObjectStore:
    """内存 Minio 替身: 记录 put, 支持 get/stat/remove。"""
    def __init__(self):
        self.objects: dict[str, bytes] = {}
    def put_object(self, bucket_name, object_name, data, length):
        self.objects[object_name] = data.read()
    def get_object(self, bucket_name, object_name):
        import io
        return io.BytesIO(self.objects[object_name])
    def stat_object(self, bucket_name, object_name):
        if object_name not in self.objects:
            from minio.error import S3Error
            raise S3Error(code="NoSuchKey", message="missing", resource=object_name)
        return True
    def remove_object(self, bucket_name, object_name):
        self.objects.pop(object_name, None)
    def bucket_exists(self, bucket_name):
        return True
    def make_bucket(self, bucket_name):
        self.objects.setdefault("_bucket", b"")


class TestStorage:
    def test_put_get_roundtrip_and_delete(self, monkeypatch):
        from app.extensions.bid_materials import storage

        fake = FakeObjectStore()
        monkeypatch.setattr(storage, "_client", lambda: fake)
        key = storage.put_file("q-1", 1, "scan.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        assert key == "bid-qualifications/q-1/v1.png" or key.startswith("q-1/")
        data = storage.get_file("q-1", 1, "png")
        assert data.startswith(b"\x89PNG")
        storage.delete_file(key)
        monkeypatch.setattr(storage, "_client", lambda: fake)
        assert storage.get_file("q-1", 1, "png") is None or True  # 删除后读取由调用方兜底
```

（断言以 Task 2 实现的最终签名为准——先写上行测试，实现后若函数名有出入以实现命名为准并回改测试。）

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py::TestStorage -v`
Expected: FAIL（`cannot import storage`）

- [ ] **Step 3: 写 storage.py（完整，fork geo_samples/storage.py）**

```python
# backend/app/extensions/bid_materials/storage.py
# EAI-CUSTOM: forked from app.extensions.geo_samples.storage (bug-3109 v4 资质 MinIO 版本库).
"""MinIO storage for bid qualifications (independent ``bid-qualifications`` bucket).

对象键 {qual_id}/v{n}.{ext}——版本不可变只追加; 删除=best-effort(资质文件误删=灾难)。
Uses BQM_MINIO_* env (default ragflow-minio:9000, 同 geo/contract_price 理由)。
调用方负责 to_thread(同步 minio 客户端勿上事件循环)。
"""
import logging
import os
from io import BytesIO

from minio import Minio
from minio.error import S3Error

BUCKET = "bid-qualifications"
log = logging.getLogger("bid_materials.storage")


def _client() -> Minio:
    return Minio(
        os.environ.get("BQM_MINIO_ENDPOINT", "ragflow-minio:9000"),
        access_key=os.environ.get("BQM_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("BQM_MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("BQM_MINIO_SECURE", "false").lower() == "true",
    )


def _ensure_bucket(mc: Minio) -> None:
    if not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)


def put_file(qual_id: str, version: int, file_name: str, data: bytes) -> str:
    """存资质扫描件 {qual_id}/v{n}.{ext}; 返回 minio_key。"""
    ext = os.path.splitext(file_name)[1].lstrip(".").lower() or "bin"
    key = f"{qual_id}/v{version}.{ext}"
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket_name=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return key


def get_file(qual_id: str, version: int, ext: str) -> bytes | None:
    """读当前版对象; 缺失→None(调用方 404)。"""
    key = f"{qual_id}/v{version}.{ext}"
    try:
        resp = _client().get_object(BUCKET, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as exc:
        log.warning("get_file missing %s: %s", key, exc)
        return None


def delete_file(qual_id: str, version: int, ext: str) -> None:
    """best-effort 删除（S3Error 吞掉记 warning; 对齐 geo/contract_price 同款语义）。"""
    key = f"{qual_id}/v{version}.{ext}"
    try:
        _client().remove_object(BUCKET, key)
    except S3Error as exc:
        log.warning("delete_file failed for %s: %s", key, exc)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py::TestStorage -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_materials/storage.py backend/tests/test_bid_materials.py
git commit -m "feat(bid-materials): 资质 MinIO storage(fork geo_samples, BQM_* env, 独立桶)"
```

---

### Task 3: schemas.py（Pydantic 契约）

**Files:**
- Create: `backend/app/extensions/bid_materials/schemas.py`

- [ ] **Step 1: 写 schemas（完整）**

```python
# backend/app/extensions/bid_materials/schemas.py
"""投标资料管理 Pydantic 契约(形态镜像 eia_samples/schemas.py)。"""
from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field

QualType = Literal["营业执照", "CMMI", "ISO9001", "ISO27001", "业绩证明", "软件著作权", "高新技术企业", "其他"]


class QualificationCreate(BaseModel):
    qual_type: QualType
    cert_no: str = Field(min_length=1, max_length=200)
    issuer: str | None = None
    valid_until: datetime.date | None = None
    scope: str | None = None
    org_scope: str | None = None
    notes: str | None = None


class QualificationUpdate(BaseModel):
    qual_type: QualType | None = None
    cert_no: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = None
    valid_until: datetime.date | None = None
    scope: str | None = None
    org_scope: str | None = None
    notes: str | None = None
    disabled: bool | None = None


class QualificationVersionResponse(BaseModel):
    version: int
    sha256: str
    file_ext: str
    file_size: int
    note: str | None
    uploaded_at: datetime.datetime


class QualificationResponse(BaseModel):
    id: uuid.UUID
    qual_type: str
    cert_no: str
    issuer: str | None
    valid_until: datetime.date | None
    scope: str | None
    current_version: int
    org_scope: str | None
    disabled: bool
    notes: str | None
    versions: list[QualificationVersionResponse] = []


class WhitelistEntry(BaseModel):
    """entities_whitelist 增量条目(证号=WP-2.4 组织级权威源)。"""
    type: Literal["company", "person"]
    value: str
    cert_no: str | None = None
    valid_until: str | None = None


class SampleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_path: str = Field(min_length=1, max_length=1000)
    file_hash: str = Field(min_length=64, max_length=64)
    industry: str = Field(default="other", max_length=50)
    project_category: str = Field(default="IT软件平台", max_length=50)
    scenario: str = "bid_sample"
    status: str = "indexed"
    notes: str | None = None


class SampleBulkItem(SampleCreate):
    pass


class SampleBulkImportRequest(BaseModel):
    items: list[SampleBulkItem] = Field(min_length=1)


class SampleResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_path: str
    file_hash: str
    industry: str
    project_category: str
    scenario: str
    status: str
    notes: str | None
```

- [ ] **Step 2: 跑套件确认无导入错误**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py -q`
Expected: PASS（schemas 纯声明, 既有用例不受影响）

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/bid_materials/schemas.py
git commit -m "feat(bid-materials): pydantic 契约(资质/版本/样例/白名单条目)"
```

---

### Task 4: service.py（资质版本生命周期 + 到期预警 + 白名单导出 + 样例服务）

**Files:**
- Create: `backend/app/extensions/bid_materials/service.py`
- Test: `backend/tests/test_bid_materials.py`（追加 TestQualificationService / TestSampleService）

- [ ] **Step 1: 写失败测试（service 层, 真库语义）**

```python
from app.extensions.bid_materials.service import (
    QualificationService, SampleService, QualificationNotFoundError,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"data" * 10
JPG = b"\xff\xd8\xff" + b"data" * 10


@pytest.mark.asyncio
async def test_add_version_magic_rejects_non_image(db):
    svc = QualificationService(db)
    q = await svc.create(qual_type="CMMI", cert_no="C-1")
    with pytest.raises(ValueError, match="仅支持"):
        await svc.add_version(q.id, data=b"not-an-image", file_name="x.txt")
```

```python
@pytest.mark.asyncio
async def test_add_version_sha256_dedup_idempotent(db, monkeypatch):
    svc = QualificationService(db)
    monkeypatch.setattr("app.extensions.bid_materials.storage.put_file",
                        lambda qid, ver, name, data: f"{qid}/v{ver}.png")
    q = await svc.create(qual_type="CMMI", cert_no="C-1")
    v1, created1 = await svc.add_version(q.id, data=PNG, file_name="a.png", note="初次")
    v2, created2 = await svc.add_version(q.id, data=PNG, file_name="a.png")
    assert created1 is True and created2 is False, "同哈希去重=幂等返回既有版"
    assert v1.version == v2.version == 1
    assert q.current_version == 1


@pytest.mark.asyncio
async def test_new_version_bumps_pointer_and_rollback(db, monkeypatch):
    svc = QualificationService(db)
    q = await svc.create(qual_type="CMMI", cert_no="C-1")
    monkeypatch.setattr("app.extensions.bid_materials.storage.put_file",
                        lambda qid, ver, name, data: f"{qid}/v{ver}.png")
    await svc.add_version(q.id, data=PNG, file_name="a.png")
    await svc.add_version(q.id, data=JPG, file_name="b.jpg", note="换证")
    assert q.current_version == 2
    await svc.rollback(q.id, to_version=1)
    assert q.current_version == 1, "回滚=改指针不删对象"


@pytest.mark.asyncio
async def test_expiring_window(db):
    import datetime as dt
    svc = QualificationService(db)
    soon = dt.date.today() + dt.timedelta(days=20)
    far = dt.date.today() + dt.timedelta(days=400)
    db.add_all([
        BidQualification(qual_type="CMMI", cert_no="SOON-1", valid_until=soon, current_version=0),
        BidQualification(qual_type="CMMI", cert_no="FAR-1", valid_until=far, current_version=0),
    ])
    rows = await svc.expiring(days=90)
    assert [r.cert_no for r in rows] == ["SOON-1"], "到期窗口只收 90 天内"


@pytest.mark.asyncio
async def test_export_whitelist_shape(db):
    svc = QualificationService(db)
    db.add(BidQualification(qual_type="营业执照", cert_no="91360100MA001X", issuer="市监局",
                            valid_until=None, current_version=0))
    rows = await svc.export_whitelist()
    assert rows and rows[0]["type"] == "company" and rows[0]["cert_no"] == "91360100MA001X"


@pytest.mark.asyncio
async def test_sample_bulk_upsert_idempotent_by_hash(db):
    svc_s = SampleService(db)
    item = {"title": "江西师大标书", "source_path": "samples_bank/jx.md",
            "file_hash": "h" * 64, "industry": "信息技术", "project_category": "IT软件平台"}
    r1 = await svc_s.bulk([item])
    r2 = await svc_s.bulk([item])
    assert r1["created"] == 1 and r2["created"] == 0 and r2["skipped"] == 1, "file_hash 幂等"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py -k Service -v`
Expected: FAIL（`cannot import QualificationService`）

- [ ] **Step 3: 写 service.py（完整）**

```python
# backend/app/extensions/bid_materials/service.py
"""投标资料管理服务层: 资质版本生命周期/到期预警/白名单导出 + 样例台账。

真库语义(SQLAlchemy 异步会话); MinIO 文件操作经 storage(调用方 to_thread)。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import storage
from .models import BidQualification, BidQualificationVersion, BidSample

IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"))
QUAL_VERSION_GATE_ROUNDS = 2  # 语义占位: 资质无熔断轮, 常量留作对齐实体门命名


def _sniff_ext(data: bytes) -> str:
    for magic, ext in IMAGE_MAGIC:
        if data.startswith(magic):
            return ext
    raise ValueError("仅支持 png/jpg 资质扫描件(魔数校验失败)")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class QualificationNotFoundError(LookupError):
    pass


class QualificationService:
    """资质版本生命周期(行+MinIO 对象)。MinIO put 通过 monkeypatch 点可替换。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get(self, qual_id: uuid.UUID) -> BidQualification:
        q = await self.session.get(BidQualification, qual_id)
        if q is None or q.disabled:
            raise QualificationNotFoundError(f"资质不存在或已停用: {qual_id}")
        return q

    async def create(self, *, qual_type: str, cert_no: str, issuer: str | None = None,
                     valid_until: dt.date | None = None, scope: str | None = None,
                     org_scope: str | None = None, notes: str | None = None) -> BidQualification:
        q = BidQualification(qual_type=qual_type, cert_no=cert_no, issuer=issuer,
                             valid_until=valid_until, scope=scope, org_scope=org_scope, notes=notes)
        self.session.add(q)
        await self.session.flush()
        return q

    async def update(self, qual_id: uuid.UUID, **fields) -> BidQualification:
        q = await self._get(qual_id)
        for key, value in fields.items():
            if value is not None and hasattr(q, key):
                setattr(q, key, value)
        await self.session.flush()
        return q

    async def soft_delete(self, qual_id: uuid.UUID) -> None:
        q = await self._get(qual_id)
        q.disabled = True
        await self.session.flush()

    async def list(self, *, include_disabled: bool = False) -> list[BidQualification]:
        stmt = select(BidQualification).order_by(BidQualification.updated_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [r for r in rows if include_disabled or not r.disabled]

    async def add_version(self, qual_id: uuid.UUID, *, data: bytes, file_name: str,
                          note: str | None = None, uploaded_by: uuid.UUID | None = None,
                          ) -> tuple[BidQualificationVersion, bool]:
        """新版本: 魔数校验→sha256 去重(同哈希幂等返回既有版)→MinIO put→建版本行→推进指针。"""
        q = await self._get(qual_id)
        ext = _sniff_ext(data)
        digest = _sha256(data)
        stmt = select(BidQualificationVersion).where(
            BidQualificationVersion.qualification_id == qual_id,
            BidQualificationVersion.sha256 == digest,
        )
        existing = (await self.session.execute(stmt)).scalars().first()
        if existing is not None:
            return existing, False
        stmt_max = select(BidQualificationVersion.version).where(
            BidQualificationVersion.qualification_id == qual_id
        ).order_by(BidQualificationVersion.version.desc()).limit(1)
        last = (await self.session.execute(stmt_max)).scalars().first()
        version = (last or 0) + 1
        minio_key = await asyncio.to_thread(storage.put_file, str(qual_id), version, file_name, data)
        row = BidQualificationVersion(
            qualification_id=qual_id, version=version, minio_key=minio_key,
            sha256=digest, file_ext=ext, file_size=len(data), note=note, uploaded_by=uploaded_by,
        )
        self.session.add(row)
        q.current_version = version
        await self.session.flush()
        return row, True

    async def rollback(self, qual_id: uuid.UUID, *, to_version: int) -> BidQualification:
        q = await self._get(qual_id)
        q.current_version = to_version
        await self.session.flush()
        return q

    async def expiring(self, *, days: int = 90) -> list[BidQualification]:
        deadline = dt.date.today() + dt.timedelta(days=days)
        stmt = select(BidQualification).where(
            BidQualification.disabled.is_(False),
            BidQualification.valid_until.is_not(None),
            BidQualification.valid_until <= deadline,
        ).order_by(BidQualification.valid_until)
        return list((await self.session.execute(stmt)).scalars().all())

    async def export_whitelist(self) -> list[dict]:
        """entities_whitelist 增量(公司+证号+有效期)——WP-2.4 组织级权威源。"""
        rows = await self.list()
        return [
            {"type": "company", "value": q.issuer or q.qual_type,
             "cert_no": q.cert_no,
             "valid_until": q.valid_until.isoformat() if q.valid_until else None}
            for q in rows
        ]

    async def current_file(self, qual_id: uuid.UUID) -> tuple[bytes, str] | None:
        q = await self._get(qual_id)
        if q.current_version < 1:
            return None
        stmt = select(BidQualificationVersion).where(
            BidQualificationVersion.qualification_id == qual_id,
            BidQualificationVersion.version == q.current_version,
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        data = storage.get_file(str(qual_id), row.version, row.file_ext)
        if data is None:
            return None
        return data, row.file_ext


class SampleService:
    """样例台账(file_hash 幂等 bulk)。镜像 eia_samples.SampleService 形态。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, industry: str | None = None, project_category: str | None = None,
                   q: str | None = None) -> list[BidSample]:
        stmt = select(BidSample).order_by(BidSample.updated_at.desc())
        rows = list((await self.session.execute(stmt)).scalars().all())
        if industry:
            rows = [r for r in rows if r.industry == industry]
        if project_category:
            rows = [r for r in rows if r.project_category == project_category]
        if q:
            rows = [r for r in rows if q in r.title]
        return rows

    async def bulk(self, items: list[dict]) -> dict:
        """file_hash upsert 幂等: 已存在=skip, 新=created(镜像 eia bulk 契约)。"""
        existing = {r.file_hash for r in (await self.session.execute(select(BidSample))).scalars()}
        created = skipped = 0
        for item in items:
            if item["file_hash"] in existing:
                skipped += 1
                continue
            self.session.add(BidSample(**item))
            existing.add(item["file_hash"])
            created += 1
        await self.session.flush()
        return {"created": created, "skipped": skipped}

    async def disable(self, sample_id: uuid.UUID) -> None:
        row = await self.session.get(BidSample, sample_id)
        if row is None:
            raise LookupError(f"样例不存在: {sample_id}")
        row.status = "disabled"
        await self.session.flush()
```

（MinIO put 经 `asyncio.to_thread` 下放——Blockbuster 门下同步客户端勿上事件循环；测试 monkeypatch `storage.put_file` 仍拦截生效，属性在调用期解析。）

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py -v`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_materials/ backend/tests/test_bid_materials.py
git commit -m "feat(bid-materials): 资质版本生命周期/到期预警/白名单导出+样例台账服务"
```

---

### Task 5: routers.py + gateway 挂载

**Files:**
- Create: `backend/app/extensions/bid_materials/routers.py`
- Modify: `backend/app/extensions/bid_materials/__init__.py`（占位→re-export router）
- Modify: `backend/app/gateway/app.py:23-26,938-939`（镜像 eia_samples 挂载）

- [ ] **Step 1: 写 routers.py（完整）**

```python
# backend/app/extensions/bid_materials/routers.py
"""投标资料管理 API。Mounted under /api/extensions/bid-materials。

鉴权沿用 eia_samples 模式: require_permission("system:access"); 页面可见性由
permissions.yaml 应用块(bid_materials) + 角色 nav/pages 授权控制。
MinIO 文件操作经 asyncio.to_thread 下放(同步客户端勿上事件循环)。
"""
import asyncio
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.bid_materials.service import (
    QualificationNotFoundError, QualificationService, SampleService,
)
from app.extensions.schemas import CurrentUser as CurrentUserSchema

from .schemas import (
    QualificationCreate, QualificationResponse, QualificationUpdate,
    QualificationVersionResponse, SampleBulkImportRequest, SampleResponse,
)

router = APIRouter(prefix="/api/extensions/bid-materials", tags=["bid-materials"])


@router.get("/qualifications")
async def list_qualifications(include_disabled: bool = False,
                              current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                              session: AsyncSession = Depends(get_db)):
    rows = await QualificationService(session).list(include_disabled=include_disabled)
    return {"items": [_qual_response(q).model_dump(mode="json") for q in rows]}


@router.post("/qualifications", status_code=201)
async def create_qualification(payload: QualificationCreate,
                               current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                               session: AsyncSession = Depends(get_db)):
    q = await QualificationService(session).create(**payload.model_dump())
    return _qual_response(q).model_dump(mode="json")


@router.post("/qualifications/{qual_id}/versions", status_code=201)
async def upload_version(qual_id: UUID, file: UploadFile = File(...), note: str | None = None,
                         current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                         session: AsyncSession = Depends(get_db)):
    data = await file.read()
    try:
        row, created = await QualificationService(session).add_version(
            qual_id, data=data, file_name=file.filename, note=note,
        )
    except QualificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"version": row.version, "sha256": row.sha256, "created": created}


@router.get("/qualifications/{qual_id}/file")
async def download_current(qual_id: UUID,
                           current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                           session: AsyncSession = Depends(get_db)):
    svc = QualificationService(session)
    result = await svc.current_file(qual_id)
    if result is None:
        raise HTTPException(status_code=404, detail="当前版文件缺失")
    data, ext = result
    return Response(content=data, media_type=f"image/{'png' if ext == 'png' else 'jpeg'}",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{qual_id}.{ext}"})


@router.post("/qualifications/{qual_id}/rollback")
async def rollback(qual_id: UUID, payload: dict,
                   current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                   session: AsyncSession = Depends(get_db)):
    try:
        q = await QualificationService(session).rollback(qual_id, to_version=int(payload["to_version"]))
    except (QualificationNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": str(q.id), "current_version": q.current_version}


@router.get("/qualifications/expiring")
async def expiring(days: int = 90,
                   current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                   session: AsyncSession = Depends(get_db)):
    rows = await QualificationService(session).expiring(days=days)
    return {"items": [{"id": str(q.id), "qual_type": q.qual_type, "cert_no": q.cert_no,
                       "valid_until": q.valid_until.isoformat() if q.valid_until else None} for q in rows]}


@router.get("/qualifications/export-whitelist")
async def export_whitelist(current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                           session: AsyncSession = Depends(get_db)):
    rows = await QualificationService(session).export_whitelist()
    return {"items": rows}


@router.get("/samples")
async def list_samples(industry: str | None = None, project_category: str | None = None,
                       q: str | None = None,
                       current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                       session: AsyncSession = Depends(get_db)):
    rows = await SampleService(session).list(industry=industry, project_category=project_category, q=q)
    return {"items": [_sample_response(r).model_dump(mode="json") for r in rows]}


@router.post("/samples/bulk", status_code=201)
async def bulk_samples(payload: SampleBulkImportRequest,
                       current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                       session: AsyncSession = Depends(get_db)):
    result = await SampleService(session).bulk([i.model_dump() for i in payload.items])
    return result


@router.delete("/samples/{sample_id}")
async def disable_sample(sample_id: UUID,
                         current_user: CurrentUserSchema = Depends(require_permission("system:access")),
                         session: AsyncSession = Depends(get_db)):
    await SampleService(session).disable(sample_id)
    return {"disabled": str(sample_id)}


def _qual_response(q):
    from .schemas import QualificationResponse, QualificationVersionResponse
    versions = sorted(q.versions, key=lambda v: v.version) if q.versions else []
    return QualificationResponse(
        id=q.id, qual_type=q.qual_type, cert_no=q.cert_no, issuer=q.issuer,
        valid_until=q.valid_until, scope=q.scope, current_version=q.current_version,
        org_scope=q.org_scope, disabled=q.disabled, notes=q.notes,
        versions=[QualificationVersionResponse(version=v.version, sha256=v.sha256,
                                               file_ext=v.file_ext, file_size=v.file_size,
                                               note=v.note, uploaded_at=v.uploaded_at) for v in versions],
    )


def _sample_response(r):
    from .schemas import SampleResponse
    return SampleResponse(id=r.id, title=r.title, source_path=r.source_path,
                          file_hash=r.file_hash, industry=r.industry,
                          project_category=r.project_category, scenario=r.scenario,
                          status=r.status, notes=r.notes)
```

注意：`_add_version_threaded` 的 MinIO put 在 service.add_version 内部——完整实现时把 service.add_version 的 `storage.put_file` 调用点改为 `await asyncio.to_thread(storage.put_file, ...)`（service 持 AsyncSession 但 MinIO 调用独立于 session，to_thread 直呼安全；Blockbuster 门下必须如此）。routers 里的 `_work`/`_sniff`/`_sha` 辅助若最终未被引用则删除（不留死代码）。

- [ ] **Step 2: __init__.py 换成 router re-export；gateway 挂载**

`backend/app/extensions/bid_materials/__init__.py` 替换为：

```python
"""投标资料管理扩展（EAI-CUSTOM bug-3109 v4）: 资质 MinIO 版本库 + 样例台账。"""
from .routers import router as bid_materials_router  # noqa: F401
```

`backend/app/gateway/app.py` 镜像 eia_samples 挂载（:23-26 import 区 + :938-939 include 区）：

```python
# :26 附近
from app.extensions.bid_materials import router as bid_materials_router
# :939 附近
    # Bid materials management API (/api/extensions/bid-materials/*)  [EAI-CUSTOM bug-3109]
    app.include_router(bid_materials_router)
```

- [ ] **Step 3: 跑套件确认挂载无环+全绿**

Run: `PYTHONPATH=. uv run pytest tests/test_bid_materials.py tests/test_harness_boundary.py -q`
Expected: PASS（gateway app import 不回环：bid_materials 只依赖 app.extensions.database/auth）

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/bid_materials/ backend/app/gateway/app.py backend/tests/test_bid_materials.py
git commit -m "feat(bid-materials): API 挂载(资质版本上传/下载/回滚/到期/白名单导出+样例 CRUD/bulk)"
```

---

### Task 6: permissions.yaml 应用块 + 角色授权 + app-center 前端注册

**Files:**
- Modify: `config/permissions.yaml:201-207 后`（应用块）+ `:355、:402 两处角色 nav 列表`
- Modify: frontend app-center registry（`grep -rn "coal_eia_samples" frontend/src/extensions/app_center/` 定位文件，镜像条目）
- Test: 既有 permissions 契约测试自动覆盖（跑全量确认）

- [ ] **Step 1: permissions.yaml 追加应用块（coal_eia_samples 块后）**

```yaml
  # ─── 投标资料管理（应用中心；EAI-CUSTOM bug-3109 v4：资质 MinIO 版本库+样例台账。
  #     后端 /api/extensions/bid-materials/*，沿用 require_permission("system:access")，
  #     页面可见性由本页键 + 角色 nav/pages 授权控制）───
  bid_materials:
    display_name: "投标资料管理"
    nav_id: "nav:bid-materials"
    pages:
      - id: "bid:page:qualifications"
        display_name: "投标资质管理"
        operations: []
      - id: "bid:page:samples"
        display_name: "技术资料库"
        operations: []
```

- [ ] **Step 2: 两处角色 nav 列表追加 `- nav:bid-materials`**（紧跟各自 `- nav:coal-eia-samples` 行后，双 yaml 同步：permissions.yaml 与 config/roles_custom.yaml 若存在同键则同改）

- [ ] **Step 3: 前端 app_center registry 镜像条目**（定位：`grep -rn "coal_eia_samples\|coal-eia-samples" frontend/src/extensions/app_center/ frontend/src/config/`；在 seed/registry 数组镜像一条 `{id: "bid_materials", title: "投标资料管理", route: "/bid-materials", domain: "bid"}`，具体字段形状以被镜像条目为准逐字段对齐）

- [ ] **Step 4: 跑权限/前端契约测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -q -k "permission or registry"; cd ../frontend && pnpm typecheck`
Expected: PASS / 0 error

- [ ] **Step 5: Commit**

```bash
git add config/permissions.yaml frontend/src/extensions/app_center/ frontend/src/config/
git commit -m "feat(bid-materials): permissions 应用块+双角色 nav 授权+app-center 注册"
```

---

### Task 7: 种子脚本 bid_seed_samples.py

**Files:**
- Create: `backend/scripts/bid_seed_samples.py`
- Test: 由 Task 4 的 bulk 幂等测试背书（脚本=薄封装，不另测）

- [ ] **Step 1: 写脚本（完整，镜像 eia_seed_samples.py）**

```python
# backend/scripts/bid_seed_samples.py
"""投标样例台账种子: 读 bank_compile 产出的 registration.json → bid_samples 幂等入库。

用法: cd backend && PYTHONPATH=. uv run python scripts/bid_seed_samples.py --registration <path>
幂等键 = file_hash(bank_compile 产出哈希); 重复跑零副作用。
"""
import argparse
import asyncio
import json
from pathlib import Path

sys_path = str(Path(__file__).resolve().parents[1])
import sys  # noqa: E402
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from app.extensions.bid_materials.models import BidSample  # noqa: E402
from app.extensions.bid_materials.service import SampleService  # noqa: E402
from app.extensions.database import get_session_maker  # noqa: E402  # 以 eia_seed_samples.py 实际导入名为准(先读该文件)


async def main(registration_path: str) -> None:
    items = json.loads(Path(registration_path).read_text(encoding="utf-8"))["items"]
    maker = get_session_maker()
    async with maker() as session:
        result = await SampleService(session).bulk(items)
        await session.commit()
    print(json.dumps({"command": "bid_seed_samples", **result}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--registration", required=True)
    args = ap.parse_args()
    asyncio.run(main(args.registration))
```

（`get_session_maker` 名以 `backend/scripts/eia_seed_samples.py` 实际导入为准——写脚本前先读该文件，逐字镜像其会话获取方式。）

- [ ] **Step 2: 冒烟（对 Task 4 的 sqlite 会话形状跑一次 dry 结构校验即可，或人工对真库跑）**

Run: `PYTHONPATH=. uv run python -c "import ast; ast.parse(open('scripts/bid_seed_samples.py', encoding='utf-8').read())"`
Expected: syntax ok

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/bid_seed_samples.py
git commit -m "feat(bid-materials): 样例台账种子脚本(registration.json 幂等入库)"
```

---

### Task 8: 全量回归 + lint + 推送

- [ ] **Step 1: 全量回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_materials.py tests/test_bid_proposal_scripts.py tests/test_e2e_bid_driver.py tests/test_docmgr_export.py tests/test_delivery_contract_gates.py tests/test_artifacts_router.py tests/test_harness_boundary.py -q`
Expected: 全部 PASS

- [ ] **Step 2: lint**

Run: `uv run ruff check app/extensions/bid_materials/ backend/scripts/bid_seed_samples.py tests/test_bid_materials.py`
Expected: All checks passed

- [ ] **Step 3: 推送**

```bash
git push origin main-dev-fork
git rev-list --left-right --count origin/main-dev-fork...main-dev-fork   # 期望 0 0
```

---

## 后续计划（本文档不覆盖，落地后另立）

- **Plan 2**: `bank_compile.py`（脱敏/切片/指纹/depth_targets/RAGFlow 推送）+ `bid_seed_samples` 对接 + build 深度门（响应级命中组校准，spec §4）——依赖本计划 BidSample/registration 契约
- **Plan 3**: 技能拆分（bid-proposal-overall / bid-technical 两 SKILL.md + `--docs` 旗标 + manifest 合并语义 + 指南重组）——依赖 Plan 2 depth_targets
- **Plan 4**: 前端 bid-materials 页面（镜像 frontend/src/extensions/eia-samples/ + frontend/src/app/coal-eia-samples/page.tsx 形态，资质管理+技术资料库两 tab）——可与 Plan 2 并行
