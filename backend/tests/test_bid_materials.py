"""投标资料管理 bid_materials：资质 MinIO 版本库 + 样例台账测试。

真库语义（sqlite+aiosqlite 内存库 + 真实模型），镜像 test_eia_samples.py 夹具。
"""

import datetime as dt
import io
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from minio.error import S3Error
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.extensions.models  # noqa: F401  — 注册 users 等表进共享 Base.metadata 供 FK 解析（只 import，不建表）
from app.extensions.bid_materials.models import (
    BidQualification,
    BidQualificationVersion,
    BidSample,
)
from app.extensions.bid_materials.service import (
    QualificationNotFoundError,
    QualificationService,
    SampleNotFoundError,
    SampleService,
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


class _FakeResp(io.BytesIO):
    """BytesIO + release_conn：真实 minio get_object 返回 urllib3 response，
    storage 层 finally 里会调 close()+release_conn() 两方法，替身须齐备。"""

    def release_conn(self):
        pass


class FakeObjectStore:
    """内存 Minio 替身: 记录 put, 支持 get/remove + buckets 集合。"""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.buckets: set[str] = set()  # 初始为空: put_file 会真走一遍 exists=False→make_bucket 路径

    def put_object(self, bucket_name, object_name, data, length):
        self.objects[object_name] = data.read()

    def get_object(self, bucket_name, object_name):
        if object_name not in self.objects:
            from minio.error import S3Error

            # minio 7.x S3Error 首位参数是 response; request_id/host_id 显式补空串, 跨 7.x 版本稳
            raise S3Error(
                response=None,
                code="NoSuchKey",
                message="missing",
                resource=object_name,
                request_id="",
                host_id="",
            )
        return _FakeResp(self.objects[object_name])

    def remove_object(self, bucket_name, object_name):
        self.objects.pop(object_name, None)

    def bucket_exists(self, bucket_name):
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name):
        self.buckets.add(bucket_name)


class TestStorage:
    def test_put_get_roundtrip_and_delete(self, monkeypatch):
        from app.extensions.bid_materials import storage

        fake = FakeObjectStore()
        monkeypatch.setattr(storage, "_client", lambda: fake)
        payload = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        key = storage.put_file("q-1", 1, "png", payload)
        assert key == "q-1/v1.png"
        # I-1 防御层: ext 由调用方(魔数嗅探)传入, storage 仍清洗到 [a-z0-9]≤9——脏 ext 不产出越界键
        assert storage.put_file("q-1", 2, "P N G!.jpeg", b"x") == "q-1/v2.pngjpeg"
        assert fake.buckets == {"bid-qualifications"}  # _ensure_bucket 真走了一遍建桶
        assert storage.get_file("q-1", 1, "png") == payload  # 全等: 捕获截断/编码错误
        storage.delete_file("q-1", 1, "png")
        # best-effort 删除真落了：替身对象表里键已移除
        assert "q-1/v1.png" not in fake.objects
        # 缺失对象: get_object 抛 NoSuchKey → get_file 收敛为 None(404)——固定缩小后的 except
        assert storage.get_file("q-1", 9, "png") is None

    def test_get_file_reraises_non_missing_s3error(self, monkeypatch):
        from app.extensions.bid_materials import storage

        class DenyStore(FakeObjectStore):
            def get_object(self, bucket_name, object_name):
                raise S3Error(
                    response=None,
                    code="AccessDenied",
                    message="denied",
                    resource=object_name,
                    request_id="",
                    host_id="",
                )

        monkeypatch.setattr(storage, "_client", lambda: DenyStore())
        # AccessDenied 不收敛 None → 原样上抛: 缩窄 except 的另一半分支（基础设施故障≠404）
        with pytest.raises(S3Error):
            storage.get_file("q-1", 1, "png")


PNG = b"\x89PNG\r\n\x1a\n" + b"data" * 10
JPG = b"\xff\xd8\xff" + b"data" * 10


