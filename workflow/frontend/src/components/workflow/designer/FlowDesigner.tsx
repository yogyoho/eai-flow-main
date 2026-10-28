"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import LogicFlow, { ElementState } from "@logicflow/core";
import { Loader2, MousePointerClick, Sparkles, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { DefJson, NodeTypeName } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { DesignerToolbar } from "./DesignerToolbar";
import { DesignerSidebar } from "./DesignerSidebar";
import { PropertyPanel, type DesignerSelection } from "./PropertyPanel";
import { DESIGNER_THEME, NODE_TYPE_META, registerWorkflowNodes } from "./nodeRegistry";
import {
  defJsonToGraph,
  graphToDefJson,
  makeNode,
  metaFromDef,
  seedGraph,
  type DefinitionMeta,
  type LFEdgeData,
  type LFGraphData,
  type LFNodeData,
} from "./graph";

/**
 * Fit the graph into the canvas without ever zooming past 100%.
 * LogicFlow's built-in fitView happily scales a narrow graph up, which makes
 * small definitions look oversized.
 */
function fitGraph(lf: LogicFlow, padding = 70) {
  const graph = lf.graphModel as unknown as {
    width: number;
    height: number;
    nodes: { x: number; y: number; width: number; height: number }[];
    transformModel: {
      zoom: (scale: number, point: [number, number]) => string;
      focusOn: (x: number, y: number, width: number, height: number) => void;
    };
  };
  const nodes = graph.nodes || [];
  if (!nodes.length || !graph.width || !graph.height) return;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const node of nodes) {
    const width = node.width || 0;
    const height = node.height || 0;
    minX = Math.min(minX, node.x - width / 2);
    maxX = Math.max(maxX, node.x + width / 2);
    minY = Math.min(minY, node.y - height / 2);
    maxY = Math.max(maxY, node.y + height / 2);
  }

  const contentWidth = Math.max(maxX - minX, 1);
  const contentHeight = Math.max(maxY - minY, 1);
  const usableWidth = Math.max(graph.width - padding * 2, 80);
  const usableHeight = Math.max(graph.height - padding * 2, 80);
  const scale = Math.max(0.2, Math.min(usableWidth / contentWidth, usableHeight / contentHeight, 1));

  graph.transformModel.zoom(scale, [graph.width / 2, graph.height / 2]);
  graph.transformModel.focusOn(
    (minX + maxX) / 2,
    (minY + maxY) / 2,
    graph.width,
    graph.height,
  );
}

