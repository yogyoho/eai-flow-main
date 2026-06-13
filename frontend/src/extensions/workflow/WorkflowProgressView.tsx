"use client";

import { GitBranch, Loader2 } from "lucide-react";
import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AnimatedFlowEdge } from "./edges/AnimatedFlowEdge";
import { ProgressPhaseNode } from "./nodes/ProgressPhaseNode";
import { ProgressReviewNode } from "./nodes/ProgressReviewNode";
import { useWorkflowStatus } from "./hooks/useWorkflowStatus";
import type { WorkflowGraph, WorkflowNodeStatus } from "./types";

// ── Node / Edge types (stable references, must be outside component) ──

const nodeTypes: NodeTypes = {
  phase: ProgressPhaseNode,
  review: ProgressReviewNode,
};

const edgeTypes: EdgeTypes = {
  animatedFlow: AnimatedFlowEdge,
};

// ── Types ──

interface WorkflowProgressViewProps {
  projectId: string;
  workflowGraph?: WorkflowGraph | null;
}

type EdgeState = "completed" | "running" | "pending";

// ── Inner component (needs ReactFlowProvider context) ──

function WorkflowProgressInner({ projectId, workflowGraph }: WorkflowProgressViewProps) {
  const { status, loading } = useWorkflowStatus(projectId, 5000);

  // Prefer graph from API response (includes full DAG), fallback to parent-passed graph
  const effectiveGraph = useMemo<WorkflowGraph | null>(() => {
    if (status?.graphJson) {
      return status.graphJson as WorkflowGraph;
    }
    return workflowGraph ?? null;
  }, [status?.graphJson, workflowGraph]);

  // Build status lookup
  const statusMap = useMemo(() => {
    if (!status?.nodes) return new Map<string, WorkflowNodeStatus>();
    return new Map(status.nodes.map((n) => [n.nodeId, n]));
  }, [status?.nodes]);

  // Derive ReactFlow nodes from graph + status
  const rfNodes: Node[] = useMemo(() => {
    if (!effectiveGraph?.mainGraph) return [];
    return effectiveGraph.mainGraph.nodes.map((graphNode) => {
      const nodeStatus = statusMap.get(graphNode.id);
      const nodeType = graphNode.type === "review" ? "review" : "phase"; // "phase" node type is used for progress rendering — maps to subflow too

      return {
        id: graphNode.id,
        type: nodeType,
        position: graphNode.position,
        data: {
          ...graphNode.data,
          status: nodeStatus?.status ?? "pending",
          chapterTotal: nodeStatus?.chapterTotal ?? null,
          chapterCompleted: nodeStatus?.chapterCompleted ?? null,
          reviewTotal: nodeStatus?.reviewTotal ?? null,
          reviewApproved: nodeStatus?.reviewApproved ?? null,
        },
      };
    });
  }, [effectiveGraph, statusMap]);

  // Derive ReactFlow edges with edge state
  const rfEdges: Edge[] = useMemo(() => {
    if (!effectiveGraph?.mainGraph) return [];

    return effectiveGraph.mainGraph.edges.map((graphEdge) => {
      const sourceStatus = statusMap.get(graphEdge.source)?.status ?? "pending";
      const targetStatus = statusMap.get(graphEdge.target)?.status ?? "pending";

      let edgeState: EdgeState = "pending";
      if (sourceStatus === "completed" && targetStatus === "completed") {
        edgeState = "completed";
      } else if (sourceStatus === "completed" && targetStatus === "running") {
        edgeState = "running";
      }

      return {
        id: graphEdge.id,
        source: graphEdge.source,
        target: graphEdge.target,
        type: "animatedFlow",
        data: { edgeState },
      };
    });
  }, [effectiveGraph, statusMap]);

  // ── Empty state: no workflow assigned ──
  if (!loading && !status?.workflowId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
        <GitBranch className="h-12 w-12 opacity-30" />
        <p className="text-sm font-medium">该项目尚未关联工作流</p>
        <p className="text-xs text-muted-foreground/60">请在项目设置中关联工作流模板</p>
      </div>
    );
  }

  // ── Loading state ──
  if (loading && !status) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/50" />
      </div>
    );
  }

  // ── Workflow status summary header ──
  const overallStatus = status?.status ?? "idle";
  const currentPhase = status?.currentPhaseNode;
  const currentNodeLabel = currentPhase ? statusMap.get(currentPhase)?.label : null;

  return (
    <div className="flex h-full flex-col">
      {/* Status header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-muted/30 shrink-0">
        <div
          className={`h-2 w-2 rounded-full ${
            overallStatus === "completed"
              ? "bg-green-500"
              : overallStatus === "running"
                ? "bg-blue-500 animate-pulse"
                : overallStatus === "failed"
                  ? "bg-red-500"
                  : "bg-gray-400"
          }`}
        />
        <span className="text-xs text-muted-foreground">
          {overallStatus === "completed" && "工作流已完成"}
          {overallStatus === "running" && `正在执行: ${currentNodeLabel ?? "..."}`}
          {overallStatus === "failed" && "工作流执行失败"}
          {overallStatus === "idle" && "工作流尚未启动"}
        </span>
      </div>

      {/* ReactFlow canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
          zoomOnPinch
          zoomOnDoubleClick={false}
          minZoom={0.3}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={16} size={1} color="var(--border)" />
          <Controls
            showInteractive={false}
            className="!bg-background !border-border !shadow-sm"
          />
        </ReactFlow>
      </div>
    </div>
  );
}

// ── Exported component with provider ──

export function WorkflowProgressView({ projectId, workflowGraph }: WorkflowProgressViewProps) {
  return (
    <ReactFlowProvider>
      <WorkflowProgressInner projectId={projectId} workflowGraph={workflowGraph} />
    </ReactFlowProvider>
  );
}
