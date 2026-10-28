"use client";

import { useMemo } from "react";
import type { DefJson, NodeJson, SkipJson } from "@/lib/types";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

const DONE = "#38a169";
const TODO = "#f59e0b";
const IDLE = "#b6bfcc";
const REJECT = "#e11d48";

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function parseCoordinate(value?: string | null) {
  if (!value) return { x: 0, y: 0, textX: undefined as number | undefined, textY: undefined as number | undefined };
  const [point, text] = value.split("|");
  const [x, y] = point.split(",").map((item) => Number.parseFloat(item));
  let textX: number | undefined;
  let textY: number | undefined;
  if (text) {
    const [tx, ty] = text.split(",").map((item) => Number.parseFloat(item));
    if (Number.isFinite(tx)) textX = tx;
    if (Number.isFinite(ty)) textY = ty;
  }
  return { x: x || 0, y: y || 0, textX, textY };
}

function parsePoints(value?: string | null) {
  if (!value) return { points: [] as { x: number; y: number }[], textX: undefined as number | undefined, textY: undefined as number | undefined };
  const [pointsPart, textPart] = value.split("|");
  const points = pointsPart
    .split(";")
    .map((item) => {
      const [x, y] = item.split(",").map((part) => Number.parseFloat(part));
      return { x: x || 0, y: y || 0 };
    })
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  let textX: number | undefined;
  let textY: number | undefined;
  if (textPart) {
    const [tx, ty] = textPart.split(",").map((item) => Number.parseFloat(item));
    if (Number.isFinite(tx)) textX = tx;
    if (Number.isFinite(ty)) textY = ty;
  }
  return { points, textX, textY };
}

function boxOf(node: NodeJson): Pick<Rect, "w" | "h"> {
  if (node.nodeType === 0 || node.nodeType === 2) return { w: 54, h: 54 };
  if (node.nodeType >= 3) return { w: 56, h: 56 };
  return { w: 176, h: 52 };
}

function distanceToBox(point: { x: number; y: number }, box: Rect): number {
  const dx = Math.max(Math.abs(point.x - box.x) - box.w / 2, 0);
  const dy = Math.max(Math.abs(point.y - box.y) - box.h / 2, 0);
  return Math.hypot(dx, dy);
}

function pointsLookValid(
  points: { x: number; y: number }[],
  source: Rect,
  target: Rect,
): boolean {
  if (points.length < 2) return false;
  return (
    distanceToBox(points[0], source) <= 64 &&
    distanceToBox(points[points.length - 1], target) <= 64
  );
}

function autoEdgePoints(
  source: Rect,
  target: Rect,
  rejected: boolean,
  rejectOffset: number,
): { x: number; y: number }[] {
  if (rejected) {
    const sy = source.y + source.h / 2;
    const ty = target.y + target.h / 2;
    const routeY = Math.max(sy, ty) + 64 + rejectOffset * 26;
    return [
      { x: source.x, y: sy },
      { x: source.x, y: routeY },
      { x: target.x, y: routeY },
      { x: target.x, y: ty },
    ];
  }
  if (Math.abs(source.y - target.y) < 6) {
    const direction = target.x >= source.x ? 1 : -1;
    return [
      { x: source.x + direction * source.w / 2, y: source.y },
      { x: target.x - direction * target.w / 2, y: target.y },
    ];
  }
  const sy = source.y + (target.y >= source.y ? source.h / 2 : -source.h / 2);
  const ty = target.y + (target.y >= source.y ? -target.h / 2 : target.h / 2);
  const midY = (sy + ty) / 2;
  return [
    { x: source.x, y: sy },
    { x: source.x, y: midY },
    { x: target.x, y: midY },
    { x: target.x, y: ty },
  ];
}

function statusColor(status?: number | null) {
  if (status === 2) return { stroke: DONE, fill: "#f0fdf4", text: "#166534", dashed: false };
  if (status === 1) return { stroke: TODO, fill: "#fffbeb", text: "#b45309", dashed: true };
  return { stroke: IDLE, fill: "#ffffff", text: "#64748b", dashed: false };
}

/* Edge color follows traversal status only. A REJECT edge is red once it was
   actually taken; an untaken reject path stays idle grey like any other edge. */
