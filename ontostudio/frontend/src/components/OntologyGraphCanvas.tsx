/* 复制自 frontend/src/extensions/ontology/components/OntologyGraphCanvas.tsx（S2 Task 1）——仅 import 路径改本地，内容零改动。 */
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
} from "@/components/chartTheme";
import {
  GraphCanvas,
  type GraphCanvasHandle,
} from "@/explorer/GraphCanvas";
import {
  graph,
  type NodeAttributes,
} from "@/explorer/graphStore";
import {
  GRAPH_THEME,
  withAlpha,
} from "@/explorer/graphTheme";
import type {
  GraphDisplayMeta,
  GraphEffectsState,
  GraphLoadPhase,
  GraphLoadProgress,
  GraphLoadSummary,
} from "@/explorer/types";
import { useLoadGraph } from "@/explorer/useLoadGraph";
import { makeExplorerFetchers } from "@/explorerDataSource";
import { readGraphSnapshot } from "@/graphSnapshot";
import { communityAssignments } from "@/stats";
import { cn } from "@/lib/utils";

// 社区着色家族色轮转（chartTheme 常量派生，非字面量）；按社区规模降序分配
const COMMUNITY_NODE_PALETTE = [BLUE, GREEN, AMBER, RED, COMPETITOR, INK_2];
const COMMUNITY_LEGEND_LIMIT = 8;

interface CommunityLegendItem {
  community: number;
  size: number;
  color: string;
}

/** 状态图例行（T2A 世界观：断言图含全行含状态）。 */
interface StatusLegendItem {
  status: string;
  size: number;
  color: string;
}

const STATUS_LABELS: Record<string, string> = {
  active: "已确认",
  pending_review: "待审",
  rejected: "已驳回",
  merged: "已合并",
};

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
  /** EAI-CUSTOM(2026-09-27 原型重构): 按抽取状态着色（T2A 世界观——断言图含全行含状态）：
   *  pending 琥珀 / rejected 红 / merged 灰，active 与未知类型保持语义色。 */
  colorByStatus?: boolean;
  /** 只看已确认：非 active 节点透明化（视觉隐藏；共享 store 不删节点）。 */
  activeOnly?: boolean;
  /** EAI-CUSTOM(2026-09-29 图谱投影域过滤): 域参数改**服务端取数**——domainFilter 非空时
   *  /graph/* 带 domain=（实体类型行域过滤，后端 422 校验未知域），取数器与查询缓存随域
   *  重建，画布只渲染服务端返回的行（不再做客户端透明化）。空串 = 全部（缺省行为不变）。 */
  domainFilter?: string;
  className?: string;
}

