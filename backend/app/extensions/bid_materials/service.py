# EAI-CUSTOM: bug-3109 v4 投标资料管理服务层.
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
    """资质版本生命周期(行+MinIO 对象)。"""

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

    async def add_version(
        self,
        qual_id: uuid.UUID,
        *,
        data: bytes,
        file_name: str,
        note: str | None = None,
        uploaded_by: uuid.UUID | None = None,
    ) -> tuple[BidQualificationVersion, bool]:
        """新版本: 魔数校验→sha256 去重(同哈希幂等返回既有版)→MinIO put(to_thread)→建版本行→推进指针。"""
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
        minio_key = await asyncio.to_thread(storage.put_file, str(qual_id), version, file_name, data)
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
        q = await self._get(qual_id)
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

    async def list(self, *, industry: str | None = None, project_category: str | None = None, q: str | None = None) -> list[BidSample]:
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
        """file_hash upsert 幂等: 已存在=skip, 新=created。"""
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
