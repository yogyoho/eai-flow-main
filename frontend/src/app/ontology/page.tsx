"use client";

/**
 * 语义地图页面 (EAI-CUSTOM, plan 2026-09-12 ontology-ui Task 3).
 *
 * 页面壳：ShellLayout + canPage("ontology:page:map")（加载中 fail-open，照
 * knowledge-factory 惯例）。布局对照 .wolf/tmp/ontology-map-prototype.html：
 * 顶栏（标题/检索/registry 指纹 chip）+ 主区（图画布 flex-1 + 右栏 300px tabs）+
 * 状态条。检索为客户端过滤的降级实现：对已加载图节点 label 子串匹配出候选下拉，
 * 点击选中并 focusNode 定位（vendored scene 无过滤 props，逐节点透明度过滤需改
 * graphSceneState，v1 不做）。样式全部 Tailwind + globals.css 语义令牌。
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";

import { usePermission } from "@/core/permissions";
import { fetchRegistryMeta } from "@/extensions/ontology/api/ontology-graph-api";
import { DetailPanel } from "@/extensions/ontology/components/DetailPanel";
import type { OntologyGraphCanvasProps } from "@/extensions/ontology/components/OntologyGraphCanvas";
import { RegistryPanel } from "@/extensions/ontology/components/RegistryPanel";
import type { GraphCanvasHandle } from "@/extensions/ontology/explorer/GraphCanvas";
import { graph, type NodeAttributes } from "@/extensions/ontology/explorer/graphStore";
import type { GraphLoadSummary } from "@/extensions/ontology/explorer/types";
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

/** 已加载图节点中按 label 子串检索（大小写不敏感），返回 [id, label] 候选。 */
function searchGraphNodes(query: string): Array<{ id: string; label: string }> {
  const q = query.trim().toLowerCase();
  if (!q) {
    return [];
  }
  const matches: Array<{ id: string; label: string }> = [];
  graph.forEachNode((nodeId, attributes) => {
    const label = String((attributes as NodeAttributes).label ?? "");
    if (label.toLowerCase().includes(q)) {
      matches.push({ id: nodeId, label });
    }
    return matches.length < SEARCH_MATCH_LIMIT;
  });
  return matches;
}

function OntologyWorkspace() {
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<PanelTab>("detail");
  const [summary, setSummary] = useState<GraphLoadSummary | null>(null);
  const canvasHandleRef = useRef<GraphCanvasHandle | null>(null);

  const metaQuery = useQuery({
    queryKey: ["ontology", "registry"],
    queryFn: fetchRegistryMeta,
  });
  const meta = metaQuery.data;

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
    canvasHandleRef.current?.focusNode(nodeId);
  };

  const fingerprint = meta?.fingerprint ? meta.fingerprint.slice(0, 8) : "—";

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 顶栏 */}
      <header className="border-border bg-card flex shrink-0 items-center gap-2.5 border-b px-3.5 py-2">
        <h1 className="text-foreground mr-1 whitespace-nowrap text-sm font-semibold tracking-tight">
          语义地图
        </h1>
        <div className="relative w-full max-w-[300px]">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="检索实体名…"
            autoComplete="off"
            className="border-border bg-muted text-foreground placeholder:text-muted-foreground focus:border-primary h-8 w-full rounded-lg border px-8 text-xs outline-none"
          />
          {searchQuery.trim() ? (
            <div className="border-border bg-card absolute top-full left-0 z-20 mt-1 w-full overflow-hidden rounded-lg border shadow-sm">
              {searchMatches.length === 0 ? (
                <div className="text-muted-foreground px-3 py-2 text-xs">无匹配节点</div>
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

      {/* 主区：图画布 + 右栏 */}
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          <OntologyGraphCanvas
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
            onReady={handleCanvasReady}
            onSummary={handleSummary}
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
                    : "border-transparent text-muted-foreground hover:text-foreground",
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

      {/* 状态条 */}
      <footer className="border-border bg-card text-muted-foreground flex shrink-0 items-center gap-3.5 overflow-x-auto whitespace-nowrap border-t px-3.5 py-1 text-[10.5px] tabular-nums">
        <span>
          registry <b className="font-mono">v{meta?.registry_version ?? "—"}</b>
        </span>
        <span>
          fingerprint <span className="font-mono">{fingerprint}</span>
        </span>
        <span>
          {meta ? `${meta.object_type_count} 对象类型 · ${meta.link_type_count} 链接` : "— 对象类型 · — 链接"}
        </span>
        <span>
          {summary ? `${summary.nodeCount} 节点 · ${summary.edgeCount} 边` : "— 节点 · — 边"}
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