export function OntologyGraphCanvas({
  selectedNodeId,
  onSelectNode,
  onReady,
  onSummary,
  colorByCommunity = false,
  colorByStatus = false,
  activeOnly = false,
  domainFilter = "",
  className,
}: OntologyGraphCanvasProps) {
  // EAI-CUSTOM(2026-09-29 图谱投影域过滤): 取数器随域重建——domainFilter 变化即换
  // fetchers 并触发 useLoadGraph 重取（domain 入 queryKey）
  const fetchers = useMemo(() => makeExplorerFetchers(domainFilter), [domainFilter]);
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
    domain: domainFilter,
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

  // ── 显示模式改色（社区 / 状态 / 只看已确认）────────────────────────────
  // 单一 effect 统一三态 + 共享恢复表：多模式叠加时恢复表只会保存"进入本模式前"
  // 的属性，关闭时原位回写——避免模式链式切换把上一模式的颜色误存为语义色。
  // 优先级：只看已确认（过滤）> 按状态着色 > 社区着色 > 语义色。
  // 状态来源 = 图快照 properties.status（graph_entity 投影含 status；其他对象类型
  // 无该字段 → 保持语义色）。
  const colorRestoreRef = useRef<Map<string, Partial<NodeAttributes>> | null>(
    null,
  );
  const [communityLegend, setCommunityLegend] = useState<CommunityLegendItem[]>(
    [],
  );
  const [statusLegend, setStatusLegend] = useState<StatusLegendItem[]>([]);

  useEffect(() => {
    if (!loadQuery.data) {
      return;
    }
    const restore = colorRestoreRef.current;
    if (restore) {
      restore.forEach((previous, nodeId) => {
        if (graph.hasNode(nodeId)) {
          graph.mergeNodeAttributes(nodeId, previous);
        }
      });
      colorRestoreRef.current = null;
    }
    setCommunityLegend([]);
    setStatusLegend([]);
    // EAI-CUSTOM(2026-09-29 图谱投影域过滤): domainFilter 不再进本 effect——域裁剪已
    // 上移服务端（/graph/*?domain=），画布只拿过滤后的行；此处只剩着色与「只看已确认」。
    if (!colorByCommunity && !colorByStatus && !activeOnly) {
      canvasRef.current?.requestRender();
      return;
    }

    const { nodes, edges } = readGraphSnapshot();
    const statusById = new Map(
      nodes.map((node) => [node.id, String(node.properties?.status ?? "")]),
    );

    // 恢复表：记录将被改写的全部可视属性（含 label——过滤模式要清标签）
    const nextRestore = new Map<string, Partial<NodeAttributes>>();
    const remember = (nodeId: string) => {
      if (nextRestore.has(nodeId)) return;
      const attrs = graph.getNodeAttributes(nodeId) as NodeAttributes;
      nextRestore.set(nodeId, {
        color: attrs.color,
        baseColor: attrs.baseColor,
        mutedColor: attrs.mutedColor,
        glowColor: attrs.glowColor,
        strokeColor: attrs.strokeColor,
        borderColor: attrs.borderColor,
        label: attrs.label,
      });
    };

    const statusCounts = new Map<string, number>();

    if (colorByStatus) {
      graph.forEachNode((nodeId) => {
        const status = statusById.get(nodeId) ?? "";
        if (status) {
          statusCounts.set(status, (statusCounts.get(status) ?? 0) + 1);
        }
        const color =
          status === "pending_review"
            ? AMBER
            : status === "rejected"
              ? RED
              : status === "merged"
                ? INK_2
                : "";
        if (!color) return true; // active / 无状态字段 → 保持语义色
        remember(nodeId);
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
      setStatusLegend(
        ["active", "pending_review", "rejected", "merged"]
          .filter((status) => statusCounts.has(status))
          .map((status) => ({
            status,
            size: statusCounts.get(status) ?? 0,
            color:
              status === "pending_review"
                ? AMBER
                : status === "rejected"
                  ? RED
                  : status === "merged"
                    ? INK_2
                    : BLUE,
          })),
      );
    } else if (colorByCommunity) {
      const assignments = communityAssignments(nodes, edges);
      if (assignments.size > 0) {
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
        graph.forEachNode((nodeId) => {
          const attrs = graph.getNodeAttributes(nodeId) as NodeAttributes;
          remember(nodeId);
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
        setCommunityLegend(
          ranked.slice(0, COMMUNITY_LEGEND_LIMIT).map(([community, size]) => ({
            community,
            size,
            color: colorByCommunityId.get(community) ?? BLUE,
          })),
        );
      }
    }

    if (activeOnly) {
      // 只看已确认：共享恢复表（remember 防重复记录原始属性）
      graph.forEachNode((nodeId) => {
        const status = statusById.get(nodeId) ?? "";
        const statusOk = status === "active" || status === "";
        if (statusOk) return true;
        remember(nodeId);
        graph.mergeNodeAttributes(nodeId, {
          color: "transparent",
          baseColor: "transparent",
          mutedColor: "transparent",
          glowColor: "transparent",
          strokeColor: "transparent",
          borderColor: "transparent",
          label: "",
        });
        return true;
      });
    }

    colorRestoreRef.current = nextRestore;
    canvasRef.current?.requestRender();
  }, [colorByCommunity, colorByStatus, activeOnly, loadQuery.data]);

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
      {statusLegend.length > 0 ? (
        <div
          className="absolute bottom-3 left-3 z-10 flex max-w-[70%] flex-wrap items-center gap-1.5"
          data-testid="status-legend"
        >
          {statusLegend.map((item) => (
            <span
              key={item.status}
              title={`${STATUS_LABELS[item.status] ?? item.status} · ${item.size} 实体`}
              className="bg-background/80 flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] backdrop-blur-sm"
            >
              <span
                className="h-2 w-2 shrink-0 rounded-[3px]"
                style={{ background: item.color }}
              />
              <span className="text-muted-foreground">
                {STATUS_LABELS[item.status] ?? item.status} · {item.size}
              </span>
            </span>
          ))}
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
