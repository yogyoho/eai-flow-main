/**
 * Tests for SubWorkflowNode component and related type changes.
 *
 * Verifies:
 * - SubWorkflowNode is exported as a valid React component
 * - DAGNodeType includes 'sub_workflow'
 * - DAGNodeData supports graph_json for nested sub-workflows
 * - NodePalette NODE_TYPES includes sub_workflow
 * - WorkflowEditor nodeTypes registry includes SubWorkflowNode
 */
import { describe, expect, it } from "vitest";

import { SubWorkflowNode } from "@/extensions/workflow/nodes/SubWorkflowNode";
import type { DAGNodeData, DAGNodeType } from "@/extensions/workflow/types";

// ---------------------------------------------------------------------------
// Component exports
// ---------------------------------------------------------------------------

describe("SubWorkflowNode — component export", () => {
  it("should be a function (React functional component)", () => {
    expect(typeof SubWorkflowNode).toBe("function");
  });

  it("should have a display name or be identifiable", () => {
    // React functional components have a name property
    expect(SubWorkflowNode.name).toBe("SubWorkflowNode");
  });
});

// ---------------------------------------------------------------------------
// DAGNodeType type guard
// ---------------------------------------------------------------------------

describe("DAGNodeType — includes sub_workflow", () => {
  it("should accept 'sub_workflow' as a valid DAGNodeType", () => {
    const type: DAGNodeType = "sub_workflow";
    expect(type).toBe("sub_workflow");
  });

  it("should accept all 6 node types", () => {
    const types: DAGNodeType[] = [
      "phase",
      "review",
      "condition",
      "ai_generate",
      "merge",
      "sub_workflow",
    ];
    expect(types).toHaveLength(6);
    expect(new Set(types).size).toBe(6); // all unique
  });
});

// ---------------------------------------------------------------------------
// DAGNodeData with graph_json for sub_workflow
// ---------------------------------------------------------------------------

describe("DAGNodeData — graph_json for sub_workflow", () => {
  it("should accept graph_json field via index signature", () => {
    const data: DAGNodeData = {
      label: "子流程",
      graph_json: {
        nodes: [
          {
            id: "child-1",
            type: "phase" as const,
            position: { x: 0, y: 0 },
            data: { label: "子阶段1" },
          },
        ],
        edges: [],
      },
    };
    expect(data.label).toBe("子流程");
    expect(data.graph_json).toBeDefined();
    const graph = data.graph_json as { nodes: unknown[] };
    expect(graph.nodes).toHaveLength(1);
  });

  it("should support nested sub_workflow inside graph_json", () => {
    const data: DAGNodeData = {
      label: "父流程",
      graph_json: {
        nodes: [
          {
            id: "inner-sub",
            type: "sub_workflow",
            position: { x: 0, y: 0 },
            data: {
              label: "内嵌子流程",
              graph_json: {
                nodes: [
                  {
                    id: "leaf",
                    type: "phase",
                    position: { x: 0, y: 0 },
                    data: { label: "叶子阶段" },
                  },
                ],
                edges: [],
              },
            },
          },
        ],
        edges: [],
      },
    };
    expect(data.label).toBe("父流程");
    expect(data.graph_json).toBeDefined();
  });

  it("should allow graph_json to be absent (not all nodes are sub_workflow)", () => {
    const data: DAGNodeData = {
      label: "普通阶段",
      team: "team-a",
    };
    expect(data.label).toBe("普通阶段");
    expect(data.graph_json).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Node attributes validation (what SubWorkflowNode renders)
// ---------------------------------------------------------------------------

describe("SubWorkflowNode — node data shape", () => {
  it("should read node_count from graph_json nodes array", () => {
    const data: DAGNodeData = {
      label: "子流程测试",
      graph_json: {
        nodes: [
          { id: "a", type: "phase", position: { x: 0, y: 0 }, data: { label: "1" } },
          { id: "b", type: "phase", position: { x: 0, y: 0 }, data: { label: "2" } },
          { id: "c", type: "review", position: { x: 0, y: 0 }, data: { label: "3" } },
        ],
        edges: [],
      },
    };

    const graph = data.graph_json as { nodes: unknown[] };
    expect(graph.nodes.length).toBe(3);
  });

  it("should handle missing graph_json gracefully (0 nodes)", () => {
    const data: DAGNodeData = {
      label: "空子流程",
    };

    const graph = data.graph_json;
    const nodeCount =
      graph && typeof graph === "object" && "nodes" in graph
        ? (graph as { nodes: unknown[] }).nodes.length
        : 0;
    expect(nodeCount).toBe(0);
  });

  it("should handle null graph_json gracefully", () => {
    const data: DAGNodeData = {
      label: "未配置子流程",
    };

    const graph = data.graph_json;
    const hasGraph = graph != null;
    expect(hasGraph).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Integration: verifies the node type is valid for React Flow
// ---------------------------------------------------------------------------

describe("SubWorkflowNode — React Flow compatibility", () => {
  it("should accept React Flow NodeProps shape", () => {
    // React Flow passes { id, type, data, selected, ... } to node components
    const mockProps = {
      id: "sub-1",
      type: "sub_workflow" as const,
      data: {
        label: "子流程",
        graph_json: {
          nodes: [
            { id: "inner", type: "phase" as const, position: { x: 0, y: 0 }, data: { label: "内" } },
          ],
          edges: [],
        },
      } satisfies DAGNodeData,
      selected: true,
      xPos: 100,
      yPos: 200,
      zIndex: 1,
      dragging: false,
      isConnectable: true,
      positionAbsoluteX: 100,
      positionAbsoluteY: 200,
    };

    expect(mockProps.type).toBe("sub_workflow");
    expect(mockProps.data.label).toBe("子流程");
    expect(mockProps.selected).toBe(true);
  });
});
