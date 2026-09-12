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
 */
import { Loader2, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { GraphCanvas, type GraphCanvasHandle } from "@/extensions/ontology/explorer/GraphCanvas";
import { graph } from "@/extensions/ontology/explorer/graphStore";
import type {
  GraphDisplayMeta,
  GraphEffectsState,
  GraphLoadPhase,
  GraphLoadProgress,
  GraphLoadSummary,
} from "@/extensions/ontology/explorer/types";
import { useLoadGraph } from "@/extensions/ontology/explorer/useLoadGraph";
import { makeExplorerFetchers } from "@/extensions/ontology/explorerDataSource";
import { cn } from "@/lib/utils";

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
  className?: string;
}

export function OntologyGraphCanvas({
  selectedNodeId,
  onSelectNode,
  onReady,
  onSummary,
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
    onProgress: (progress: GraphLoadProgress) => setProgressMessage(formatProgress(progress)),
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

  return (
    <div className={cn("relative h-full w-full", className)} data-testid="ontology-graph-canvas">
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
    </div>
  );
}
