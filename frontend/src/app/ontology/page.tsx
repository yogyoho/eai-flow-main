"use client";

/**
 * 语义地图页面 (EAI-CUSTOM, plan 2026-09-12 ontology-ui Task 3 + semantic-map v2 Task 3).
 *
 * 页面壳：ShellLayout + canPage("ontology:page:map")（加载中 fail-open，照
 * knowledge-factory 惯例）。布局对照 .wolf/tmp/ontology-map-prototype.html：
 * 顶栏（标题/检索/registry 指纹 chip）+ 顶栏下分段切换（地图|概览|实体消解，
 * v2 Task 3；地图 = v1 内容原样保留）+ 主区（图画布 flex-1 + 右栏 300px tabs）+
 * 状态条。检索为客户端过滤的降级实现：对已加载图节点 label 子串匹配出候选下拉，
 * 点击选中并 focusNode 定位（vendored scene 无过滤 props，逐节点透明度过滤需改
 * graphSceneState，v1 不做）。样式全部 Tailwind + globals.css 语义令牌。
 * 概览/实体消解 tab 为 bid-quote 式浅色定版（不随暗色，chartTheme 常量上色）；
 * 概览图数据从 graphStore 单例快照（readGraphSnapshot，缓存已由 useLoadGraph 去重
 * 加载，独立再拉一份是浪费），待复核实体数走 doc-graph resolution REST；
 * 消解 tab = ResolutionPanel（v2 Task 4），merge/unmerge 成功后 useReloadGraph
 * 全量失效重载，地图节点状态与已合并计数随之刷新。
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useMemo, useRef, useState } from "react";

import { usePermission } from "@/core/permissions";
import {
  fetchPendingReviewCount,
  fetchRegistryMeta,
} from "@/extensions/ontology/api/ontology-graph-api";
import { DetailPanel } from "@/extensions/ontology/components/DetailPanel";
import type { OntologyGraphCanvasProps } from "@/extensions/ontology/components/OntologyGraphCanvas";
import { OverviewPanel } from "@/extensions/ontology/components/OverviewPanel";
import { RegistryPanel } from "@/extensions/ontology/components/RegistryPanel";
import { ResolutionPanel } from "@/extensions/ontology/components/ResolutionPanel";
import type { GraphCanvasHandle } from "@/extensions/ontology/explorer/GraphCanvas";
import {
  graph,
  type NodeAttributes,
} from "@/extensions/ontology/explorer/graphStore";
import type { GraphLoadSummary } from "@/extensions/ontology/explorer/types";
import { useReloadGraph } from "@/extensions/ontology/explorer/useLoadGraph";
import {
  readGraphSnapshot,
  type GraphSnapshot,
} from "@/extensions/ontology/graphSnapshot";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// WebGL 画布只在客户端挂载（sigma 实例化依赖 canvas/WebGL，禁 SSR 预渲染）
const OntologyGraphCanvas = dynamic<OntologyGraphCanvasProps>(
  () =>
    import("@/extensions/ontology/components/OntologyGraphCanvas").then(
      (mod) => mod.OntologyGraphCanvas,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="text-muted-foreground flex h-full w-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    ),
  },
);

const SEARCH_MATCH_LIMIT = 8;
type PanelTab = "detail" | "registry";
type PageView = "map" | "overview" | "resolution";

const PAGE_VIEWS: Array<[PageView, string]> = [
  ["map", "地图"],
  ["overview", "概览"],
  ["resolution", "实体消解"],
];

const EMPTY_SNAPSHOT: GraphSnapshot = { nodes: [], edges: [] };

/** 已加载图节点中按 label 子串检索（大小写不敏感）；前缀命中排前，截取前 8 条。 */
function searchGraphNodes(query: string): Array<{ id: string; label: string }> {
  const q = query.trim().toLowerCase();
  if (!q) {
    return [];
  }
  const matches: Array<{ id: string; label: string; prefixHit: boolean }> = [];
  graph.forEachNode((nodeId, attributes) => {
    const label = String((attributes as NodeAttributes).label ?? "");
    const lower = label.toLowerCase();
    if (lower.includes(q)) {
      matches.push({ id: nodeId, label, prefixHit: lower.startsWith(q) });
    }
    return true;
  });
  // 稳定排序保住图内原序；前缀命中优先（评审 minor：exact/prefix first）
  matches.sort(
    (left, right) => Number(right.prefixHit) - Number(left.prefixHit),
  );
  return matches
    .slice(0, SEARCH_MATCH_LIMIT)
    .map(({ id, label }) => ({ id, label }));
}