class TestQualificationService:
    @pytest.mark.asyncio
    async def test_add_version_magic_rejects_non_image(self, db):
        svc = QualificationService(db)
        q = await svc.create(qual_type="CMMI", cert_no="C-1")
        with pytest.raises(ValueError, match="仅支持"):
            await svc.add_version(q.id, data=b"not-an-image")

    @pytest.mark.asyncio
    async def test_unknown_qual_id_raises_not_found(self, db):
        svc = QualificationService(db)
        with pytest.raises(QualificationNotFoundError):
            await svc.add_version(uuid.uuid4(), data=PNG)

    @pytest.mark.asyncio
    async def test_add_version_sha256_dedup_idempotent(self, db, monkeypatch):
        svc = QualificationService(db)
        monkeypatch.setattr("app.extensions.bid_materials.storage.put_file", lambda qid, ver, ext, data: f"{qid}/v{ver}.{ext}")
        q = await svc.create(qual_type="CMMI", cert_no="C-1")
        v1, created1 = await svc.add_version(q.id, data=PNG, note="初次")
        v2, created2 = await svc.add_version(q.id, data=PNG)
        assert created1 is True and created2 is False, "同哈希去重=幂等返回既有版"
        assert v1.version == v2.version == 1
        assert q.current_version == 1
        # I-1: put 键 ext 与 DB file_ext 同源(均为魔数嗅探结果)——minio_key↔file_ext 一致性钉死
        assert v1.minio_key == f"{q.id}/v1.{v1.file_ext}"

    @pytest.mark.asyncio
    async def test_new_version_bumps_pointer_and_rollback(self, db, monkeypatch):
        svc = QualificationService(db)
        q = await svc.create(qual_type="CMMI", cert_no="C-1")
        monkeypatch.setattr("app.extensions.bid_materials.storage.put_file", lambda qid, ver, ext, data: f"{qid}/v{ver}.{ext}")
        await svc.add_version(q.id, data=PNG)
        v2, _ = await svc.add_version(q.id, data=JPG, note="换证")
        assert q.current_version == 2
        assert v2.minio_key == f"{q.id}/v2.{v2.file_ext}"
        await svc.rollback(q.id, to_version=1)
        assert q.current_version == 1, "回滚=改指针不删对象"

    @pytest.mark.asyncio
    async def test_rollback_to_missing_version_raises(self, db):
        """I-2: 幽灵版本号(0/负数/超界)不许静默改指针——指针悬空=下载永久404。"""
        svc = QualificationService(db)
        q = await svc.create(qual_type="CMMI", cert_no="C-1")
        for ghost in (0, -1, 99):
            with pytest.raises(QualificationNotFoundError):
                await svc.rollback(q.id, to_version=ghost)
        assert q.current_version == 0, "失败的回滚不得动指针"

    @pytest.mark.asyncio
    async def test_update_whitelist_and_none_semantics(self, db):
        """M-1: update 白名单——未知键(含拼错/id/created_at) raise 不静默; None=不清空, 清空走显式路径。"""
        svc = QualificationService(db)
        q = await svc.create(qual_type="CMMI", cert_no="C-1", issuer="原发证机构")
        with pytest.raises(ValueError, match="不可更新"):
            await svc.update(q.id, created_at="2020-01-01")
        with pytest.raises(ValueError, match="不可更新"):
            await svc.update(q.id, issuer_new="typo")
        updated = await svc.update(q.id, issuer=None, notes="补充说明")
        assert updated.issuer == "原发证机构", "None=不清空"
        assert updated.notes == "补充说明"

    @pytest.mark.asyncio
    async def test_expiring_window(self, db):
        import datetime as dt

        svc = QualificationService(db)
        soon = dt.date.today() + dt.timedelta(days=20)
        far = dt.date.today() + dt.timedelta(days=400)
        db.add_all(
            [
                BidQualification(qual_type="CMMI", cert_no="SOON-1", valid_until=soon, current_version=0),
                BidQualification(qual_type="CMMI", cert_no="FAR-1", valid_until=far, current_version=0),
            ]
        )
        rows = await svc.expiring(days=90)
        assert [r.cert_no for r in rows] == ["SOON-1"], "到期窗口只收 90 天内"

    @pytest.mark.asyncio
    async def test_export_whitelist_shape(self, db):
        svc = QualificationService(db)
        db.add(BidQualification(qual_type="营业执照", cert_no="91360100MA001X", issuer="市监局", valid_until=None, current_version=0))
        rows = await svc.export_whitelist()
        assert rows and rows[0]["type"] == "company" and rows[0]["cert_no"] == "91360100MA001X"

    @pytest.mark.asyncio
    async def test_list_excludes_disabled_with_paging(self, db):
        svc = QualificationService(db)
        await svc.create(qual_type="CMMI", cert_no="LIVE-1")
        dead = await svc.create(qual_type="CMMI", cert_no="DEAD-1")
        await svc.soft_delete(dead.id)
        rows = await svc.list()
        assert [r.cert_no for r in rows] == ["LIVE-1"], "软删行默认不可见(SQL 下推)"
        assert len(await svc.list(include_disabled=True)) == 2
        assert len(await svc.list(limit=1)) == 1


