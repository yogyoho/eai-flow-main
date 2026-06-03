"""Tests for workflow template management — approval workflow, visibility, state transitions."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.workflow.models import TemplateApproval, WorkflowDefinition


# ── Task 1: Model field tests ──


class TestWorkflowDefinitionModel:
    """Test model field defaults and assignment."""

    def test_workflow_definition_has_template_fields(self):
        wf = WorkflowDefinition(
            name="Test Template",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            description="A test template",
            template_status="draft",
            visible_dept_ids=["dept-1", "dept-2"],
            version=1,
        )
        assert wf.description == "A test template"
        assert wf.template_status == "draft"
        assert wf.visible_dept_ids == ["dept-1", "dept-2"]
        assert wf.version == 1

    def test_workflow_definition_defaults(self):
        """Defaults are declared on the model columns and applied on DB INSERT,
        not at Python construction time. Verify the column default declarations exist."""
        from sqlalchemy import inspect as sa_inspect_func

        mapper = sa_inspect_func(WorkflowDefinition)
        col_defaults = {c.key: c.default for c in mapper.columns if c.default is not None}
        assert "template_status" in col_defaults
        assert col_defaults["template_status"].arg == "draft"
        assert "version" in col_defaults
        assert col_defaults["version"].arg == 1

        # Verify nullable fields default to None at construction time
        wf = WorkflowDefinition(name="Defaults", graph_json={"nodes": [], "edges": []})
        assert wf.visible_dept_ids is None
        assert wf.description is None

    def test_template_approval_creation(self):
        user_id = uuid.uuid4()
        approval = TemplateApproval(
            template_id=uuid.uuid4(),
            requester_id=user_id,
            status="pending",
        )
        assert approval.status == "pending"
        assert approval.reviewer_id is None
        assert approval.comment is None
        assert approval.template_id is not None


# ── Task 3: Service layer tests ──

from app.extensions.workflow.service import (
    list_approvals,
    review_approval,
    submit_for_approval,
    withdraw_approval,
)


class TestSubmitForApproval:
    @pytest.mark.asyncio
    async def test_submit_from_draft(self):
        user_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Submit Test",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            template_status="draft",
            created_by=user_id,
        )
        wf.id = uuid.uuid4()

        db = AsyncMock()
        db.get = AsyncMock(return_value=wf)
        db.add = MagicMock()
        db.commit = AsyncMock()

        async def mock_refresh(obj, **kwargs):
            if isinstance(obj, TemplateApproval):
                obj.id = uuid.uuid4()
            return obj

        db.refresh = AsyncMock(side_effect=mock_refresh)

        approval = await submit_for_approval(db, wf.id, user_id)
        assert approval.status == "pending"
        assert approval.template_id == wf.id
        assert wf.template_status == "pending_approval"

    @pytest.mark.asyncio
    async def test_submit_from_rejected(self):
        user_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Resubmit Test",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            template_status="rejected",
            created_by=user_id,
        )
        wf.id = uuid.uuid4()

        db = AsyncMock()
        db.get = AsyncMock(return_value=wf)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        approval = await submit_for_approval(db, wf.id, user_id)
        assert approval.status == "pending"
        assert wf.template_status == "pending_approval"

    @pytest.mark.asyncio
    async def test_submit_fails_for_published(self):
        user_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Published",
            graph_json={"nodes": [], "edges": []},
            template_status="published",
        )
        wf.id = uuid.uuid4()

        db = AsyncMock()
        db.get = AsyncMock(return_value=wf)

        with pytest.raises(ValueError, match="Cannot submit template in status"):
            await submit_for_approval(db, wf.id, user_id)

    @pytest.mark.asyncio
    async def test_submit_fails_for_not_found(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Template not found"):
            await submit_for_approval(db, uuid.uuid4(), uuid.uuid4())


class TestReviewApproval:
    @pytest.mark.asyncio
    async def test_review_approve(self):
        requester_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Review Test",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            template_status="pending_approval",
            created_by=requester_id,
        )
        wf.id = uuid.uuid4()

        approval = TemplateApproval(
            template_id=wf.id,
            requester_id=requester_id,
            status="pending",
        )
        approval.id = uuid.uuid4()

        db = AsyncMock()
        # First call returns approval, second returns wf
        db.get = AsyncMock(side_effect=[approval, wf])
        db.commit = AsyncMock()

        async def mock_refresh(obj, **kwargs):
            return obj

        db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await review_approval(db, approval.id, reviewer_id, "approved", "Looks good")
        assert result.status == "approved"
        assert result.reviewer_id == reviewer_id
        assert wf.template_status == "published"
        assert wf.is_template is True
        assert result.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_review_reject(self):
        requester_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Reject Test",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            template_status="pending_approval",
            created_by=requester_id,
        )
        wf.id = uuid.uuid4()

        approval = TemplateApproval(
            template_id=wf.id,
            requester_id=requester_id,
            status="pending",
        )
        approval.id = uuid.uuid4()

        db = AsyncMock()
        db.get = AsyncMock(side_effect=[approval, wf])
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj, **kw: obj)

        result = await review_approval(db, approval.id, reviewer_id, "rejected", "Missing review node")
        assert result.status == "rejected"
        assert wf.template_status == "rejected"

    @pytest.mark.asyncio
    async def test_review_already_processed(self):
        approval = TemplateApproval(
            template_id=uuid.uuid4(),
            requester_id=uuid.uuid4(),
            status="approved",
        )
        approval.id = uuid.uuid4()

        db = AsyncMock()
        db.get = AsyncMock(return_value=approval)

        with pytest.raises(ValueError, match="Approval already"):
            await review_approval(db, approval.id, uuid.uuid4(), "approved")

    @pytest.mark.asyncio
    async def test_review_not_found(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Approval not found"):
            await review_approval(db, uuid.uuid4(), uuid.uuid4(), "approved")


class TestWithdrawApproval:
    @pytest.mark.asyncio
    async def test_withdraw_pending(self):
        user_id = uuid.uuid4()
        wf = WorkflowDefinition(
            name="Withdraw Test",
            graph_json={"nodes": [], "edges": []},
            is_template=True,
            template_status="pending_approval",
            created_by=user_id,
        )
        wf.id = uuid.uuid4()

        approval = TemplateApproval(
            template_id=wf.id,
            requester_id=user_id,
            status="pending",
        )

        db = AsyncMock()

        # Mock the execute call for the select query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = approval
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        # get returns wf for the definition lookup
        db.get = AsyncMock(return_value=wf)
        db.commit = AsyncMock()

        result = await withdraw_approval(db, wf.id, user_id)
        assert result is True
        assert approval.status == "withdrawn"
        assert wf.template_status == "draft"

    @pytest.mark.asyncio
    async def test_withdraw_no_pending(self):
        db = AsyncMock()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        result = await withdraw_approval(db, uuid.uuid4(), uuid.uuid4())
        assert result is False


class TestListApprovals:
    @pytest.mark.asyncio
    async def test_list_approvals(self):
        user_id = uuid.uuid4()
        template_id = uuid.uuid4()

        approval = TemplateApproval(
            template_id=template_id,
            requester_id=user_id,
            status="pending",
        )

        db = AsyncMock()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [approval]
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        approvals = await list_approvals(db, template_id)
        assert len(approvals) == 1
        assert approvals[0].status == "pending"

    @pytest.mark.asyncio
    async def test_list_approvals_empty(self):
        db = AsyncMock()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        approvals = await list_approvals(db, uuid.uuid4())
        assert len(approvals) == 0
