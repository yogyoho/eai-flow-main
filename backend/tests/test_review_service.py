"""Tests for the review service layer."""

import uuid

import pytest

from app.extensions.workflow.schemas import (
    PhaseReviewOut,
    ReviewAssignmentCreate,
    ReviewAssignmentItem,
    ReviewStatusResponse,
)
from app.extensions.workflow.service import topological_sort, validate_dag


class TestReviewSchemas:
    def test_assignment_with_chapter(self):
        item = ReviewAssignmentItem(
            chapter_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            review_type="chapter",
        )
        req = ReviewAssignmentCreate(
            project_id=uuid.uuid4(),
            phase_node="review-1",
            assignments=[item],
        )
        assert req.assignments[0].chapter_id is not None

    def test_assignment_with_dimension(self):
        item = ReviewAssignmentItem(
            reviewer_id=uuid.uuid4(),
            review_type="dimension",
            dimension="technical",
        )
        assert item.dimension == "technical"

    def test_invalid_review_type(self):
        with pytest.raises(Exception):
            ReviewAssignmentItem(
                reviewer_id=uuid.uuid4(),
                review_type="invalid",
            )

    def test_status_response_serialization(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=5,
            approved=3,
            rejected=1,
            pending=1,
            all_approved=False,
        )
        d = resp.model_dump()
        assert d["total"] == 5
        assert d["approved"] == 3

    def test_status_response_includes_reviews_list(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=2,
            approved=2,
            rejected=0,
            pending=0,
            all_approved=True,
        )
        d = resp.model_dump()
        assert "reviews" in d
        assert isinstance(d["reviews"], list)

    def test_assignment_create_requires_at_least_one(self):
        with pytest.raises(Exception):
            ReviewAssignmentCreate(
                project_id=uuid.uuid4(),
                phase_node="review-1",
                assignments=[],
            )


class TestDAGValidation:
    def test_complex_dag(self):
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "phase-1", "type": "phase", "data": {"label": "Write"}},
                {"id": "phase-2", "type": "phase", "data": {"label": "Review Phase"}},
                {"id": "review-1", "type": "review", "data": {"label": "Review", "mode": "mixed"}},
                {"id": "cond-1", "type": "condition", "data": {"label": "Type?"}},
                {"id": "phase-3a", "type": "phase", "data": {"label": "Path A"}},
                {"id": "phase-3b", "type": "phase", "data": {"label": "Path B"}},
                {"id": "merge-1", "type": "merge", "data": {"label": "Merge"}},
                {"id": "ai-1", "type": "ai_generate", "data": {"label": "AI Write"}},
            ],
            "edges": [
                {"source": "start-node", "target": "phase-1"},
                {"source": "phase-1", "target": "phase-2"},
                {"source": "phase-2", "target": "review-1"},
                {"source": "review-1", "target": "cond-1"},
                {"source": "cond-1", "target": "phase-3a", "label": "true"},
                {"source": "cond-1", "target": "phase-3b", "label": "false"},
                {"source": "phase-3a", "target": "merge-1"},
                {"source": "phase-3b", "target": "merge-1"},
                {"source": "merge-1", "target": "ai-1"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"]
        assert len(result["errors"]) == 0

    def test_cycle_detected(self):
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "a", "type": "phase", "data": {"label": "A"}},
                {"id": "b", "type": "phase", "data": {"label": "B"}},
                {"id": "c", "type": "phase", "data": {"label": "C"}},
            ],
            "edges": [
                {"source": "start-node", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "c", "target": "a"},
            ],
        }
        result = validate_dag(graph)
        assert not result["valid"]
        assert any("cycle" in e.lower() for e in result["errors"])

    def test_disconnected_node_warning(self):
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "a", "type": "phase", "data": {"label": "A"}},
                {"id": "b", "type": "phase", "data": {"label": "B"}},
                {"id": "c", "type": "phase", "data": {"label": "C"}},
            ],
            "edges": [
                {"source": "start-node", "target": "a"},
                {"source": "a", "target": "b"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"]  # Still valid, just a warning
        assert len(result["warnings"]) >= 1

    def test_empty_graph_invalid(self):
        result = validate_dag({"nodes": [], "edges": []})
        assert not result["valid"]

    def test_unknown_edge_target_error(self):
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "a", "type": "phase", "data": {"label": "A"}},
            ],
            "edges": [
                {"source": "start-node", "target": "a"},
                {"source": "a", "target": "nonexistent"},
            ],
        }
        result = validate_dag(graph)
        assert not result["valid"]
        assert any("unknown" in e.lower() for e in result["errors"])

    def test_single_node_valid(self):
        """Minimal valid DAG: START node with one outgoing edge."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "only", "type": "phase", "data": {"label": "Only"}},
            ],
            "edges": [
                {"source": "start-node", "target": "only"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"]


class TestTopologicalSort:
    def test_linear_order(self):
        graph = {
            "nodes": [
                {"id": "a", "type": "phase", "data": {"label": "A"}},
                {"id": "b", "type": "phase", "data": {"label": "B"}},
                {"id": "c", "type": "phase", "data": {"label": "C"}},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
            ],
        }
        order = topological_sort(graph)
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_diamond_dag(self):
        graph = {
            "nodes": [
                {"id": "a", "type": "phase", "data": {"label": "A"}},
                {"id": "b", "type": "phase", "data": {"label": "B"}},
                {"id": "c", "type": "phase", "data": {"label": "C"}},
                {"id": "d", "type": "phase", "data": {"label": "D"}},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "a", "target": "c"},
                {"source": "b", "target": "d"},
                {"source": "c", "target": "d"},
            ],
        }
        order = topological_sort(graph)
        assert order.index("a") < order.index("d")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")