class TestSampleService:
    @pytest.mark.asyncio
    async def test_sample_bulk_upsert_idempotent_by_hash(self, db):
        svc_s = SampleService(db)
        item = {"title": "江西师大标书", "source_path": "samples_bank/jx.md", "file_hash": "h" * 64, "industry": "信息技术", "project_category": "IT软件平台"}
        items = [item]
        r1 = await svc_s.bulk(items)
        r2 = await svc_s.bulk(items)
        assert r1["created"] == 1 and r2["created"] == 0 and r2["skipped"] == 1, "file_hash 幂等"
        # M-5 遗留: bulk 响应恒等式——skipped == total - created（total=len(items)），两轮各自闭合
        assert r1["skipped"] == len(items) - r1["created"] == 0
        assert r2["skipped"] == len(items) - r2["created"] == 1

    @pytest.mark.asyncio
    async def test_get_returns_row_and_missing_raises(self, db):
        """详情走 service.get：命中返行, 缺失 raise SampleNotFoundError(路由 404 同源)。"""
        svc_s = SampleService(db)
        await svc_s.bulk([{"title": "t", "source_path": "p", "file_hash": "e" * 64}])
        row = (await svc_s.list())[0]
        assert (await svc_s.get(row.id)).id == row.id
        with pytest.raises(SampleNotFoundError):
            await svc_s.get(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_disable_sets_status_and_missing_raises(self, db):
        svc_s = SampleService(db)
        await svc_s.bulk([{"title": "t", "source_path": "p", "file_hash": "a" * 64}])
        rows = await svc_s.list()
        await svc_s.disable(rows[0].id)
        assert rows[0].status == "disabled"
        with pytest.raises(SampleNotFoundError):
            await svc_s.disable(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_filters_pushed_down_with_paging(self, db):
        """M-3: 过滤下推 SQL(==/ilike) + limit/offset 分页(Task 5 路由接入)。"""
        svc_s = SampleService(db)
        await svc_s.bulk(
            [
                {"title": "江西师大标书", "source_path": "p1", "file_hash": "b" * 64, "industry": "信息技术", "project_category": "IT软件平台"},
                {"title": "煤矿环评标书", "source_path": "p2", "file_hash": "c" * 64, "industry": "环保", "project_category": "环评"},
                {"title": "江西煤矿标书", "source_path": "p3", "file_hash": "d" * 64, "industry": "环保", "project_category": "IT软件平台"},
            ]
        )
        assert len(await svc_s.list(industry="环保")) == 2
        assert len(await svc_s.list(industry="环保", project_category="IT软件平台")) == 1
        assert {r.title for r in await svc_s.list(q="煤矿")} == {"煤矿环评标书", "江西煤矿标书"}
        assert len(await svc_s.list(limit=1, offset=1)) == 1


BASE = "/api/extensions/bid-materials"


class TestBidMaterialsRoutes:
    """路由层测试（闭合 spec §6 权限挂载）: 只挂 bid_materials router 的最小 app + dependency_overrides。

    - get_db → 本文件 sqlite 夹具 session（真库语义）；
    - 权限依赖 → 覆盖 routers._require_system_access（命名收口: require_permission 工厂每次
      调用产新闭包, 匿名形态无法按对象同一性 override）——放行给 SimpleNamespace 形状用户,
      拒绝场景 raise HTTPException(403) 镜像真中间件 deny 路径。
    - 走 httpx ASGITransport（test_data_source_routers.py 先例）而非 TestClient: db 是 async
      夹具 session, TestClient 的 portal 线程会把 session 拽进另一个事件循环。
    """

    @pytest_asyncio.fixture()
    async def client(self, db):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.extensions.bid_materials import routers as bid_routers
        from app.extensions.database import get_db

        app = FastAPI()
        app.include_router(bid_routers.router)

        async def _fake_db():
            yield db

        async def _allow():
            return SimpleNamespace(id=uuid.uuid4())  # 路由只读 current_user.id

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[bid_routers._require_system_access] = _allow
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    async def _seed_qual(self, db: AsyncSession, cert_no: str = "CMMI-2024-001") -> BidQualification:
        q = BidQualification(qual_type="CMMI", cert_no=cert_no, issuer="CMMI Institute")
        db.add(q)
        await db.flush()
        return q

    @pytest.mark.asyncio
    async def test_get_detail_404_when_missing(self, client):
        resp = await client.get(f"{BASE}/qualifications/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_detail_returns_row(self, client, db):
        q = await self._seed_qual(db)
        resp = await client.get(f"{BASE}/qualifications/{q.id}")
        assert resp.status_code == 200
        assert resp.json()["cert_no"] == "CMMI-2024-001"

    @pytest.mark.asyncio
    async def test_fixed_paths_not_shadowed_by_qual_id(self, client, db):
        """路由顺序: 单段 {qual_id} 不得遮蔽 /expiring 与 /export-whitelist（FastAPI 按声明顺序匹配）。"""
        db.add(BidQualification(qual_type="CMMI", cert_no="EXP-1", valid_until=dt.date.today() + dt.timedelta(days=10)))
        await db.flush()
        resp = await client.get(f"{BASE}/qualifications/expiring")
        assert resp.status_code == 200
        assert [r["cert_no"] for r in resp.json()] == ["EXP-1"]
        resp = await client.get(f"{BASE}/qualifications/export-whitelist")
        assert resp.status_code == 200
        assert resp.json()[0]["cert_no"] == "EXP-1"

    @pytest.mark.asyncio
    async def test_patch_updates_cert_no_and_persists(self, client, db):
        q = await self._seed_qual(db)
        qual_id = q.id  # expire_all 后过期实例的属性访问会触发同步 lazy load(MissingGreenlet), 先取值
        resp = await client.patch(f"{BASE}/qualifications/{qual_id}", json={"cert_no": "CMMI-2026-999"})
        assert resp.status_code == 200
        assert resp.json()["cert_no"] == "CMMI-2026-999"
        db.expire_all()  # 丢身份映射缓存, 真读库验证落库
        assert (await db.get(BidQualification, qual_id)).cert_no == "CMMI-2026-999"

    @pytest.mark.asyncio
    async def test_patch_missing_qual_404(self, client):
        resp = await client.patch(f"{BASE}/qualifications/{uuid.uuid4()}", json={"cert_no": "x"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_out_of_whitelist_field_400(self, client, db):
        """disabled 不在 service 白名单（软删走 DELETE 显式路径）→ 400 而非静默放行。"""
        q = await self._seed_qual(db)
        resp = await client.patch(f"{BASE}/qualifications/{q.id}", json={"disabled": True})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_soft_disables_and_hidden(self, client, db):
        q = await self._seed_qual(db)
        qual_id, cert_no = q.id, q.cert_no  # expire_all 后过期实例属性访问会同步 lazy load, 先取值
        resp = await client.delete(f"{BASE}/qualifications/{qual_id}")
        assert resp.status_code == 200
        assert resp.json() == {"disabled": True}
        db.expire_all()
        assert (await db.get(BidQualification, qual_id)).disabled is True
        assert (await client.get(f"{BASE}/qualifications/{qual_id}")).status_code == 404, "详情对停用行 404"
        listing = await client.get(f"{BASE}/qualifications")
        assert all(r["cert_no"] != cert_no for r in listing.json()), "列表默认滤软删行"

    @pytest.mark.asyncio
    async def test_delete_missing_qual_404(self, client):
        resp = await client.delete(f"{BASE}/qualifications/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_versions_listed_ascending(self, client, db, monkeypatch):
        from app.extensions.bid_materials import storage

        monkeypatch.setattr(storage, "put_file", lambda qid, ver, ext, data: f"{qid}/v{ver}.{ext}")
        q = await self._seed_qual(db)
        r1 = await client.post(f"{BASE}/qualifications/{q.id}/versions", files={"file": ("a.png", PNG, "image/png")}, data={"note": "初版"})
        assert r1.status_code == 201, "版本上传与 POST /qualifications 同一 201 先例"
        r2 = await client.post(f"{BASE}/qualifications/{q.id}/versions", files={"file": ("b.jpg", JPG, "image/jpeg")})
        assert r2.status_code == 201
        assert r2.json()["version"] == 2
        resp = await client.get(f"{BASE}/qualifications/{q.id}/versions")
        assert resp.status_code == 200
        rows = resp.json()
        assert [v["version"] for v in rows] == [1, 2], "升序"
        assert [v["file_ext"] for v in rows] == ["png", "jpg"]
        assert rows[0]["note"] == "初版" and rows[0]["minio_key"].endswith("v1.png")

    @pytest.mark.asyncio
    async def test_versions_missing_qual_404(self, client):
        resp = await client.get(f"{BASE}/qualifications/{uuid.uuid4()}/versions")
        assert resp.status_code == 404

    @staticmethod
    def _fake_object_store(monkeypatch) -> dict[str, bytes]:
        """下载测试替身: put/get 全内存键值（真 MinIO 不可达）——镜像 test_versions_listed_ascending
        的 storage 模块属性 monkeypatch 模式; service 经 asyncio.to_thread(storage.get_file, ...)
        调用, 属性运行期解析, 替换生效。"""
        from app.extensions.bid_materials import storage

        store: dict[str, bytes] = {}

        def _put(qid, ver, ext, data):
            key = f"{qid}/v{ver}.{ext}"
            store[key] = data
            return key

        def _get(qid, ver, ext):
            return store.get(f"{qid}/v{ver}.{ext}")

        monkeypatch.setattr(storage, "put_file", _put)
        monkeypatch.setattr(storage, "get_file", _get)
        return store

    async def _seed_two_versions(self, client, db):
        """上传两版(内容不同: v1=png, v2=jpg) → 当前版已推进到 v2。"""
        q = await self._seed_qual(db)
        r1 = await client.post(f"{BASE}/qualifications/{q.id}/versions", files={"file": ("a.png", PNG, "image/png")})
        assert r1.status_code == 201 and r1.json()["version"] == 1
        r2 = await client.post(f"{BASE}/qualifications/{q.id}/versions", files={"file": ("b.jpg", JPG, "image/jpeg")})
        assert r2.status_code == 201 and r2.json()["version"] == 2, "前置: 当前版已推进到 v2"
        return q

    @pytest.mark.asyncio
    async def test_file_download_serves_current_version_by_default(self, client, db, monkeypatch):
        """GET /file 缺省=当前版（spec §2.3「默认当前版」）——?version= 落地后原语义不得漂移。"""
        self._fake_object_store(monkeypatch)
        q = await self._seed_two_versions(client, db)
        resp = await client.get(f"{BASE}/qualifications/{q.id}/file")
        assert resp.status_code == 200
        assert resp.content == JPG, "缺省下发当前版(v2)字节"
        assert resp.headers["content-type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_file_download_per_version(self, client, db, monkeypatch):
        """spec §2.3 ?version=n 按版本下发（前端 Plan 4 版本行预览）: 当前已 v2, ?version=1 取回首版字节。"""
        self._fake_object_store(monkeypatch)
        q = await self._seed_two_versions(client, db)
        resp = await client.get(f"{BASE}/qualifications/{q.id}/file", params={"version": 1})
        assert resp.status_code == 200
        assert resp.content == PNG, "指定 v1 → 首版字节(非当前版)"
        assert resp.headers["content-type"] == "image/png"

    @pytest.mark.asyncio
    async def test_file_download_unknown_version_404(self, client, db, monkeypatch):
        """幽灵版本号 → 404「指定版本不存在: v{n}」（与 rollback 幽灵版本同语义; 0/负数不 422 也走存在性校验）。"""
        self._fake_object_store(monkeypatch)
        q = await self._seed_two_versions(client, db)
        resp = await client.get(f"{BASE}/qualifications/{q.id}/file", params={"version": 99})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "指定版本不存在: v99"
        resp0 = await client.get(f"{BASE}/qualifications/{q.id}/file", params={"version": 0})
        assert resp0.status_code == 404
        # 资质不存在 + version 参数 → 同 _get 同源 404（不因带版本绕过存在性校验）
        resp_missing = await client.get(f"{BASE}/qualifications/{uuid.uuid4()}/file", params={"version": 1})
        assert resp_missing.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_rejects_non_image_400(self, client, db):
        q = await self._seed_qual(db)
        resp = await client.post(f"{BASE}/qualifications/{q.id}/versions", files={"file": ("x.txt", b"not-an-image", "text/plain")})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_qualifications_filters_by_qual_type(self, client, db):
        await self._seed_qual(db, cert_no="CMMI-1")
        db.add(BidQualification(qual_type="ISO9001", cert_no="ISO-1"))
        await db.flush()
        resp = await client.get(f"{BASE}/qualifications", params={"qual_type": "ISO9001"})
        assert resp.status_code == 200
        assert [r["cert_no"] for r in resp.json()] == ["ISO-1"]

    @pytest.mark.asyncio
    async def test_permission_deny_403(self, db):
        """权限挂载断言: require_permission 依赖覆盖为拒绝 → 403（路由确实挂在权限链上）。"""
        from fastapi import FastAPI, HTTPException
        from httpx import ASGITransport, AsyncClient

        from app.extensions.bid_materials import routers as bid_routers
        from app.extensions.database import get_db

        app = FastAPI()
        app.include_router(bid_routers.router)

        async def _fake_db():
            yield db

        async def _deny():
            raise HTTPException(status_code=403, detail="no permission")

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[bid_routers._require_system_access] = _deny
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"{BASE}/qualifications")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# bid-proposal-overall 深度门(Plan2 Task 6): depth_target 字段贯通 + build 深度门。
# 技能脚本非本扩展代码——经 conftest._SkillScriptsFinder 同名脚本隔离加载(build_output
# 三个技能同名), 模块级 SCRIPTS_DIR 是隔离锚, 勿删; 技能模块一律在用例内懒加载。
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "skills" / "public" / "bid-proposal-overall" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _responses_module():
    import responses  # 技能平铺脚本(单名无冲突: responses 仅本技能有, pip responses 未安装)

    return responses


def _build_module():
    import importlib

    return importlib.import_module("build_output")  # 经 finder 解析到本技能 scripts(三技能同名)


def _cjk_text(n: int) -> str:
    """纯 CJK 文本——剥空白/标点后实质长 == len, 深度门输入可精确控制。"""
    return ("系统采用模块化架构支持远程诊断与全生命周期运维保障" * 100)[:n]


def _depth_clause(clause_id="ZB-C-001", **over):
    clause = {
        "clause_id": clause_id,
        "source_file": "招标文件.md",
        "class": "normal",
        "category": "technical",
        "source_ref": {"page": 1, "section": "技术要求", "para": 1, "quote": "系统须支持远程诊断"},
        "requirement": "系统须支持远程诊断与运维",
        "response_status": "compliant",
        "response_skeleton": {"points": [], "evidence_ref": None, "suggestion": None},
        "from_addendum": False,
        "superseded_by": None,
        "voided": False,
    }
    clause.update(over)
    return clause


def _depth_node(node_id, path, volume, linked=None):
    return {
        "node_id": node_id,
        "volume": volume,
        "path": path,
        "slot_type": "text",
        "required_format": {"desc": None, "table_spec": None, "template_text": None},
        "linked_clause_ids": list(linked or []),
    }


def _write_bytes(path: Path, obj) -> None:
    """write_bytes 强制 LF(对齐 test_bid_proposal_scripts._copy_prestate: Windows write_text 会翻 CRLF)。"""
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _write_text_raw(path: Path, text: str) -> None:
    """原样字节落盘(不 JSON 编码)——构造损坏基线文件用。"""
    path.write_bytes(text.encode("utf-8"))


def _depth_state(tmp_path, responses=None):
    """最小可构建状态: 一技术条款挂一技术节点 + 一商务节点(两卷章分组非空)。

    权威件直写后走真签名(state_guard: build/merge 是消费者角色, 读盘前复核签名——
    直写不签会被"在盘未登记=注入"拦截; 生产语义不 monkeypatch, 登记即过)。
    """
    import state_guard

    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    structure = [
        _depth_node("S-001", "第一章 投标函（格式）", "commercial"),
        _depth_node("S-002", "第三章 技术方案/1 总体方案", "technical", linked=["ZB-C-001"]),
    ]
    _write_bytes(state / "clauses.json", [_depth_clause("ZB-C-001")])
    _write_bytes(state / "structure.json", structure)
    _write_bytes(state / "entities_whitelist.json", {"locked_at": None, "source": "test", "entities": []})
    signed = ["clauses.json", "structure.json"]
    if responses is not None:
        _write_bytes(state / "responses.json", responses)
        signed.append("responses.json")
    state_guard.sign_state_files(state, signed)
    return state


def _depth_candidate(tmp_path, items, name="RESP-depth-001.json"):
    path = tmp_path / "candidates"
    path.mkdir(parents=True, exist_ok=True)
    _write_bytes(path / name, {"kind": "responses", "items": items})
    return path / name


def _write_depth_targets(tmp_path, floor=60, median=200):
    """bank_compile 产物形态(库级聚合键, bank_compile.py 契约键名稳定)。"""
    path = tmp_path / "depth_targets.json"
    _write_bytes(path, {"absolute_floor": floor, "global_median": median, "paragraph_count": 12, "calibrated_from": "a" * 64})
    return path


def _summary(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _anomaly_kinds(summary) -> list[str]:
    return [a["kind"] for a in summary["anomalies"]]


class TestBuildDepthGate:
    """build 深度门三态(Plan2 T6): 有 target 达标/不足; 无 target floor 兜底达标/不足。

    深度=质量牵引非凭据阻断门(spec §4.4): anomaly 汇 lint 报告"深度"节与摘要,
    delivery_manifest 照写不撤; 基线缺失(bid-technical/references/depth_targets.json 不在盘)=门静默跳过。
    """

    @pytest.fixture()
    def depth_baseline(self, tmp_path, monkeypatch):
        """build_output 基线路径 monkeypatch 到 tmp 副本——测试绝不触碰仓库 references/。"""
        path = _write_depth_targets(tmp_path)
        monkeypatch.setattr(_build_module(), "DEFAULT_DEPTH_TARGETS_PATH", path)
        return path

    @staticmethod
    def _response(clause_id="ZB-C-001", *, chars=80, depth_target=None):
        item = {"clause_id": clause_id, "response_text": _cjk_text(chars), "source_mode": "sample", "needs_human_verify": True}
        if depth_target is not None:
            item["depth_target"] = depth_target
        return item

    def _build(self, tmp_path, capsys, items):
        state = _depth_state(tmp_path, items)
        out = tmp_path / "out"
        rc = _build_module().main(["--state-dir", str(state), "--out", str(out)])
        return rc, _summary(capsys), out

    def test_target_met_no_anomaly(self, tmp_path, capsys, depth_baseline):
        rc, summary, out = self._build(tmp_path, capsys, [self._response(chars=120, depth_target=100)])
        assert rc == 0, "达标响应零异常"
        assert summary["anomalies"] == []
        assert summary["depth_gate"] == {"enabled": True, "skip_reason": None, "absolute_floor": 60, "responses_checked": 1, "below_target": 0, "below_floor": 0}
        lint = (out / "实体lint报告.md").read_text(encoding="utf-8")
        assert "## 深度门" in lint and "(无——全部响应达到深度基线)" in lint

    def test_target_precedence_over_floor(self, tmp_path, capsys, depth_baseline):
        """有 depth_target 即以 target 为唯一基准(floor 不叠加)——命中组校准优先于库级兜底。"""
        rc, summary, _ = self._build(tmp_path, capsys, [self._response(chars=40, depth_target=30)])
        assert rc == 0, "实质长 40 < floor 60 但 >= target 30: target 在场 floor 不判"
        assert summary["anomalies"] == [] and summary["depth_gate"]["below_floor"] == 0

    def test_below_target_anomaly_reported_not_blocking(self, tmp_path, capsys, depth_baseline):
        rc, summary, out = self._build(tmp_path, capsys, [self._response(chars=80, depth_target=300)])
        assert rc == 3, "未达 target = anomaly(退出码 3 完成但有异常项)"
        assert _anomaly_kinds(summary) == ["depth_below_target"]
        assert summary["depth_gate"]["below_target"] == 1
        anomaly = summary["anomalies"][0]
        assert anomaly["clause_id"] == "ZB-C-001" and anomaly["substantive_chars"] == 80 and anomaly["depth_target"] == 300
        lint = (out / "实体lint报告.md").read_text(encoding="utf-8")
        assert "depth_below_target" in lint and "300" in lint, "缺口逐条进 lint 报告深度节"
        assert (out / "delivery_manifest.json").is_file(), "深度门非凭据阻断门: anomaly 在凭据照写"
        assert (out / ".delivery-contract").is_file()

    def test_floor_fallback_below_floor(self, tmp_path, capsys, depth_baseline):
        rc, summary, out = self._build(tmp_path, capsys, [self._response(chars=30)])
        assert rc == 3
        assert _anomaly_kinds(summary) == ["depth_below_floor"], "无 depth_target 落库级 absolute_floor 兜底"
        assert summary["depth_gate"]["below_floor"] == 1
        anomaly = summary["anomalies"][0]
        assert "target_discarded" not in anomaly and "无 depth_target" in anomaly["message"], "真缺省才叫'无 depth_target'(对照 T6 评审②弃用留痕分支)"
        lint = (out / "实体lint报告.md").read_text(encoding="utf-8")
        assert "depth_below_floor" in lint
        assert (out / "delivery_manifest.json").is_file(), "floor 异常同样不阻断凭据"

    def test_floor_fallback_met(self, tmp_path, capsys, depth_baseline):
        rc, summary, _ = self._build(tmp_path, capsys, [self._response(chars=80)])
        assert rc == 0 and summary["anomalies"] == [], "无 target 但实质长 >= floor: 兜底达标"

    def test_gate_skipped_without_baseline(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(_build_module(), "DEFAULT_DEPTH_TARGETS_PATH", tmp_path / "missing.json")
        rc, summary, out = self._build(tmp_path, capsys, [self._response(chars=30)])
        assert rc == 0, "基线缺失=门跳过(bank 未编译不阻塞), 短响应也不报异常"
        assert summary["depth_gate"]["enabled"] is False and summary["anomalies"] == []
        assert summary["depth_gate"]["skip_reason"] == "missing", "跳过原因随摘要呈现——门静默失效可诊断(T6 评审①)"
        lint = (out / "实体lint报告.md").read_text(encoding="utf-8")
        assert "深度门" in lint and "跳过" in lint
        assert "跳过原因: 文件缺失(样例库未编译)" in lint, "跳过原因分句进 lint 报告(T6 评审①)"

    def test_gate_skipped_when_baseline_malformed(self, tmp_path, capsys, monkeypatch):
        """基线在盘但形态不可用 = 与缺失同语义(门跳过不硬错); 失效形态可分辨(T6 评审①)。"""
        path = tmp_path / "depth_targets.json"
        _write_bytes(path, {"absolute_floor": "60", "global_median": 200})
        monkeypatch.setattr(_build_module(), "DEFAULT_DEPTH_TARGETS_PATH", path)
        rc, summary, _ = self._build(tmp_path, capsys, [self._response(chars=30)])
        assert rc == 0 and summary["depth_gate"]["enabled"] is False
        assert summary["depth_gate"]["skip_reason"] == "bad_floor", "absolute_floor 非整数 → bad_floor"

        _write_text_raw(path, "{not-json")  # 损坏 JSON = 另一失效形态
        rc, summary, _ = self._build(tmp_path, capsys, [self._response(chars=30)])
        assert rc == 0 and summary["depth_gate"]["enabled"] is False
        assert summary["depth_gate"]["skip_reason"] == "malformed", "不可解析 → malformed"

    def test_item_level_malformed_target_falls_back_to_floor(self, tmp_path, capsys, depth_baseline):
        """responses.json 内 depth_target 非整数(脚本外直写脏数据) → 按"未提供"回落 floor,
        不硬错不静默丢基准; anomaly 带 target_discarded 原值留痕+文案点破"形态不符已弃用"
        (纠正"无 depth_target"的误导, T6 评审②)。"""
        rc, summary, _ = self._build(tmp_path, capsys, [self._response(chars=30, depth_target="300")])
        assert rc == 3
        assert _anomaly_kinds(summary) == ["depth_below_floor"], "脏 target 回落 floor 判定"
        anomaly = summary["anomalies"][0]
        assert anomaly["target_discarded"] == "300", "弃用原值随 anomaly 留痕(T6 评审②)"
        assert "形态不符已弃用" in anomaly["message"], "文案不再误称'无 depth_target'(T6 评审②)"

    def test_direct_dirty_floor_dict_skips_and_renders_skip(self):
        """直调防御分支(T7 评审 I-2): 脏 floor dict(非 None) 传给 run_depth_gate 必须判跳过
        (summary.skip_reason="bad_floor"), 且 _render_depth_section 同态渲染跳过说明——
        不许把脏 floor 原样渲进"基线"行(摘要说跳过/报告说有基线 = 互斥诊断)。"""
        bo = _build_module()
        dirty = {"absolute_floor": "60", "global_median": 200}
        anoms, summary = bo.run_depth_gate([self._response(chars=30)], dirty)
        assert anoms == [], "脏 floor 不得产出判异"
        assert summary["enabled"] is False and summary["skip_reason"] == "bad_floor", "防御分支同样可诊断"
        assert bo._valid_floor("60") is False and bo._valid_floor(60) is True and bo._valid_floor(True) is False, "模块级单源形态校验"
        text = "\n".join(bo._render_depth_section(anoms, dirty, skip_reason=summary["skip_reason"]))
        assert "(跳过——无基线可比)" in text and "absolute_floor 形态不符(非整数)" in text, "skip 态渲染跳过说明"
        assert "> 基线: " not in text, "脏 floor 值不得渲进基线行"

    def test_substantive_chars_mirrors_responses(self):
        """build_output 复制了 responses.py 的实质长口径(不跨脚本 import)——同步断言兜漂移。"""
        bo, rs = _build_module(), _responses_module()
        for sample in ("系统采用模块化架构(支持远程诊断)", " meets ISO 9001_V2.3 要求, 报价****元", "  \n\t ", "ABC123中文,、；！", ""):
            assert bo._substantive_chars(sample) == rs._substantive_chars(sample), "实质长口径与 responses.py 漂移"


class TestResponsesDepthTarget:
    """depth_target 字段贯通(Plan2 T6): merge 透传落 responses.json; validate 仅校形态
    (≥0 整数——schema type/minimum, 非整数/负数 → schema_violation 不合并)。"""

    @staticmethod
    def _valid_item(**over):
        item = {
            "clause_id": "ZB-C-001",
            "response_text": _cjk_text(80),
            "source_mode": "sample",
            "citations": [{"title": "样例标书", "url": None, "source_doc": "样例库/PaaS平台标书", "quote_span": "p3-4", "quote": "提供远程诊断平台"}],
            "needs_human_verify": True,
        }
        item.update(over)
        return item

    def _merge(self, tmp_path, capsys, items):
        state = _depth_state(tmp_path)
        cand = _depth_candidate(tmp_path, items)
        rc = _responses_module().main(["merge", "--candidates", str(cand), "--state-dir", str(state)])
        return rc, _summary(capsys), state

    def test_merge_passes_depth_target_through(self, tmp_path, capsys):
        rc, summary, state = self._merge(tmp_path, capsys, [self._valid_item(depth_target=100)])
        assert rc == 0
        merged = {r["clause_id"]: r for r in json.loads((state / "responses.json").read_text(encoding="utf-8"))}
        assert merged["ZB-C-001"]["depth_target"] == 100, "merge 原样透传 depth_target 落 responses.json"

    def test_merge_accepts_zero_target(self, tmp_path, capsys):
        rc, _, state = self._merge(tmp_path, capsys, [self._valid_item(depth_target=0)])
        assert rc == 0, "minimum 0: 零目标合法(等价不设下限)"
        merged = json.loads((state / "responses.json").read_text(encoding="utf-8"))
        assert merged[0]["depth_target"] == 0

    @pytest.mark.parametrize("bad_target", [-5, "100", 1.5, True])
    def test_validate_rejects_malformed_depth_target(self, tmp_path, capsys, bad_target):
        state = _depth_state(tmp_path)
        cand = _depth_candidate(tmp_path, [self._valid_item(depth_target=bad_target)], name="RESP-bad.json")
        rc = _responses_module().main(["validate", "--candidates", str(cand), "--state-dir", str(state)])
        assert rc == 3, "形态不符 = anomaly 不合并"
        summary = _summary(capsys)
        assert _anomaly_kinds(summary) == ["schema_violation"]
        errors = " ".join(summary["anomalies"][0]["errors"])
        assert "depth_target" in errors, f"错误消息点名 depth_target 字段: {errors}"

    def test_malformed_target_not_merged(self, tmp_path, capsys):
        rc, _, state = self._merge(tmp_path, capsys, [self._valid_item(depth_target=-1)])
        assert rc == 3
        assert not (state / "responses.json").exists(), "带病条目不落账(responses.json 保持缺省空态)"