function OntologyWorkspace() {
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<PanelTab>("detail");
  const [summary, setSummary] = useState<GraphLoadSummary | null>(null);
  const [view, setView] = useState<PageView>("map");
  const [colorByCommunity, setColorByCommunity] = useState(false);
  const canvasHandleRef = useRef<GraphCanvasHandle | null>(null);

  const metaQuery = useQuery({
    queryKey: ["ontology", "registry"],
    queryFn: fetchRegistryMeta,
  });
  const meta = metaQuery.data;

  // 待复核实体计数：仅概览 tab 挂载时拉取；失败（含无 system:access 403）→ null → "—"
  const pendingQuery = useQuery({
    queryKey: ["ontology", "pending-review-count"],
    queryFn: fetchPendingReviewCount,
    enabled: view === "overview",
    staleTime: 30_000,
    retry: false,
  });

  // 图数据快照：graphStore 单例已由 useLoadGraph 去重加载，直接读投影（summary 就绪即数据在）
  const graphData = useMemo(
    () => (summary ? readGraphSnapshot() : EMPTY_SNAPSHOT),
    [summary],
  );

  // 已合并实体计数：图快照中 graph_entity 节点 properties.status === "merged"
  // （doc_graph.yaml 注册表把 dg_entities 投影为 graph_entity，status 是可见属性）；
  // merge/unmerge 后经 reloadGraph 全量重载 → summary 更新 → 此计数随之刷新
  const mergedCount = useMemo(() => {
    if (!summary) {
      return null;
    }
    return graphData.nodes.filter(
      (node) => node.type === "graph_entity" && node.properties?.status === "merged",
    ).length;
  }, [graphData, summary]);

  // 消解 merge/unmerge 成功 → 图全量查询失效重载（vendored 层暴露的 useReloadGraph，
  // 最短路径：无需在画布层新开 refetch props），地图节点状态与"已合并数"卡同步
  const reloadGraph = useReloadGraph();
  const handleRefreshGraph = useCallback(() => {
    void reloadGraph();
  }, [reloadGraph]);

  const handleGoResolution = useCallback(() => setView("resolution"), []);

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      setActiveTab("detail");
    }
  }, []);

  const handleCanvasReady = useCallback((handle: GraphCanvasHandle | null) => {
    canvasHandleRef.current = handle;
  }, []);

  const handleSummary = useCallback((nextSummary: GraphLoadSummary | null) => {
    setSummary(nextSummary);
  }, []);

  // 直接渲染期计算：图规模数千级，每次击键一次全量扫描可接受；
  // summary 变化（图加载完成）自然随重渲染重算
  const searchMatches = searchQuery.trim() ? searchGraphNodes(searchQuery) : [];

  const handlePickMatch = (nodeId: string) => {
    handleSelectNode(nodeId);
    setSearchQuery(""); // 选中后收起候选下拉（评审 minor：下拉保持常开）
    canvasHandleRef.current?.focusNode(nodeId);
  };

  const handleSearchKeyDown = (
    event: React.KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key === "Escape") {
      setSearchQuery("");
    }
  };

  const fingerprint = meta?.fingerprint ? meta.fingerprint.slice(0, 8) : "—";

  return (
    <div className="bg-background flex h-full flex-col">
      {/* 顶栏 */}
      <header className="border-border bg-card flex shrink-0 items-center gap-2.5 border-b px-3.5 py-2">
        <h1 className="text-foreground mr-1 text-sm font-semibold tracking-tight whitespace-nowrap">
          语义地图
        </h1>
        <div className="relative w-full max-w-[300px]">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="检索实体名…"
            aria-label="检索实体"
            autoComplete="off"
            className="border-border bg-muted text-foreground placeholder:text-muted-foreground focus:border-primary h-8 w-full rounded-lg border px-8 text-xs outline-none"
          />
          {searchQuery.trim() ? (
            <div className="border-border bg-card absolute top-full left-0 z-20 mt-1 w-full overflow-hidden rounded-lg border shadow-sm">
              {searchMatches.length === 0 ? (
                <div className="text-muted-foreground px-3 py-2 text-xs">
                  无匹配节点
                </div>
              ) : (
                searchMatches.map((match) => (
                  <button
                    key={match.id}
                    type="button"
                    onClick={() => handlePickMatch(match.id)}
                    className="hover:bg-accent block w-full truncate px-3 py-1.5 text-left text-xs"
                    title={`${match.label}（${match.id}）`}
                  >
                    {match.label}
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>
        <span className="flex-1" />
        <span
          className="border-border text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] whitespace-nowrap tabular-nums"
          title="registry 指纹（SHA-256 前 8 位）与版本"
        >
          <span className="font-mono">{fingerprint}</span>
          {meta ? <span>· v{meta.registry_version}</span> : null}
        </span>
      </header>

      {/* 分段切换：地图 | 概览 | 实体消解（地图 = v1 内容原样；地图视图附社区着色开关） */}
      <div className="border-border bg-card flex shrink-0 items-center gap-2 border-b px-3.5 py-1.5">
        <div
          className="border-border bg-muted inline-flex items-center gap-0.5 rounded-lg border p-0.5"
          role="group"
          aria-label="语义地图视图切换"
          data-testid="ontology-view-switch"
        >
          {PAGE_VIEWS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              onClick={() => setView(value)}
              className={cn(
                "rounded-md px-3 py-1 text-xs transition-colors",
                view === value
                  ? "bg-primary text-primary-foreground font-medium shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        {view === "map" ? (
          <button
            type="button"
            aria-pressed={colorByCommunity}
            onClick={() => setColorByCommunity((previous) => !previous)}
            data-testid="community-color-toggle"
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors",
              colorByCommunity
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            社区着色
          </button>
        ) : null}
      </div>

      {/* 地图视图（v1 主区：图画布 + 右栏；切换 tab 时保持挂载避免画布重载/重排） */}
      <div className={cn("min-h-0 flex-1", view !== "map" && "hidden")}>
        <div className="flex h-full min-h-0">
          <div className="relative min-w-0 flex-1">
            <OntologyGraphCanvas
              selectedNodeId={selectedNodeId}
              onSelectNode={handleSelectNode}
              onReady={handleCanvasReady}
              onSummary={handleSummary}
              colorByCommunity={colorByCommunity}
            />
          </div>
          <aside className="border-border bg-card flex w-[300px] shrink-0 flex-col border-l">
            <div className="border-border flex border-b">
              {(
                [
                  ["detail", "详情"],
                  ["registry", "Registry"],
                ] as Array<[PanelTab, string]>
              ).map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={cn(
                    "flex-1 border-b-2 py-2 text-xs transition-colors",
                    activeTab === tab
                      ? "border-primary text-primary font-semibold"
                      : "text-muted-foreground hover:text-foreground border-transparent",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {activeTab === "detail" ? (
                <DetailPanel nodeId={selectedNodeId || null} />
              ) : (
                <div className="p-3">
                  <RegistryPanel />
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>

      {/* 概览视图（浅色定版：KPI 卡 + 类型分布/Hub Top10/社区规模图） */}
      {view === "overview" ? (
        <div className="min-h-0 flex-1" data-testid="ontology-overview">
          <OverviewPanel
            nodes={graphData.nodes}
            edges={graphData.edges}
            pendingCount={pendingQuery.data ?? null}
            onGoResolution={handleGoResolution}
          />
        </div>
      ) : null}

      {/* 实体消解视图（浅色定版：pending 列表 + 相似建议 + 合并/撤销） */}
      {view === "resolution" ? (
        <div className="min-h-0 flex-1" data-testid="ontology-resolution">
          <ResolutionPanel
            mergedCount={mergedCount}
            onRefreshGraph={handleRefreshGraph}
          />
        </div>
      ) : null}

      {/* 状态条 */}
      <footer className="border-border bg-card text-muted-foreground flex shrink-0 items-center gap-3.5 overflow-x-auto border-t px-3.5 py-1 text-[10.5px] whitespace-nowrap tabular-nums">
        <span>
          registry <b className="font-mono">v{meta?.registry_version ?? "—"}</b>
        </span>
        <span>
          fingerprint <span className="font-mono">{fingerprint}</span>
        </span>
        <span>
          {meta
            ? `${meta.object_type_count} 对象类型 · ${meta.link_type_count} 链接`
            : "— 对象类型 · — 链接"}
        </span>
        <span>
          {summary
            ? `${summary.nodeCount} 节点 · ${summary.edgeCount} 边`
            : "— 节点 · — 边"}
        </span>
      </footer>
    </div>
  );
}

// EAI-CUSTOM: usePermission 必须在 ShellLayout 的 PermissionProvider 内部调用（照 knowledge-factory 模式）
function OntologyMain() {
  const { canPage, isLoading: permLoading } = usePermission();
  // 权限加载中 fail-open 先渲染，加载完成无权限则空态
  if (!permLoading && !canPage("ontology:page:map")) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        无语义地图访问权限
      </div>
    );
  }
  return <OntologyWorkspace />;
}

export default function OntologyPage() {
  return (
    <ShellLayout>
      <OntologyMain />
    </ShellLayout>
  );
}
