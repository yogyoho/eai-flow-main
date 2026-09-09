# EAI-CUSTOM: bug-3109 v4 投标资料管理服务层.
"""投标资料管理服务层: 资质版本生命周期/到期预警/白名单导出 + 样例台账。

真库语义(SQLAlchemy 异步会话); MinIO 文件操作经 storage(调用方 to_thread)。
commit 归路由层(data_source 先例), 本服务只 flush。
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


def _sniff_ext(data: bytes) -> str:
    for magic, ext in IMAGE_MAGIC:
        if data.startswith(magic):
            return ext
    raise ValueError("仅支持 png/jpg 资质扫描件(魔数校验失败)")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class QualificationNotFoundError(LookupError):
    pass


class SampleNotFoundError(LookupError):
    pass


class QualificationService:
    """资质版本生命周期(行+MinIO 对象)。"""

    # update() 白名单: 只放行业字段, id/created_at/updated_at/disabled 等结构性字段不开放
    _UPDATABLE_FIELDS = ("qual_type", "cert_no", "issuer", "valid_until", "scope", "org_scope", "notes")

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get(self, qual_id: uuid.UUID) -> BidQualification:
        q = await self.session.get(BidQualification, qual_id)
        if q is None or q.disabled:
            raise QualificationNotFoundError(f"资质不存在或已停用: {qual_id}")
        return q

    async def create(self, *, qual_type: str, cert_no: str, issuer: str | None = None, valid_until: dt.date | None = None, scope: str | None = None, org_scope: str | None = None, notes: str | None = None) -> BidQualification:
        q = BidQualification(qual_type=qual_type, cert_no=cert_no, issuer=issuer, valid_until=valid_until, scope=scope, org_scope=org_scope, notes=notes)
        self.session.add(q)
        await self.session.flush()
        return q

    async def update(self, qual_id: uuid.UUID, **fields) -> BidQualification:
        """部分更新。白名单校验: 未知键 raise(不再 hasattr 静默放行)。

        None=不清空(跳过该键); 清空语义走显式路径(软删/专用方法),
        对齐 eia schemas model_dump(exclude_unset) 先例的等价形态。
        """
        unknown = set(fields) - set(self._UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"不可更新字段: {sorted(unknown)}")
        q = await self._get(qual_id)
        for key, value in fields.items():
            if value is not None:
                setattr(q, key, value)
        await self.session.flush()
        return q

    async def soft_delete(self, qual_id: uuid.UUID) -> None:
        q = await self._get(qual_id)
        q.disabled = True
        await self.session.flush()

    async def list(self, *, include_disabled: bool = False, limit: int = 200, offset: int = 0) -> list[BidQualification]:
        stmt = select(BidQualification)
        if not include_disabled:
            stmt = stmt.where(BidQualification.disabled.is_(False))  # 软删过滤 SQL 下推
        stmt = stmt.order_by(BidQualification.updated_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_version(
        self,
        qual_id: uuid.UUID,
        *,
        data: bytes,
        note: str | None = None,
        uploaded_by: uuid.UUID | None = None,
    ) -> tuple[BidQualificationVersion, bool]:
        """新版本: 魔数校验→sha256 去重(同哈希幂等返回既有版)→MinIO put(to_thread)→建版本行→推进指针。

        评审 I-1: put_file 的 ext 实参直接传嗅探结果——put 键/DB file_ext/get 重建键三方同源,
        若 put 端从 file_name 另行派生 ext, 对象落 .dat 而 DB 记 png → current_file 永久 404。
        """
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
        stmt_max = select(BidQualificationVersion.version).where(BidQualificationVersion.qualification_id == qual_id).order_by(BidQualificationVersion.version.desc()).limit(1)
        last = (await self.session.execute(stmt_max)).scalars().first()
        version = (last or 0) + 1
        minio_key = await asyncio.to_thread(storage.put_file, str(qual_id), version, ext, data)
        row = BidQualificationVersion(
            qualification_id=qual_id,
            version=version,
            minio_key=minio_key,
            sha256=digest,
            file_ext=ext,
            file_size=len(data),
            note=note,
            uploaded_by=uploaded_by,
        )
        self.session.add(row)
        q.current_version = version
        await self.session.flush()
        return row, True

    async def rollback(self, qual_id: uuid.UUID, *, to_version: int) -> BidQualification:
        """回滚=改指针不删对象。目标版本行必须真实存在——幽灵版本号(0/负数/超界)
        会造出悬空指针, 下载侧按指针查版本行查不到 → 永久 404(评审 I-2)。"""
        q = await self._get(qual_id)
        stmt = select(BidQualificationVersion).where(
            BidQualificationVersion.qualification_id == qual_id,
            BidQualificationVersion.version == to_version,
        )
        if (await self.session.execute(stmt)).scalars().first() is None:
            raise QualificationNotFoundError(f"回滚目标版本不存在: {qual_id} v{to_version}")
        q.current_version = to_version
        await self.session.flush()
        return q

    async def expiring(self, *, days: int = 90) -> list[BidQualification]:
        deadline = dt.date.today() + dt.timedelta(days=days)
        stmt = (
            select(BidQualification)
            .where(
                BidQualification.disabled.is_(False),
                BidQualification.valid_until.is_not(None),
                BidQualification.valid_until <= deadline,
            )
            .order_by(BidQualification.valid_until)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def export_whitelist(self) -> list[dict]:
        """entities_whitelist 增量(公司+证号+有效期)——WP-2.4 组织级权威源。"""
        rows = await self.list()
        return [{"type": "company", "value": q.issuer or q.qual_type, "cert_no": q.cert_no, "valid_until": q.valid_until.isoformat() if q.valid_until else None} for q in rows]

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
        data = await asyncio.to_thread(storage.get_file, str(qual_id), row.version, row.file_ext)
        if data is None:
            return None
        return data, row.file_ext


class SampleService:
    """样例台账(file_hash 幂等 bulk)。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, sample_id: uuid.UUID) -> BidSample:
        """单样例详情（不存在 raise SampleNotFoundError → 路由 404; 与 disable 同语义）。"""
        row = await self.session.get(BidSample, sample_id)
        if row is None:
            raise SampleNotFoundError(f"样例不存在: {sample_id}")
        return row

    async def list(self, *, industry: str | None = None, project_category: str | None = None, q: str | None = None, limit: int = 200, offset: int = 0) -> list[BidSample]:
        """台账查询: 过滤全部下推 SQL(industry/project_category 走 ==, 标题走 ilike),
        limit/offset 供路由分页(Task 5 接入)。"""
        stmt = select(BidSample)
        if industry:
            stmt = stmt.where(BidSample.industry == industry)
        if project_category:
            stmt = stmt.where(BidSample.project_category == project_category)
        if q:
            stmt = stmt.where(BidSample.title.ilike(f"%{q}%"))
        stmt = stmt.order_by(BidSample.updated_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def bulk(self, items: list[dict]) -> dict:
        """file_hash upsert 幂等: 已存在=skip, 新=created。

        M-4: 哈希集合走单列 select——省整表 ORM 实例化。
        """
        existing = set((await self.session.execute(select(BidSample.file_hash))).scalars())
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
            raise SampleNotFoundError(f"样例不存在: {sample_id}")
        row.status = "disabled"
        await self.session.flush()
