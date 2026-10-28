"""SQLAlchemy models mirroring the eight warm-flow tables.

Column names intentionally match ``warm-flow-all.sql`` so a database dump can
be imported without a translation layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .config import settings
from .database import Base
from .utils import next_id, utcnow


class TimestampMixin:
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    create_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    update_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    del_flag: Mapped[str] = mapped_column(String(1), default="0", nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(40), default=settings.default_tenant, nullable=False)


class FlowDefinition(TimestampMixin, Base):
    __tablename__ = "flow_definition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    flow_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    flow_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_value: Mapped[str] = mapped_column(String(40), default="CLASSICS", nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    is_publish: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    form_custom: Mapped[str] = mapped_column(String(1), default="N", nullable=False)
    form_path: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activity_status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    listener_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listener_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ext: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FlowNode(TimestampMixin, Base):
    __tablename__ = "flow_node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    node_type: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    node_code: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permission_flag: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    node_ratio: Mapped[str | None] = mapped_column(String(200), default="0", nullable=True)
    coordinate: Mapped[str | None] = mapped_column(String(200), nullable=True)
    any_node_skip: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listener_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listener_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    form_custom: Mapped[str] = mapped_column(String(1), default="N", nullable=False)
    form_path: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1", nullable=False)
    ext: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlowSkip(TimestampMixin, Base):
    __tablename__ = "flow_skip"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    definition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    now_node_code: Mapped[str] = mapped_column(String(100), nullable=False)
    now_node_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_node_code: Mapped[str] = mapped_column(String(100), nullable=False)
    next_node_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skip_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skip_type: Mapped[str | None] = mapped_column(String(40), default="PASS", nullable=True)
    skip_condition: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coordinate: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FlowInstance(TimestampMixin, Base):
    __tablename__ = "flow_instance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    definition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    node_type: Mapped[int] = mapped_column(Integer, nullable=False)
    node_code: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    variable: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_status: Mapped[str] = mapped_column(String(20), default="0", nullable=False)
    activity_status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    def_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ext: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FlowTask(TimestampMixin, Base):
    __tablename__ = "flow_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    definition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    node_code: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    node_type: Mapped[int] = mapped_column(Integer, nullable=False)
    flow_status: Mapped[str] = mapped_column(String(20), default="1", nullable=False)
    form_custom: Mapped[str] = mapped_column(String(1), default="N", nullable=False)
    form_path: Mapped[str | None] = mapped_column(String(100), nullable=True)


class FlowHisTask(TimestampMixin, Base):
    __tablename__ = "flow_his_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    definition_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    node_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    node_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    node_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_node_code: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_node_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approver: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cooperate_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collaborator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skip_type: Mapped[str] = mapped_column(String(10), nullable=False)
    flow_status: Mapped[str] = mapped_column(String(20), nullable=False)
    form_custom: Mapped[str] = mapped_column(String(1), default="N", nullable=False)
    form_path: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    variable: Mapped[str | None] = mapped_column(Text, nullable=True)
    ext: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlowUser(TimestampMixin, Base):
    __tablename__ = "flow_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    type: Mapped[str] = mapped_column(String(1), nullable=False)
    processed_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    associated: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class FlowForm(TimestampMixin, Base):
    __tablename__ = "flow_form"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    form_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    form_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    is_publish: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    form_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    form_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    form_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ext: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FlowInstanceRuntime(TimestampMixin, Base):
    """Temporal execution binding for one warm-flow instance.

    Kept separate from ``flow_instance`` so the eight warm-flow tables remain
    import-compatible. The workflow id is deterministic: ``flow-instance-{id}``.
    """

    __tablename__ = "flow_instance_runtime"

    instance_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(20), default="temporal", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="STARTING", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlowCommand(TimestampMixin, Base):
    """Durable command inbox; the API writes it before signalling Temporal."""

    __tablename__ = "flow_command"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    instance_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    definition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)


class FlowOutboxEvent(TimestampMixin, Base):
    """Transactional domain event awaiting delivery to the marketing BFF."""

    __tablename__ = "flow_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    command_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(40), default="flow_instance", nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
