"""Tests for project Pydantic schemas: validation, defaults, serialization."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.project.schemas import (
    VALID_APPROVAL_ACTIONS,
    VALID_MEMBER_ROLES,
    VALID_PROJECT_STATUSES,
    VALID_WORKFLOW_STATUSES,
    ApprovalActionRequest,
    ApprovalStepConfig,
    ApprovalSubmitRequest,
    ChapterOut,
    MemberCreate,
    MemberOut,
    ProjectCreate,
    ProjectListItem,
    ProjectListResponse,
    ProjectOut,
    ProjectUpdate,
)


# ── Validation Constants ──


class TestValidationConstants:
    # test_report_types removed — VALID_REPORT_TYPES is replaced by DB-driven dictionary
    # (business_dictionaries table, category="report_type"). No hardcoded list to validate.

    def test_project_statuses(self):
        # Project status is workflow-driven; the validator allows the full
        # lifecycle set (routers/service set "active"/"in_progress" on the model).
        assert VALID_PROJECT_STATUSES == [
            "setup", "outline", "writing", "editing", "approval",
            "in_progress", "active", "completed", "archived",
        ]

    def test_member_roles_expanded(self):
        assert VALID_MEMBER_ROLES == ["owner", "manager", "editor", "reviewer", "approver", "member"]

    def test_workflow_statuses(self):
        assert VALID_WORKFLOW_STATUSES == ["pending", "in_progress", "approved", "rejected"]

    def test_approval_actions(self):
        assert VALID_APPROVAL_ACTIONS == ["approve", "reject", "comment"]


# ── Chapter Schemas ──


class TestChapterOut:
    def test_defaults(self):
        uid = uuid4()
        pid = uuid4()
        c = ChapterOut(id=uid, project_id=pid, title="Ch1")
        assert c.level == 1
        assert c.sort_order == 0
        assert c.status == "pending"
        assert c.content is None
        assert c.assigned_to is None
        assert c.word_count_target == 3000
        assert c.word_count_current == 0
        assert c.children == []

    def test_nested_children(self):
        uid = uuid4()
        pid = uuid4()
        child = ChapterOut(id=uuid4(), project_id=pid, title="Sub")
        parent = ChapterOut(id=uid, project_id=pid, title="Root", children=[child])
        assert len(parent.children) == 1
        assert parent.children[0].title == "Sub"


# ── Member Schemas ──


class TestMemberCreate:
    def test_default_role_is_member(self):
        uid = uuid4()
        m = MemberCreate(user_id=uid)
        assert m.role == "member"

    def test_custom_role(self):
        uid = uuid4()
        m = MemberCreate(user_id=uid, role="owner")
        assert m.role == "owner"


class TestMemberOut:
    def test_fields(self):
        mid = uuid4()
        pid = uuid4()
        uid = uuid4()
        m = MemberOut(id=mid, project_id=pid, user_id=uid, role="owner")
        assert m.username == ""
        assert m.created_at is None


# ── Project Schemas ──


class TestProjectCreate:
    def test_valid(self):
        p = ProjectCreate(name="Test Project", report_type="environmental_impact")
        assert p.name == "Test Project"
        assert p.template_id is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="", report_type="other")

    def test_with_template(self):
        tid = uuid4()
        p = ProjectCreate(name="T", report_type="other", template_id=tid)
        assert p.template_id == tid


class TestProjectUpdate:
    def test_all_none_by_default(self):
        u = ProjectUpdate()
        assert u.name is None
        assert u.status is None

    def test_partial_update(self):
        u = ProjectUpdate(status="completed")
        assert u.status == "completed"
        assert u.name is None


class TestProjectOut:
    def test_from_attributes_config(self):
        assert ProjectOut.model_config.get("from_attributes") is True

    def test_defaults(self):
        uid = uuid4()
        p = ProjectOut(id=uid, name="Test", report_type="other")
        assert p.status == "active"
        assert p.members == []
        assert p.chapters == []
        assert p.chapter_count == 0
        assert p.thread_id is None
        assert p.created_by is None


class TestProjectListItem:
    def test_from_attributes_config(self):
        assert ProjectListItem.model_config.get("from_attributes") is True

    def test_defaults(self):
        uid = uuid4()
        p = ProjectListItem(id=uid, name="Test", report_type="other")
        assert p.chapter_count == 0
        assert p.member_count == 0
        assert p.template_name is None
        assert p.status == "active"

    def test_with_template_name(self):
        uid = uuid4()
        tid = uuid4()
        p = ProjectListItem(id=uid, name="Test", report_type="other", template_id=tid, template_name="环评模板")
        assert p.template_name == "环评模板"


class TestProjectListResponse:
    def test_empty(self):
        r = ProjectListResponse()
        assert r.items == []
        assert r.total == 0

    def test_with_items(self):
        uid = uuid4()
        item = ProjectListItem(id=uid, name="T", report_type="other")
        r = ProjectListResponse(items=[item], total=1)
        assert len(r.items) == 1
        assert r.total == 1


# ── Approval Schemas ──


class TestApprovalActionRequest:
    def test_valid_approve(self):
        wid = uuid4()
        a = ApprovalActionRequest(workflow_id=wid, action="approve")
        assert a.action == "approve"

    def test_valid_reject(self):
        wid = uuid4()
        a = ApprovalActionRequest(workflow_id=wid, action="reject", comment="Bad")
        assert a.comment == "Bad"

    def test_invalid_action_rejected(self):
        wid = uuid4()
        with pytest.raises(ValidationError):
            ApprovalActionRequest(workflow_id=wid, action="invalid")

    def test_comment_action(self):
        wid = uuid4()
        a = ApprovalActionRequest(workflow_id=wid, action="comment", comment="Note")
        assert a.action == "comment"


class TestApprovalStepConfig:
    def test_fields(self):
        uid = uuid4()
        s = ApprovalStepConfig(step_order=1, step_name="初审", reviewer_id=uid)
        assert s.step_order == 1
        assert s.step_name == "初审"
        assert s.reviewer_id == uid


class TestApprovalSubmitRequest:
    def test_empty(self):
        r = ApprovalSubmitRequest(steps=[])
        assert r.steps == []

    def test_with_steps(self):
        uid = uuid4()
        step = ApprovalStepConfig(step_order=1, step_name="Review", reviewer_id=uid)
        r = ApprovalSubmitRequest(steps=[step])
        assert len(r.steps) == 1
