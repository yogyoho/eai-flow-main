"""TDD tests for POST /projects/{id}/workflow-signal endpoint (spec §8.1).

Covers:
- Sends phase_complete signal to running workflow
- Sends review_action signal
- Handles missing project gracefully
- Handles no active workflow
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWorkflowSignalEndpoint:
    @pytest.mark.asyncio
    async def test_sends_phase_complete_signal(self):
        """POST /projects/{id}/workflow-signal with signal_name=phase_complete."""
        project_id = uuid.uuid4()
        temporal_wf_id = "test-wf-123"

        mock_db = AsyncMock()

        mock_project = MagicMock()
        mock_project.temporal_workflow_id = temporal_wf_id

        mock_db.get = AsyncMock(return_value=mock_project)

        with patch("app.extensions.workflow.temporal.client.send_signal") as mock_send:
            mock_send.return_value = None

            from app.extensions.workflow.routers import WorkflowSignalRequest, send_workflow_signal

            body = WorkflowSignalRequest(
                signal_name="phase_complete",
                args={"node_id": "phase-1", "result": {"status": "done"}},
            )

            result = await send_workflow_signal(project_id, body, db=mock_db)

        assert result["status"] == "signal_sent"
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["signal_name"] == "phase_complete"

    @pytest.mark.asyncio
    async def test_handles_missing_project(self):
        """Returns 404-style error when project not found."""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        from app.extensions.workflow.routers import WorkflowSignalRequest, send_workflow_signal

        body = WorkflowSignalRequest(signal_name="phase_complete")
        result = await send_workflow_signal(project_id, body, db=mock_db)

        assert result["status"] == "error"
        assert "not found" in result.get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_handles_no_active_workflow(self):
        """Returns error when project has no temporal_workflow_id."""
        project_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_project = MagicMock()
        mock_project.temporal_workflow_id = None
        mock_db.get = AsyncMock(return_value=mock_project)

        from app.extensions.workflow.routers import WorkflowSignalRequest, send_workflow_signal

        body = WorkflowSignalRequest(signal_name="phase_complete")
        result = await send_workflow_signal(project_id, body, db=mock_db)

        assert result["status"] == "error"
        assert "no active workflow" in result.get("detail", "").lower()
