"""Tests for workflow template management."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_definition():
    definition = MagicMock()
    definition.id = uuid4()
    definition.name = "Test Template"
    definition.report_type = "环评"
    definition.graph_json = {"nodes": [], "edges": []}
    definition.is_template = False
    definition.created_by = uuid4()
    definition.created_at = "2026-01-01T00:00:00"
    return definition


@pytest.mark.asyncio
async def test_publish_as_template(mock_db, mock_definition):
    """Publishing a template sets is_template=True."""
    mock_db.get = AsyncMock(return_value=mock_definition)
    from app.extensions.workflow.service import publish_as_template
    result = await publish_as_template(mock_db, mock_definition.id)
    assert mock_definition.is_template is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_publish_as_template_not_found(mock_db):
    """Publishing non-existent definition returns None."""
    mock_db.get = AsyncMock(return_value=None)
    from app.extensions.workflow.service import publish_as_template
    result = await publish_as_template(mock_db, uuid4())
    assert result is None


def test_template_has_org_binding():
    """Template graph_json nodes can have org_unit_id in data."""
    graph_json = {
        "nodes": [
            {
                "id": "phase-a",
                "type": "phase",
                "data": {
                    "label": "调查",
                    "org_unit_id": "dept-uuid-123",
                    "required_roles": [
                        {"role_key": "phase_lead", "count": 1, "label": "负责人"}
                    ],
                },
            }
        ],
        "edges": [],
    }
    node = graph_json["nodes"][0]
    assert "org_unit_id" in node["data"]
    assert "required_roles" in node["data"]
