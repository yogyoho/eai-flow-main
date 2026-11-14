"""Generic subject-bound approval instances.

This module reuses the workflow engine's DAG ordering and review gate without
coupling approvals to ``ReportProject`` / ``PhaseReview``.  A subject can be any
business object (for example a bid-write document revision) identified by
``subject_type`` + ``subject_id`` + ``subject_version``.

The approval instance stores a snapshot of the workflow graph at submit time so
later edits to a workflow definition cannot change an in-flight approval.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base
from app.extensions.review.gate import GateMode, GateResult, evaluate_gate

from .service import topological_sort, validate_dag


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class SubjectApprovalError(Exception):
    """Base class for subject approval failures."""


class SubjectApprovalNotFound(SubjectApprovalError):
    """The approval instance or assignment does not exist."""


class SubjectApprovalForbidden(SubjectApprovalError):
    """The caller is not an assigned reviewer."""


class SubjectApprovalConflict(SubjectApprovalError):
    """The approval is no longer actionable (already decided, duplicate, ...)."""


class WorkflowSubjectInstance(Base):
    """One approval run bound to an arbitrary business subject."""

    __tablename__ = "workflow_subject_instances"
    __table_args__ = (UniqueConstraint("subject_type", "subject_id", "subject_version", name="uq_workflow_subject_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    subject_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    definition_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    node_order: Mapped[list] = mapped_column(JSON, default=list)
    assignments: Mapped[dict] = mapped_column(JSON, default=dict)
    current_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowSubjectReview(Base):
    """One reviewer assignment for one node of a subject approval instance."""

    __tablename__ = "workflow_subject_reviews"
    __table_args__ = (UniqueConstraint("instance_id", "node_id", "reviewer_id", name="uq_workflow_subject_reviewer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_subject_instances.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(100), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(64), index=True)
    reviewer_role: Mapped[str] = mapped_column(String(50), default="reviewer")
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|cancelled
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


def _main_graph(graph: dict) -> dict:
    if not isinstance(graph, dict):
        raise ValueError("审批流 graph 必须是对象")
    main = graph.get("mainGraph", graph)
    if not isinstance(main, dict):
        raise ValueError("审批流 graph.mainGraph 必须是对象")
    return main


def review_nodes(graph: dict) -> list[dict]:
    """Return review nodes in DAG topological order."""

    main = _main_graph(graph)
    nodes = {str(node.get("id")): node for node in main.get("nodes", []) if isinstance(node, dict) and node.get("id")}
    order = topological_sort(graph)
    ordered = [nodes[node_id] for node_id in order if node_id in nodes and nodes[node_id].get("type") == "review"]
    if not ordered:
        raise ValueError("审批流没有 review 节点")
    return ordered


def _node_data(node: dict) -> dict:
    data = node.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _reviewer_ids(node: dict) -> list[str]:
    """Resolve explicit user bindings from a review node.

    Only ``type=user`` bindings are supported here.  Role/position resolution
    belongs to the organisation layer and is intentionally not guessed.
    """

    data = _node_data(node)
    found: list[str] = []
    for raw in data.get("reviewers") or []:
        if isinstance(raw, str):
            value = raw
        elif isinstance(raw, dict):
            if raw.get("type") not in (None, "user"):
                continue
            value = raw.get("value") or raw.get("id")
        else:
            continue
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
    for raw in data.get("reviewer_ids") or []:
        if isinstance(raw, str) and raw.strip():
            found.append(raw.strip())
    return list(dict.fromkeys(found))


def _mode_of(node: dict) -> tuple[GateMode, str, float | None, bool]:
    data = _node_data(node)
    raw = str(data.get("reviewMode") or data.get("gate_mode") or data.get("mode") or "all").strip().lower()
    mapping = {
        "all": GateMode.ALL_MUST_APPROVE,
        "all_must_approve": GateMode.ALL_MUST_APPROVE,
        "any": GateMode.ANY_CAN_APPROVE,
        "any_can_approve": GateMode.ANY_CAN_APPROVE,
        "majority": GateMode.MAJORITY,
        "ratio": GateMode.WEIGHTED,
        "weighted": GateMode.WEIGHTED,
        "sequential": GateMode.ALL_MUST_APPROVE,
        "sequence": GateMode.ALL_MUST_APPROVE,
    }
    mode = mapping.get(raw, GateMode.ALL_MUST_APPROVE)
    sequential = raw in ("sequential", "sequence")
    threshold_raw = data.get("ratioThreshold", data.get("threshold"))
    threshold: float | None = None
    if raw in ("ratio", "weighted"):
        try:
            value = float(threshold_raw) if threshold_raw is not None else 0.5
        except (TypeError, ValueError):
            value = 0.5
        threshold = min(1.0, max(0.0, value))
    return mode, raw, threshold, sequential


async def start_subject_approval(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: str,
    subject_version: str | None,
    created_by: str,
    graph: dict,
    definition_id: str | None = None,
    label: str | None = None,
    reviewer_overrides: dict[str, list[str]] | None = None,
    mode_overrides: dict[str, dict] | None = None,
    commit: bool = True,
) -> WorkflowSubjectInstance:
    """Create a pending approval instance and assign the first review node.

    Raises:
        ValueError: invalid graph / no review node / no explicit user reviewer.
        SubjectApprovalConflict: the subject version already has an instance.
    """

    snapshot = copy.deepcopy(graph)
    validation = validate_dag(snapshot)
    if not validation["valid"]:
        raise ValueError("审批流定义非法:" + "；".join(validation["errors"]))

    nodes = review_nodes(snapshot)
    assignments: dict[str, list[str]] = {}
    for node in nodes:
        node_id = str(node["id"])
        data = node.setdefault("data", {})
        if not isinstance(data, dict):
            data = {}
            node["data"] = data
        override = (mode_overrides or {}).get(node_id) or {}
        for key, value in override.items():
            if value is not None and key not in ("reviewer_ids", "reviewers"):
                data[key] = value
        explicit = (reviewer_overrides or {}).get(node_id)
        ids = list(dict.fromkeys(str(item).strip() for item in (explicit or []) if str(item).strip())) if explicit else _reviewer_ids(node)
        if not ids:
            raise ValueError(f"审批节点 {node_id} 未绑定用户审批人（仅支持 type=user）")
        if len(ids) > 50:
            raise ValueError(f"审批节点 {node_id} 审批人超过 50 人上限")
        assignments[node_id] = ids

    existing = await db.execute(
        select(WorkflowSubjectInstance).where(
            WorkflowSubjectInstance.subject_type == subject_type,
            WorkflowSubjectInstance.subject_id == subject_id,
            WorkflowSubjectInstance.subject_version == subject_version,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise SubjectApprovalConflict("该修订已提交过审批")

    node_order = [str(node["id"]) for node in nodes]
    first_id = node_order[0]
    instance = WorkflowSubjectInstance(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_version=subject_version,
        definition_id=definition_id,
        label=label,
        graph=snapshot,
        node_order=node_order,
        assignments=assignments,
        current_node_id=first_id,
        status="pending",
        created_by=created_by,
    )
    db.add(instance)
    await db.flush()
    for sequence, reviewer_id in enumerate(assignments[first_id], start=1):
        db.add(
            WorkflowSubjectReview(
                instance_id=instance.id,
                node_id=first_id,
                reviewer_id=reviewer_id,
                sequence=sequence,
                status="pending",
            )
        )
    if commit:
        await db.commit()
    else:
        await db.flush()
    await db.refresh(instance)
    return instance


async def get_subject_instance(db: AsyncSession, instance_id: str) -> WorkflowSubjectInstance | None:
    return await db.get(WorkflowSubjectInstance, instance_id)


async def get_active_subject_instance(db: AsyncSession, *, subject_type: str, subject_id: str) -> WorkflowSubjectInstance | None:
    result = await db.execute(
        select(WorkflowSubjectInstance)
        .where(
            WorkflowSubjectInstance.subject_type == subject_type,
            WorkflowSubjectInstance.subject_id == subject_id,
            WorkflowSubjectInstance.status == "pending",
        )
        .order_by(WorkflowSubjectInstance.created_at.desc())
    )
    return result.scalars().first()


async def list_subject_instances(db: AsyncSession, *, subject_type: str, subject_id: str) -> list[WorkflowSubjectInstance]:
    result = await db.execute(select(WorkflowSubjectInstance).where(WorkflowSubjectInstance.subject_type == subject_type, WorkflowSubjectInstance.subject_id == subject_id).order_by(WorkflowSubjectInstance.created_at.desc()))
    return list(result.scalars().all())


async def list_instance_reviews(db: AsyncSession, instance_id: str) -> list[WorkflowSubjectReview]:
    result = await db.execute(select(WorkflowSubjectReview).where(WorkflowSubjectReview.instance_id == instance_id).order_by(WorkflowSubjectReview.node_id, WorkflowSubjectReview.sequence, WorkflowSubjectReview.created_at))
    return list(result.scalars().all())


async def user_is_assigned_reviewer(db: AsyncSession, *, subject_type: str, subject_id: str, reviewer_id: str) -> bool:
    result = await db.execute(
        select(WorkflowSubjectReview.id)
        .join(WorkflowSubjectInstance, WorkflowSubjectReview.instance_id == WorkflowSubjectInstance.id)
        .where(
            WorkflowSubjectInstance.subject_type == subject_type,
            WorkflowSubjectInstance.subject_id == subject_id,
            WorkflowSubjectReview.reviewer_id == reviewer_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _node_by_id(instance: WorkflowSubjectInstance, node_id: str) -> dict:
    main = _main_graph(instance.graph or {})
    for node in main.get("nodes", []):
        if isinstance(node, dict) and str(node.get("id")) == node_id:
            return node
    raise SubjectApprovalNotFound(f"审批节点 {node_id} 不存在")


async def submit_subject_action(
    db: AsyncSession,
    *,
    instance_id: str,
    reviewer_id: str,
    action: str,
    comment: str | None = None,
) -> WorkflowSubjectInstance:
    """Record one reviewer action and advance/decide the approval instance.

    Raises:
        SubjectApprovalNotFound: instance missing.
        SubjectApprovalForbidden: caller is not assigned to the current node.
        SubjectApprovalConflict: duplicate action or instance already decided.
        ValueError: unsupported action.
    """

    if action not in ("approved", "rejected"):
        raise ValueError("审批动作只支持 approved / rejected")

    instance = await db.get(WorkflowSubjectInstance, instance_id)
    if instance is None:
        raise SubjectApprovalNotFound("审批实例不存在")
    if not instance.current_node_id:
        raise SubjectApprovalConflict(f"审批已结束（status={instance.status}）")

    node_id = instance.current_node_id
    node = _node_by_id(instance, node_id)
    _, _, _, sequential = _mode_of(node)

    result = await db.execute(
        select(WorkflowSubjectReview).where(
            WorkflowSubjectReview.instance_id == instance.id,
            WorkflowSubjectReview.node_id == node_id,
            WorkflowSubjectReview.reviewer_id == reviewer_id,
        )
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise SubjectApprovalForbidden("当前用户不是该审批节点的指定审批人")
    if instance.status != "pending":
        raise SubjectApprovalConflict(f"审批已结束（status={instance.status}）")
    if review.status != "pending":
        raise SubjectApprovalConflict(f"该审批人已提交过意见（status={review.status}）")

    if sequential:
        pending_before = await db.execute(
            select(WorkflowSubjectReview.id).where(
                WorkflowSubjectReview.instance_id == instance.id,
                WorkflowSubjectReview.node_id == node_id,
                WorkflowSubjectReview.status == "pending",
                WorkflowSubjectReview.sequence < review.sequence,
            )
        )
        if pending_before.first() is not None:
            raise SubjectApprovalConflict("顺序签必须按指定顺序提交")

    updated = await db.execute(update(WorkflowSubjectReview).where(WorkflowSubjectReview.id == review.id, WorkflowSubjectReview.status == "pending").values(status=action, comment=comment, updated_at=_now()))
    if updated.rowcount == 0:
        raise SubjectApprovalConflict("该审批人已提交过意见")

    reviews = (await db.execute(select(WorkflowSubjectReview).where(WorkflowSubjectReview.instance_id == instance.id, WorkflowSubjectReview.node_id == node_id))).scalars().all()
    judgments = [{"reviewer_id": row.reviewer_id, "status": row.status} for row in reviews if row.status in ("approved", "rejected")]
    mode, _, threshold, _ = _mode_of(node)
    gate = evaluate_gate(mode, len(reviews), judgments, threshold=threshold)

    if gate == GateResult.WAITING:
        await db.commit()
        await db.refresh(instance)
        return instance

    if gate == GateResult.REJECT:
        instance.status = "rejected"
        instance.decided_at = _now()
        await db.execute(
            update(WorkflowSubjectReview)
            .where(
                WorkflowSubjectReview.instance_id == instance.id,
                WorkflowSubjectReview.node_id == node_id,
                WorkflowSubjectReview.status == "pending",
            )
            .values(status="cancelled", updated_at=_now())
        )
        await db.commit()
        await db.refresh(instance)
        return instance

    # Gate passed early (ANY_CAN_APPROVE) or all reviewers acted.  Remaining
    # pending assignments for this node are no longer actionable.
    await db.execute(
        update(WorkflowSubjectReview)
        .where(
            WorkflowSubjectReview.instance_id == instance.id,
            WorkflowSubjectReview.node_id == node_id,
            WorkflowSubjectReview.status == "pending",
        )
        .values(status="cancelled", updated_at=_now())
    )

    order: list[str] = list(instance.node_order or [])
    current_index = order.index(node_id) if node_id in order else len(order) - 1
    next_node_id = order[current_index + 1] if current_index + 1 < len(order) else None
    if next_node_id:
        instance.current_node_id = next_node_id
        for sequence, next_reviewer in enumerate((instance.assignments or {}).get(next_node_id, []), start=1):
            db.add(
                WorkflowSubjectReview(
                    instance_id=instance.id,
                    node_id=next_node_id,
                    reviewer_id=next_reviewer,
                    sequence=sequence,
                    status="pending",
                )
            )
    else:
        instance.status = "approved"
        instance.decided_at = _now()
    await db.commit()
    await db.refresh(instance)
    return instance


def node_label(node: dict) -> str:
    data = _node_data(node)
    return str(data.get("label") or node.get("id") or "")


def node_mode_label(node: dict) -> str:
    _, raw, _, _ = _mode_of(node)
    return raw
