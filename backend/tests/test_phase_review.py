"""Tests for PhaseReview model, schemas, and DAG validation."""

import uuid

import pytest

from app.extensions.workflow.models import PhaseReview
from app.extensions.workflow.schemas import (
    PhaseReviewOut,
    ReviewActionRequest,
    ReviewAssignmentCreate,
    ReviewAssignmentItem,
    ReviewStatusResponse,
)
from app.extensions.workflow.service import validate_dag


class TestPhaseReviewModel:
    def test_model_fields(self):
        cols = [c.name for c in PhaseReview.__table__.columns]
        assert "id" in cols
        assert "project_id" in cols
        assert "phase_node" in cols
        assert "chapter_id" in cols
        assert "reviewer_id" in cols
        assert "review_type" in cols
        assert "dimension" in cols
        assert "status" in cols
        assert "comment" in cols


class TestReviewSchemas:
    def test_assignment_create_valid(self):
        item = ReviewAssignmentItem(
            reviewer_id=uuid.uuid4(),
            review_type="chapter",
        )
        req = ReviewAssignmentCreate(
            project_id=uuid.uuid4(),
            phase_node="review-1",
            assignments=[item],
        )
        assert len(req.assignments) == 1

    def test_assignment_dimension(self):
        item = ReviewAssignmentItem(
            reviewer_id=uuid.uuid4(),
            review_type="dimension",
            dimension="technical",
        )
        assert item.dimension == "technical"

    def test_action_request_approved(self):
        req = ReviewActionRequest(action="approved", comment="LGTM")
        assert req.action == "approved"

    def test_action_request_rejected(self):
        req = ReviewActionRequest(action="rejected")
        assert req.action == "rejected"

    def test_action_request_invalid(self):
        with pytest.raises(Exception):
            ReviewActionRequest(action="maybe")

    def test_review_status_response(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=3,
            approved=2,
            rejected=0,
            pending=1,
            all_approved=False,
        )
        assert resp.total == 3
        assert not resp.all_approved

    def test_review_status_all_approved(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=2,
            approved=2,
            rejected=0,
            pending=0,
            all_approved=True,
        )
        assert resp.all_approved


class TestDAGValidation:
    def test_review_node_in_dag(self):
        graph = {
            "nodes": [
                {"id": "phase-1", "type": "phase", "data": {"label": "Write"}},
                {"id": "review-1", "type": "review", "data": {"label": "Review", "mode": "mixed"}},
            ],
            "edges": [{"source": "phase-1", "target": "review-1"}],
        }
        result = validate_dag(graph)
        assert result["valid"]

    def test_dag_with_condition_and_review(self):
        graph = {
            "nodes": [
                {"id": "cond-1", "type": "condition", "data": {"label": "Type?"}},
                {"id": "review-a", "type": "review", "data": {"label": "Review A"}},
                {"id": "review-b", "type": "review", "data": {"label": "Review B"}},
            ],
            "edges": [
                {"source": "cond-1", "target": "review-a", "label": "true"},
                {"source": "cond-1", "target": "review-b", "label": "false"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"]

    def test_empty_graph_invalid(self):
        result = validate_dag({"nodes": [], "edges": []})
        assert not result["valid"]