function edgePalette(skip: SkipJson) {
  if (skip.status === 2) {
    return skip.skipType === "REJECT"
      ? { stroke: REJECT, marker: "arrow-reject", text: REJECT, dashed: true, opacity: 1 }
      : { stroke: DONE, marker: "arrow-done", text: "#64748b", dashed: false, opacity: 1 };
  }
  if (skip.status === 1) {
    return { stroke: TODO, marker: "arrow-todo", text: "#b45309", dashed: true, opacity: 1 };
  }
  return { stroke: IDLE, marker: "arrow-idle", text: "#64748b", dashed: false, opacity: 0.85 };
}

export function FlowChart({ chart, className }: { chart: DefJson; className?: string }) {
  const layout = useMemo(() => {
    const nodes = (chart.nodeList || []).map((node) => {
      const coord = parseCoordinate(node.coordinate);
      const box = boxOf(node);
      return {
        node,
        x: coord.x,
        y: coord.y,
        textX: coord.textX ?? coord.x,
        textY: coord.textY ?? coord.y + 44,
        ...box,
      };
    });
    const byCode = new Map(nodes.map((item) => [item.node.nodeCode, item]));

    const edges: {
      skip: SkipJson;
      source: NodeJson;
      target: NodeJson;
      points: { x: number; y: number }[];
      textX: number;
      textY: number;
    }[] = [];

    let rejectOffset = 0;
    for (const item of nodes) {
      for (const skip of item.node.skipList || []) {
        const target = byCode.get(skip.nextNodeCode || "");
        if (!target) continue;
        const rejected = skip.skipType === "REJECT";
        const offset = rejected ? rejectOffset++ : 0;
        const coord = parsePoints(skip.coordinate);
        const storedPathIsValid = pointsLookValid(coord.points, item, target);
        const points = storedPathIsValid
          ? coord.points
          : autoEdgePoints(item, target, rejected, offset);
        const midpoint = points[Math.floor(points.length / 2)];
        const textX =
          storedPathIsValid && coord.textX !== undefined ? coord.textX : midpoint.x;
        const textY =
          storedPathIsValid && coord.textY !== undefined
            ? coord.textY
            : rejected
              ? Math.max(...points.map((point) => point.y)) + 16
              : Math.min(...points.map((point) => point.y)) - 8;
        edges.push({
          skip,
          source: item.node,
          target: target.node,
          points,
          textX,
          textY,
        });
      }
    }

    // Overlapping edges share path segments; paint unvisited (grey) ones
    // first so traversed and pending paths stay visible on top. The sort is
    // stable, so edges of the same status keep their natural order.
    edges.sort((a, b) => (a.skip.status ?? 0) - (b.skip.status ?? 0));

    const xs: number[] = [];
    const ys: number[] = [];
    for (const node of nodes) {
      xs.push(node.x - node.w / 2, node.x + node.w / 2, node.textX);
      ys.push(node.y - node.h / 2, node.y + node.h / 2, node.textY + 8);
    }
    for (const edge of edges) {
      for (const point of edge.points) {
        xs.push(point.x);
        ys.push(point.y);
      }
      xs.push(edge.textX);
      ys.push(edge.textY);
    }

    const minX = Math.min(...xs) - 60;
    const maxX = Math.max(...xs) + 60;
    const minY = Math.min(...ys) - 60;
    const maxY = Math.max(...ys) + 60;

    return {
      nodes,
      edges,
      viewBox: `${minX} ${minY} ${Math.max(maxX - minX, 200)} ${Math.max(maxY - minY, 200)}`,
    };
  }, [chart]);

  if (!chart.nodeList?.length) {
    return (
      <EmptyState
        title="暂无流程图数据"
        description="流程实例启动后会自动生成 DefJson 快照与节点状态。"
        className={cn("h-full", className)}
      />
    );
  }

  const hasPending = layout.nodes.some((item) => item.node.status === 1);
  const hasDone = layout.nodes.some((item) => item.node.status === 2);

  return (
    <div className={cn("overflow-hidden rounded-xl border border-border bg-card", className)}>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-2.5">
        <p className="text-[12px] font-semibold">流程进度图</p>
        <span className="text-[10.5px] text-muted-foreground">
          v{chart.version || "1"} · {layout.nodes.length} 节点
        </span>
        <div className="ml-auto flex items-center gap-3 text-[10px] text-muted-foreground">
          <Legend color={DONE} label="已完成" active={hasDone} />
          <Legend color={TODO} label="待办" active={hasPending} />
          <Legend color={IDLE} label="未到达" active />
        </div>
      </div>
      <div className="canvas-grid-bg w-full">
        <svg
          viewBox={layout.viewBox}
          className="flow-chart-svg block max-h-[560px] w-full"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="流程进度图"
        >
          <defs>
            {[
              { id: "arrow-done", color: DONE },
              { id: "arrow-todo", color: TODO },
              { id: "arrow-idle", color: IDLE },
              { id: "arrow-reject", color: REJECT },
            ].map((marker) => (
              <marker
                key={marker.id}
                id={marker.id}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path
                  d="M 1 1 L 9 5 L 1 9"
                  fill="none"
                  stroke={marker.color}
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </marker>
            ))}
          </defs>

          {layout.edges.map((edge, index) => {
            const palette = edgePalette(edge.skip);
            const points = edge.points.map((point) => `${point.x},${point.y}`).join(" ");
            return (
              <g key={`${edge.skip.nowNodeCode}-${edge.skip.nextNodeCode}-${index}`}>
                <polyline
                  points={points}
                  fill="none"
                  stroke={palette.stroke}
                  strokeWidth={edge.skip.status === 1 ? 2 : 1.6}
                  strokeDasharray={palette.dashed ? "6 4" : undefined}
                  markerEnd={`url(#${palette.marker})`}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  opacity={palette.opacity}
                />
                {edge.skip.skipName && (
                  <text
                    x={edge.textX}
                    y={edge.textY}
                    textAnchor="middle"
                    fontSize={10.5}
                    fill={palette.text}
                    stroke="#ffffff"
                    strokeWidth={3}
                    paintOrder="stroke"
                  >
                    {edge.skip.skipName}
                  </text>
                )}
              </g>
            );
          })}

          {layout.nodes.map(({ node, x, y, w, h, textX, textY }) => {
            const palette = statusColor(node.status);
            const pending = node.status === 1;
            const label = node.nodeName || node.nodeCode;
            return (
              <g key={node.nodeCode}>
                {pending && (
                  <rect
                    x={x - w / 2 - 5}
                    y={y - h / 2 - 5}
                    width={w + 10}
                    height={h + 10}
                    rx={node.nodeType === 0 || node.nodeType === 2 ? w / 2 + 5 : 14}
                    fill="none"
                    stroke={TODO}
                    strokeWidth={2}
                    opacity={0.25}
                  />
                )}
                {node.nodeType === 0 || node.nodeType === 2 ? (
                  <circle
                    cx={x}
                    cy={y}
                    r={26}
                    fill={palette.fill}
                    stroke={palette.stroke}
                    strokeWidth={2.2}
                    strokeDasharray={palette.dashed ? "5 4" : undefined}
                  />
                ) : node.nodeType >= 3 ? (
                  <polygon
                    points={`${x},${y - 30} ${x + 30},${y} ${x},${y + 30} ${x - 30},${y}`}
                    fill={palette.fill}
                    stroke={palette.stroke}
                    strokeWidth={2}
                    strokeDasharray={palette.dashed ? "5 4" : undefined}
                  />
                ) : (
                  <rect
                    x={x - w / 2}
                    y={y - h / 2}
                    width={w}
                    height={h}
                    rx={10}
                    fill={palette.fill}
                    stroke={palette.stroke}
                    strokeWidth={pending ? 2 : 1.7}
                    strokeDasharray={palette.dashed ? "5 4" : undefined}
                  />
                )}
                <text
                  x={textX}
                  y={textY}
                  textAnchor="middle"
                  fontSize={11.5}
                  fontWeight={pending ? 600 : 500}
                  fill={palette.text}
                  stroke="#ffffff"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {label}
                </text>
                {node.nodeType >= 3 && (
                  <text
                    x={x}
                    y={y + 4}
                    textAnchor="middle"
                    fontSize={9}
                    fill={palette.stroke}
                    fontWeight={700}
                  >
                    {node.nodeType === 3 ? "XOR" : node.nodeType === 4 ? "AND" : "OR"}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function Legend({ color, label, active }: { color: string; label: string; active?: boolean }) {
  return (
    <span className={cn("flex items-center gap-1.5", !active && "opacity-45")}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
