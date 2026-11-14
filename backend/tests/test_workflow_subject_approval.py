"""批三十二：workflow 通用 subject 审批（不依赖 ReportProject / Temporal）。"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.database import Base
from app.extensions.workflow import subject_approval as SA


def _graph(
    reviewers: list[str] | None = None,
    *,
    mode: str = "all",
    threshold: float | None = None,
    two_nodes: bool = False,
) -> dict:
    first = {
        "id": "r1",
        "type": "review",
        "data": {
            "label": "商务负责人",
            "reviewMode": mode,
            "reviewer_ids": reviewers or [],
        },
    }
    if threshold is not None:
        first["data"]["ratioThreshold"] = threshold
    nodes = [
        {"id": "start", "type": "system:start", "data": {"label": "开始"}},
        first,
    ]
    edges = [{"id": "e1", "source": "start", "target": "r1"}]
    if two_nodes:
        nodes.append({"id": "r2", "type": "review", "data": {"label": "法务", "reviewMode": "all", "reviewer_ids": ["legal"]}})
        nodes.append({"id": "end", "type": "system:end", "data": {"label": "结束"}})
        edges.extend(
            [
                {"id": "e2", "source": "r1", "target": "r2"},
                {"id": "e3", "source": "r2", "target": "end"},
            ]
        )
    else:
        nodes.append({"id": "end", "type": "system:end", "data": {"label": "结束"}})
        edges.append({"id": "e2", "source": "r1", "target": "end"})
    return {"version": 2, "mainGraph": {"nodes": nodes, "edges": edges}}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SA.WorkflowSubjectInstance.__table__, SA.WorkflowSubjectReview.__table__])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _start(db, graph, *, version="v1"):
    return await SA.start_subject_approval(
        db,
        subject_type="bid_write_task",
        subject_id="task-1",
        subject_version=version,
        created_by="owner",
        graph=graph,
    )


@pytest.mark.asyncio
async def test_all_must_approve_and_duplicate_guard(db):
    instance = await _start(db, _graph(["u1", "u2"]))
    assert instance.status == "pending" and instance.current_node_id == "r1"
    reviews = await SA.list_instance_reviews(db, instance.id)
    assert {review.reviewer_id for review in reviews} == {"u1", "u2"}

    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="approved", comment="同意")
    assert instance.status == "pending"
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u2", action="approved", comment=None)
    assert instance.status == "approved" and instance.decided_at is not None

    with pytest.raises(SA.SubjectApprovalConflict):
        await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u2", action="approved", comment=None)


@pytest.mark.asyncio
async def test_non_assigned_reviewer_forbidden(db):
    instance = await _start(db, _graph(["u1"]))
    with pytest.raises(SA.SubjectApprovalForbidden):
        await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="intruder", action="approved", comment=None)


@pytest.mark.asyncio
async def test_any_can_approve(db):
    instance = await _start(db, _graph(["u1", "u2"], mode="any"))
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="approved", comment=None)
    assert instance.status == "approved"
    reviews = await SA.list_instance_reviews(db, instance.id)
    assert {review.status for review in reviews} == {"approved", "cancelled"}


@pytest.mark.asyncio
async def test_ratio_gate_waits_until_threshold(db):
    instance = await _start(db, _graph(["u1", "u2", "u3"], mode="ratio", threshold=0.5))
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="approved", comment=None)
    assert instance.status == "pending"
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u2", action="approved", comment=None)
    assert instance.status == "approved"


@pytest.mark.asyncio
async def test_sequential_requires_order(db):
    instance = await _start(db, _graph(["u1", "u2"], mode="sequential"))
    with pytest.raises(SA.SubjectApprovalConflict):
        await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u2", action="approved", comment=None)
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="approved", comment=None)
    assert instance.status == "pending"
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u2", action="approved", comment=None)
    assert instance.status == "approved"


@pytest.mark.asyncio
async def test_multi_node_advances(db):
    instance = await _start(db, _graph(["u1"], two_nodes=True))
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="approved", comment=None)
    assert instance.status == "pending" and instance.current_node_id == "r2"
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="legal", action="approved", comment=None)
    assert instance.status == "approved"


@pytest.mark.asyncio
async def test_reject_cancels_remaining(db):
    instance = await _start(db, _graph(["u1", "u2"]))
    instance = await SA.submit_subject_action(db, instance_id=instance.id, reviewer_id="u1", action="rejected", comment="金额不一致")
    assert instance.status == "rejected"
    reviews = await SA.list_instance_reviews(db, instance.id)
    assert {review.status for review in reviews} == {"rejected", "cancelled"}


@pytest.mark.asyncio
async def test_requires_explicit_user_reviewer_and_unique_version(db):
    with pytest.raises(ValueError):
        await _start(db, _graph([]))
    instance = await _start(db, _graph(["u1"]), version="dup")
    assert instance.status == "pending"
    with pytest.raises(SA.SubjectApprovalConflict):
        await _start(db, _graph(["u1"]), version="dup")
