"use client";

/**
 * 语义地图图画布挂载层 (EAI-CUSTOM, plan 2026-09-12 ontology-ui Task 3).
 *
 * 把 vendored GraphCanvas（Explorer 裸 props 面）接上本系统数据源与页面状态：
 * - displayGraph 直接复用 explorer/graphStore 的单例 graph（layoutMode "base"，
 *   FA2 跑在 store 图上，useLoadGraph 已写好种子坐标）；
 * - 取数经 explorerDataSource.makeExplorerFetchers() 注入 useLoadGraph 的
 *   fetchNodes/fetchEdges 接缝（T2 adaptation #5，绝不走上游 /api/graph/* 默认）；
 * - graphReady/graphVersion 由 useLoadGraph 的查询结果驱动（缓存重挂载也能就绪）；
 * - onReady 把 GraphCanvasHandle 交给页面（检索定位 focusNode 用）。经 next/dynamic
 *   ssr:false 加载，dynamic 不透传 ref，故用回调而不是 forwardRef。
 * - 画布配色沿用 vendored GRAPH_THEME（标签 chip 自带深色底、节点为中饱和语义色，
 *   明暗两套页面底色上都可读）；页面底色走 bg-background 语义令牌，themeAdapter
 *   接缝保留给后续画布级主题注入。
 * - colorByCommunity 开关（semantic-map v2 Task 3）：开启时算 Louvain 社区并把
 *   节点 color/baseColor 系列属性改写为 chartTheme 家族色轮转色，关闭时原位恢复。
 *   挂点 = sigma 节点 reducer 每次全量 refresh 都读实时节点属性（getSemanticNodeColor
 *   ← baseColor || color），故改属性后 handle.requestRender()（scheduleRefresh）即可
 *   重着色——零 vendored 改动，不动 graphVersion（避免 setGraph + 相机重置）。
 */
import { Loader2, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  AMBER,
  BLUE,
  COMPETITOR,
  GREEN,
  INK_2,
  RED,
} from "@/extensions/bid-quote/components/chartTheme";
import {
  GraphCanvas,
  type GraphCanvasHandle,
} from "@/extensions/ontology/explorer/GraphCanvas";
import {
  graph,
  type NodeAttributes,
} from "@/extensions/ontology/explorer/graphStore";
import {
  GRAPH_THEME,
  withAlpha,
} from "@/extensions/ontology/explorer/graphTheme";
import type {
  GraphDisplayMeta,
  GraphEffectsState,
  GraphLoadPhase,
  GraphLoadProgress,
  GraphLoadSummary,
} from "@/extensions/ontology/explorer/types";
import { useLoadGraph } from "@/extensions/ontology/explorer/useLoadGraph";
import { makeExplorerFetchers } from "@/extensions/ontology/explorerDataSource";
import { readGraphSnapshot } from "@/extensions/ontology/graphSnapshot";
import { communityAssignments } from "@/extensions/ontology/stats";
import { cn } from "@/lib/utils";

// 社区着色家族色轮转（chartTheme 常量派生，非字面量）；按社区规模降序分配
const COMMUNITY_NODE_PALETTE = [BLUE, GREEN, AMBER, RED, COMPETITOR, INK_2];
const COMMUNITY_LEGEND_LIMIT = 8;

interface CommunityLegendItem {
  community: number;
  size: number;
  color: string;
}

const DISPLAY_META: GraphDisplayMeta = {
  layoutMode: "base",
  positionSource: "store",
  tracksStoreNodePositions: true,
  hasSyntheticNodes: false,
};

// v1 效果开关：只开边标签 + 邻域透镜；社区/中心性等重分析关闭（数据量小无收益）
const EFFECTS_STATE: GraphEffectsState = {
  pathPulseEnabled: false,
  pathFlowEnabled: false,
  lensEnabled: true,
  temporalEmphasisEnabled: false,
  semanticRegionsEnabled: false,
  contoursEnabled: false,
  pathfindingEnabled: false,
  edgeLabelsEnabled: true,
  communitiesEnabled: false,
  centralityEnabled: false,
  legendEnabled: false,
  diagnosticsEnabled: false,
  lensMode: "neighborhood",
  effectQuality: "bounded",
};

