"""SQLAlchemy models for the translation extension ``tlt_`` tables (EAI-CUSTOM).

设计: docs/designs/2026-10-11-jv-mining-translation-kb.md 构件 3（任务模型）。
新表经共享 Base 的 create_all 在 gateway 启动时自动创建（contract_price 同机制）。

状态机（设计构件 3，含 R3-1/R3-2/R3-3 生命周期语义）::

    pending → running → check_failed → retrying(≤2) → exceeded / indexed → delivered
    exceeded(人工) → indexed(review_approved) | archived(review_rejected，仅未 delivered)
    failed: 基础设施失败（LLM/OCR/block树/MinIO/RAGFlow），可人工重跑回 pending
    cancelled/superseded: 重传即替换与显式取消（终态）
    delivered 后否决走「重传即替换」版本流，不新增状态（R3-2）
"""

import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base

# 全部合法状态（含终态）。stored=资产库已上传未入队（用户点「翻译」→pending）
STATES: frozenset[str] = frozenset(
    {
        "stored",
        "pending",
        "running",
        "check_failed",
        "retrying",
        "exceeded",
        "indexed",
        "delivered",
        "archived",
        "failed",
        "cancelled",
        "superseded",
        "skipped",
    }
)

# 终态（无出边；failed 可人工重跑、delivered 保留 reviewed 重交付边→indexed，均不在终态列）
TERMINAL_STATES: frozenset[str] = frozenset({"archived", "cancelled", "superseded", "skipped"})

# 合法出边（R7: running→failed 覆盖 indexed→delivered 阶段的基础设施失败，幂等键=doc sha；
# stored→pending = 资产库「翻译」动作入队；库删除(→archived)走 DELETE 端点直达，不经此表）
TRANSITIONS: dict[str, frozenset[str]] = {
    "stored": frozenset({"pending", "cancelled", "superseded", "skipped"}),
    "pending": frozenset({"running", "cancelled", "superseded", "skipped"}),
    "running": frozenset({"check_failed", "indexed", "failed", "cancelled", "superseded", "exceeded", "skipped"}),
    "check_failed": frozenset({"retrying", "exceeded", "cancelled", "superseded"}),
    "retrying": frozenset({"check_failed", "exceeded", "indexed", "cancelled", "superseded"}),
    "exceeded": frozenset({"indexed", "archived", "superseded"}),
    "indexed": frozenset({"delivered", "failed", "superseded"}),
    "delivered": frozenset({"indexed", "superseded"}),
    "failed": frozenset({"pending", "superseded"}),
    "archived": frozenset(),
    "cancelled": frozenset(),
    "superseded": frozenset(),
    "skipped": frozenset({"superseded"}),
}


def validate_transition(current: str, target: str) -> bool:
    """状态机边校验（纯函数，worker 与复核 API 共用）。"""
    if current not in STATES or target not in STATES:
        return False
    return target in TRANSITIONS[current]


class TltFolder(Base):
    """资产库文件夹（虚拟分类树；物理文件在 MinIO/本地存储，移动只改指针）。"""

    __tablename__ = "tlt_folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tlt_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=func.now())

    def __repr__(self) -> str:
        return f"<TltFolder(id={self.id}, name={self.name})>"


class TranslationTask(Base):
    """翻译任务行（幂等键 = doc_sha + task_version，设计构件 3）。

    占位符注册表 / gate 明细 / 不确定段均为每次运行的载荷，入 JSONB，
    不另立表（ponytail: 单一消费方，二期 UI 需要时再拆）。
    """

    __tablename__ = "tlt_translation_tasks"
    __table_args__ = (
        # 幂等键含 kb 维度：同一文件可入不同 KB 各自成任务；同 KB 同 sha 重传=幂等复用（enqueue 检查）
        UniqueConstraint("kb_id", "doc_sha", "task_version", name="uq_tlt_task_kb_sha_version"),
        Index("ix_tlt_task_kb_state", "kb_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # EAI-CUSTOM (bug-1791807358242): ondelete CASCADE——delete_kb 不清理本表,
    # NO ACTION 缺省会让删 KB 撞 FK IntegrityError 500(tlt-bridge-* 事故)
    kb_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    doc_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="en")  # en/fr/zh/mixed
    content_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)  # narrative/tabular/mixed
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    quality_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")  # draft/reviewed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    task_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gate_failures: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 逐轴失败明细
    uncertainty: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # LLM 不确定标记段（list[{block,...}]，勿用 dict）
    # EAI-CUSTOM (P0 复核闭环): exceeded 时保存的逐块草稿；复核通过后用它走
    # index_translation 完成中文份索引与交付（zh_blocks 原本只存在内存里）。
    draft_blocks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # EAI-CUSTOM (P1 复核对照): 源文逐块快照，供复核页左右对照（id 与 draft_blocks 对齐）。
    draft_source_blocks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # EAI-CUSTOM (P2 MTPE): 首次人工编辑前的机器草稿（TM 种子）、编辑审计
    draft_blocks_original: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    draft_edited_at: Mapped[object] = mapped_column(DateTime, nullable=True)
    draft_edited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 基础设施错误详情
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # T6 交付物（delivered 分界事件的物证：MinIO uri + RAGFlow 中文版文档 id）
    deliverable_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ragflow_zh_doc_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ragflow_source_doc_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # B1 原文入库 doc id（R3-3 删除级联钩子）
    # 资产库文件夹归属（NULL=根；T7 资产库页）
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tlt_folders.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<TranslationTask(id={self.id}, sha={self.doc_sha[:8]}, state={self.state})>"


class TltBackfillJob(Base):
    """超大回填任务（EAI-CUSTOM, P2 scheduled backfill）。

    平台 scheduled_tasks 是 agent prompt 调度，不适合确定性队列；本表由 gateway 内嵌
    的 backfill tick 消费：每次把 chunk_size 个 stored/failed 任务转 pending，直到游标耗尽。
    """

    __tablename__ = "tlt_backfill_jobs"
    __table_args__ = (Index("ix_tlt_backfill_state", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active|done|cancelled
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<TltBackfillJob(id={self.id}, state={self.state}, cursor={self.cursor}/{len(self.task_ids or [])})>"
