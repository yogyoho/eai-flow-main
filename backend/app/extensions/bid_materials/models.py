"""投标资料管理数据模型: 资质元数据/资质版本(MinIO)/样例台账。

形态沿用 eia_samples.KFSample（声明式 Base；commit 1ce049220 领域样例库独立应用先例）。
资质文件本体存 MinIO 桶 bid-qualifications（storage.py），行内只存 minio_key/sha256。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
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
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 证书载明的业务范围（证书覆盖什么）
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    org_scope: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 企业经营范围（公司主体做什么，与证书范围区分）
    disabled: Mapped[bool] = mapped_column(nullable=False, default=False)  # 软删标记
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<BidQualification(id={self.id}, qual_type={self.qual_type}, cert_no={self.cert_no}, current_version={self.current_version})>"


class BidQualificationVersion(Base):
    """资质文件版本行（不可变只追加）。回滚=改 BidQualification.current_version 指针。"""

    __tablename__ = "bid_qualification_versions"
    __table_args__ = (
        # (qualification_id, version) 唯一：并发上传不可铸出重复版本号，current_version 指针才无歧义
        UniqueConstraint("qualification_id", "version", name="uq_bid_qualification_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qualification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bid_qualifications.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    def __repr__(self) -> str:
        return f"<BidQualificationVersion(id={self.id}, qualification_id={self.qualification_id}, version={self.version})>"


class BidSample(Base):
    """样例台账（沿用 KFSample 形态; 深度地板统一走 depth_targets.json, 册级不存）。"""

    __tablename__ = "bid_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False, default="other", index=True)  # 默认行业=other（未标注样例的台账过滤兜底）
    project_category: Mapped[str] = mapped_column(String(50), nullable=False, default="IT软件平台", index=True)  # 默认品类=IT软件平台（主战场品类; 枚举契约 Task 3 统一）
    scenario: Mapped[str] = mapped_column(String(50), nullable=False, default="bid_sample")  # 默认场景=投标样例
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="indexed", index=True)  # 默认状态=已索引（登记即可用）
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<BidSample(id={self.id}, industry={self.industry}, status={self.status}, title={self.title[:30]})>"
