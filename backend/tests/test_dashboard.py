"""Tests for dashboard service and API endpoints."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.extensions.dashboard.schemas import (
    CalendarEvent,
    MyProjectItem,
    MyProjectsResponse,
    MyStatsResponse,
    MyTasksResponse,
    NotificationListResponse,
    NotificationOut,
    TaskItem,
)
from app.extensions.dashboard.service import (
    _classify_project_role,
    _compute_priority,
    _compute_urgency,
    get_my_stats,
    get_my_tasks,
)


# ── Priority computation tests ──


def test_compute_urgency_none():
    assert _compute_urgency(None) == "none"


def test_compute_urgency_overdue():
    past = datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1)
    assert _compute_urgency(past) == "overdue"


def test_compute_urgency_today():
    future = datetime.now(timezone.utc) + __import__("datetime").timedelta(minutes=30)
    assert _compute_urgency(future) == "today"


def test_compute_priority_review():
    score = _compute_priority("review", None)
    assert score == 30  # base only


def test_compute_priority_review_overdue():
    past = datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1)
    score = _compute_priority("review", past)
    assert score == 60  # 30 base + 30 overdue


def test_compute_priority_with_blocking():
    score = _compute_priority("phase_lead", None, is_blocking=True)
    assert score == 40  # 15 base + 25 blocking


# ── Role classification tests ──


def test_classify_role_owner():
    member = MagicMock()
    member.role = "owner"
    assert _classify_project_role(member, MagicMock()) == "owner"


def test_classify_role_phase_lead():
    member = MagicMock()
    member.role = "member"
    member.phase_duties = {"phase-a": {"duty": "lead"}}
    assert _classify_project_role(member, MagicMock()) == "phase_lead"


def test_classify_role_reviewer():
    member = MagicMock()
    member.role = "member"
    member.phase_duties = {"phase-a": {"duty": "reviewer"}}
    assert _classify_project_role(member, MagicMock()) == "reviewer"


def test_classify_role_writer():
    member = MagicMock()
    member.role = "member"
    member.phase_duties = {"phase-a": {"duty": "writer"}}
    assert _classify_project_role(member, MagicMock()) == "writer"


def test_classify_role_viewer():
    member = MagicMock()
    member.role = "member"
    member.phase_duties = None
    assert _classify_project_role(member, MagicMock()) == "viewer"


# ── Schema tests ──


def test_task_item_schema():
    task = TaskItem(
        id="review-123",
        type="review",
        priority_score=50,
        project_id=uuid4(),
        project_name="Test Project",
        action_label="开始审核",
        action_url="/projects/123?tab=review",
    )
    assert task.type == "review"
    assert task.priority_score == 50


def test_my_projects_response():
    resp = MyProjectsResponse(
        groups={
            "owner": [
                MyProjectItem(
                    project_id=uuid4(),
                    project_name="P1",
                    role_label="owner",
                )
            ]
        },
        total_count=1,
    )
    assert resp.total_count == 1
    assert "owner" in resp.groups


def test_calendar_event_schema():
    event = CalendarEvent(
        id="milestone-1",
        title="数据收集完成",
        date=datetime.now(timezone.utc),
        type="milestone",
        color="purple",
    )
    assert event.type == "milestone"


# ── Notification schema tests ──


def test_notification_out():
    uid = uuid4()
    n = NotificationOut(
        id=uuid4(),
        user_id=uid,
        type="review_pending",
        title="新审核任务",
        body="请审核第3章",
        is_read=False,
    )
    assert n.type == "review_pending"
    assert n.is_read is False


# ── Integration-like tests (mocked DB) ──


@pytest.mark.asyncio
async def test_get_my_tasks_empty():
    """Empty task list for user with no memberships."""
    db = AsyncMock()
    # No reviews
    db.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    result = await get_my_tasks(db, uuid4())
    assert isinstance(result, MyTasksResponse)
    assert result.total_count == 0
    assert result.urgent_count == 0


@pytest.mark.asyncio
async def test_get_my_stats_empty():
    """Empty stats for user with no activity."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    result = await get_my_stats(db, uuid4())
    assert isinstance(result, MyStatsResponse)
    assert result.projects_count == 0
    assert result.pending_reviews == 0
