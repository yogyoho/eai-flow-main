"""Bid-write approval: immutable revisions on top of workflow subject approvals.

The mutable editor buffer stays in ``bid_write_task_documents``.  Submitting an
approval freezes a new ``bid_write_document_revisions`` row and starts a generic
workflow subject approval.  Approval never reads the mutable buffer again.
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.workflow import subject_approval

from . import crud
from .models import BidWriteDocumentRevision, TaskDocument, WriteTask

_AST_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SUBJECT_TYPE = "bid_write_task"


class ApprovalError(Exception):
    """Business-level approval failure mapped to an HTTP status by the router."""


class ApprovalConflict(ApprovalError):
    pass


class ApprovalForbidden(ApprovalError):
    pass


class ApprovalNotFound(ApprovalError):
    pass


async def has_pending_approval(db: AsyncSession, task_id: str) -> bool:
    return await subject_approval.get_active_subject_instance(db, subject_type=SUBJECT_TYPE, subject_id=task_id) is not None


def canonical_hash(ast: dict) -> str:
    payload = json.dumps(ast, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_ast(ast: dict, schema_version: str) -> None:
    if not isinstance(ast, dict) or ast.get("type") != "doc":
        raise ApprovalError('ast 根节点 type 必须为 "doc"')
    if not _AST_VERSION_RE.match(schema_version or ""):
        raise ApprovalError(f"schema_version 需为 semver(收到:{schema_version!r})")


def default_graph(*, reviewer_ids: list[str], gate_mode: str = "all", ratio_threshold: float | None = None, label: str = "商务负责人审批") -> dict:
    """Built-in single-node approval graph, shaped like a workflow definition."""

    data: dict = {
        "label": label,
        "reviewMode": gate_mode,
        "reviewer_ids": list(reviewer_ids),
    }
    if ratio_threshold is not None:
        data["ratioThreshold"] = ratio_threshold
    return {
        "version": 2,
        "mainGraph": {
            "nodes": [
                {"id": "start", "type": "system:start", "data": {"label": "提交审批"}},
                {"id": "review-1", "type": "review", "data": data},
                {"id": "end", "type": "system:end", "data": {"label": "审批完成"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "review-1"},
                {"id": "e2", "source": "review-1", "target": "end"},
            ],
        },
    }


async def load_definition_graph(db: AsyncSession, definition_id: str) -> tuple[dict, str]:
    """Load a workflow definition graph. Imported lazily to keep SQLite bid tests
    independent from the PostgreSQL-specific workflow ORM types."""

    import uuid

    from app.extensions.workflow.models import WorkflowDefinition

    try:
        key = uuid.UUID(str(definition_id))
    except (ValueError, TypeError) as exc:
        raise ApprovalError("workflow_definition_id 非法") from exc
    definition = await db.get(WorkflowDefinition, key)
    if definition is None:
        raise ApprovalNotFound("审批流定义不存在")
    graph = definition.graph_json
    if not isinstance(graph, dict) or not graph:
        raise ApprovalError("审批流定义 graph 为空")
    return graph, definition.name


def _assertion_snapshot(ctx: dict, ast: dict) -> dict:
    try:
        from app.extensions.bid_write.executor.editor import run_editor_assertions

        payload = run_editor_assertions(ctx, ast)
        summary = payload.get("summary") or {}
        return {
            "status": "ok",
            "run_at": payload.get("run_at"),
            "summary": summary,
            "blocked": bool((summary.get("d0") or 0) > 0),
        }
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - snapshot failure must be recorded, not hidden
        return {"status": "unavailable", "reason": str(exc)[:500]}


def _node_map(graph: dict) -> dict[str, dict]:
    main = graph.get("mainGraph", graph) if isinstance(graph, dict) else {}
    return {str(node.get("id")): node for node in main.get("nodes", []) if isinstance(node, dict) and node.get("id")}


def _revision_summary(revision: BidWriteDocumentRevision) -> dict:
    return {
        "id": revision.id,
        "revision_no": revision.revision_no,
        "status": revision.status,
        "doc_hash": revision.doc_hash,
        "schema_version": revision.schema_version,
        "assertion_snapshot": revision.assertion_snapshot or {},
        "approval_instance_id": revision.approval_instance_id,
        "hash_ok": canonical_hash(revision.ast or {}) == revision.doc_hash,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
        "submitted_at": revision.submitted_at.isoformat() if revision.submitted_at else None,
        "decided_at": revision.decided_at.isoformat() if revision.decided_at else None,
    }


def revision_detail(revision: BidWriteDocumentRevision, *, include_ast: bool = True) -> dict:
    out = _revision_summary(revision)
    if include_ast:
        out["ast"] = revision.ast
    return out


async def _instance_payload(db: AsyncSession, instance, current_user: str) -> dict:
    reviews = await subject_approval.list_instance_reviews(db, instance.id)
    nodes = _node_map(instance.graph or {})
    current_node = nodes.get(instance.current_node_id or "", {})
    my_review = next(
        (review for review in reviews if review.reviewer_id == current_user and review.node_id == instance.current_node_id and review.status == "pending"),
        None,
    )
    return {
        "instance_id": instance.id,
        "status": instance.status,
        "current_node_id": instance.current_node_id,
        "current_node_label": subject_approval.node_label(current_node) if current_node else "",
        "gate_mode": subject_approval.node_mode_label(current_node) if current_node else "",
        "definition_id": instance.definition_id,
        "workflow_source": "definition" if instance.definition_id else "builtin",
        "label": instance.label,
        "created_by": instance.created_by,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "decided_at": instance.decided_at.isoformat() if instance.decided_at else None,
        "can_act": bool(instance.status == "pending" and my_review is not None),
        "my_review": (
            {
                "id": my_review.id,
                "node_id": my_review.node_id,
                "reviewer_id": my_review.reviewer_id,
                "status": my_review.status,
                "comment": my_review.comment,
            }
            if my_review is not None
            else None
        ),
        "reviews": [
            {
                "id": review.id,
                "node_id": review.node_id,
                "node_label": subject_approval.node_label(nodes.get(review.node_id, {})),
                "reviewer_id": review.reviewer_id,
                "reviewer_role": review.reviewer_role,
                "sequence": review.sequence,
                "status": review.status,
                "comment": review.comment,
                "created_at": review.created_at.isoformat() if review.created_at else None,
                "updated_at": review.updated_at.isoformat() if review.updated_at else None,
            }
            for review in reviews
        ],
    }


async def get_approval_state(db: AsyncSession, task_id: str, owner_id: str, current_user: str | None = None) -> dict:
    revisions = await crud.list_revisions(db, task_id, owner_id)
    latest = revisions[0] if revisions else None
    viewer = current_user or owner_id
    if latest is None:
        return {"revision": None, "approval": None, "revisions": [], "is_owner": viewer == owner_id}
    instance = None
    if latest.approval_instance_id:
        instance = await subject_approval.get_subject_instance(db, latest.approval_instance_id)
    if instance is None:
        active = await subject_approval.get_active_subject_instance(db, subject_type=SUBJECT_TYPE, subject_id=task_id)
        instance = active
    return {
        "revision": _revision_summary(latest),
        "is_owner": viewer == owner_id,
        "approval": (await _instance_payload(db, instance, viewer)) if instance is not None else None,
        "revisions": [_revision_summary(revision) for revision in revisions],
    }


async def submit_revision(
    db: AsyncSession,
    *,
    task: WriteTask,
    owner_id: str,
    body,
    ctx: dict,
) -> dict:
    """Freeze a revision and start its workflow subject approval."""

    latest = await crud.latest_revision(db, task.id, owner_id)
    if latest is not None and latest.status in ("submitted", "approved"):
        if latest.status == "approved":
            raise ApprovalConflict("正文已批准，修订已锁定；如确需修改请从新修订流程重开")
        raise ApprovalConflict("正文正在审批中，不能重复提交")
    active = await subject_approval.get_active_subject_instance(db, subject_type=SUBJECT_TYPE, subject_id=task.id)
    if active is not None:
        raise ApprovalConflict("该任务已有进行中的审批实例")

    if body.ast is not None:
        _validate_ast(body.ast, body.schema_version)
        ast = body.ast
        schema_version = body.schema_version
    else:
        doc: TaskDocument | None = await crud.get_document(db, task_id=task.id, owner_id=owner_id)
        if doc is None:
            raise ApprovalConflict("正文尚未保存，不能提交审批")
        ast = doc.ast or {}
        schema_version = body.schema_version or doc.schema_version
        _validate_ast(ast, schema_version)

    doc_hash = canonical_hash(ast)
    if body.document_hash and body.document_hash != doc_hash:
        raise ApprovalConflict("正文哈希不匹配（可能已被他人修改），请刷新后重试")
    body.schema_version = schema_version

    graph: dict
    definition_id: str | None = body.workflow_definition_id
    label = body.label or "商务投标正文审批"
    if definition_id:
        graph, definition_name = await load_definition_graph(db, definition_id)
        label = body.label or f"{definition_name} · 投标正文审批"
        nodes = subject_approval.review_nodes(graph)
        first_node_id = str(nodes[0]["id"])
        overrides = {first_node_id: body.reviewer_ids} if body.reviewer_ids else None
        mode_overrides = {
            first_node_id: {
                "reviewMode": body.gate_mode,
                "ratioThreshold": body.ratio_threshold,
            }
        }
    else:
        if not body.reviewer_ids:
            raise ApprovalError("内置审批流需要至少 1 名 reviewer_ids 审批人")
        graph = default_graph(
            reviewer_ids=body.reviewer_ids,
            gate_mode=body.gate_mode or "all",
            ratio_threshold=body.ratio_threshold,
            label=body.label or "商务负责人审批",
        )
        first_node_id = "review-1"
        overrides = None
        mode_overrides = {}

    if body.ast is not None:
        await crud.put_document(db, task_id=task.id, owner_id=owner_id, ast=ast, schema_version=schema_version, commit=False)

    revision = BidWriteDocumentRevision(
        task_id=task.id,
        owner_id=owner_id,
        revision_no=(latest.revision_no + 1) if latest is not None else 1,
        ast=ast,
        schema_version=schema_version,
        doc_hash=doc_hash,
        assertion_snapshot=_assertion_snapshot(ctx, ast),
        status="submitted",
    )
    db.add(revision)
    await db.flush()
    try:
        instance = await subject_approval.start_subject_approval(
            db,
            subject_type=SUBJECT_TYPE,
            subject_id=task.id,
            subject_version=revision.id,
            created_by=owner_id,
            graph=graph,
            definition_id=definition_id,
            label=label,
            reviewer_overrides=overrides,
            mode_overrides=mode_overrides,
            commit=False,
        )
    except Exception:
        await db.rollback()
        raise
    revision.approval_instance_id = instance.id
    await db.commit()
    await db.refresh(revision)
    return await get_approval_state(db, task.id, owner_id)


async def act_on_approval(
    db: AsyncSession,
    *,
    task_id: str,
    owner_id: str,
    instance_id: str,
    reviewer_id: str,
    action: str,
    comment: str | None,
) -> dict:
    instance = await subject_approval.get_subject_instance(db, instance_id)
    if instance is None or instance.subject_type != SUBJECT_TYPE or instance.subject_id != task_id:
        raise ApprovalNotFound("审批实例不存在")
    try:
        instance = await subject_approval.submit_subject_action(
            db,
            instance_id=instance_id,
            reviewer_id=reviewer_id,
            action=action,
            comment=comment,
        )
    except subject_approval.SubjectApprovalForbidden as exc:
        raise ApprovalForbidden(str(exc)) from exc
    except subject_approval.SubjectApprovalConflict as exc:
        raise ApprovalConflict(str(exc)) from exc

    revision = next(
        (row for row in await crud.list_revisions(db, task_id, owner_id) if row.approval_instance_id == instance.id),
        None,
    )
    if revision is None and instance.subject_version:
        revision = await crud.get_revision(db, instance.subject_version, task_id, owner_id)
    if revision is not None and instance.status in ("approved", "rejected"):
        await crud.set_revision_status(db, revision, instance.status)
    return await get_approval_state(db, task_id, owner_id, current_user=reviewer_id)
