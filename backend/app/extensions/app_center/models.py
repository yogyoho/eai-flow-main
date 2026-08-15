"""App-center SQLAlchemy models — domain labels & app definitions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class AppDomain(Base):
    """Business domain / category label for apps."""

    __tablename__ = "app_domains"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    accent_color: Mapped[str] = mapped_column(String(20), nullable=False, default="blue")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_universal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AppDomain key={self.key!r} label={self.label!r}>"


class AppDefinition(Base):
    """An app entry in the app-center catalog."""

    __tablename__ = "app_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    app_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_name: Mapped[str] = mapped_column(String(100), nullable=False)
    business_domain: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("app_domains.key"),
        nullable=False,
    )
    stage_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    license_module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_key: Mapped[str] = mapped_column(String(200), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AppDefinition app_id={self.app_id!r} name={self.name!r}>"
