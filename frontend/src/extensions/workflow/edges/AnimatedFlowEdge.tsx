"use client";

import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

type EdgeState = "completed" | "running" | "pending";

const EDGE_STYLES: Record<EdgeState, React.CSSProperties> = {
  completed: {
    stroke: "#22c55e",
    strokeWidth: 2,
  },
  running: {
    stroke: "#3b82f6",
    strokeWidth: 2,
    strokeDasharray: "8 4",
    animation: "dash-flow 1s linear infinite",
  },
  pending: {
    stroke: "#d1d5db",
    strokeWidth: 1.5,
    strokeDasharray: "5 5",
  },
};

export function AnimatedFlowEdge(props: EdgeProps) {
  const {
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
  } = props;

  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const edgeState = (data as { edgeState?: EdgeState })?.edgeState ?? "pending";
  const style = EDGE_STYLES[edgeState] ?? EDGE_STYLES.pending;

  return <BaseEdge path={edgePath} style={style} />;
}
