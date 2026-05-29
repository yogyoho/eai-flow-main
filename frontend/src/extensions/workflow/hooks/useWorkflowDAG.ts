"use client";

import { useCallback } from "react";
import { addEdge, useEdgesState, useNodesState, type Connection } from "@xyflow/react";

import type { DAGNode, DAGNodeData, DAGNodeType, DAGEdge, WorkflowGraph } from "../types";

let nodeCounter = 0;

function createNodeId(type: DAGNodeType): string {
  nodeCounter += 1;
  return `${type}-${nodeCounter}-${Date.now()}`;
}

function getDefaultData(type: DAGNodeType): DAGNodeData {
  switch (type) {
    case "phase":
      return { label: "新阶段" };
    case "review":
      return { label: "新审核", mode: "chapter" };
    case "condition":
      return { label: "新条件", expression: "" };
    case "ai_generate":
      return { label: "AI 生成", aiAssist: true };
    case "merge":
      return { label: "汇聚" };
  }
}

export function useWorkflowDAG() {
  const [nodes, setNodes, onNodesChange] = useNodesState<DAGNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<DAGEdge>([]);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e-${connection.source}-${connection.target}-${Date.now()}`,
          },
          eds,
        ),
      );
    },
    [setEdges],
  );

  const addNode = useCallback(
    (type: DAGNodeType, position: { x: number; y: number }) => {
      const id = createNodeId(type);
      const newNode: DAGNode = {
        id,
        type,
        position,
        data: getDefaultData(type),
      };
      setNodes((nds) => [...nds, newNode]);
      return id;
    },
    [setNodes],
  );

  const removeNode = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    },
    [setNodes, setEdges],
  );

  const updateNodeData = useCallback(
    (id: string, data: Partial<DAGNodeData>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...data } } : n)),
      );
    },
    [setNodes],
  );

  const toGraphJson = useCallback((): WorkflowGraph => {
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
        data: { ...n.data },
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      })),
    };
  }, [nodes, edges]);

  const fromGraphJson = useCallback((graph: WorkflowGraph) => {
    setNodes(
      graph.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
    );
    setEdges(
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      })),
    );
  }, [setNodes, setEdges]);

  return {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    removeNode,
    updateNodeData,
    toGraphJson,
    fromGraphJson,
  };
}
