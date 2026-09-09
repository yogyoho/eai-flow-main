"""样例库服务层（EAI-CUSTOM: coal-eia-report v2 BS3 样例库 MVP；二期+提取流水线/质检）。

样例 = 已解析环评报告文件的登记记录。台账双轴：scenario（场景）× status（解析状态）；
file_hash 全局唯一，批量导入按哈希 upsert 幂等（既有台账数据可反复灌入）。
"""

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import KFSample
from .schemas import (
    SampleBatchUpdate,
    SampleBulkImportRequest,
    SampleBulkItem,
    SampleCreate,
    SampleScenario,
    SampleStatus,
    SampleUpdate,
)

logger = logging.getLogger(__name__)


class SampleHashConflictError(Exception):
    """file_hash 已被其他样例登记（POST 手工登记冲突）"""


class SampleService:
    """样例台账 CRUD + 批量导入"""

    @staticmethod
    async def list_samples(
        db: AsyncSession,
        scenario: SampleScenario | None = None,
        status: SampleStatus | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[KFSample], int]:
        """分页列出样例；scenario/status 过滤 + 标题/路径模糊搜索。"""
        query = select(KFSample)
        if scenario is not None:
            query = query.where(KFSample.scenario == scenario.value)
        if status is not None:
            query = query.where(KFSample.status == status.value)
        if search:
            like = f"%{search.strip()}%"
            query = query.where((KFSample.title.ilike(like)) | (KFSample.source_path.ilike(like)))
        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0
        query = query.order_by(KFSample.created_at.desc(), KFSample.id)
        query = query.offset((page - 1) * limit).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_sample(db: AsyncSession, sample_id) -> KFSample | None:
        result = await db.execute(select(KFSample).where(KFSample.id == sample_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_hash(db: AsyncSession, file_hash: str) -> KFSample | None:
        result = await db.execute(select(KFSample).where(KFSample.file_hash == file_hash))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_sample(db: AsyncSession, data: SampleCreate, user_id=None) -> KFSample:
        """手工登记样例；file_hash 重复时抛 SampleHashConflictError（路由层转 409）。"""
        if await SampleService.get_by_hash(db, data.file_hash):
            raise SampleHashConflictError(f"file_hash {data.file_hash[:16]}… 已登记")
        sample = KFSample(
            title=data.title,
            source_path=data.source_path,
            file_hash=data.file_hash,
            scenario=data.scenario.value,
            variant=data.variant,
            status=data.status.value,
            confidence=data.confidence,
            notes=data.notes,
            created_by=user_id,
        )
        db.add(sample)
        await db.commit()
        await db.refresh(sample)
        return sample

    @staticmethod
    async def bulk_import(db: AsyncSession, payload: SampleBulkImportRequest) -> dict:
        """按 file_hash upsert 批量导入（幂等）——既有台账数据入库通道。

        命中已有哈希：用条目覆盖业务字段（title/source_path/scenario/variant/status/
        confidence/notes）；未命中：插入新行。重复运行 created/updated 计数互换、
        台账终态不变。
        """
        created = updated = 0
        for item in payload.items:
            existing = await SampleService.get_by_hash(db, item.file_hash)
            if existing is None:
                db.add(
                    KFSample(
                        title=item.title,
                        source_path=item.source_path,
                        file_hash=item.file_hash,
                        scenario=item.scenario.value,
                        variant=item.variant,
                        status=item.status.value,
                        confidence=item.confidence,
                        notes=item.notes,
                    )
                )
                created += 1
            else:
                existing.title = item.title
                existing.source_path = item.source_path
                existing.scenario = item.scenario.value
                existing.variant = item.variant
                existing.status = item.status.value
                existing.confidence = item.confidence
                existing.notes = item.notes
                updated += 1
        await db.commit()
        logger.info("KFSample bulk import: created=%d updated=%d total=%d", created, updated, len(payload.items))
        return {"created": created, "updated": updated, "total": len(payload.items)}

    @staticmethod
    async def update_sample(db: AsyncSession, sample: KFSample, data: SampleUpdate) -> KFSample:
        for key, value in data.model_dump(exclude_unset=True).items():
            if key in ("scenario", "status") and value is not None:
                value = value.value
            setattr(sample, key, value)
        await db.commit()
        await db.refresh(sample)
        return sample

    @staticmethod
    async def batch_update(db: AsyncSession, data: SampleBatchUpdate) -> int:
        """批量修改 scenario/status/variant/confidence（台账归类）。返回更新行数。"""
        fields = data.model_dump(exclude_unset=True, exclude={"ids"})
        fields = {k: (v.value if isinstance(v, (SampleScenario, SampleStatus)) else v) for k, v in fields.items()}
        if not fields:
            return 0
        result = await db.execute(update(KFSample).where(KFSample.id.in_(data.ids)).values(**fields))
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def delete_sample(db: AsyncSession, sample: KFSample) -> None:
        await db.delete(sample)
        await db.commit()

    @staticmethod
    def make_bulk_payload(items: list[dict]) -> SampleBulkImportRequest:
        """从 dict 列表（种子 JSON）构造导入请求——管理脚本与测试共用。"""
        return SampleBulkImportRequest(items=[SampleBulkItem.model_validate(it) for it in items])

    # ── 二期：提取流水线（BS3 ③）──

    @staticmethod
    async def save_outline(db: AsyncSession, sample: KFSample, outline: dict) -> KFSample:
        """提取结果写入 outline_json；仅登记状态（filename_only）的成功提取升级为 parsed。"""
        sample.outline_json = outline
        if sample.status == SampleStatus.FILENAME_ONLY.value and outline.get("chapters"):
            sample.status = SampleStatus.PARSED.value
        await db.commit()
        await db.refresh(sample)
        logger.info(
            "KFSample outline saved: id=%s chapters=%d candidates=%s",
            sample.id,
            len(outline.get("chapters") or []),
            {k: len(v) for k, v in (outline.get("candidates") or {}).items()},
        )
        return sample
