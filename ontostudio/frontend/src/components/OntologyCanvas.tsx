/**
 * 本体建模器 关系图画布（React Flow, EAI-CUSTOM 2026-09-20）.
 *
 * 节点 = OWL 类（subClassOf 层次自动布局）；边 = rdfs:subClassOf。
 * 编辑能力（拖拽定位/缩放/平移/小地图）由 React Flow 内建；
 * 选中节点 → 回调 onSelect 通知父组件切换右栏详情。
 */
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeTypes,
  type ProOptions,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo } from "react";

export interface CanvasNodeData {
  label: string;
  etype: string;
  definition: string;
}

interface OntologyCanvasProps {
  classes: Array<{ name: string; label: string; definition: string; parents: string[] }>;
  edgesData: Array<{ source: string; target: string; label?: string }>;
  selectedName?: string | null;
  onSelect?: (name: string | null) => void;
  onNodeDrag?: (name: string, x: number, y: number) => void;
}

const nodeTypes: NodeTypes = {};

/** 层次布局：按 parent 链分 layer，同层水平均分 */
function autoLayout(
  classes: Array<{ name: string; label: string; definition: string; parents: string[] }>,
) {
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  const nameSet = new Set(classes.map((c) => c.name));
  for (const c of classes) {
    const realParents = c.parents.filter((p) => nameSet.has(p));
    if (realParents.length === 0) {
      roots.push(c.name);
    } else {
      for (const p of realParents) {
        const list = children.get(p) ?? [];
        list.push(c.name);
        children.set(p, list);
      }
    }
  }
  // BFS 分层
  const depth = new Map<string, number>();
  const queue = roots.map((r) => ({ name: r, d: 0 }));
  while (queue.length) {
    const { name, d } = queue.shift()!;
    depth.set(name, d);
    for (const child of children.get(name) ?? []) {
      if (!depth.has(child)) {
        depth.set(child, d + 1);
        queue.push({ name: child, d: d + 1 });
      }
    }
  }
  // 同层分组均分
  const layers = new Map<number, string[]>();
  for (const c of classes) {
    const d = depth.get(c.name) ?? 0;
    const list = layers.get(d) ?? [];
    list.push(c.name);
    layers.set(d, list);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const LAYER_H = 140;
  const NODE_W = 170;
  for (const [d, names] of [...layers.entries()].sort((a, b) => a[0] - b[0])) {
    const w = Math.max(names.length * (NODE_W + 40), 400);
    names.forEach((name, i) => {
      positions.set(name, {
        x: (w - names.length * (NODE_W + 40)) / 2 + i * (NODE_W + 40),
        y: d * LAYER_H,
      });
    });
  }
  return positions;
}

function OntologyCanvasInner({
  classes,
  edgesData,
  selectedName,
  onSelect,
}: OntologyCanvasProps) {
  const positions = useMemo(() => autoLayout(classes), [classes]);

  const initialNodes = useMemo(
    () =>
      classes.map((c) => ({
        id: c.name,
        type: "default" as const,
        position: positions.get(c.name) ?? { x: 0, y: 0 },
        data: { label: c.label || c.name },
        style: {
          width: 170,
          borderRadius: 8,
          border: "1px solid var(--border, #e4e6e6)",
          background: "var(--card, #fff)",
          color: "var(--foreground, #151616)",
          fontSize: 13,
          fontWeight: 600,
          padding: "8px 12px",
        },
      })),
    [classes, positions],
  );

  const initialEdges = useMemo(
    () =>
      edgesData.map((e, i) => ({
        id: `e-${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.label,
        animated: false,
        style: { stroke: "var(--primary, #2563eb)", strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: "var(--muted-foreground, #71717a)" },
      })),
    [edgesData],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges]);

  const proOptions: ProOptions = { hideAttribution: true };

  const handleNodeClick = useCallback(
    (_: unknown, node: Node) => onSelect?.(node.id),
    [onSelect],
  );
  const handlePaneClick = useCallback(() => onSelect?.(null), [onSelect]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onPaneClick={handlePaneClick}
      nodeTypes={nodeTypes}
      proOptions={proOptions}
      fitView
      minZoom={0.2}
      maxZoom={2}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable
      className="bg-background"
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border, #e4e6e6)" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        style={{ width: 140, height: 90 }}
        nodeColor={() => "var(--primary, #2563eb)"}
      />
    </ReactFlow>
  );
}

export function OntologyCanvas(props: OntologyCanvasProps) {
  return (
    <div className="h-full w-full">
      <OntologyCanvasInner {...props} />
    </div>
  );
}
