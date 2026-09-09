"""ORM models for the coal EIA report sample bank (EAI-CUSTOM)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class KFSample(Base):
    """样例库样例台账（EAI-CUSTOM: coal-eia-report v2 BS3 样例库 MVP）。

    已解析环评报告样例文件的登记记录：场景(scenario)×状态(status)双轴台账，
    file_hash 唯一——同一文件的重复登记（含 import-bulk 重跑）按哈希 upsert 幂等。
    """

    __tablename__ = "kf_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scenario: Mapped[str] = mapped_column(String(50), nullable=False, default="other", index=True)
    variant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="filename_only", index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # EAI-CUSTOM (2026-09 二期 BS3 ③提取流水线): 提取产物 JSON（outline/v1：chapters+candidates+元数据）。
    # JSONB 为主型（postgres 迁移见 database.py migrate_db），sqlite 测试库用 JSON 变体。
    outline_json: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<KFSample(id={self.id}, scenario={self.scenario}, status={self.status}, title={self.title[:30]})>"


# EAI-CUSTOM (2026-09 样例库迁出): 原挂在 knowledge_factory（表 kf_samples 随之建于彼处）。
# 迁出为独立应用「煤矿环评报告样例库」时，类名与表名均原样沿用（免数据迁移/免全量改引用）；
# 模块归属 eia_samples，建表由 Base create_all（gateway 启动序 init_db）承接。