// vendored 进度 phase → 中文短句（评审 minor：加载态保持中文；未知 phase 回退原值）
const PHASE_LABELS: Partial<Record<GraphLoadPhase, string>> = {
  bootstrapping: "准备会话",
  fetching_nodes: "加载节点",
  fetching_edges: "加载边",
  computing_styling: "计算样式",
  hydrating_scene: "写入渲染场景",
  stabilizing_layout: "稳定布局中",
  ready: "就绪",
};

function formatProgress(progress: GraphLoadProgress): string {
  const label = PHASE_LABELS[progress.phase] ?? progress.phase;
  if (progress.phase === "fetching_nodes") {
    return `加载节点 ${progress.nodesLoaded.toLocaleString()}…`;
  }
  if (progress.phase === "fetching_edges") {
    return `加载边 ${progress.edgesLoaded.toLocaleString()}…`;
  }
  return `${label}…`;
}

export interface OntologyGraphCanvasProps {
  selectedNodeId: string;
  onSelectNode: (nodeId: string) => void;
  onReady?: (handle: GraphCanvasHandle | null) => void;
  onSummary?: (summary: GraphLoadSummary | null) => void;
  /** 开启后按 Louvain 社区给节点着色（chartTheme 家族色轮转），关闭恢复语义色。 */
  colorByCommunity?: boolean;
  className?: string;
}

