"""Tests for review rejection rollback — apply_rejection_rollback.

Covers:
- Rejection updates current_phase_node to DAG rollback target
- No workflow_id → returns None (no rollback)
- No definition → returns None
- No rejected edge → returns None
- Multiple edges: finds the one with label='rejected'
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.workflow.review import apply_rejection_rollback


class TestApplyRejectionRollback:
    @pytest.mark.asyncio
    async def test_updates_phase_node_to_rollback_target(self):
        project_id = uuid.uuid4()
        wf_id = uuid.uuid4()
        rollback_target = "phase-1"

        mock_project = MagicMock()
        mock_project.workflow_id = wf_id
        mock_project.current_phase_node = "review-1"

        mock_definition = MagicMock()
        mock_definition.graph_json = {
            "edges": [
                {"source": "review-1", "target": rollback_target, "label": "rejected"},
                {"source": "review-1", "target": "phase-2", "label": "approved"},
            ],
        }

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_get(model, pk):
            if pk == project_id:
                return mock_project
            if pk == wf_id:
                return mock_definition
            return None

        mock_db.get = mock_get

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result == rollback_target
        assert mock_project.current_phase_node == rollback_target
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_without_workflow_id(self):
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.workflow_id = None

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_project)

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_without_definition(self):
        project_id = uuid.uuid4()
        wf_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.workflow_id = wf_id

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_get(model, pk):
            if pk == project_id:
                return mock_project
            return None  # No definition found

        mock_db.get = mock_get

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_without_rejected_edge(self):
        project_id = uuid.uuid4()
        wf_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.workflow_id = wf_id
        mock_project.current_phase_node = "review-1"

        mock_definition = MagicMock()
        mock_definition.graph_json = {
            "edges": [
                {"source": "review-1", "target": "phase-2", "label": "approved"},
            ],
        }

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_get(model, pk):
            if pk == project_id:
                return mock_project
            if pk == wf_id:
                return mock_definition
            return None

        mock_db.get = mock_get

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result is None
        assert mock_project.current_phase_node == "review-1"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_project(self):
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_finds_rejected_edge_among_multiple(self):
        """When multiple edges exist, finds the one with label='rejected'."""
        project_id = uuid.uuid4()
        wf_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.workflow_id = wf_id
        mock_project.current_phase_node = "review-1"

        mock_definition = MagicMock()
        mock_definition.graph_json = {
            "edges": [
                {"source": "review-1", "target": "phase-2", "label": "approved"},
                {"source": "review-1", "target": "phase-1", "label": "rejected"},
                {"source": "review-1", "target": "end", "label": "cancelled"},
            ],
        }

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_get(model, pk):
            if pk == project_id:
                return mock_project
            if pk == wf_id:
                return mock_definition
            return None

        mock_db.get = mock_get

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result == "phase-1"
        assert mock_project.current_phase_node == "phase-1"

    @pytest.mark.asyncio
    async def test_empty_edges_list(self):
        project_id = uuid.uuid4()
        wf_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.workflow_id = wf_id
        mock_project.current_phase_node = "review-1"

        mock_definition = MagicMock()
        mock_definition.graph_json = {"edges": []}

        mock_db = AsyncMock()

        async def mock_get(model, pk):
            if pk == project_id:
                return mock_project
            if pk == wf_id:
                return mock_definition
            return None

        mock_db.get = mock_get

        result = await apply_rejection_rollback(mock_db, project_id, "review-1")

        assert result is None