export function FlowDesigner({ definitionId }: { definitionId: number | "new" }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const containerRef = useRef<HTMLDivElement>(null);
  const lfRef = useRef<LogicFlow | null>(null);
  const saveRef = useRef<() => Promise<void>>(async () => {});

  const [meta, setMeta] = useState<DefinitionMeta | null>(null);
  const [selection, setSelection] = useState<DesignerSelection | null>(null);
  const [snapshot, setSnapshot] = useState<LFGraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [zoom, setZoom] = useState(1);

  const formsQuery = useQuery({
    queryKey: ["designer", "published-forms"],
    queryFn: api.designer.publishedForms,
    staleTime: 60_000,
  });
  const handlersQuery = useQuery({
    queryKey: ["meta", "handlers"],
    queryFn: api.meta.handlers,
    staleTime: 5 * 60 * 1000,
  });

  const refreshSnapshot = useCallback(() => {
    const lf = lfRef.current;
    if (!lf) return;
    const graph = lf.getGraphData() as unknown as LFGraphData;
    setSnapshot({ nodes: graph.nodes || [], edges: graph.edges || [] });
    setZoom((lf as unknown as { graphModel: { transformModel: { scale: number } } }).graphModel.transformModel.scale || 1);
  }, []);

  const selectNode = useCallback((data: LFNodeData) => {
    setSelection({
      kind: "node",
      id: data.id,
      type: data.type,
      text: typeof data.text === "string" ? data.text : data.text?.value || "",
      properties: { ...(data.properties || {}) },
    });
  }, []);

  const selectEdge = useCallback((data: LFEdgeData) => {
    setSelection({
      kind: "edge",
      id: data.id,
      source: data.sourceNodeId,
      target: data.targetNodeId,
      text: typeof data.text === "string" ? data.text : data.text?.value || "",
      properties: { ...(data.properties || {}) },
    });
  }, []);

  /* --------------------------------------------------------------------- */
  /* Boot the canvas and load the definition                                */
  /* --------------------------------------------------------------------- */
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    const lf = new LogicFlow({
      container: containerRef.current,
      grid: { size: 20, visible: false, type: "dot", config: { color: "#dfe5ee" } },
      background: { backgroundColor: "transparent" },
      style: DESIGNER_THEME as never,
      edgeType: "skip",
      snapline: true,
      history: true,
      adjustEdge: true,
      // Draw selection on the node/edge itself instead of LogicFlow's
      // rectangular outline overlay, which reads as a harsh black frame.
      nodeSelectedOutline: false,
      edgeSelectedOutline: false,
      hoverOutline: false,
      allowRotate: false,
      allowResize: false,
      textEdit: true,
      stopScrollGraph: false,
      stopZoomGraph: false,
      multipleSelectKey: "shift",
      idGenerator: (type) => `${type}_${Math.random().toString(36).slice(2, 9)}`,
    });
    registerWorkflowNodes(lf);
    lfRef.current = lf;

    lf.on("node:click", (args: any) => {
      selectNode(args.data as LFNodeData);
    });
    lf.on("edge:click", (args: any) => {
      selectEdge(args.data as LFEdgeData);
    });
    // Double-click enters inline label editing instead of emitting the normal
    // click event, so mirror the selection into the React property panel here.
    lf.on("node:dbclick", (args: any) => {
      selectNode(args.data as LFNodeData);
    });
    lf.on("edge:dbclick", (args: any) => {
      selectEdge(args.data as LFEdgeData);
    });
    lf.on("text:dbclick", (args: any) => {
      const model = args?.model as
        | {
            BaseType?: string;
            getData?: () => LFNodeData | LFEdgeData;
          }
        | undefined;
      const data = model?.getData?.();
      if (!data) return;
      if (model?.BaseType === "edge") selectEdge(data as LFEdgeData);
      else selectNode(data as LFNodeData);
    });
    lf.on("blank:click", () => setSelection(null));
    lf.on("node:add", () => {
      refreshSnapshot();
      setDirty(true);
    });
    lf.on("edge:add", () => {
      refreshSnapshot();
      setDirty(true);
    });
    lf.on("node:delete", () => {
      refreshSnapshot();
      setSelection(null);
      setDirty(true);
    });
    lf.on("edge:delete", () => {
      refreshSnapshot();
      setSelection(null);
      setDirty(true);
    });
    lf.on("node:drag", () => {
      setDirty(true);
    });
    lf.on("edge:adjust", () => {
      setDirty(true);
    });
    lf.on("text:update", (args: any) => {
      const data = args?.data as { id?: string; text?: string } | undefined;
      if (data?.id) {
        setSelection((current) =>
          current && current.id === data.id
            ? { ...current, text: data.text ?? "" }
            : current,
        );
      }
      refreshSnapshot();
      setDirty(true);
    });

    lf.render({ nodes: [], edges: [] } as never);

    /* LogicFlow commits inline labels on blur or Alt+Enter. Workflow labels
       are single-line, so let a plain Enter finish editing as users expect;
       Shift+Enter still inserts a line break. */
    const onLabelKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target?.classList.contains("lf-text-input")) return;
      if (event.key !== "Enter" || event.shiftKey || event.altKey || event.isComposing) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const textEditElement = (
        lf as unknown as {
          graphModel: {
            textEditElement?: {
              setElementState: (state: ElementState) => void;
            } | null;
          };
        }
      ).graphModel.textEditElement;
      textEditElement?.setElementState(ElementState.DEFAULT);
    };
    containerRef.current?.addEventListener("keydown", onLabelKeyDown, true);

    api.designer
      .query(definitionId)
      .then((def) => {
        if (cancelled) return;
        const graph = def.nodeList?.length ? defJsonToGraph(def) : seedGraph();
        lf.render(graph as never);
        setMeta(metaFromDef(def));
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "流程定义加载失败");
        setLoading(false);
      });

    const onResize = () => lf.resize();
    window.addEventListener("resize", onResize);
    const observer = new ResizeObserver(onResize);
    observer.observe(containerRef.current);

    return () => {
      cancelled = true;
      containerRef.current?.removeEventListener("keydown", onLabelKeyDown, true);
      observer.disconnect();
      window.removeEventListener("resize", onResize);
      lf.destroy();
      lfRef.current = null;
    };
  }, [definitionId, refreshSnapshot, selectEdge, selectNode]);

  /* Fit the graph once the toolbar and property panel have been laid out.
     Fitting from the load callback runs before the panel mounts and measures
     a wider canvas than the user eventually sees. */
  useLayoutEffect(() => {
    if (loading) return;
    const lf = lfRef.current;
    if (!lf) return;
    lf.resize();
    fitGraph(lf);
    refreshSnapshot();
  }, [definitionId, loading, refreshSnapshot]);

  /* Warn before leaving with unsaved changes. */
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const deleteSelection = useCallback(() => {
    const lf = lfRef.current;
    if (!lf || !selection) return;
    if (selection.kind === "node") lf.deleteNode(selection.id);
    else lf.deleteEdge(selection.id);
    setSelection(null);
    refreshSnapshot();
    setDirty(true);
  }, [refreshSnapshot, selection]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) {
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveRef.current();
        return;
      }
      if ((event.key === "Delete" || event.key === "Backspace") && selection) {
        event.preventDefault();
        deleteSelection();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [deleteSelection, selection]);

  /* --------------------------------------------------------------------- */
  /* Mutation helpers                                                      */
  /* --------------------------------------------------------------------- */
  const updateNode = useCallback(
    (id: string, updates: { text?: string; properties?: Record<string, unknown> }) => {
      const lf = lfRef.current;
      if (!lf) return;
      if (updates.text !== undefined) {
        lf.updateText(id, updates.text);
      }
      if (updates.properties) {
        lf.setProperties(id, updates.properties);
      }
      setSelection((current) =>
        current && current.kind === "node" && current.id === id
          ? {
              ...current,
              text: updates.text ?? current.text,
              properties: { ...current.properties, ...(updates.properties || {}) },
            }
          : current,
      );
      setDirty(true);
    },
    [],
  );

  const updateEdge = useCallback(
    (id: string, updates: { text?: string; properties?: Record<string, unknown> }) => {
      const lf = lfRef.current;
      if (!lf) return;
      if (updates.text !== undefined) lf.updateText(id, updates.text);
      if (updates.properties) lf.setProperties(id, updates.properties);
      setSelection((current) =>
        current && current.kind === "edge" && current.id === id
          ? {
              ...current,
              text: updates.text ?? current.text,
              properties: { ...current.properties, ...(updates.properties || {}) },
            }
          : current,
      );
      setDirty(true);
    },
    [],
  );

  function edgeId(source: string, target: string) {
    return `edge_${source}_${target}_${Math.random().toString(36).slice(2, 7)}`;
  }

  const addEdge = useCallback(
    (
      source: string,
      target: string,
      text = "通过",
      properties: Record<string, unknown> = {},
    ) => {
      const lf = lfRef.current;
      if (!lf) return;
      lf.addEdge({
        id: edgeId(source, target),
        type: "skip",
        sourceNodeId: source,
        targetNodeId: target,
        text: { value: text },
        properties: {
          skipType: "PASS",
          skipName: text,
          skipCondition: "",
          ...properties,
          designer: true,
        },
      } as never);
    },
    [],
  );

  const addNode = useCallback(
    (type: NodeTypeName, point?: { x: number; y: number }) => {
      const lf = lfRef.current;
      if (!lf) return;
      const graph = lf.getGraphData() as unknown as LFGraphData;
      const existing = graph.nodes.map((node) => node.id);
      if (type === "start" && existing.includes("start")) {
        toast.error("一个流程只能有一个开始节点");
        return;
      }
      const anchor =
        selection?.kind === "node" ? graph.nodes.find((node) => node.id === selection.id) : undefined;
      const maxY = graph.nodes.reduce((value, node) => Math.max(value, node.y), 80);

      let x = point?.x ?? anchor?.x ?? 420;
      let y = point?.y ?? (anchor ? anchor.y + 138 : maxY + 138);
      if (!point && anchor && anchor.type !== "start" && anchor.type !== "end") {
        x = anchor.x + (anchor.type === "between" ? 0 : 210);
        y = anchor.y + (anchor.type === "between" ? 138 : 0);
      }
      const node = makeNode(type, Math.round(x), Math.round(y), existing);
      lf.addNode(node as never);

      if (!point) {
        const endNode = graph.nodes.find((item) => item.type === "end");
        const anchorOutgoing = graph.edges.filter(
          (edge) => edge.sourceNodeId === anchor?.id,
        );

        if (type === "start") {
          // Start nodes never receive an auto-connection.
        } else if (anchor?.type === "end" && endNode) {
          const incoming = graph.edges.find((edge) => edge.targetNodeId === endNode.id);
          if (incoming) {
            lf.deleteEdge(incoming.id);
            addEdge(incoming.sourceNodeId, node.id, String(incoming.text?.value || "通过"), {
              ...(incoming.properties || {}),
            });
            addEdge(node.id, endNode.id);
            (lf.getNodeModelById(endNode.id) as any)?.moveTo?.(endNode.x, endNode.y + 138);
          }
        } else if (anchor) {
          const directToEnd = endNode
            ? anchorOutgoing.find(
                (edge) =>
                  edge.targetNodeId === endNode.id && edge.properties?.skipType !== "REJECT",
              )
            : undefined;
          if (directToEnd && endNode && type !== "end") {
            lf.deleteEdge(directToEnd.id);
            addEdge(anchor.id, node.id, String(directToEnd.text?.value || "通过"), {
              ...(directToEnd.properties || {}),
            });
            addEdge(node.id, endNode.id);
            (lf.getNodeModelById(endNode.id) as any)?.moveTo?.(endNode.x, endNode.y + 138);
          } else if (anchorOutgoing.length === 0 || type === "end") {
            addEdge(anchor.id, node.id);
          } else {
            addEdge(anchor.id, node.id);
          }
        }
      }

      setSelection({
        kind: "node",
        id: node.id,
        type: node.type,
        text: node.text?.value || "",
        properties: { ...node.properties },
      });
      refreshSnapshot();
      setDirty(true);
    },
    [addEdge, refreshSnapshot, selection],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/x-flow-node") as NodeTypeName;
      if (!type) return;
      const lf = lfRef.current;
      if (!lf) return;
      const point = (lf as unknown as {
        getPointByClient: (x: number, y: number) => { x: number; y: number };
      }).getPointByClient(event.clientX, event.clientY);
      addNode(type, { x: Math.round(point.x), y: Math.round(point.y) });
    },
    [addNode],
  );

  const updateFlow = useCallback((patch: Partial<DefinitionMeta>) => {
    setMeta((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  }, []);

  /* --------------------------------------------------------------------- */
  /* Save / publish                                                        */
  /* --------------------------------------------------------------------- */
  const persist = useCallback(async (): Promise<DefJson | null> => {
    const lf = lfRef.current;
    if (!lf || !meta) return null;
    setSaving(true);
    try {
      const graph = lf.getGraphData() as unknown as LFGraphData;
      const payload = graphToDefJson(graph, meta);
      const response = await api.designer.save(payload);
      const saved = response.data;
      setMeta(metaFromDef(saved));
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["definitions"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success(definitionId === "new" ? "流程已创建" : "流程已保存");
      if (definitionId === "new" && saved.id) {
        router.replace(`/design/${saved.id}`);
      }
      return saved;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  }, [definitionId, meta, queryClient, router]);

  const save = useCallback(async () => {
    await persist();
  }, [persist]);

  saveRef.current = save;

  const publish = useCallback(async () => {
    const saved = await persist();
    if (!saved?.id) return;
    setPublishing(true);
    try {
      const published = await api.definitions.publish(saved.id);
      setMeta((current) =>
        current
          ? { ...current, isPublish: published.is_publish, version: published.version }
          : current,
      );
      queryClient.invalidateQueries({ queryKey: ["definitions"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success(`已发布 v${published.version}，可在实例页发起`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  }, [persist, queryClient]);

  const nextOptions =
    selection?.kind === "node"
      ? snapshot.edges
          .filter((edge) => edge.sourceNodeId === selection.id)
          .map((edge) => {
            const target = snapshot.nodes.find((node) => node.id === edge.targetNodeId);
            const label =
              typeof target?.text === "string" ? target.text : target?.text?.value || edge.targetNodeId;
            return { code: edge.targetNodeId, label: `${label} · ${edge.targetNodeId}` };
          })
      : [];

  const zoomBy = (direction: "in" | "out") => {
    const lf = lfRef.current;
    if (!lf) return;
    lf.zoom(direction === "in");
    refreshSnapshot();
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {meta ? (
        <DesignerToolbar
          name={meta.flowName}
          code={meta.flowCode}
          version={meta.version}
          isPublish={meta.isPublish}
          dirty={dirty}
          saving={saving}
          publishing={publishing}
          zoom={zoom}
          onUndo={() => {
            lfRef.current?.undo();
            setSelection(null);
            refreshSnapshot();
          }}
          onRedo={() => {
            lfRef.current?.redo();
            setSelection(null);
            refreshSnapshot();
          }}
          onZoomIn={() => zoomBy("in")}
          onZoomOut={() => zoomBy("out")}
          onFit={() => {
            if (lfRef.current) fitGraph(lfRef.current);
            refreshSnapshot();
          }}
          onSave={() => void save()}
          onPublish={() => void publish()}
        />
      ) : (
        <div className="flex h-14 shrink-0 items-center border-b border-border bg-card/80 px-4">
          <div className="h-4 w-40 animate-pulse rounded bg-muted" />
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {meta ? <DesignerSidebar onAdd={(type) => addNode(type)} /> : null}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div
            ref={containerRef}
            className="lf-designer canvas-grid-bg h-full w-full"
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "copy";
            }}
            onDrop={handleDrop}
          />

          <div className="pointer-events-none absolute left-4 top-4 flex flex-col gap-2">
            <div className="pointer-events-auto flex items-center gap-2 rounded-lg border border-border bg-card/90 px-2.5 py-1.5 text-[10.5px] text-muted-foreground shadow-sm backdrop-blur">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              经典画布
              <span className="h-3 w-px bg-border" />
              {snapshot.nodes.length} 节点 · {snapshot.edges.length} 跳转
            </div>
            {!selection && (
              <div className="pointer-events-auto flex max-w-[260px] items-start gap-2 rounded-lg border border-primary/15 bg-primary/[0.04] px-2.5 py-2 text-[10.5px] leading-relaxed text-primary/90">
                <MousePointerClick className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                选中节点或连线以编辑属性；双击名称可直接在画布上修改。从左侧拖入节点，或点击快速添加。
              </div>
            )}
          </div>

          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between gap-3 border-t border-border bg-card/85 px-4 py-1.5 text-[10.5px] text-muted-foreground backdrop-blur">
            <div className="flex items-center gap-3">
              <span>DefJson</span>
              <span className="font-mono">CLASSICS</span>
              <span className="hidden sm:inline">坐标 x,y|textX,textY</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden sm:inline">
                双击节点/连线编辑名称 · Delete 删除 · ⌘/Ctrl + S 保存
              </span>
              <span className="tabular-nums">{Math.round(zoom * 100)}%</span>
            </div>
          </div>
        </div>

        <div className="hidden md:flex">
          {meta ? (
            <PropertyPanel
              flow={meta}
              selection={selection}
              forms={formsQuery.data || []}
              handlers={handlersQuery.data || []}
              nextOptions={nextOptions}
              onChangeFlow={updateFlow}
              onChangeNode={updateNode}
              onChangeEdge={updateEdge}
              onDelete={deleteSelection}
            />
          ) : null}
        </div>
      </div>

      {meta ? (
        <div className="pointer-events-none absolute left-1/2 top-[70px] hidden -translate-x-1/2 xl:block">
          <div className="flex items-center gap-1.5 rounded-full border border-border bg-card/85 px-3 py-1 text-[10px] text-muted-foreground shadow-sm backdrop-blur">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: NODE_TYPE_META[selection?.kind === "node" ? selection.type : "between"].color }}
            />
            {selection
              ? selection.kind === "node"
                ? `已选中：${selection.text || selection.id}`
                : `已选中跳转：${selection.source} → ${selection.target}`
              : "未选中元素 · 显示流程属性"}
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-background/95 backdrop-blur-sm">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border bg-card shadow-sm">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium">正在装载设计器</p>
            <p className="mt-1 text-[11px] text-muted-foreground">读取 DefJson 与节点坐标…</p>
          </div>
        </div>
      ) : error || !meta ? (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-background px-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-rose-200 bg-rose-50 text-rose-600">
            <TriangleAlert className="h-5 w-5" />
          </div>
          <div className="max-w-sm text-center">
            <p className="text-sm font-medium">设计器加载失败</p>
            <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
              {error || "流程定义不存在"}
            </p>
          </div>
          <Button variant="secondary" onClick={() => router.push("/")}>
            返回流程列表
          </Button>
        </div>
      ) : null}
    </div>
  );
}
