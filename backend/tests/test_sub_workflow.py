"""TDD tests for sub_workflow node type and child workflow support.

Covers:
- DAG validation accepts sub_workflow nodes
- DAG validation warns about disconnected sub_workflow nodes
- DAG validation with nested graph_json in sub_workflow data
- WorkflowDefinition schemas with sub_workflow in graph_json
- Topological sort includes sub_workflow nodes correctly
- Service layer CRUD with sub_workflow definitions
- sub_workflow node without graph_json is still valid (graceful skip at runtime)
"""
import uuid

import pytest

from app.extensions.workflow.service import validate_dag, topological_sort


# ── Helpers ──

def _make_sub_workflow_graph(extra_nodes=None, extra_edges=None, sub_graph=None):
    """Build a minimal DAG with a sub_workflow node."""
    nodes = [
        {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
        {"id": "phase-start", "type": "phase", "data": {"label": "开始"}},
        {
            "id": "sub-1",
            "type": "sub_workflow",
            "data": {
                "label": "子流程",
                "graph_json": sub_graph or {
                    "nodes": [
                        {"id": "child-phase-1", "type": "phase", "data": {"label": "子阶段1"}},
                        {"id": "child-phase-2", "type": "phase", "data": {"label": "子阶段2"}},
                    ],
                    "edges": [
                        {"source": "child-phase-1", "target": "child-phase-2"},
                    ],
                },
            },
        },
        {"id": "phase-end", "type": "phase", "data": {"label": "结束"}},
    ]
    edges = [
        {"source": "start-node", "target": "phase-start"},
        {"source": "phase-start", "target": "sub-1"},
        {"source": "sub-1", "target": "phase-end"},
    ]
    if extra_nodes:
        nodes.extend(extra_nodes)
    if extra_edges:
        edges.extend(extra_edges)
    return {"nodes": nodes, "edges": edges}


def _make_sub_workflow_node_only():
    """Single sub_workflow node with embedded graph_json."""
    return {
        "nodes": [
            {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
            {
                "id": "sub-only",
                "type": "sub_workflow",
                "data": {
                    "label": "独立子流程",
                    "graph_json": {
                        "nodes": [
                            {"id": "inner-1", "type": "phase", "data": {"label": "内部阶段"}},
                        ],
                        "edges": [],
                    },
                },
            },
        ],
        "edges": [
            {"source": "start-node", "target": "sub-only"},
        ],
    }


# ── DAG Validation ──


class TestSubWorkflowDAGValidation:
    """Verify validate_dag() accepts and correctly checks sub_workflow nodes."""

    def test_sub_workflow_graph_is_valid(self):
        """A well-formed DAG with a sub_workflow node passes validation."""
        graph = _make_sub_workflow_graph()
        result = validate_dag(graph)
        assert result["valid"] is True, f"Expected valid, got errors: {result['errors']}"
        assert len(result["errors"]) == 0

    def test_sub_workflow_node_without_graph_json_is_valid(self):
        """sub_workflow without graph_json is valid (handled gracefully at runtime)."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "start", "type": "phase", "data": {"label": "开始"}},
                {"id": "sub", "type": "sub_workflow", "data": {"label": "空子流程"}},
                {"id": "end", "type": "phase", "data": {"label": "结束"}},
            ],
            "edges": [
                {"source": "start-node", "target": "start"},
                {"source": "start", "target": "sub"},
                {"source": "sub", "target": "end"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"] is True

    def test_disconnected_sub_workflow_node_warns(self):
        """A sub_workflow node with no connections triggers a warning."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "phase-a", "type": "phase", "data": {"label": "A"}},
                {"id": "phase-b", "type": "phase", "data": {"label": "B"}},
                {"id": "sub-disconnected", "type": "sub_workflow", "data": {"label": "未连接"}},
            ],
            "edges": [
                {"source": "start-node", "target": "phase-a"},
                {"source": "phase-a", "target": "phase-b"},
            ],
        }
        result = validate_dag(graph)
        # Disconnected nodes produce warnings, not errors
        disconnected_warnings = [w for w in result["warnings"] if "disconnected" in w.lower()]
        assert len(disconnected_warnings) >= 1

    def test_sub_workflow_can_be_start_node(self):
        """A sub_workflow node directly after START is a valid entry point."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "sub-start", "type": "sub_workflow", "data": {"label": "起始子流程"}},
                {"id": "phase-after", "type": "phase", "data": {"label": "后续"}},
            ],
            "edges": [
                {"source": "start-node", "target": "sub-start"},
                {"source": "sub-start", "target": "phase-after"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"] is True

    def test_mixed_node_types_with_sub_workflow(self):
        """DAG containing all node types including sub_workflow validates."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "p1", "type": "phase", "data": {"label": "阶段"}},
                {"id": "r1", "type": "review", "data": {"label": "审核", "mode": "chapter"}},
                {"id": "c1", "type": "condition", "data": {"label": "条件", "expression": "report.subtype"}},
                {"id": "ai1", "type": "ai_generate", "data": {"label": "AI生成", "aiAssist": True}},
                {"id": "m1", "type": "merge", "data": {"label": "汇聚"}},
                {"id": "sw1", "type": "sub_workflow", "data": {"label": "子流程"}},
            ],
            "edges": [
                {"source": "start-node", "target": "p1"},
                {"source": "p1", "target": "c1"},
                {"source": "c1", "target": "ai1", "label": "true"},
                {"source": "c1", "target": "sw1", "label": "false"},
                {"source": "ai1", "target": "m1"},
                {"source": "sw1", "target": "m1"},
                {"source": "m1", "target": "r1"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"] is True

    def test_single_sub_workflow_node_valid(self):
        """DAG with only a sub_workflow node is valid."""
        graph = _make_sub_workflow_node_only()
        result = validate_dag(graph)
        assert result["valid"] is True, f"Errors: {result['errors']}"


# ── Topological Sort ──


class TestSubWorkflowTopologicalSort:
    """Verify topological_sort() includes sub_workflow nodes in correct order."""

    def test_sub_workflow_in_middle_of_chain(self):
        """phase → sub_workflow → phase should sort sub in the middle."""
        graph = _make_sub_workflow_graph()
        order = topological_sort(graph)
        assert "sub-1" in order
        sub_idx = order.index("sub-1")
        assert order.index("phase-start") < sub_idx
        assert sub_idx < order.index("phase-end")

    def test_sub_workflow_as_first_node(self):
        """sub_workflow directly after START should be second in order."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "sw", "type": "sub_workflow", "data": {"label": "子流程"}},
                {"id": "p2", "type": "phase", "data": {"label": "后续"}},
            ],
            "edges": [
                {"source": "start-node", "target": "sw"},
                {"source": "sw", "target": "p2"},
            ],
        }
        order = topological_sort(graph)
        assert order[0] == "start-node"
        assert order[1] == "sw"

    def test_multiple_sub_workflows_in_parallel(self):
        """Two sub_workflow nodes in parallel branches."""
        graph = {
            "nodes": [
                {"id": "start-node", "type": "system:start", "data": {"label": "项目启动"}},
                {"id": "start", "type": "phase", "data": {"label": "开始"}},
                {"id": "sw-a", "type": "sub_workflow", "data": {"label": "子流程A"}},
                {"id": "sw-b", "type": "sub_workflow", "data": {"label": "子流程B"}},
                {"id": "end", "type": "merge", "data": {"label": "汇聚"}},
            ],
            "edges": [
                {"source": "start-node", "target": "start"},
                {"source": "start", "target": "sw-a"},
                {"source": "start", "target": "sw-b"},
                {"source": "sw-a", "target": "end"},
                {"source": "sw-b", "target": "end"},
            ],
        }
        order = topological_sort(graph)
        # Both sub_workflows should appear before end and after start
        assert order.index("sw-a") < order.index("end")
        assert order.index("sw-b") < order.index("end")
        assert order.index("start") < order.index("sw-a")
        assert order.index("start") < order.index("sw-b")


# ── Schemas ──


class TestSubWorkflowSchemas:
    """Verify schemas accept graph_json with sub_workflow nodes."""

    def test_workflow_definition_create_with_sub_workflow(self):
        """WorkflowDefinitionCreate accepts graph_json with sub_workflow node."""
        from app.extensions.workflow.schemas import WorkflowDefinitionCreate

        graph = _make_sub_workflow_graph()
        req = WorkflowDefinitionCreate(
            name="子流程测试",
            graph_json={"mainGraph": graph},
        )
        assert req.name == "子流程测试"
        assert req.graph_json is not None
        nodes = req.graph_json["mainGraph"].get("nodes", [])
        sub_nodes = [n for n in nodes if n["type"] == "sub_workflow"]
        assert len(sub_nodes) == 1
        assert sub_nodes[0]["id"] == "sub-1"

    def test_workflow_definition_out_with_sub_workflow(self):
        """WorkflowDefinitionOut serializes graph_json with sub_workflow."""
        from app.extensions.workflow.schemas import WorkflowDefinitionOut

        graph = _make_sub_workflow_graph()
        out = WorkflowDefinitionOut(
            id=uuid.uuid4(),
            name="子流程测试",
            graph_json={"mainGraph": graph},
            is_template=False,
            created_by=uuid.uuid4(),
        )
        main_nodes = out.graph_json["mainGraph"]["nodes"]
        node_types = {n["type"] for n in main_nodes}
        assert "sub_workflow" in node_types

    def test_workflow_definition_update_preserves_sub_workflow(self):
        """WorkflowDefinitionUpdate allows partial update of graph_json."""
        from app.extensions.workflow.schemas import WorkflowDefinitionUpdate

        update = WorkflowDefinitionUpdate(name="更新后名称")
        assert update.name == "更新后名称"
        assert update.graph_json is None  # partial update is fine


# ── Service Layer CRUD ──


class TestSubWorkflowServiceCRUD:
    """Verify service layer handles sub_workflow definitions correctly."""

    @pytest.mark.asyncio
    async def test_create_definition_with_sub_workflow(self):
        """create_definition persists a definition containing sub_workflow nodes."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.workflow.service import create_definition

        mock_db = AsyncMock()
        graph = _make_sub_workflow_graph()
        user_id = uuid.uuid4()

        definition = await create_definition(
            db=mock_db,
            name="子流程定义",
            report_type="环评",
            graph_json=graph,
            created_by=user_id,
            is_template=False,
        )

        # Verify the model was created with correct fields
        assert definition.name == "子流程定义"
        assert definition.report_type == "环评"
        assert definition.graph_json == graph
        assert definition.created_by == user_id
        assert definition.is_template is False
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_definitions_includes_sub_workflow(self):
        """list_definitions returns definitions with sub_workflow nodes."""
        from unittest.mock import AsyncMock, MagicMock

        from app.extensions.workflow.service import list_definitions

        mock_db = AsyncMock()

        # Mock count result
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1

        # Mock items result
        mock_def = MagicMock()
        mock_def.graph_json = _make_sub_workflow_graph()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_def]

        mock_db.execute = AsyncMock(side_effect=[mock_count, mock_result])

        items, total = await list_definitions(mock_db)
        assert total == 1
        assert len(items) == 1
        assert "sub_workflow" in str(items[0].graph_json)


# ── Integration: DAG edge cases ──


class TestSubWorkflowEdgeCases:
    """Edge case tests for sub_workflow in workflows."""

    def test_nested_sub_workflow_inside_sub_workflow(self):
        """Deeply nested sub_workflow in sub_workflow data passes validation."""
        inner_inner = {
            "nodes": [
                {"id": "leaf", "type": "phase", "data": {"label": "最内层"}},
            ],
            "edges": [],
        }
        inner = {
            "nodes": [
                {"id": "mid", "type": "phase", "data": {"label": "中层"}},
                {
                    "id": "nested-sub",
                    "type": "sub_workflow",
                    "data": {"label": "嵌套", "graph_json": inner_inner},
                },
            ],
            "edges": [{"source": "mid", "target": "nested-sub"}],
        }
        graph = _make_sub_workflow_graph(sub_graph=inner)
        result = validate_dag(graph)
        assert result["valid"] is True

    def test_empty_sub_graph_is_valid(self):
        """sub_workflow with empty nodes/edges passes validation."""
        graph = _make_sub_workflow_graph(sub_graph={"nodes": [], "edges": []})
        result = validate_dag(graph)
        # The outer DAG is valid; inner DAG is validated only at runtime
        assert result["valid"] is True

    def test_sub_workflow_node_type_preserved_in_roundtrip(self):
        """Graph JSON roundtrip through validate does not modify sub_workflow type."""
        graph = _make_sub_workflow_graph()
        result = validate_dag(graph)
        assert result["valid"] is True
        # validate_dag must not modify the graph
        sub_nodes = [n for n in graph["nodes"] if n["type"] == "sub_workflow"]
        assert len(sub_nodes) == 1
        assert "graph_json" in sub_nodes[0]["data"]
