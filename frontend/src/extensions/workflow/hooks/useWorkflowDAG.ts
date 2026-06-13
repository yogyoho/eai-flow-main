"use client";

import { useCallback, useRef } from "react";
import { addEdge, useEdgesState, useNodesState, type Connection } from "@xyflow/react";

import type { DAGNode, DAGNodeData, DAGNodeType, DAGEdge, FlatGraph, WorkflowGraph } from "../types";

let nodeCounter = 0;

function createNodeId(type: DAGNodeType): string {
  nodeCounter += 1;
  return `${type}-${nodeCounter}-${Date.now()}`;
}

function getDefaultData(type: DAGNodeType): DAGNodeData {
  switch (type) {
    case "subflow":
      return { label: "新子流程" };
    case "task":
      return { label: "新任务", aiAssist: true };
    case "review":
      return { label: "新审核", mode: "chapter" };
    case "ai_generate":
      return { label: "AI 生成", aiAssist: true };
    case "condition":
      return { label: "新条件", expression: "" };
    case "merge":
      return { label: "汇聚" };
  }
}

export function useWorkflowDAG() {
  const [nodes, setNodes, onNodesChange] = useNodesState<DAGNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<DAGEdge>([]);

  // Store the full graph for sub-graph navigation
  const fullGraphRef = useRef<WorkflowGraph | null>(null);

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

  /** Get a flat graph from the current canvas state. */
  const currentFlatGraph = useCallback((): FlatGraph => ({
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
  }), [nodes, edges]);

  /** Serialize full graph (mainGraph + all subGraphs). */
  const toGraphJson = useCallback((): WorkflowGraph => {
    const graph: WorkflowGraph = {
      version: 2,
      mainGraph: currentFlatGraph(),
      subGraphs: fullGraphRef.current?.subGraphs ?? {},
    };
    return graph;
  }, [currentFlatGraph]);

  /** Load mainGraph onto the canvas. */
  const fromGraphJson = useCallback((graph: WorkflowGraph) => {
    fullGraphRef.current = graph;
    const mainGraph = graph.mainGraph;
    if (!mainGraph) {
      console.warn("fromGraphJson: graph is missing mainGraph", graph);
      return;
    }
    setNodes(
      (mainGraph.nodes ?? []).map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
    );
    setEdges(
      (mainGraph.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      })),
    );
  }, [setNodes, setEdges]);

  /** Save current canvas into a subGraph slot, then load the subGraph for `subflowId`. */
  const enterSubflow = useCallback((subflowId: string) => {
    if (!fullGraphRef.current) return;
    const graph = fullGraphRef.current;

    // Save current canvas into mainGraph
    graph.mainGraph = currentFlatGraph();

    // Load the subGraph for this subflow
    const subGraph = graph.subGraphs?.[subflowId] ?? { nodes: [], edges: [] };
    setNodes(
      (subGraph.nodes ?? []).map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
    );
    setEdges(
      (subGraph.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      })),
    );
  }, [currentFlatGraph, setNodes, setEdges]);

  /** Save current canvas into the active subGraph slot, then load mainGraph. */
  const exitSubflow = useCallback((activeSubflowId: string) => {
    if (!fullGraphRef.current) return;
    const graph = fullGraphRef.current;

    // Save current canvas into the subGraph slot
    if (!graph.subGraphs) graph.subGraphs = {};
    graph.subGraphs[activeSubflowId] = currentFlatGraph();

    // Reload mainGraph
    const mainGraph = graph.mainGraph;
    setNodes(
      (mainGraph?.nodes ?? []).map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
    );
    setEdges(
      (mainGraph?.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      })),
    );
  }, [currentFlatGraph, setNodes, setEdges]);

  /** Save current canvas into the active subGraph slot (call before toGraphJson if inside a subflow). */
  const saveCurrentSubGraph = useCallback((activeSubflowId: string) => {
    if (!fullGraphRef.current) return;
    if (!fullGraphRef.current.subGraphs) fullGraphRef.current.subGraphs = {};
    fullGraphRef.current.subGraphs[activeSubflowId] = currentFlatGraph();
  }, [currentFlatGraph]);

  /** Save current mainGraph (call before toGraphJson if on main canvas). */
  const saveCurrentMainGraph = useCallback(() => {
    if (!fullGraphRef.current) return;
    fullGraphRef.current.mainGraph = currentFlatGraph();
  }, [currentFlatGraph]);

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
    enterSubflow,
    exitSubflow,
    saveCurrentSubGraph,
    saveCurrentMainGraph,
    fullGraphRef,
  };
}