export function OntologyGraphCanvas({
  selectedNodeId,
  onSelectNode,
  onReady,
  onSummary,
  colorByCommunity = false,
  className,
}: OntologyGraphCanvasProps) {
  const fetchers = useMemo(() => makeExplorerFetchers(), []);
  const canvasRef = useRef<GraphCanvasHandle | null>(null);
  const [graphReady, setGraphReady] = useState(false);
  const [graphVersion, setGraphVersion] = useState(0);
  const [isLayoutRunning, setIsLayoutRunning] = useState(false);
  const [progressMessage, setProgressMessage] = useState("准备加载语义图…");

  // 回调存 ref：effect 只依赖 loadQuery.data，避免父组件重渲染触发版本号空转
  const onSummaryRef = useRef(onSummary);
  onSummaryRef.current = onSummary;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const loadQuery = useLoadGraph({
    fetchNodes: fetchers.fetchNodes,
    fetchEdges: fetchers.fetchEdges,
    onProgress: (progress: GraphLoadProgress) =>
      setProgressMessage(formatProgress(progress)),
  });

  useEffect(() => {
    if (!loadQuery.data) {
      return;
    }
    setGraphReady(true);
    setGraphVersion((version) => version + 1);
    setIsLayoutRunning(true);
    onSummaryRef.current?.(loadQuery.data);
  }, [loadQuery.data]);

  useEffect(() => {
    onReadyRef.current?.(canvasRef.current);
    return () => onReadyRef.current?.(null);
  }, [graphReady]);

  const handleRetry = () => {
    void loadQuery.refetch();
  };

  // ── 社区着色（semantic-map v2 Task 3）────────────────────────────
  // 开：改写节点 color/baseColor 系列为社区色（原值存恢复表），requestRender 重着色；
  // 关/图重载：恢复表原位回写。store 是共享单例，恢复表保证语义色可逆。
  const colorRestoreRef = useRef<Map<string, Partial<NodeAttributes>> | null>(
    null,
  );
  const [communityLegend, setCommunityLegend] = useState<CommunityLegendItem[]>(
    [],
  );

  useEffect(() => {
    if (!loadQuery.data) {
      return;
    }
    if (!colorByCommunity) {
      const restore = colorRestoreRef.current;
      if (!restore) {
        return;
      }
      restore.forEach((previous, nodeId) => {
        if (graph.hasNode(nodeId)) {
          graph.mergeNodeAttributes(nodeId, previous);
        }
      });
      colorRestoreRef.current = null;
      setCommunityLegend([]);
      canvasRef.current?.requestRender();
      return;
    }
    // 开启（或开启状态下图重载——store 已被 clearGraph 清空重建，旧恢复表作废）
    const { nodes, edges } = readGraphSnapshot();
    const assignments = communityAssignments(nodes, edges);
    if (assignments.size === 0) {
      return;
    }
    const sizeByCommunity = new Map<number, number>();
    assignments.forEach((community) => {
      sizeByCommunity.set(community, (sizeByCommunity.get(community) ?? 0) + 1);
    });
    const ranked = [...sizeByCommunity.entries()].sort(
      (left, right) => right[1] - left[1] || left[0] - right[0],
    );
    const colorByCommunityId = new Map<number, string>();
    ranked.forEach(([community], index) => {
      // EAI: fallback satisfies noUncheckedIndexedAccess — index is total (modulo palette.length)
      colorByCommunityId.set(
        community,
        COMMUNITY_NODE_PALETTE[index % COMMUNITY_NODE_PALETTE.length] ?? BLUE,
      );
    });
    const restore = new Map<string, Partial<NodeAttributes>>();
    graph.forEachNode((nodeId) => {
      const attrs = graph.getNodeAttributes(nodeId) as NodeAttributes;
      restore.set(nodeId, {
        color: attrs.color,
        baseColor: attrs.baseColor,
        mutedColor: attrs.mutedColor,
        glowColor: attrs.glowColor,
        strokeColor: attrs.strokeColor,
        borderColor: attrs.borderColor,
      });
      const color =
        colorByCommunityId.get(assignments.get(nodeId) ?? -1) ??
        attrs.baseColor ??
        "";
      graph.mergeNodeAttributes(nodeId, {
        color,
        baseColor: color,
        mutedColor: withAlpha(color, GRAPH_THEME.nodes.mutedAlpha),
        glowColor: withAlpha(color, 0.24),
        strokeColor: color,
        borderColor: color,
      });
      return true;
    });
    colorRestoreRef.current = restore;
    setCommunityLegend(
      ranked.slice(0, COMMUNITY_LEGEND_LIMIT).map(([community, size]) => ({
        community,
        size,
        color: colorByCommunityId.get(community) ?? BLUE,
      })),
    );
    canvasRef.current?.requestRender();
  }, [colorByCommunity, loadQuery.data]);

  return (
    <div
      className={cn("relative h-full w-full", className)}
      data-testid="ontology-graph-canvas"
    >
      <GraphCanvas
        ref={canvasRef}
        graphVersion={graphVersion}
        graphReady={graphReady}
        displayGraph={graph}
        displayMeta={DISPLAY_META}
        onNodeClick={onSelectNode}
        selectedNodeId={selectedNodeId}
        focusedNodeId=""
        selectedEdgeId=""
        effectsState={EFFECTS_STATE}
        isLayoutRunning={isLayoutRunning}
        onLayoutRunningChange={setIsLayoutRunning}
        viewMode="full"
      />
      {!graphReady ? (
        <div className="bg-background/60 absolute inset-0 z-10 flex items-center justify-center">
          <div className="text-muted-foreground flex flex-col items-center gap-2 text-sm">
            {loadQuery.isError ? (
              <>
                <span>语义图加载失败：{String(loadQuery.error)}</span>
                <button
                  type="button"
                  onClick={handleRetry}
                  className="border-border text-foreground hover:bg-accent inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  重试
                </button>
              </>
            ) : (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>{progressMessage}</span>
              </>
            )}
          </div>
        </div>
      ) : null}
      {communityLegend.length > 0 ? (
        <div
          className="absolute bottom-3 left-3 z-10 flex max-w-[70%] flex-wrap items-center gap-1.5"
          data-testid="community-legend"
        >
          {communityLegend.map((item) => (
            <span
              key={item.community}
              title={`社区 #${item.community} · ${item.size} 实体`}
              className="bg-background/80 flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] backdrop-blur-sm"
            >
              <span
                className="h-2 w-2 shrink-0 rounded-[3px]"
                style={{ background: item.color }}
              />
              <span className="text-muted-foreground tabular-nums">
                #{item.community} · {item.size}
              </span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
